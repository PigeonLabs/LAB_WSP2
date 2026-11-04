"""Fresh frozen post-hoc robustness test: typed brackets without adjacent mismatch cues.

Generate/freeze/test before inference. Evaluation reuses existing model checkpoints
and calibration locks; it never trains, chooses formats, or refits primary maps.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import time
import numpy as np
from .followup_data import WRAPPERS, _bracket_valid, load_dataset as load_original
from .followup_stress import adjacent_type_mismatch, max_stack_depth
from .statistics import cluster_bootstrap, paired_randomization_test

ROOT=Path(__file__).resolve().parents[1]
VERSION='followup-v2-hard-stress-v1'
SEED=90210
SPLIT='hard_stress'
NAMES=('seed101','seed211','seed307','seed401','seed503','qwen','smol','olmo')


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _write_once(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_text()!=text:raise ValueError(f'Refusing divergent frozen evidence: {path}')
    else:
        with path.open('x') as stream:stream.write(text)


def _json_once(path,obj):_write_once(path,json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def original_bracket_strings(original):
    return {r['semantic']['brackets'] for rows in original.values() for r in rows if r['concept']=='syntax'}


def _sample_pair(rng,length,excluded):
    for attempt in range(100000):
        stack=[];chars=[]
        for _ in range(length):
            left,right=rng.choice((('(',')'),('[',']'),('{','}')));chars.append(left);stack.append(right)
            while stack and rng.random()<.5:chars.append(stack.pop())
        chars.extend(reversed(stack));valid=''.join(chars)
        if valid in excluded:continue
        eligible=[i for i in range(1,len(valid)) if valid[i] in ')]}' and valid[i-1] in ')]}']
        swaps=[(i,j) for i in eligible for j in eligible if i<j and valid[i]!=valid[j]]
        rng.shuffle(swaps)
        for i,j in swaps:
            invalid=list(valid);invalid[i],invalid[j]=invalid[j],invalid[i];invalid=''.join(invalid)
            if invalid in excluded or _bracket_valid(invalid) or adjacent_type_mismatch(invalid):continue
            return valid,invalid,[i,j]
    raise RuntimeError('Finite hard-stress candidate generation exhausted')


def generate_dataset(original,seed=SEED):
    """Exactly384 fresh matched pairs,24 reused D3 wrappers, length5..8 balanced."""
    if seed!=SEED:raise ValueError('This frozen protocol fixes seed90210; use a new version for another seed')
    rng=random.Random(seed);excluded=original_bracket_strings(original);rows=[]
    for wrapper in range(24):
        for slot in range(16):
            length=5+slot%4
            valid,invalid,swaps=_sample_pair(rng,length,excluded);excluded.update((valid,invalid))
            pair_id=f'{VERSION}:w{wrapper:02d}:p{slot:02d}'
            for label,brackets in ((0,invalid),(1,valid)):
                statement=f'The bracket sequence {brackets} is well-formed.'
                template=WRAPPERS['D3'][wrapper];prompt=template.format(s=statement);start=prompt.index(statement)
                rows.append({'id':pair_id+f':{label}','split':SPLIT,'concept':'syntax','label':label,
                    'prompt':prompt,'correct':' yes' if label else ' no','foil':' no' if label else ' yes',
                    'span':[start,start+len(statement)],'statement':statement,'template':template,
                    'template_id':f'{SPLIT}:wrapper:t{wrapper:02d}','group_id':f'{SPLIT}:wrapper:t{wrapper:02d}',
                    'pair_id':pair_id,'content_key':['syntax',valid],'numeric_tuple':None,'semantic':{'brackets':brackets},
                    'generation_seed':seed,'source':VERSION,'valid_max_stack_depth':max_stack_depth(valid),
                    'bracket_pairs':length,'swapped_closing_indices':swaps,'wrapper_source':'D3 reused; held out from model training'})
    rng.shuffle(rows);validate_dataset(rows,original);return rows


def validate_dataset(rows,original):
    if len(rows)!=768 or len({r['id'] for r in rows})!=768:raise ValueError('Exactly768 unique records required')
    strings=[];pairs={};counts=Counter();original_strings=original_bracket_strings(original)
    for r in rows:
        text=r['semantic']['brackets'];strings.append(text)
        if r['split']!=SPLIT or r['concept']!='syntax' or r['label'] not in (0,1) or r['generation_seed']!=SEED:raise ValueError('Wrong hard-stress schema or generation seed')
        if _bracket_valid(text)!=bool(r['label']):raise ValueError('Semantic oracle label mismatch')
        if adjacent_type_mismatch(text):raise ValueError('Adjacent mismatch cue survives')
        if r['correct']!=(' yes' if r['label'] else ' no') or r['foil']!=(' no' if r['label'] else ' yes'):raise ValueError('Wrong answer candidates')
        if text in original_strings:raise ValueError('Original train/calibration/D1-D4 content overlap')
        expected=f'The bracket sequence {text} is well-formed.'
        if r['statement']!=expected or r['prompt']!=r['template'].format(s=expected) or r['prompt'][slice(*r['span'])]!=expected:raise ValueError('Prompt/semantic/span mismatch')
        if r['template'] not in WRAPPERS['D3']:raise ValueError('Must reuse the frozen24 D3 wrappers')
        if len(text)//2 not in (5,6,7,8) or len(text)%2 or r['bracket_pairs']!=len(text)//2:raise ValueError('Out-of-training length range')
        if r['group_id']!=r['template_id']:raise ValueError('Group identity mismatch')
        pairs.setdefault(r['pair_id'],[]).append(r);counts[r['group_id'],r['bracket_pairs'],r['label']]+=1
    if len(set(strings))!=768:raise ValueError('Repeated valid or invalid string')
    if len(pairs)!=384 or len({r['group_id'] for r in rows})!=24 or set(counts.values())!={4}:raise ValueError('Wrapper/length/truth balance failure')
    for pair in pairs.values():
        if len(pair)!=2 or {r['label'] for r in pair}!={0,1}:raise ValueError('Incomplete donor pair')
        false,true=sorted(pair,key=lambda r:r['label']);bad,good=false['semantic']['brackets'],true['semantic']['brackets']
        if Counter(bad)!=Counter(good) or [c in '([{' for c in bad]!=[c in '([{' for c in good]:raise ValueError('Character counts or skeleton differ')
        positions=[i for i,(a,b) in enumerate(zip(bad,good)) if a!=b]
        if positions!=true['swapped_closing_indices'] or positions!=false['swapped_closing_indices'] or len(positions)!=2:raise ValueError('Not exactly two declared closing swaps')
        if any(i==0 or good[i] not in ')]}' or good[i-1] not in ')]}' for i in positions):raise ValueError('Swapped position preceded by opening symbol')
        for r in pair:
            if r['valid_max_stack_depth']!=max_stack_depth(good):raise ValueError('Wrong depth annotation')
        if false['group_id']!=true['group_id'] or false['content_key']!=true['content_key']:raise ValueError('Cross-group donor pair')
    return {'version':VERSION,'split':SPLIT,'seed':SEED,'n':768,'n_pairs':384,'n_wrappers':24,
            'rows_sha256':_digest(rows),'max_prompt_bytes':max(len(r['prompt'].encode()) for r in rows),
            'length_rows':dict(sorted(Counter(r['bracket_pairs'] for r in rows).items())),
            'valid_depth_pairs':dict(sorted(Counter(r['valid_max_stack_depth'] for r in rows if r['label']).items())),
            'original_string_overlap':0,'adjacent_mismatch_rows':0,'all_pairs_equal_character_multiset':True,
            'all_pairs_equal_open_close_skeleton':True,'wrapper_policy':'Reuse24 D3 wrappers; fresh content, not a new-wrapper OOD test',
            'protocol_phase':'FROZEN_BEFORE_ANY_HARD_STRESS_INFERENCE','posthoc_motivation':True,
            'excluded_from_primary_110_test_family':True,
            'limitations':['Post-hoc motivated by D3 local-cue weakness; fresh outcomes do not make it preregistered primary evidence.',
                'Valid strings need suitable closing runs, so their structural distribution differs from the original syntax corpus.',
                'Equal5..8pair length range prevents longer strings being the sole explanation; depth distribution can still differ.',
                'Removing adjacent type mismatches does not remove every finite-state/local cue or prove recursive parsing.',
                'Wrappers were already inspected in D3; only content/outcomes are new.']}


def freeze_dataset(root=ROOT):
    root=Path(root);original=load_original(root/'data/followup-v2');rows=generate_dataset(original);manifest=validate_dataset(rows,original)
    directory=root/'data/followup-v2-hard-stress';text=''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows)
    manifest.update(file_sha256=hashlib.sha256(text.encode()).hexdigest(),original_manifest_sha256=_sha(root/'data/followup-v2/manifest.json'))
    # Preflight both files before writing either.
    payloads={'hard_stress.jsonl':text,'manifest.json':json.dumps(manifest,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n'}
    for name,payload in payloads.items():
        path=directory/name
        if path.exists() and path.read_text()!=payload:raise ValueError(f'Immutable hard-stress dataset changed: {path}')
    for name,payload in payloads.items():_write_once(directory/name,payload)
    return manifest


def load_dataset(root=ROOT):
    root=Path(root);directory=root/'data/followup-v2-hard-stress';manifest=json.loads((directory/'manifest.json').read_text());path=directory/'hard_stress.jsonl'
    if _sha(path)!=manifest['file_sha256']:raise ValueError('Hard-stress bytes changed')
    if _sha(root/'data/followup-v2/manifest.json')!=manifest['original_manifest_sha256']:raise ValueError('Original exclusion corpus changed')
    rows=[json.loads(line) for line in path.read_text().splitlines()];checked=validate_dataset(rows,load_original(root/'data/followup-v2'))
    for key,value in checked.items():
        if json.loads(json.dumps(value))!=manifest[key]:raise ValueError(f'Hard-stress manifest mismatch: {key}')
    return rows,manifest


def summarize(margins,rows):
    margins=np.asarray(margins,float)
    if margins.shape!=(len(rows),) or not np.isfinite(margins).all():raise ValueError('One finite margin per frozen record required')
    groups=np.asarray([r['group_id'] for r in rows]);correct=(margins>0).astype(float);labels=np.asarray([r['label'] for r in rows]);yes=margins*(2*labels-1)>0
    result={'n':len(rows),'n_wrappers':len(set(groups)),'correct':int(correct.sum()),'accuracy':float(correct.mean()),
        'accuracy_true':float(correct[labels==1].mean()),'accuracy_false':float(correct[labels==0].mean()),'yes_rate':float(yes.mean()),'tie_rate':float(np.mean(margins==0)),
        'accuracy_cluster_bootstrap95':cluster_bootstrap(correct,groups,seed=90210),
        'accuracy_minus_half_cluster_bootstrap95':cluster_bootstrap(correct-.5,groups,seed=90210),
        'unadjusted_exploratory_signflip_vs_half':paired_randomization_test(correct,np.full(len(rows),.5),groups,seed=90210),
        'by_bracket_pairs':{},'by_valid_depth':{},'interpretation':'Descriptive post-hoc robustness evidence; no support verdict or inclusion in primary110 BH family.'}
    for key,field in [('by_bracket_pairs','bracket_pairs'),('by_valid_depth','valid_max_stack_depth')]:
        for value in sorted({r[field] for r in rows}):
            mask=np.array([r[field]==value for r in rows]);result[key][str(value)]={'n':int(mask.sum()),'accuracy':float(correct[mask].mean())}
    return result


def evaluate(root=ROOT,names=NAMES,checkpoints=('final','initial','middle'),device='cuda',batch_size=16):
    """Serial GPU EVAL only. Does not alter primary files, models, locks or fits."""
    import torch
    from .followup_calibration_runner import load_followup_model,transform_for_model
    from .followup_calibration import validate_context
    from .experiment import sequence_margins
    root=Path(root).resolve();run=root/'results/followup-v2';rows,manifest=load_dataset(root);train=load_original(root/'data/followup-v2')['train'];out=run/'hard_stress'
    if device.startswith('cuda') and not torch.cuda.is_available():raise RuntimeError('Requested GPU unavailable; no silent CPU fallback')
    summaries={}
    for name in names:
        if name not in NAMES:raise ValueError('Unknown frozen model')
        for checkpoint in checkpoints:
            if checkpoint!='final' and not name.startswith('seed'):continue
            destination=out/name/checkpoint;summary_path=destination/'summary.json'
            transformed=transform_for_model(rows,name,train,run)
            lock_sha=_sha(run/'calibration'/name/'lock.json')
            if summary_path.is_file():
                summary=json.loads(summary_path.read_text())
                if summary['data_sha256']!=manifest['file_sha256'] or summary['lock_sha256']!=lock_sha or summary['records_sha256']!=_digest(transformed):raise ValueError('Existing hard-stress inputs changed')
                if _sha(destination/'measurements.npz')!=summary['measurements_sha256']:raise ValueError('Hard-stress result checksum mismatch')
                with np.load(destination/'measurements.npz',allow_pickle=False) as saved:
                    if saved['row_ids'].tolist()!=[r['id'] for r in rows]:raise ValueError('Stored hard-stress row order mismatch')
                    if summarize(saved['margins'],rows)!=summary['metrics']:raise ValueError('Hard-stress metric replay differs')
                summaries[f'{name}/{checkpoint}']=summary;continue
            if destination.exists() and any(destination.iterdir()):raise ValueError('Partial hard-stress output exists; preserve and diagnose before resume')
            model,tokenizer,info=load_followup_model(name,checkpoint,device=device,run_dir=run)
            if any(p.dtype!=torch.float32 for p in model.parameters() if p.is_floating_point()):raise ValueError('Hard-stress scoring requires FP32')
            context=validate_context(transformed,tokenizer,model.config,variant=transformed[0]['prompt_variant'])
            start=time.monotonic();margins,counts=sequence_margins(model,tokenizer,transformed,device=device,batch_size=batch_size)
            metrics=summarize(margins,rows);destination.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(destination/'measurements.npz',margins=margins,answer_token_counts=counts,row_ids=np.asarray([r['id'] for r in rows]),groups=np.asarray([r['group_id'] for r in rows]),labels=np.asarray([r['label'] for r in rows]),bracket_pairs=np.asarray([r['bracket_pairs'] for r in rows]),valid_max_stack_depth=np.asarray([r['valid_max_stack_depth'] for r in rows]))
            summary={'version':VERSION,'status':'MEASURED_EXPLORATORY','name':name,'checkpoint':checkpoint,'model_info':info,
                'data_sha256':manifest['file_sha256'],'records_sha256':_digest(transformed),'lock_sha256':lock_sha,
                'prompt_variant':transformed[0]['prompt_variant'],'context':context,'precision':'float32','device':device,
                'elapsed_seconds':time.monotonic()-start,'metrics':metrics,'measurements_sha256':_sha(destination/'measurements.npz'),
                'no_retraining_or_primary_refitting':True,'primary_family_membership':False,'limitations':manifest['limitations']}
            _json_once(summary_path,summary);summaries[f'{name}/{checkpoint}']=summary
            print(json.dumps({'model':name,'checkpoint':checkpoint,'accuracy':metrics['accuracy'],'ci':metrics['accuracy_cluster_bootstrap95']['ci'],'seconds':summary['elapsed_seconds']}),flush=True)
            model.cpu();del model
            if device.startswith('cuda'):torch.cuda.empty_cache()
    # Subset calls retain their own immutable measurements and never claim a full sweep.
    expected={f'{name}/{ck}' for name in NAMES for ck in (('final','initial','middle') if name.startswith('seed') else ('final',))}
    if set(summaries)==expected:_json_once(out/'summary.json',{'version':VERSION,'status':'COMPLETE_EXPLORATORY','n_evaluations':len(summaries),'evaluations':summaries,'no_primary_family_change':True})
    return summaries


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['freeze','verify','evaluate']);parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--models',nargs='+',default=list(NAMES));parser.add_argument('--checkpoints',nargs='+',choices=['final','initial','middle'],default=['final','initial','middle']);parser.add_argument('--device',default='cuda');parser.add_argument('--batch-size',type=int,default=16);args=parser.parse_args()
    if args.action=='freeze':print(json.dumps(freeze_dataset(args.root),ensure_ascii=False))
    elif args.action=='verify':print(json.dumps(load_dataset(args.root)[1],ensure_ascii=False))
    else:evaluate(args.root,args.models,args.checkpoints,args.device,args.batch_size)


if __name__=='__main__':main()
