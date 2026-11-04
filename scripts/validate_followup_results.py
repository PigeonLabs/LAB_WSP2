#!/usr/bin/env python3
"""Replay followup-v2 artifacts on CPU without loading or requiring model weights.

An archive is located by --root; every artifact lookup is relative to that root.
Partial evidence is labeled PARTIAL. --require-complete exits nonzero until all
stages and their expected evidence exist. Corrupt available evidence always fails.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile
from collections import Counter
import numpy as np

SOURCE_ROOT=Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path: sys.path.insert(0,str(SOURCE_ROOT))


def sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''): digest.update(block)
    return digest.hexdigest()


def json_hash(value,compact=False):
    options={'sort_keys':True,'ensure_ascii':False}
    if compact: options['separators']=(',',':')
    canonical=json.loads(json.dumps(value,ensure_ascii=False,allow_nan=False))
    return hashlib.sha256(json.dumps(canonical,**options).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def portable_bytes(root,relative):
    """Read a raw file or its exact regular tar member, without extracting."""
    root=Path(root).resolve();relative=Path(relative)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Archive-relative path required')
    path=root/relative
    if path.is_file():return path.read_bytes(),{'storage':'file','path':str(relative)}
    if len(relative.parts)>=3 and relative.parts[0]=='data' and relative.suffix=='.jsonl':
        archive=root/'data'/f'{relative.parts[1]}.tar.gz'
        if archive.is_file():
            with tarfile.open(archive,'r:*') as tar:
                matches=[m for m in tar.getmembers() if m.name==relative.as_posix()]
                if len(matches)!=1 or not matches[0].isfile():raise ValueError(f'Need one regular archive member: {relative}')
                stream=tar.extractfile(matches[0])
                if stream is None:raise ValueError(f'Unreadable archive member: {relative}')
                return stream.read(),{'storage':'tar_member','archive':str(archive.relative_to(root)),'member':relative.as_posix()}
    raise FileNotFoundError(str(relative))


def load_portable_followup(root):
    from src.followup_data import SPLITS,validate_dataset
    root=Path(root);directory=root/'data/followup-v2';manifest=read_json(directory/'manifest.json');dataset={};storage=[]
    for split in SPLITS:
        name=f'{split}.jsonl';raw,source=portable_bytes(root,Path('data/followup-v2')/name)
        if hashlib.sha256(raw).hexdigest()!=manifest['file_sha256'][name]:raise ValueError(f'Frozen data hash mismatch: {name}')
        dataset[split]=[json.loads(line) for line in raw.decode().splitlines()];storage.append(source)
    checked=validate_dataset(dataset)
    equal(json.loads(json.dumps(checked['splits'])),manifest['splits'],'portable data manifest')
    return dataset,storage


def load_npz(path):
    with np.load(path,allow_pickle=False) as raw: arrays={k:raw[k] for k in raw.files}
    for key,value in arrays.items():
        if np.issubdtype(value.dtype,np.number) and not np.isfinite(value).all():
            raise ValueError(f'Nonfinite array {key}')
    return arrays


def equal(actual,expected,path='value',atol=1e-10):
    """Recursive numerical replay comparison, allowing JSON list/NumPy conversion."""
    if isinstance(actual,np.ndarray):actual=actual.tolist()
    if isinstance(expected,np.ndarray):expected=expected.tolist()
    if isinstance(actual,np.generic):actual=actual.item()
    if isinstance(expected,np.generic):expected=expected.item()
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or set(actual)!=set(expected): raise ValueError(f'{path}: keys differ')
        for key in expected: equal(actual[key],expected[key],f'{path}.{key}',atol)
    elif isinstance(expected,(list,tuple)):
        if not isinstance(actual,(list,tuple)) or len(actual)!=len(expected): raise ValueError(f'{path}: lengths differ')
        for i,(a,b) in enumerate(zip(actual,expected)):equal(a,b,f'{path}[{i}]',atol)
    elif isinstance(expected,(int,float)) and not isinstance(expected,bool):
        if not isinstance(actual,(int,float)) or not np.isfinite(actual) or not np.isclose(actual,expected,rtol=1e-9,atol=atol):raise ValueError(f'{path}: {actual} != {expected}')
    elif actual!=expected:raise ValueError(f'{path}: values differ')


def validate_rows(arrays,records):
    ids=arrays['row_ids'].astype(str).tolist()
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate measured row IDs')
    lookup={r['id']:r for r in records}
    if any(i not in lookup for i in ids):raise ValueError('Unknown measured row ID')
    ordered=[lookup[i] for i in ids]
    for key,field in [('labels','label'),('groups','group_id'),('concepts','concept')]:
        if key in arrays:equal(arrays[key],[r[field] for r in ordered],key)
    return ordered


def complete_pairs(rows):
    pairs={}
    for row in rows:pairs.setdefault(row['pair_id'],[]).append(row)
    for pair in pairs.values():
        if len(pair)!=2 or {r['label'] for r in pair}!={0,1}:raise ValueError('Patch donor pair is incomplete')
        if any(pair[0][k]!=pair[1][k] for k in ('concept','group_id')):raise ValueError('Patch donor crosses task/wrapper')
    return len(pairs)


def competence(margins,rows):
    from src.followup_calibration import summarize_margins
    return summarize_margins(margins,rows,expected_split=rows[0]['split'])


def validate_collection(directory,rows,atol=5e-5):
    directory=Path(directory);manifest=read_json(directory/'manifest.json');plan=manifest['plan']
    if sha_file(directory/'measurements.npz')!=manifest['measurements_sha256']:raise ValueError('Collection checksum mismatch')
    if json_hash(plan)!=manifest['signature']:raise ValueError('Collection plan signature mismatch')
    arrays=load_npz(directory/'measurements.npz');ordered=validate_rows(arrays,rows)
    if json_hash(ordered)!=plan['records_sha256']:raise ValueError('Collection records hash mismatch')
    n,k=len(ordered),len(arrays['neuron_ids'])
    if manifest['n']!=n or manifest['neurons']!=k:raise ValueError('Collection manifest axes mismatch')
    if arrays['layers'].shape!=(k,) or len(set(zip(arrays['layers'],arrays['neuron_ids'])))!=k:raise ValueError('Invalid neuron identity axes')
    selected={int(l):list(map(int,ns)) for l,ns in manifest['selection'].items()}
    coords=[(l,neuron) for l in sorted(selected) for neuron in selected[l]]
    equal(list(zip(arrays['layers'].tolist(),arrays['neuron_ids'].tolist())),coords,'selection axes')
    for location in ('answer','span'):
        for quantity in ('product','gate','up','contribution_norm'):
            if arrays[f'{location}_{quantity}'].shape!=(n,k):raise ValueError(f'{location}/{quantity} axes')
        if (arrays[f'{location}_contribution_norm']<0).any():raise ValueError('Negative contribution norm')
    if arrays['span_sign_frequencies'].shape!=(n,k,5) or arrays['span_product_by_sign'].shape!=(n,k,5):raise ValueError('Sign route axes')
    if not np.allclose(arrays['span_sign_frequencies'].sum(-1),1,atol=1e-8):raise ValueError('Sign frequencies do not sum to1')
    if (arrays['span_sign_frequencies']<0).any() or (arrays['span_sign_frequencies']>1).any():raise ValueError('Sign frequency outside[0,1]')
    if not np.allclose(arrays['span_product_by_sign'].sum(-1),arrays['span_product'],atol=atol,rtol=1e-4):raise ValueError('Sign products do not reconstruct span')
    if not np.isin(arrays['answer_sign_regime'],range(5)).all():raise ValueError('Invalid answer sign regime')
    gate,up=arrays['answer_gate'],arrays['answer_up']
    expected_sign=np.where((gate==0)|(up==0),4,2*(gate<0).astype(int)+(up<0).astype(int))
    if not np.array_equal(arrays['answer_sign_regime'],expected_sign):raise ValueError('Answer sign regimes disagree with gate/up')
    if not np.allclose(gate*((1+np.tanh(gate/2))/2)*up,arrays['answer_product'],atol=atol,rtol=1e-4):raise ValueError('SwiGLU product disagrees with gate/up')
    if arrays['margins'].shape!=(n,) or arrays['answer_token_counts'].shape!=(n,2):raise ValueError('Margin/answer count axes')
    for key in ('prompt_token_lengths','span_token_lengths','answer_positions'):
        if arrays[key].shape!=(n,):raise ValueError(f'{key} axes')
    if (arrays['span_token_lengths']<=0).any() or (arrays['span_token_lengths']>arrays['prompt_token_lengths']).any():raise ValueError('Invalid span token lengths')
    if (arrays['answer_positions']<arrays['prompt_token_lengths']-1).any():raise ValueError('Answer intervention before prompt end')
    summary=competence(arrays['margins'],ordered)
    expected={c:{'n':v['n'],'accuracy':v['accuracy']} for c,v in summary['per_task'].items()}
    equal(manifest['competence'],expected,'collection competence')
    return manifest,arrays,summary


def validate_causal(directory,rows,atol=5e-5):
    directory=Path(directory);manifest=read_json(directory/'manifest.json');plan=manifest['plan']
    if json_hash(plan)!=manifest['signature']:raise ValueError('Causal plan signature mismatch')
    if sha_file(directory/'effects.npz')!=manifest['effects_sha256']:raise ValueError('Causal checksum mismatch')
    arrays=load_npz(directory/'effects.npz');ordered=validate_rows(arrays,rows);complete_pairs(ordered)
    if json_hash(ordered)!=plan['records_sha256']:raise ValueError('Causal record hash mismatch')
    n,u,l,m=len(ordered),len(plan['units']),len(plan['locations']),len(plan['modes'])
    if arrays['effects'].shape!=(n,u,l,m) or arrays['margins'].shape!=(n,):raise ValueError('Causal array axes mismatch')
    equal(arrays['locations'],plan['locations'],'locations');equal(arrays['modes'],plan['modes'],'modes')
    equal(arrays['unit_ids'],[x['id'] for x in plan['units']],'unit IDs');equal(arrays['unit_kinds'],[x['kind'] for x in plan['units']],'unit kinds')
    modes=plan['modes'];effects=arrays['effects']
    if 'zero' in modes and 'scale_0' in modes:
        if not np.allclose(effects[:,:,:,modes.index('zero')],effects[:,:,:,modes.index('scale_0')],atol=atol,rtol=1e-5):raise ValueError('zero != scale0 intervention')
    if 'scale_1' in modes and np.max(np.abs(effects[:,:,:,modes.index('scale_1')]))>atol:raise ValueError('scale1 changed baseline')
    ref_manifest,reference,_=validate_collection(directory/'references',ordered,atol)
    equal(arrays['margins'],reference['margins'],'causal baseline',atol)
    chunk_dir=directory/'chunks'
    if chunk_dir.exists():
        if not chunk_dir.is_dir():raise ValueError('Causal chunks path is not a directory')
        for ui in range(u):
            for li in range(l):
                for mi in range(m):
                    path=chunk_dir/f'unit{ui:03d}_location{li}_mode{mi}.npz'
                    if not path.is_file():raise ValueError(f'Partial chunk directory: missing {path.name}')
                    chunk=load_npz(path)
                    if str(chunk['signature'])!=manifest['signature']:raise ValueError('Causal chunk signature mismatch')
                    equal(effects[:,ui,li,mi],arrays['margins']-chunk['margin_intervened'],'chunk effect',atol)
    return manifest,arrays,competence(arrays['margins'],ordered)


def fast_evaluate_pair(a,b,records,fitted,split='D3'):
    """Independent vectorized replay of the published equal-source/task estimand.

    Reuses only the within-task correlation definition, not stored score values.
    Random assignment controls have one target per source; batching them avoids
    millions of repeated tiny Python/NumPy loops during archive verification.
    """
    from src.followup_analysis import within_task_correlation_matrices
    if fitted.get('fit_split')!='D2':raise ValueError('Need frozen D2 fit')
    matrices=within_task_correlation_matrices(a,b,records,split=split)
    def mapped(cells,mapping):
        rows=np.asarray(mapping['source'],int);cols=np.asarray(mapping['target'],int)
        if not len(rows):return None
        _,inverse=np.unique(rows,return_inverse=True);tasks=[]
        for matrix in cells.values():
            values=matrix[rows,cols];valid=np.isfinite(values)
            counts=np.bincount(inverse,weights=valid,minlength=inverse.max()+1)
            sums=np.bincount(inverse,weights=np.where(valid,values,0),minlength=len(counts))
            if np.any(counts):tasks.append(float(np.mean(sums[counts>0]/counts[counts>0])))
        return float(np.mean(tasks)) if tasks else None
    scores={name:{group:mapped(cells,mapping) for group,cells in matrices.items()} for name,mapping in fitted['mappings'].items()}
    controls={}
    for scope,maps in fitted['random_mappings'].items():
        if len(maps)<100:raise ValueError('Missing repeated random controls')
        simple=all(len(m['source'])==len(set(m['source'])) for m in maps) and len({len(m['source']) for m in maps})==1
        draws=[{} for _ in maps]
        if simple and len(maps[0]['source']):
            sources=np.asarray([m['source'] for m in maps],int);targets=np.asarray([m['target'] for m in maps],int)
            for group,cells in matrices.items():
                task_values=[]
                for matrix in cells.values():
                    values=matrix[sources,targets];valid=np.isfinite(values);counts=valid.sum(1)
                    means=np.divide(np.where(valid,values,0).sum(1),counts,out=np.full(len(maps),np.nan),where=counts>0)
                    task_values.append(means)
                task_values=np.asarray(task_values);valid=np.isfinite(task_values);counts=valid.sum(0)
                means=np.divide(np.where(valid,task_values,0).sum(0),counts,out=np.full(len(maps),np.nan),where=counts>0)
                for i,value in enumerate(means):draws[i][group]=float(value) if np.isfinite(value) else None
        else:
            draws=[{group:mapped(cells,mapping) for group,cells in matrices.items()} for mapping in maps]
        means=[]
        for draw in draws:
            finite=[v for v in draw.values() if v is not None];means.append(float(np.mean(finite)) if finite else None)
        controls[scope]={'wrapper_scores':draws,'means':means,'n_draws':len(draws)}
        scores['random__'+scope]={}
        for group in matrices:
            finite=[draw[group] for draw in draws if draw[group] is not None]
            scores['random__'+scope][group]=float(np.mean(finite)) if finite else None
    descriptives={}
    for name,values in scores.items():
        finite=[v for v in values.values() if v is not None]
        descriptives[name]={'mean':float(np.mean(finite)) if finite else None,'n_valid_wrappers':len(finite),'n_wrappers':len(values)}
    return dict(evaluation_split=split,fit_split='D2',wrapper_scores=scores,descriptive=descriptives,random_controls=controls,
        metric='within-task wrapper-equal native-neuron Pearson correlation',
        limitations=['Pair estimates are descriptive; shared model seeds are dependent.','One-to-many averages targets within each source neuron.','Invalid constant-neuron correlations are excluded and coverage must be reported.'])


def replay_global_bh(payload):
    from src.followup_analysis import apply_global_bh
    if 'tests' not in payload:raise ValueError('Global BH payload missing tests')
    expected=apply_global_bh({name:{k:v for k,v in test.items() if k!='qvalue'} for name,test in payload['tests'].items()})
    for key in ('family','family_size','finite_pvalue_count','tests'):equal(payload[key],expected[key],f'global BH {key}')
    return expected


class Audit:
    def __init__(self,root,atol=5e-5):
        self.root=Path(root).resolve();self.run=self.root/'results/followup-v2';self.atol=atol
        self.errors=[];self.pending=[];self.checked=[];self.competence={};self.cache={}
        self.archive_fallbacks=[];self.preservation_detail=None;self.data_storage=[];self.hard_stress_coverage=None
    def check(self,label,fn):
        try:
            result=fn();self.checked.append(label);return result
        except Exception as exc:self.errors.append({'check':label,'error':f'{type(exc).__name__}: {exc}'})
    def available(self,path):
        if path.is_file():return True
        self.pending.append(str(path.relative_to(self.root)));return False
    def preservation(self):
        snap=read_json(self.run/'preservation_before.json');verified=[];omitted=[]
        for name,digest in snap['files'].items():
            if name=='README.md':
                saved='reports/pilot-v1-README.md';path=self.root/saved
                if not path.is_file() or sha_file(path)!=digest:raise ValueError('Saved original README differs from pre-followup snapshot')
                verified.append({'original_path':name,'storage':'saved_copy','path':saved});continue
            path=(self.root/name).resolve()
            if not path.is_relative_to(self.root):raise ValueError('Preservation path escapes archive root')
            try:raw,source=portable_bytes(self.root,name)
            except FileNotFoundError:
                suffix=Path(name).suffix
                if suffix=='.pt':omitted.append({'path':name,'reason':'Model weights intentionally excluded from portable weights-free archive; hash not independently verified here'})
                elif suffix=='.png' and Path(name).parts[:2]==('artifacts','figures'):omitted.append({'path':name,'reason':'Legacy PNG intentionally omitted; published SVG/data remain required and verified'})
                else:raise ValueError(f'Unexpected missing preserved pilot artifact: {name}')
                continue
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError(f'Preserved pilot artifact changed: {name}')
            verified.append({'original_path':name,**source})
        detail={'snapshot_entries':len(snap['files']),'verified_count':len(verified),'verified':verified,
                'optional_omitted_count':len(omitted),'optional_omitted':omitted,
                'claim':'Only listed present files, archived member bytes, and saved README were verified; omitted weights/PNGs were not verified.'}
        self.preservation_detail=detail
        return detail
    def training(self):
        initials=[]
        for seed in self.cfg['training']['seeds']:
            directory=self.run/'training'/f'seed_{seed}';path=directory/'manifest.json'
            if not self.available(path):continue
            manifest=read_json(path)
            if manifest['seed']!=seed or manifest['steps']!=self.cfg['training']['steps'] or manifest['planned_steps']!=manifest['steps'] or not manifest['completed']:raise ValueError('Training did not finish planned independent steps')
            expected_train=hashlib.sha256(json.dumps(self.dataset['train'],sort_keys=True).encode()).hexdigest()
            equal(manifest['train_hash'],expected_train,'training data hash')
            signature=hashlib.sha256(json.dumps({'config':self.cfg['training'],'train_hash':expected_train},sort_keys=True).encode()).hexdigest()
            equal(manifest['signature'],signature,'training signature')
            if manifest['initial_hash']==manifest['final_hash']:raise ValueError('Weights did not change during training')
            initials.append(manifest['initial_hash'])
            log=[json.loads(line) for line in (directory/'training.jsonl').read_text().splitlines()]
            equal(log,manifest['losses'],'training log vs manifest')
            steps=[r['step'] for r in log]
            if steps!=sorted(set(steps)) or steps[-1]!=manifest['steps']:raise ValueError('Training log step sequence incomplete')
            for row in log:
                if any(not np.isfinite(row[k]) for k in ('loss','lm_loss','answer_loss','elapsed_seconds')):raise ValueError('Nonfinite training measurements')
        if len(initials)!=len(set(initials)):raise ValueError('Independent models share initial weight hash')
    def positive_control(self):
        from src.alignment import correlation_matrix,match_neurons
        directory=self.run/'positive_control';summary=read_json(directory/'summary.json');arrays=load_npz(directory/'activations.npz');mapping=read_json(directory/'mapping.json')
        coords=[(r['source_layer'],r['source_neuron']) for r in mapping];targets=[(r['target_layer'],r['target_neuron']) for r in mapping]
        if len(coords)!=len(set(coords)) or len(targets)!=len(set(targets)):raise ValueError('Permutation mapping is not bijective')
        rng=np.random.default_rng(907)
        for location in ('answer','span'):
            x,y=arrays['original_'+location],arrays['permuted_'+location]
            if x.shape!=y.shape or x.shape[0]!=summary['n'] or x.shape[1]!=summary['candidates']:raise ValueError('Positive control axes')
            score=correlation_matrix(x,y);match=match_neurons(score)
            draws=[float(np.mean(np.diag(score[:,rng.permutation(len(score))]))) for _ in range(100)]
            expected=dict(recovered_fraction=float(np.mean(match['source']==match['target'])),matched_correlation=float(np.mean(score[match['source'],match['target']])),random_mean=float(np.mean(draws)),random_sd=float(np.std(draws,ddof=1)),max_abs_product_difference=float(np.max(abs(x-y))))
            equal(summary['alignment'][location],expected,'constructed positive alignment')
        passed=all(v['passed'] for v in summary['intervention_checks'].values()) and all(v['recovered_fraction']==1 for v in summary['alignment'].values()) and not any(v['equal_at_positive_control_tolerance'] for v in summary['negative_checks'].values())
        if summary['passed']!=passed or not passed:raise ValueError('Constructed positive/negative intervention checks failed')
    def prepared(self,name,split):
        from src.followup_calibration import transform_records
        lock=read_json(self.run/'calibration'/name/'lock.json')
        return transform_records(self.dataset[split],lock['variant'],self.dataset['train'])
    def calibration(self,name):
        from src.followup_calibration import transform_records,choose_variant
        path=self.run/'calibration'/name;summary=read_json(path/'summary.json');lock=read_json(path/'lock.json');arrays=load_npz(path/'evidence.npz')
        for filename,digest in summary['artifact_sha256'].items():
            if sha_file(path/filename)!=digest:raise ValueError(f'Calibration {filename} checksum')
        if sha_file(path/'evidence.npz')!=lock['evidence_file_sha256']:raise ValueError('Calibration lock evidence checksum')
        ordered=validate_rows(arrays,self.dataset['calibration']);equal([r['id'] for r in ordered],[r['id'] for r in self.dataset['calibration']],'calibration order')
        variants={}
        for variant in lock['variants_evaluated']:
            rows=transform_records(ordered,variant,self.dataset['train']);margins=arrays['margins_'+variant]
            equal(arrays['prompts_'+variant],[r['prompt'] for r in rows],'calibration prompts')
            result=competence(margins,rows);equal(result,lock['metrics'][variant],f'calibration {variant} metrics')
            variants[variant]={'margins':margins,'rows':rows}
        if lock['selection_mode']=='calibration_only_format_selection':
            choice=choose_variant(variants)
            for key in ('variant','evidence_sha256','metrics','selected_metrics'):equal(lock[key],choice[key],f'lock {key}')
        elif lock['variant']!='default':raise ValueError('Fixed tiny checkpoint format must be default')
        self.competence[f'calibration/{name}']=lock['selected_metrics']
    def collection(self,name,checkpoint,split):
        path=self.run/'collections'/name/checkpoint/split
        value=validate_collection(path,self.prepared(name,split),self.atol);manifest,arrays,summary=value
        d1path=self.run/'collections'/name/'final/D1/manifest.json'
        if split!='D1' and d1path.exists():equal(manifest['selection'],read_json(d1path)['selection'],'fixed D1 selection')
        if split=='D1' and manifest['plan']['selection'] is not None:raise ValueError('D1 should be the discovery source')
        self.cache[name,checkpoint,split]=value;self.competence[f'{name}/{checkpoint}/{split}']=summary
    def causal(self,name,split):
        from src.followup_engine import stratified_pairs
        path=self.run/'causal'/name/split;plan=read_json(path/'manifest.json')['plan']
        rows=stratified_pairs(self.prepared(name,split),plan['pairs_per_task_wrapper'])
        value=validate_causal(path,rows,self.atol);manifest,arrays,summary=value
        if not (path/'chunks').exists():self.archive_fallbacks.append({'path':str(path.relative_to(self.root)),'check':'individual intervention chunk cross-check','status':'SKIPPED_CHUNKS_NOT_PUBLISHED','retained_checks':'effects byte hash, finite axes, row labels/pairs, source identity, baseline references, zero=scale0 and scale1=baseline; maps/statistics replay remains mandatory','limitation':'Intervened margins are algebraically baseline minus effects; no independent chunk-level comparison in this archive'})
        d1=read_json(self.run/'collections'/name/'final/D1/manifest.json')
        equal(plan['d1_signature'],d1['signature'],'causal D1 signature');equal(plan['d1_measurements_sha256'],d1['measurements_sha256'],'causal D1 checksum')
        for unit in plan['units']:
            for layer,neurons in unit['units_by_layer'].items():
                if not set(neurons)<=set(d1['selection'][str(layer)]):raise ValueError('Causal neuron outside frozen D1 selection')
        self.cache[name,'causal',split]=value;self.competence[f'{name}/causal/{split}']=summary
    def run_checks(self,require_complete=False):
        self.check('pilot preservation with explicit archive coverage',self.preservation)
        loaded=self.check('frozen data semantic and byte hashes',lambda:load_portable_followup(self.root))
        self.dataset=loaded[0] if loaded is not None else None
        if loaded is not None:self.data_storage=loaded[1]
        if self.dataset is None:return self.result(require_complete)
        cfg=read_json(self.root/'configs/followup_v2.json');self.cfg=cfg
        tiny=[f'seed{s}' for s in cfg['training']['seeds']];names=tiny+['qwen','smol','olmo'];self.names=names
        for stage in cfg['stage_order']:
            if stage=='F6':continue  # F6 snapshot follows successful replay; global stats are required below.
            path=self.run/'stages'/f'{stage}.json'
            if self.available(path):
                value=read_json(path)
                if value.get('status') not in ('MEASURED','COMPLETED'):self.pending.append(f'{stage}:status={value.get("status")}')
        self.check('independent training log evidence',self.training)
        if self.available(self.run/'positive_control/summary.json'):self.check('constructed permutation positive control',self.positive_control)
        for name in names:
            path=self.run/'calibration'/name/'summary.json'
            if self.available(path):self.check(f'calibration/{name}',lambda name=name:self.calibration(name))
            for checkpoint,split in [('final','D1'),('final','D2'),('final','D3')]+([('initial','D3'),('middle','D3')] if name in tiny else []):
                path=self.run/'collections'/name/checkpoint/split/'manifest.json'
                if self.available(path):self.check(f'collection/{name}/{checkpoint}/{split}',lambda name=name,checkpoint=checkpoint,split=split:self.collection(name,checkpoint,split))
            for split in ('D2','D4'):
                path=self.run/'causal'/name/split/'manifest.json'
                if self.available(path):self.check(f'causal/{name}/{split}',lambda name=name,split=split:self.causal(name,split))
        self.check('analysis replay',self.replay_analyses)
        self.check('transfers replay',self.replay_transfers)
        if (self.run/'hard_stress').exists():self.check('optional hard-stress replay',self.replay_hard_stress)
        return self.result(require_complete)
    def replay_analyses(self):
        from src.followup_analysis import json_ready,aggregate_pairs
        evaluate_pair=fast_evaluate_pair
        from src.followup_alignment_runner import PAIRS,POSITIONS,annotate_subtype,wilson_gate,_compact_eval,_primary_contrasts
        cohort_inputs={};confirmatory={}
        for left,right in PAIRS:
            pair=f'{left}_{right}';cohort='independent_seeds' if left.startswith('seed') else 'cross_family'
            for location in POSITIONS:
                path=self.run/'alignment'/pair/location/'fit.json'
                if not self.available(path):continue
                fit=read_json(path)
                for side,name in (('a',left),('b',right)):
                    source=self.cache.get((name,'final','D2'))
                    if source is None:raise ValueError('Missing D2 inputs for stored alignment fit')
                    equal(fit['source']['measurements_sha256_'+side],source[0]['measurements_sha256'],'fit source hash')
                    equal(fit['source']['candidates_'+side],{'layers':source[1]['layers'].tolist(),'neuron_ids':source[1]['neuron_ids'].tolist()},'fit candidates')
                for checkpoint in (('final','initial','middle') if cohort=='independent_seeds' else ('final',)):
                    evaluation_path=path.parent/('eval.json' if checkpoint=='final' else f'eval_{checkpoint}.json')
                    if not self.available(evaluation_path):continue
                    evaluation=read_json(evaluation_path);a=self.cache.get((left,checkpoint,'D3'));b=self.cache.get((right,checkpoint,'D3'))
                    if a is None or b is None:raise ValueError(f'Missing measurement inputs for {evaluation_path}')
                    rows=[annotate_subtype(r) for r in validate_rows(a[1],self.dataset['D3'])];equal(a[1]['row_ids'],b[1]['row_ids'],'paired row order')
                    replay=json_ready(evaluate_pair(a[1][location+'_product'],b[1][location+'_product'],rows,fit))
                    for key,value in replay.items():equal(evaluation[key],value,f'F3 {pair}/{location}/{checkpoint}/{key}')
                    source={'measurements_sha256_a':a[0]['measurements_sha256'],'measurements_sha256_b':b[0]['measurements_sha256'],'fit_sha256':sha_file(path)}
                    equal(evaluation['source'],source,'evaluation source hashes')
                    gate_a,gate_b=wilson_gate(a[1]['margins'],a[1]['concepts']),wilson_gate(b[1]['margins'],b[1]['concepts'])
                    gates={c:dict(model_a=gate_a[c],model_b=gate_b[c],both_passed=gate_a[c]['passed'] and gate_b[c]['passed']) for c in gate_a}
                    equal(evaluation['task_competence'],gates,'F3 competence gates')
                    equal(evaluation['competent_tasks'],[c for c in gates if gates[c]['both_passed']],'F3 competent tasks')
                    for concept in sorted(gates):
                        mask=np.array([r['concept']==concept for r in rows]);subset=[r for r,k in zip(rows,mask) if k]
                        task=_compact_eval(json_ready(evaluate_pair(a[1][location+'_product'][mask],b[1][location+'_product'][mask],subset,fit)))
                        equal(evaluation['by_task'][concept],task,'F3 task '+concept)
                    comparison=json_ready(aggregate_pairs({pair:replay},_primary_contrasts(),correct=False))['tests']
                    equal(evaluation['comparisons'],comparison,'F3 comparisons')
                    cohort_inputs.setdefault(f'{cohort}/{location}/{checkpoint}',{})[pair]=replay
                    if checkpoint=='final':
                        for contrast,test in comparison.items():confirmatory[f'F3/{pair}/{location}/{contrast}']=dict(test,descriptive_pair=True,competence_passed_tasks=evaluation['competent_tasks'])
                    self.checked.append(str(evaluation_path.relative_to(self.root)))
        summary_path=self.run/'alignment/summary.json'
        if self.available(summary_path):
            summary=read_json(summary_path);equal(summary['confirmatory_tests'],confirmatory,'F3 confirmatory tests')
            for cohort,evaluations in cohort_inputs.items():
                expected=json_ready(aggregate_pairs(evaluations,_primary_contrasts(),correct=False));equal(summary['cohorts'][cohort],expected,'F3 shared-wrapper cohort')
            if len(confirmatory)!=52:raise ValueError('Incomplete F3 confirmatory family')
        self.replay_causal_analyses()
        family_path=self.run/'statistics/global_tests.json'
        if self.available(family_path):
            payload=read_json(family_path);replay_global_bh(payload)
            tests={}
            for relative in ('alignment/summary.json','causal_alignment/summary.json'):
                source=read_json(self.run/relative)
                if not source['full_protocol_complete']:raise ValueError('Global family includes incomplete analysis')
                equal(payload['source_sha256'][relative],sha_file(self.run/relative),'BH source hash')
                for name,test in source['confirmatory_tests'].items():
                    if name in tests:raise ValueError('Duplicate global hypothesis identity')
                    tests[name]=test
            relative='transfers/summary.json';source=read_json(self.run/relative)
            equal(payload['source_sha256'][relative],sha_file(self.run/relative),'BH transfer source hash')
            tests['F5/aggregate/selected_minus_baseline']=source['aggregate_selected_minus_baseline']
            for pair,result in source['pairs'].items():tests[f'F5/{pair}/selected_minus_baseline']=result['selected_minus_baseline']
            equal(sorted(payload['tests']),sorted(tests),'global family membership')
            if len(tests)!=110 or payload['expected_family_size']!=110:raise ValueError('Global family must contain110 tests')
            for name,test in tests.items():equal({k:v for k,v in payload['tests'][name].items() if k!='qvalue'},test,'global source statistic')
            self.checked.append(str(family_path.relative_to(self.root)))
    def replay_causal_analyses(self):
        from src.followup_analysis import evaluate_causal_alignment,json_ready,aggregate_pairs
        from src.followup_alignment_runner import PAIRS,annotate_subtype,wilson_gate,_compact_causal,dose_response_diagnostics
        collected={};confirmatory={}
        for left,right in PAIRS:
            pair=f'{left}_{right}';cohort='independent_seeds' if left.startswith('seed') else 'cross_family'
            for kind in ('single','group'):
                path=self.run/'causal_alignment'/pair/kind/'fit.json'
                if not self.available(path):continue
                fit=read_json(path);evalpath=path.parent/'eval.json'
                if fit['fit_split']!='D2':raise ValueError('Causal maps not fitted on D2')
                for side,name in (('a',left),('b',right)):
                    source=self.cache.get((name,'causal','D2'))
                    if source is None:raise ValueError('Missing D2 causal inputs for fitted map')
                    equal(fit['source']['effects_sha256_'+side],source[0]['effects_sha256'],'F4 D2 source hash')
                    core_modes=[str(source[1]['modes'][i]) for i in fit['source']['primary_mode_indices']]
                    equal(core_modes,['zero','mean','patch'],'F4 primary intervention modes')
                d2groups=sorted(set(r['group_id'] for r in self.dataset['D2']))
                equal(fit['train_wrappers'],d2groups[:len(d2groups)//2],'F4 causal fit wrappers')
                equal(fit['validation_wrappers'],d2groups[len(d2groups)//2:],'F4 causal validation wrappers')
                if not self.available(evalpath):continue
                evaluation=read_json(evalpath);a=self.cache.get((left,'causal','D4'));b=self.cache.get((right,'causal','D4'))
                if a is None or b is None:raise ValueError('Missing D4 causal arrays for stored evaluation')
                rows=[annotate_subtype(r) for r in validate_rows(a[1],self.dataset['D4'])];equal(a[1]['row_ids'],b[1]['row_ids'],'D4 paired row order')
                for side,measurement in (('a',a),('b',b)):
                    equal(fit['source']['unit_ids_'+side],measurement[1]['unit_ids'],'D4 fixed unit IDs')
                    if not all(measurement[1]['unit_kinds'][i]==kind for i in fit['unit_indices_'+side]):raise ValueError('Unit kind selection mismatch')
                core=fit['source']['primary_mode_indices'];aa=a[1]['effects'][:,fit['unit_indices_a']][...,core];bb=b[1]['effects'][:,fit['unit_indices_b']][...,core]
                replay=json_ready(evaluate_causal_alignment(aa,bb,rows,fit))
                for key,value in replay.items():equal(evaluation[key],value,'F4 '+key)
                source=dict(effects_sha256_a=a[0]['effects_sha256'],effects_sha256_b=b[0]['effects_sha256'],fit_sha256=sha_file(path));equal(evaluation['source'],source,'F4 source hashes')
                gate_a,gate_b=wilson_gate(a[1]['margins'],a[1]['concepts']),wilson_gate(b[1]['margins'],b[1]['concepts'])
                gates={c:dict(model_a=gate_a[c],model_b=gate_b[c],both_passed=gate_a[c]['passed'] and gate_b[c]['passed']) for c in gate_a}
                equal(evaluation['task_competence'],gates,'F4 competence gates')
                equal(evaluation['competent_tasks'],[c for c in gates if gates[c]['both_passed']],'F4 competent tasks')
                for concept in sorted(gates):
                    mask=np.array([r['concept']==concept for r in rows]);subset=[r for r,k in zip(rows,mask) if k]
                    task=json_ready(_compact_causal(evaluate_causal_alignment(aa[mask],bb[mask],subset,fit)))
                    equal(evaluation['by_task'][concept],task,'F4 task '+concept)
                dose=dict(model_a=dose_response_diagnostics(a[1]['effects'][:,fit['unit_indices_a']],a[1]['modes'].tolist()),model_b=dose_response_diagnostics(b[1]['effects'][:,fit['unit_indices_b']],b[1]['modes'].tolist()))
                equal(evaluation['supplementary_dose_response'],json_ready(dose),'F4 dose response')
                for location,local in replay['locations'].items():
                    stats=json_ready(aggregate_pairs({pair:local},{'combined_minus_semantic':('combined','semantic')},correct=False))['tests']['combined_minus_semantic']
                    equal(evaluation['comparisons'][location],stats,'F4 comparisons')
                    collected.setdefault(f'{cohort}/{kind}/{location}',{})[pair]=local
                    confirmatory[f'F4/{pair}/{location}/{kind}/combined_minus_semantic']=dict(stats,descriptive_pair=True,competence_passed_tasks=evaluation['competent_tasks'])
                self.checked.append(str(evalpath.relative_to(self.root)))
        summary_path=self.run/'causal_alignment/summary.json'
        if self.available(summary_path):
            summary=read_json(summary_path);equal(summary['confirmatory_tests'],confirmatory,'F4 confirmatory tests')
            for cohort,evaluations in collected.items():
                expected=json_ready(aggregate_pairs(evaluations,{'combined_minus_semantic':('combined','semantic')},correct=False));equal(summary['cohorts'][cohort],expected,'F4 shared-wrapper cohort')
            if len(confirmatory)!=52:raise ValueError('Incomplete F4 confirmatory family')
    def replay_transfers(self):
        from src.followup_transfer import _accuracy,select_policy,choose_target_task,_condition_key
        from src.statistics import paired_randomization_test,cluster_bootstrap
        vectors={};pair_summaries={}
        for donor,target in self.cfg['transplant']['directed_pairs']:
            donor,target=f'seed{donor}',f'seed{target}';pair=f'{donor}_to_{target}';path=self.run/'transfers'/pair
            if not self.available(path/'summary.json'):continue
            policy=read_json(path/'policy.json');summary=read_json(path/'summary.json');d2=load_npz(path/'D2_margins.npz');d4=load_npz(path/'D4_margins.npz')
            r2=validate_rows(d2,self.prepared(target,'D2'));r4=validate_rows(d4,self.prepared(target,'D4'))
            equal(policy['plan']['d2_sha256'],json_hash(r2),'transfer D2 records hash');equal(policy['plan']['d4_sha256'],json_hash(r4),'transfer D4 records hash')
            equal(policy['signature'],json_hash(policy['plan']),'transfer plan signature')
            donor_data=self.cache[donor,'final','D2'][1];target_data=self.cache[target,'final','D2'][1]
            task_choice=choose_target_task(donor_data['margins'],target_data['margins'],r2);equal(task_choice,policy['task_choice'],'D2 target task')
            d2_results={};d4_results={}
            for condition in policy['conditions']:
                key=_condition_key(**condition)
                for arrays in (d2,d4):
                    if arrays[key].shape!=arrays['baseline'].shape:raise ValueError('Transfer margin axes')
                    if condition['alpha']==0 and not np.array_equal(arrays[key],arrays['baseline']):raise ValueError('Transfer alpha0 changed baseline')
                d2_results[key]={**condition,'accuracy':_accuracy(d2[key],r2)}
                d4_results[key]={**condition,'accuracy':_accuracy(d4[key],r4),'status':'DESCRIPTIVE_ONLY_NO_D4_SELECTION'}
            equal(d2_results,policy['d2_results'],'D2 transfer accuracies');equal(d4_results,summary['d4_conditions'],'D4 transfer accuracies')
            decision=select_policy(d2_results,_accuracy(d2['baseline'],r2),task_choice['target_task'],self.cfg['transplant']['retention_tolerance'])
            equal(decision,policy['policy'],'D2 policy');equal(decision,summary['policy'],'frozen policy')
            selected=d4[decision['selected']] if decision['selected'] else d4['baseline']
            mask=np.array([r['concept']==task_choice['target_task'] for r in r4]);groups=np.array([r['group_id'] for r in r4])[mask]
            a=(selected[mask]>0).astype(float);b=(d4['baseline'][mask]>0).astype(float);difference=a-b
            expected=paired_randomization_test(a,b,groups)
            for key,value in expected.items():equal(summary['selected_minus_baseline'][key],value,'selected transfer '+key)
            equal(summary['selected_minus_baseline']['bootstrap'],cluster_bootstrap(difference,groups),'transfer CI')
            vector={str(g):float(difference[groups==g].mean()) for g in sorted(set(groups))};equal(summary['selected_minus_baseline']['wrapper_effects'],vector,'transfer wrapper effects');vectors[pair]=vector
            hashes=summary['original_parameter_hashes']
            for who in ('donor','target'):
                if hashes[who+'_before']!=hashes[who+'_after']:raise ValueError('Original model mutated during transfer')
            pair_summaries[pair]=summary
            self.checked.append('transfers/'+pair)
        final=self.run/'transfers/summary.json'
        if self.available(final):
            if len(vectors)!=len(self.cfg['transplant']['directed_pairs']):raise ValueError('Transfer aggregate without all directed pairs')
            summary=read_json(final);equal(summary['pairs'],pair_summaries,'F5 aggregate pair inputs');groups=sorted(next(iter(vectors.values())));joint=np.mean([[v[g] for g in groups] for v in vectors.values()],axis=0)
            expected=paired_randomization_test(joint,np.zeros_like(joint),groups)
            for key,value in expected.items():equal(summary['aggregate_selected_minus_baseline'][key],value,'aggregate transfer '+key)
            equal(summary['aggregate_selected_minus_baseline']['bootstrap'],cluster_bootstrap(joint,groups),'aggregate transfer CI')
            equal(summary['aggregate_selected_minus_baseline']['wrapper_effects'],dict(zip(groups,joint.tolist())),'aggregate transfer wrapper effects')
    def replay_hard_stress(self):
        from src.followup_hard_stress import validate_dataset,summarize
        from src.followup_calibration import transform_records
        manifest=read_json(self.root/'data/followup-v2-hard-stress/manifest.json')
        raw,storage=portable_bytes(self.root,'data/followup-v2-hard-stress/hard_stress.jsonl')
        if hashlib.sha256(raw).hexdigest()!=manifest['file_sha256']:raise ValueError('Hard-stress dataset byte checksum')
        equal(manifest['original_manifest_sha256'],sha_file(self.root/'data/followup-v2/manifest.json'),'hard-stress exclusion source')
        rows=[json.loads(line) for line in raw.decode().splitlines()]
        checked=validate_dataset(rows,self.dataset)
        for key,value in checked.items():equal(manifest[key],json.loads(json.dumps(value)),'hard-stress manifest '+key)
        results={}
        for path in sorted((self.run/'hard_stress').glob('*/*/summary.json')):
            summary=read_json(path);name,checkpoint=path.parent.parent.name,path.parent.name
            equal(summary['name'],name,'hard-stress model');equal(summary['checkpoint'],checkpoint,'hard-stress checkpoint')
            arrays=load_npz(path.parent/'measurements.npz')
            equal(summary['measurements_sha256'],sha_file(path.parent/'measurements.npz'),'hard-stress measurements checksum')
            ordered=validate_rows(arrays,rows)
            equal([r['id'] for r in ordered],[r['id'] for r in rows],'hard-stress frozen row order')
            equal(arrays['bracket_pairs'],[r['bracket_pairs'] for r in rows],'hard-stress bracket lengths')
            equal(arrays['valid_max_stack_depth'],[r['valid_max_stack_depth'] for r in rows],'hard-stress depths')
            if arrays['answer_token_counts'].shape!=(len(rows),2):raise ValueError('Hard-stress answer-count axes')
            equal(summary['metrics'],summarize(arrays['margins'],rows),'hard-stress statistics replay')
            lockpath=self.run/'calibration'/name/'lock.json';lock=read_json(lockpath)
            equal(summary['lock_sha256'],sha_file(lockpath),'hard-stress calibration lock')
            equal(summary['data_sha256'],manifest['file_sha256'],'hard-stress frozen source hash')
            prepared=transform_records(rows,lock['variant'],self.dataset['train'])
            equal(summary['records_sha256'],json_hash(prepared,compact=True),'hard-stress transformed records hash')
            equal(summary['prompt_variant'],lock['variant'],'hard-stress unchanged format')
            if summary['primary_family_membership'] or not summary['no_retraining_or_primary_refitting']:raise ValueError('Hard-stress must remain exploratory')
            source=self.cache.get((name,checkpoint,'D3'))
            if source:equal(summary['model_info'],source[0]['plan']['model_info'],'hard-stress existing model identity')
            results[f'{name}/{checkpoint}']=summary;self.checked.append(str(path.relative_to(self.root)))
        final=self.run/'hard_stress/summary.json'
        if final.exists():
            aggregate=read_json(final);equal(aggregate['evaluations'],results,'hard-stress aggregate')
            if aggregate['n_evaluations']!=18 or len(results)!=18 or not aggregate['no_primary_family_change']:raise ValueError('Incomplete hard-stress aggregate')
        self.hard_stress_coverage={'verified_evaluations':len(results),'expected_full_sweep':18,'complete_exploratory_sweep':len(results)==18,'data_storage':storage,'required_for_primary_completion':False}
    def result(self,require_complete):
        complete=not self.pending and not self.errors
        return {'status':'FAILED' if self.errors else 'COMPLETE' if complete else 'PARTIAL',
                'valid_available_evidence':not self.errors,'complete':complete,
                'require_complete':require_complete,'exit_code':1 if self.errors or require_complete and not complete else 0,
                'checks_passed':len(self.checked),'checked':self.checked,'errors':self.errors,
                'pending':self.pending,'competence_recomputed':self.competence,
                'model_weights_required':False,'causal_numerical_atol':self.atol,
                'preservation_coverage':self.preservation_detail,'data_storage':self.data_storage,'archive_fallbacks':self.archive_fallbacks,'hard_stress_coverage':self.hard_stress_coverage,
                'scope':'Replay of saved data, measurements, maps and reported statistics; does not establish historical execution chronology.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=SOURCE_ROOT);parser.add_argument('--require-complete',action='store_true');parser.add_argument('--output',type=Path);parser.add_argument('--atol',type=float,default=5e-5);args=parser.parse_args()
    result=Audit(args.root,args.atol).run_checks(args.require_complete)
    text=json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(json.dumps({k:v for k,v in result.items() if k not in ('checked','competence_recomputed','pending','preservation_coverage','data_storage','archive_fallbacks')},ensure_ascii=False,allow_nan=False));print(f'Pending artifacts: {len(result["pending"])}')
    return result['exit_code']


if __name__=='__main__':raise SystemExit(main())
