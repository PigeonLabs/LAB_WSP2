#!/usr/bin/env python3
"""CPU-only frozen-map replay and explicitly post-hoc competence diagnostics.

Never refits a mapping, reselects a neuron, loads a model, or rewrites a measured
artifact. Run after all stages with --require-complete for a failing exit status
when expected outputs are missing. Uses saved maps even if current fit code differs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from scipy.stats import rankdata
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data import generate_dataset,validate_dataset
from src.statistics import cluster_bootstrap,paired_randomization_test,fdr_bh
from src.experiment import analysis_input_signature


def read(path):return json.loads(Path(path).read_text())
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,allow_nan=False))

def same(actual,expected,context):
    if expected is None:
        if actual is not None:raise AssertionError(context)
    elif not np.allclose(actual,expected,rtol=1e-10,atol=1e-10):
        raise AssertionError(f'{context}: {actual} != {expected}')


def correlations(a,b):
    """Independent replay implementation; zero-variance pairs contribute zero."""
    aa=np.asarray(a,np.float64);bb=np.asarray(b,np.float64)
    aa=aa-aa.mean(axis=0);bb=bb-bb.mean(axis=0)
    den=np.sqrt(np.sum(aa**2,axis=0)*np.sum(bb**2,axis=0))
    valid=den>1e-14
    out=np.zeros(aa.shape[1],np.float64)
    out[valid]=np.sum(aa*bb,axis=0)[valid]/den[valid]
    return np.clip(out,-1,1),valid


def scores(a,b,groups,source,target):
    values=[];invalid=0
    for group in np.unique(groups):
        left=a[groups==group][:,source];right=b[groups==group][:,target]
        if left.ndim==3:
            left=left.transpose(0,2,1).reshape(-1,len(source))
            right=right.transpose(0,2,1).reshape(-1,len(target))
        corr,valid=correlations(left,right)
        values.append(float(corr.mean()) if len(corr) else 0.)
        invalid+=int(np.sum(~valid))
    return np.asarray(values),invalid


def finite_file(path):
    arrays=np.load(path)
    for name,value in arrays.items():
        if np.issubdtype(value.dtype,np.number) and not np.isfinite(value).all():raise AssertionError(f'{path}:{name} nonfinite')
    return arrays


def selected_pairs(rows,per_concept):
    # Replay the recorded outcome-blind stratification without importing engine.
    result=[]
    for concept in sorted({r['concept'] for r in rows}):
        pairs={}
        for row in rows:
            if row['concept']==concept:pairs.setdefault(row['pair_id'],[]).append(row)
        strata={}
        for pid,pair in sorted(pairs.items()):strata.setdefault(pair[0]['group_id'],[]).append(pair)
        chosen=[];cursor=0
        while len(chosen)<min(per_concept,2*len(pairs)):
            for group,seq in sorted(strata.items()):
                if cursor<len(seq) and len(chosen)<per_concept:chosen.extend(sorted(seq[cursor],key=lambda r:r['label']))
            cursor+=1
        result.extend(chosen)
    return result


def competence(margins,concepts):
    return {str(c):{'accuracy':float(np.mean(margins[concepts==c]>0)),'n':int(np.sum(concepts==c))} for c in np.unique(concepts)}



def original_weight_similarity(root,run):
    """Read saved checkpoint tensors on CPU; no model construction or inference."""
    exported=run/"E1/trained/weight_similarity.npy"
    if exported.exists():
        values=np.load(exported,allow_pickle=False)
        if values.shape!=(64,64) or not np.isfinite(values).all():raise AssertionError("Exported weight baseline matrix malformed")
        expected=read(run/"E1/trained/input_signature.json")["inputs"]["weight_similarity_sha256"]
        if hashlib.sha256(np.ascontiguousarray(values,dtype=np.float64).tobytes()).hexdigest()!=expected:raise AssertionError("Exported weight baseline matrix checksum mismatch")
        return values
    import torch
    from src.alignment import weight_similarity
    arrays=[]
    for seed in (11,29):
        state=torch.load(run/f"training/seed_{seed}/final.pt",map_location="cpu",weights_only=True)["state_dict"]
        selection=read(run/f"collections/seed{seed}/selection.json")["selection"]
        gates=[];ups=[];downs=[]
        for layer,neurons in selection.items():
            prefix=f"layers.{layer}.mlp."
            gates.append(state[prefix+"gate_proj.weight"][neurons].numpy())
            ups.append(state[prefix+"up_proj.weight"][neurons].numpy())
            downs.append(state[prefix+"down_proj.weight"][:,neurons].numpy())
        arrays.append((np.concatenate(gates),np.concatenate(ups),np.concatenate(downs,axis=1)))
    return weight_similarity(*arrays[0],*arrays[1])


def validate(root=ROOT,require_complete=False):
    run=root/'results/pilot-v1';cfg=read(root/'configs/pilot.json')
    dataset=generate_dataset(cfg['seed'],cfg['data_counts']);data_check=validate_dataset(dataset)
    persisted=read(root/'data/pilot-v1-cluster-corrected/manifest.json')
    if persisted['splits']!=data_check['splits']:raise AssertionError('Persisted split hashes differ from generated dataset')
    report={'status':'PASS','data_hashes':{s:v['sha256'] for s,v in data_check['splits'].items()},'checks':[],'missing':[],'artifact_hashes':{},'optional_checkpoint_checks_not_available':[]}
    original={}
    historical_manifest=read(root/'data/pilot-v1/manifest.json')
    for split,rows in dataset.items():
        historical_path=root/'data/pilot-v1'/f'{split}.jsonl'
        original[split]=[json.loads(line) for line in historical_path.read_text().splitlines()] if historical_path.exists() else [dict(row,group_id=row['template_id']) for row in rows]
        regenerated_hash=hashlib.sha256(json.dumps(original[split],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if regenerated_hash!=historical_manifest['splits'][split]['sha256']:raise AssertionError('Regenerated historical dataset hash mismatch')
    for split,rows in original.items():
        without_group=lambda r:{k:v for k,v in r.items() if k!='group_id'}
        if [without_group(r) for r in rows]!=[without_group(r) for r in dataset[split]]:raise AssertionError('Grouping correction changed model inputs or labels')
    original_train_hash=hashlib.sha256(json.dumps(original['train'],sort_keys=True).encode()).hexdigest()
    initial_hashes=[]
    for seed in (11,29):
        training=read(run/f'training/seed_{seed}/manifest.json')
        if training['train_hash']!=original_train_hash:raise AssertionError('Training data hash mismatch')
        if training['steps']!=training['planned_steps']:raise AssertionError('Training did not finish planned steps')
        initial_hashes.append(training['initial_hash'])
    if len(set(initial_hashes))!=2:raise AssertionError('Initialization hashes are not independent')
    report['checks'].append('Training-era/corrected datasets differ only in cluster metadata; both training hashes and completed steps exact; independent initialization hashes differ')
    diag={'status':'EXPLORATORY_POSTHOC_AFTER_D3_D4','selection_policy':'Frozen mappings and neurons only. No retraining, no rematching. Task grouping and 0.60 competence display flag are post-hoc diagnostics, not confirmatory thresholds.','activation':{},'causal':{},'model_intervention_stability':{}}
    collections={};causals={}
    expected_models=['seed11','seed29','untrained11','untrained29','qwen','smol','olmo']
    for name in expected_models:
        path=run/'collections'/name
        if not (path/'manifest.json').exists():report['missing'].append(str(path.relative_to(root)));continue
        manifest=read(path/'manifest.json');selection=read(path/'selection.json')['selection']
        signature=hashlib.sha256(json.dumps({'model_info':manifest['model_info'],'dataset':dataset,'per_layer':16,'boundary':'shared-answer-prefix-v2','precision':'float32'},sort_keys=True).encode()).hexdigest()
        if signature!=manifest['signature']:raise AssertionError(f'{name}: data/model/config signature mismatch')
        layers=np.array([int(layer) for layer,neurons in selection.items() for _ in neurons]);neurons=np.array([n for ids in selection.values() for n in ids])
        captures={}
        if 'checkpoint' in manifest['model_info']:
            checkpoint=root/manifest['model_info']['checkpoint']
            if checkpoint.exists():
                if digest(checkpoint)!=manifest['model_info']['sha256']:raise AssertionError('Checkpoint file hash mismatch')
            else:report['optional_checkpoint_checks_not_available'].append(str(checkpoint.relative_to(root)))
        for split in ['D1','D2','D3']:
            f=path/f'{split}.npz';a=finite_file(f);captures[split]=a
            if a['row_ids'].tolist()!=[r['id'] for r in dataset[split]]:raise AssertionError(f'{name}/{split}: wrong rows')
            if not np.array_equal(a['layers'],layers) or not np.array_equal(a['neuron_ids'],neurons):raise AssertionError(f'{name}/{split}: wrong selected neurons')
            if a['product'].shape!=(len(dataset[split]),len(neurons)):raise AssertionError('Wrong matrix shape')
            if not set(a['sign_regime'].ravel()).issubset({0,1,2,3,4}):raise AssertionError('Invalid sign regimes')
            comp=competence(a['margins'],np.array([r['concept'] for r in dataset[split]]))
            if comp!=manifest['competence'][split]:raise AssertionError('Competence mismatch')
            report['artifact_hashes'][str(f.relative_to(root))]=digest(f)
        collections[name]=captures;report['checks'].append(f'{name}: D1/D2/D3 finite, row/selection/signature/competence exact')
    for name in [n for n in expected_models if not n.startswith('untrained')]:
        path=run/'causal'/name
        if not (path/'manifest.json').exists():report['missing'].append(str(path.relative_to(root)));continue
        manifest=read(path/'manifest.json');source=run/'collections'/name
        origins_path=run/'origin_roots.json'
        legacy_source=read(origins_path)['causal_collection_sources'][name] if origins_path.exists() else str(source.resolve())
        sig=hashlib.sha256(json.dumps({'dataset':dataset,'source':legacy_source,'source_manifest_sha256':digest(source/'manifest.json'),'per_layer':2,'per_concept':128,'boundary':'shared-answer-prefix-v2','precision':'float32'},sort_keys=True).encode()).hexdigest()
        if sig!=manifest['signature']:raise AssertionError(f'{name}: causal signature mismatch')
        ca={}
        for split in ['D2','D4']:
            f=path/f'{split}_causal.npz';a=finite_file(f);ca[split]=a;rows=selected_pairs(dataset[split],128)
            for field,key in [('id','row_ids'),('concept','concepts'),('label','labels'),('group_id','groups')]:
                if a[key].tolist()!=[r[field] for r in rows]:raise AssertionError(f'{name}/{split}: causal {field} mismatch')
            d1=collections[name]['D1'];ix=a['source_columns']
            if not np.array_equal(a['layers'],d1['layers'][ix]) or not np.array_equal(a['neuron_ids'],d1['neuron_ids'][ix]):raise AssertionError('Causal candidate mismatch')
            if a['effects'].shape!=(len(rows),len(ix),3):raise AssertionError('Causal effect shape')
            if competence(a['margins'],a['concepts'])!=manifest['splits'][split]['competence']:raise AssertionError('Causal competence mismatch')
            report['artifact_hashes'][str(f.relative_to(root))]=digest(f)
        causals[name]=ca;report['checks'].append(f'{name}: D2/D4 causal finite, full matched-pair IDs, source columns, signature and competence exact')
        a=ca['D4'];effects=a['effects'];stability={}
        for i,j in [(0,1),(0,2),(1,2)]:
            left=effects[:,:,i];right=effects[:,:,j];nz=(np.abs(left)>1e-7)&(np.abs(right)>1e-7)
            corr,_=correlations(left,right)
            stability[f'{manifest["interventions"][i]}_vs_{manifest["interventions"][j]}']={'mean_neuron_pearson':float(corr.mean()),'nonzero_sign_agreement':float(np.mean(np.sign(left[nz])==np.sign(right[nz]))) if nz.any() else None,'nonzero_fraction':float(nz.mean())}
        diag['model_intervention_stability'][name]={'D4_competence':competence(a['margins'],a['concepts']),'pairwise_interventions':stability}
    for stage in ['E1','E2','E3','E4']:
        expected={'E1':2,'E2':3,'E3':4,'E4':4}[stage];paths=sorted((run/stage).glob('*/metrics.json'))
        if len(paths)!=expected:report['missing'].append(f'{stage}: expected {expected} metrics, found {len(paths)}')
        for path in paths:
            m=read(path);a_name,b_name=m['pair'].split('_');frozen=read(path.parent/'frozen_mappings.json');is_causal=stage=='E4'
            if is_causal:
                a,b=causals[a_name]['D4'],causals[b_name]['D4'];maps=frozen['maps'];groups=a['groups'];concepts=a['concepts']
                aa=a['effects']/m['normalization']['a'];bb=b['effects']/m['normalization']['b']
            else:
                a,b=collections[a_name]['D3'],collections[b_name]['D3'];maps=frozen;groups=np.array([r['group_id'] for r in dataset['D3']]);concepts=np.array([r['concept'] for r in dataset['D3']]);aa=a['product'];bb=b['product']
            ug=np.unique(groups);all_scores={};pair_diag={}
            for method,mapping in maps.items():
                source=np.asarray(mapping['source'],int);target=np.asarray(mapping['target'],int)
                if np.any(source<0) or np.any(source>=aa.shape[1]) or np.any(target<0) or np.any(target>=bb.shape[1]):raise AssertionError('Frozen map out of bounds')
                sc,invalid=scores(aa,bb,groups,source,target);all_scores[method]=sc;summary=cluster_bootstrap(sc,ug)
                for key in ['mean','median','std','ci']:same(summary[key],m['results'][method][key],f'{stage}/{m["pair"]}/{method}/{key}')
                same(invalid,m['results'][method]['invalid_constant_pair_clusters'],'invalid-pair count')
                saved=np.load(path.parent/'cluster_scores.npz');same(sc,saved[method],'stored cluster scores')
                task={}
                for concept in np.unique(concepts):
                    ix=concepts==concept;cs,_=scores(aa[ix],bb[ix],groups[ix],source,target)
                    acca=float(np.mean(a['margins'][ix]>0));accb=float(np.mean(b['margins'][ix]>0))
                    task[str(concept)]={'mean':float(cs.mean()),'cluster_scores':cs.tolist(),'competence_a':acca,'competence_b':accb,'both_accuracy_over_0_60_posthoc':acca>.60 and accb>.60}
                pair_diag[method]={'per_task':task}
                if is_causal:
                    left=a['effects'][:,source,:];right=b['effects'][:,target,:]
                    lv=left.transpose(0,2,1).reshape(-1,len(source));rv=right.transpose(0,2,1).reshape(-1,len(target))
                    p,_=correlations(lv,rv);s,_=correlations(rankdata(lv,axis=0),rankdata(rv,axis=0))
                    same(float(p.mean()),m['results'][method]['pearson_pooled_mean'],'pooled Pearson');same(float(s.mean()),m['results'][method]['spearman_pooled_mean'],'pooled Spearman')
                    nz=(np.abs(left)>1e-7)&(np.abs(right)>1e-7)
                    sign=float(np.mean(np.sign(left[nz])==np.sign(right[nz]))) if nz.any() else None
                    same(sign,m['results'][method]['causal_sign_agreement'],'causal sign')
                    per_type={}
                    for k,mode in enumerate(['zero','mean','patch']):
                        cs,_=scores(aa[:,:,k],bb[:,:,k],groups,source,target)
                        nz=(np.abs(left[:,:,k])>1e-7)&(np.abs(right[:,:,k])>1e-7)
                        per_type[mode]={'mean':float(cs.mean()),'sign_agreement':float(np.mean(np.sign(left[:,:,k][nz])==np.sign(right[:,:,k][nz]))) if nz.any() else None,'nonzero_fraction':float(nz.mean())}
                    pair_diag[method]['per_intervention']=per_type
            comparison_replay={}
            for key,old in m['comparisons'].items():
                candidate,baseline=key.split('_minus_');test=paired_randomization_test(all_scores[candidate],all_scores[baseline],ug);summary=cluster_bootstrap(all_scores[candidate]-all_scores[baseline],ug)
                for attr in ['effect','pvalue','standardized_effect']:same(test[attr],old[attr],f'{key}/{attr}')
                for attr in ['mean','ci','std']:same(summary[attr],old['bootstrap'][attr],f'{key}/bootstrap/{attr}')
                comparison_replay[key]=test
            q=fdr_bh([t['pvalue'] for t in comparison_replay.values()])
            for key,value in zip(comparison_replay,q):same(value,m['comparisons'][key]['qvalue'],f'{key}/q')
            if is_causal:
                best=maps['semantic_causal'];shifted=np.roll(b['effects'],len(b['effects'])//len(np.unique(concepts)),axis=0)
                sc,_=scores(a['effects'],shifted,groups,np.asarray(best['source']),np.asarray(best['target']));control=cluster_bootstrap(sc,ug)
                for key in ['mean','ci']:same(control[key],m['mismatched_task_control'][key],'mismatched task control')
            # Backfill provenance only after this complete frozen-metric replay passes.
            if is_causal:
                source_paths=[run/'causal'/a_name/'D2_causal.npz',run/'causal'/b_name/'D2_causal.npz',run/'causal'/a_name/'D4_causal.npz',run/'causal'/b_name/'D4_causal.npz',run/'collections'/a_name/'D2.npz',run/'collections'/b_name/'D2.npz']
                signature=analysis_input_signature(source_paths,dataset)
            else:
                source_paths=[run/'collections'/a_name/'D2.npz',run/'collections'/b_name/'D2.npz',run/'collections'/a_name/'D3.npz',run/'collections'/b_name/'D3.npz']
                weight=original_weight_similarity(root,run) if 'weight' in maps else None
                signature=analysis_input_signature(source_paths,dataset,weight)
            sidecar=path.parent/'input_signature.json'
            if sidecar.exists():
                if read(sidecar)['inputs']!=signature:raise AssertionError(f'{sidecar}: analysis source hash mismatch')
            else:write(sidecar,{'inputs':signature,'validation':'backfilled only after independent frozen-map numerical replay; original metrics unchanged'})
            report['checks'].append(f'{stage}/{m["pair"]}: {len(maps)} frozen methods; means/CIs/cluster vectors/tests/BH q exactly replayed'+('; pooled rank/sign/control replayed' if is_causal else ''))
            for fname in ['metrics.json','frozen_mappings.json','cluster_scores.npz']:report['artifact_hashes'][str((path.parent/fname).relative_to(root))]=digest(path.parent/fname)
            diag['causal' if is_causal else 'activation'][f'{stage}/{m["pair"]}']=pair_diag
    import pandas as pd
    natural=read(root/'data/natural_reference.json') if (root/'data/natural_reference.json').exists() else None
    supplementary=[]
    for name in ['seed11','seed29','qwen','smol','olmo']:
        folder=run/'diagnostics'/name
        if not (folder/'manifest.json').exists():continue
        manifest=read(folder/'manifest.json');provenance=manifest['provenance']
        signature_provenance=dict(provenance,selection={int(k):v for k,v in provenance['selection'].items()})
        expected_signature=hashlib.sha256(json.dumps(signature_provenance,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if manifest['signature']!=expected_signature:raise AssertionError('Supplementary signature mismatch')
        if provenance['natural_sha256']!=digest(root/'data/natural_reference.json'):raise AssertionError('Natural corpus hash mismatch')
        if provenance['collection_manifest_sha256']!=digest(run/'collections'/name/'manifest.json'):raise AssertionError('Supplementary model source mismatch')
        if provenance['selection']!=read(run/'collections'/name/'selection.json')['selection']:raise AssertionError('Supplementary reselected neurons')
        arrays=finite_file(folder/'natural_activations.npz')
        atlas=read(folder/'natural_top_activations.json');sources={r['id']:r for r in atlas['sources']}
        originals={r['id']:r['text'] for r in natural['examples']}
        if len(sources)!=manifest['natural_paragraphs']:raise AssertionError('Natural paragraph count mismatch')
        for sid,source in sources.items():
            raw=originals[sid];used=source['used_text'];prefix=source['npz_key_prefix']
            if not raw.startswith(used) or source['raw_sha256']!=hashlib.sha256(raw.encode()).hexdigest():raise AssertionError('Natural source text mismatch')
            offsets=arrays[prefix+'_offsets'];values=arrays[prefix+'_product']
            if values.shape!=(source['token_count'],len(arrays['neuron_ids'])) or len(offsets)!=len(values):raise AssertionError('Natural token matrix shape')
            if np.any(offsets<0) or np.any(offsets>len(used)) or np.any(offsets[:,0]>offsets[:,1]):raise AssertionError('Natural character offset bounds')
        for row in atlas['top_contexts']:
            source=sources[row['source_id']];prefix=source['npz_key_prefix'];text=source['used_text']
            column=np.flatnonzero((arrays['layers']==row['layer'])&(arrays['neuron_ids']==row['neuron']))
            if len(column)!=1:raise AssertionError('Atlas neuron outside frozen selection')
            j=column[0];token=row['token_index']
            for key in ['product','gate','up','sign_regime','contribution_norm']:same(row[key],arrays[prefix+'_'+key][token,j],'Natural top value trace')
            if row['token_text']!=text[row['char_start']:row['char_end']] or row['context']!=text[row['context_char_start']:row['context_char_end']]:raise AssertionError('Natural top text trace')
            if [row['char_start'],row['char_end']]!=arrays[prefix+'_offsets'][token].tolist():raise AssertionError('Natural top offset trace')
        frame=pd.read_parquet(folder/'span_boundary_comparison.parquet');span=read(folder/'span_boundary_summary.json')
        if not np.isfinite(frame.select_dtypes(include=np.number).to_numpy()).all():raise AssertionError('Nonfinite span measurements')
        byid={r['id']:r for r in dataset['D1']}
        for source in span['source_rows']:
            expected=byid[source['id']]
            if source['prompt']!=expected['prompt'] or source['span']!=expected['span']:raise AssertionError('Span source mismatch')
        for summary_row in span['neurons']:
            group=frame[(frame.layer==summary_row['layer'])&(frame.neuron==summary_row['neuron'])]
            actual=float(np.corrcoef(group.span_mean_product,group.boundary_product)[0,1]) if np.std(group.span_mean_product)>0 and np.std(group.boundary_product)>0 else None
            same(actual,summary_row['span_boundary_correlation'],'Span summary correlation')
            same(float(np.mean(np.abs(group.span_mean_product-group.boundary_product))),summary_row['mean_absolute_difference'],'Span difference')
        supplementary.append(name)
        report['checks'].append(f'{name}: supplementary natural arrays finite, corpus/model/selection hashes exact, all top-context numeric/text/offset traces exact, span summaries replayed')
        for fname in ['manifest.json','natural_activations.npz','natural_top_activations.json','span_boundary_summary.json','span_boundary_comparison.parquet']:report['artifact_hashes'][str((folder/fname).relative_to(root))]=digest(folder/fname)
    report['supplementary_models']=supplementary
    for provenance_file in [run/'origin_roots.json',run/'E1/trained/weight_similarity.npy']:
        if provenance_file.exists():report['artifact_hashes'][str(provenance_file.relative_to(root))]=digest(provenance_file)
    report['status']='PASS_COMPLETE' if not report['missing'] else 'PASS_AVAILABLE_PENDING'
    report['label_shuffle_note']='Historical label-shuffled mappings depended on Python set iteration/hash order. Replay uses stored maps exclusively; current deterministic fit code is not used. E1/E3 shuffled-map differences are preserved as a documented reproducibility limitation.'
    write(run/'diagnostics/posthoc_competence.json',diag)
    write(run/'diagnostics/frozen_reanalysis.json',report)
    summary='\n'.join('- '+c for c in report['checks'])
    missing='\n'.join('- '+c for c in report['missing']) or '- None.'
    supplemental_text=(f'Supplementary natural-context and span-boundary measurements were verified for {len(supplementary)} models: '+', '.join(supplementary)+'. They remain descriptive diagnostics of frozen synthetic-task candidates on one author/book, not confirmatory cross-domain evidence.') if supplementary else 'No supplementary natural-context/span measurements were found at this validation run.'
    text=f'''# Final artifact validation\n\nStatus: **{report['status']}**. This report is generated by `scripts/validate_results.py` using CPU only. No model inference, neuron reselection, fitting, or original artifact modification occurs. Archived replay uses exported weight-similarity values and immutable legacy origin strings; the current files are still content-hashed. Dataset rows can be regenerated without unpacking JSONL, and their historical/corrected hashes must match. Checkpoint files are optional for numerical replay: {len(report["optional_checkpoint_checks_not_available"])} checkpoint-file checks were unavailable in this snapshot; checkpoint checksums remain recorded in the original manifests.\n\n## Executed verification\n\n{summary}\n\nThe exact replay tolerance is absolute/relative 1e-10 for floating-point summaries. Replay uses an independent NumPy implementation of the frozen-map correlation estimand and the original cluster-statistics definitions. Every checked raw numeric array is finite; saved IDs, selected neuron columns, collection signatures, data split hashes, and competence values match. Artifact SHA256 receipts are in [frozen_reanalysis.json](../results/pilot-v1/diagnostics/frozen_reanalysis.json).\n\n## Pending or missing outputs\n\n{missing}\n\n## Reproducibility correction\n\n{report['label_shuffle_note']} This correction does not justify rewriting an observed result or selecting a more favorable permutation. Other mapping methods and the stored frozen mappings remain the evidence used for evaluation.\n\n## Explicitly post-hoc diagnostics\n\n[posthoc_competence.json](../results/pilot-v1/diagnostics/posthoc_competence.json) splits the already-frozen correspondence scores by task and records both models' task accuracy. The display flag for both accuracies above 0.60 was chosen after observing D3 and is **not a hypothesis test or a preregistered selection threshold**. It must not replace the main pooled metrics. Causal diagnostics additionally report each intervention separately and within-model intervention sign/correlation consistency. All retain the original neurons, mappings, and held-out examples.\n\n## What this validation does not establish\n\nFinite arrays and exact replay establish computational consistency, not causal identification, monosemanticity, statistical power, robustness to random mapping seeds, or model-merging safety. There are only six independent wrapper clusters. Synthetic task shortcuts, low model competence, one random-map realization, pair-local multiplicity correction, and limited intervention/candidate coverage remain material. {supplemental_text} See [ENGINE_AUDIT.md](ENGINE_AUDIT.md) and [DATA_DESIGN_LIMITATIONS.md](DATA_DESIGN_LIMITATIONS.md).\n\nRun `OMP_NUM_THREADS=1 .venv/bin/python scripts/validate_results.py --require-complete` to reproduce this audit. Original measured arrays and metrics are read-only inputs. Missing analysis input-signature sidecars are backfilled only after exact frozen-map replay; existing sidecars must match.\n'''
    (root/'reports/FINAL_VALIDATION.md').write_text(text)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--require-complete',action='store_true');args=parser.parse_args()
    result=validate(require_complete=args.require_complete)
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'missing':result['missing']},indent=2))
    if args.require_complete and result['missing']:sys.exit(2)
