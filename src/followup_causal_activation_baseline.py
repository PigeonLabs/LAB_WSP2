"""Separate POST-HOC activation controls for F4; no primary result is changed.

The original F4 lacked an activation-only causal-agreement baseline. This module
freezes both raw and task-centered activation mappings on the first 12 D2
wrappers, then scores unchanged D4 effects. Some D4 results were already observed
before this supplement was designed: it is not preregistered or confirmatory.
No new p-values/q-values are calculated or added to the global 110-test family.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from .alignment import correlation_matrix,match_neurons
from .followup_analysis import json_ready,evaluate_causal_alignment
from .followup_alignment_runner import PAIRS,load_rows,load_measurements,write_once

VERSION='posthoc-causal-activation-controls-v1'
ROOT=Path(__file__).resolve().parents[1]
CONTROL_NAMES=('activation_raw','activation_task_centered')


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _read(path):return json.loads(Path(path).read_text())
def _data_hash(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def member_mean_activations(reference,units,indices,location):
    """Arithmetic mean of the same fixed group's member activation values."""
    values=np.asarray(reference[location+'_product'],float)
    if values.ndim!=2 or not np.isfinite(values).all():raise ValueError('Finite reference activation matrix required')
    coordinates={(int(l),int(n)):i for i,(l,n) in enumerate(zip(reference['layers'],reference['neuron_ids']))}
    if len(coordinates)!=values.shape[1]:raise ValueError('Duplicate or inconsistent reference neuron coordinates')
    output=[]
    for index in indices:
        unit=units[int(index)];columns=[]
        for layer,neurons in unit['units_by_layer'].items():
            for neuron in neurons:
                key=(int(layer),int(neuron))
                if key not in coordinates:raise ValueError('Frozen unit references an absent D1 candidate')
                columns.append(coordinates[key])
        if not columns or len(columns)!=len(set(columns)):raise ValueError('Empty or duplicated unit members')
        output.append(values[:,columns].mean(1))
    return np.stack(output,axis=1)


def fit_activation_maps(a,b,records,train_wrappers,location_names=('answer','span')):
    """Pure D2-only fit. Array axes are [row,unit,location]; no effects accepted."""
    a,b=np.asarray(a,float),np.asarray(b,float)
    if a.ndim!=3 or b.ndim!=3 or a.shape[0]!=b.shape[0] or a.shape[2]!=b.shape[2] or a.shape[2]!=len(location_names):raise ValueError('Need compatible row/unit/location activation arrays')
    if not len(records) or len(records)!=len(a) or any(r['split']!='D2' for r in records):raise ValueError('Activation fitting accepts D2 records only')
    if not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('Nonfinite activation inputs')
    groups=np.asarray([r['group_id'] for r in records]);concepts=np.asarray([r['concept'] for r in records]);unique=sorted(set(groups))
    if len(unique)<4 or len(unique)%2 or list(train_wrappers)!=unique[:len(unique)//2]:raise ValueError('Must use exactly the first half of sorted D2 wrappers')
    keep=np.isin(groups,train_wrappers);tasks=concepts[keep]
    result={'fit_split':'D2','train_wrappers':list(train_wrappers),'excluded_validation_wrappers':unique[len(unique)//2:],'location_order':list(location_names),'locations':{},'definitions':{'activation_raw':'Pearson on D2 causal-train activations: same raw-correlation fit family as F3.','activation_task_centered':'Subtract each task mean on D2 causal-train only, then Pearson; distinct additional control, not the F3 raw fitting rule.','group':'Mean member-neuron activation before matching; same frozen groups as primary F4.'},'posthoc':True,'no_primary_family_changes':True}
    for li,location in enumerate(location_names):
        aa,bb=a[keep,:,li],b[keep,:,li]
        centered_a,centered_b=aa.copy(),bb.copy()
        means={}
        for task in sorted(set(tasks)):
            mask=tasks==task
            means[task]={'a':aa[mask].mean(0),'b':bb[mask].mean(0),'n':int(mask.sum())}
            centered_a[mask]-=means[task]['a'];centered_b[mask]-=means[task]['b']
        matrices={'activation_raw':correlation_matrix(aa,bb),'activation_task_centered':correlation_matrix(centered_a,centered_b)}
        result['locations'][location]={'mappings':{name:match_neurons(matrix) for name,matrix in matrices.items()},'similarities':matrices,'task_means':means,'train_rows':int(keep.sum()),'constant_unit_counts':{'raw_a':int(np.sum(aa.std(0)<=1e-10)),'raw_b':int(np.sum(bb.std(0)<=1e-10)),'centered_a':int(np.sum(centered_a.std(0)<=1e-10)),'centered_b':int(np.sum(centered_b.std(0)<=1e-10))}}
    return result


def fit_all(run,data,output=None):
    """Freeze all 26 pair/kind files before any evaluation entrypoint can run.

    Reads only D2 references, D2 causal metadata, and preexisting D2 fit files.
    Does not open D4 arrays, D4 JSONL, or any primary eval.json file.
    """
    run=Path(run);output=Path(output) if output else run/'supplemental_causal_activation'
    canonical=load_rows(data,'D2');completed=[]
    source_files={Path(__file__).name:_sha(__file__), 'followup_analysis.py':_sha(Path(__file__).with_name('followup_analysis.py')),'alignment.py':_sha(Path(__file__).with_name('alignment.py'))}
    for pair in PAIRS:
        left,right=pair
        ma,mb=_read(run/'causal'/left/'D2/manifest.json'),_read(run/'causal'/right/'D2/manifest.json')
        mra,ra,rows=load_measurements(run/'causal'/left/'D2/references',canonical)
        mrb,rb,rows_b=load_measurements(run/'causal'/right/'D2/references',canonical)
        if not np.array_equal(ra['row_ids'],rb['row_ids']):raise ValueError('D2 reference rows differ between models')
        wrappers=sorted({r['group_id'] for r in rows})
        if len(wrappers)!=24:raise ValueError('Supplement requires the frozen 24-wrapper benchmark')
        for kind,expected_count in [('single',8),('group',4)]:
            primary_path=run/'causal_alignment'/'_'.join(pair)/kind/'fit.json';primary=_read(primary_path)
            if primary['pair']!=list(pair) or primary['unit_kind']!=kind or primary['train_wrappers']!=wrappers[:12]:raise ValueError('Primary F4 unit/partition identity changed')
            for suffix,metadata,reference_meta in [('a',ma,mra),('b',mb,mrb)]:
                if primary['source']['reference_sha256_'+suffix]!=reference_meta['measurements_sha256']:raise ValueError('D2 references differ from primary F4 source')
                if primary['source']['effects_sha256_'+suffix]!=metadata['effects_sha256']:raise ValueError('D2 causal metadata differs from primary F4 source')
                if primary['source']['unit_ids_'+suffix]!=[u['id'] for u in metadata['plan']['units']]:raise ValueError('Frozen primary unit identities changed')
            ia,ib=primary['unit_indices_a'],primary['unit_indices_b']
            if len(ia)!=expected_count or len(ib)!=expected_count:raise ValueError('Expected original eight single or four grouped units')
            for manifest,indices in [(ma,ia),(mb,ib)]:
                if any(manifest['plan']['units'][i]['kind']!=kind for i in indices):raise ValueError('Frozen unit kind mismatch')
            locations=primary['location_order']
            if locations!=['answer','span'] or primary['modes']!=['zero','mean','patch']:raise ValueError('Primary location/mode scope changed')
            source={'D2_reference_sha256_a':mra['measurements_sha256'],'D2_reference_sha256_b':mrb['measurements_sha256'],'D2_causal_manifest_sha256_a':_sha(run/'causal'/left/'D2/manifest.json'),'D2_causal_manifest_sha256_b':_sha(run/'causal'/right/'D2/manifest.json'),'primary_D2_fit_sha256':_sha(primary_path),'D2_rows_sha256':_data_hash(rows),'code_sha256':source_files}
            path=output/'_'.join(pair)/kind/'fit.json'
            if path.exists():
                fit=_read(path)
                if fit.get('source')!=source:raise ValueError('Supplement fit sources changed; choose a new output directory')
            else:
                a=np.stack([member_mean_activations(ra,ma['plan']['units'],ia,loc) for loc in locations],axis=-1)
                b=np.stack([member_mean_activations(rb,mb['plan']['units'],ib,loc) for loc in locations],axis=-1)
                fit=fit_activation_maps(a,b,rows,primary['train_wrappers'],locations)
                fit.update(version=VERSION,pair=list(pair),unit_kind=kind,unit_indices_a=ia,unit_indices_b=ib,source=source,unit_ids_a=[ma['plan']['units'][i]['id'] for i in ia],unit_ids_b=[mb['plan']['units'][i]['id'] for i in ib])
                write_once(path,fit)
            completed.append({'pair':list(pair),'unit_kind':kind,'path':str(path.relative_to(output)),'sha256':_sha(path)})
    manifest={'version':VERSION,'status':'ALL_SUPPLEMENTAL_D2_MAPS_FROZEN','posthoc_after_some_D4_observed':True,'D4_read_during_fitting':False,'n_fit_files':len(completed),'n_location_control_maps':len(completed)*4,'controls':list(CONTROL_NAMES),'fits':completed,'code_sha256':source_files,'global_primary_test_family_modified':False,'no_new_pvalues_or_qvalues':True}
    if len(completed)!=26:raise ValueError('Must freeze every one of the 26 pair/kind files before evaluation')
    write_once(output/'fit_manifest.json',manifest)
    return manifest


def _frozen_manifest(output):
    manifest=_read(output/'fit_manifest.json')
    if manifest.get('n_fit_files')!=26 or len(manifest.get('fits',[]))!=26 or manifest.get('D4_read_during_fitting') is not False:raise ValueError('Incomplete or ambiguous supplemental freeze')
    expected={(tuple(pair),kind) for pair in PAIRS for kind in ('single','group')}
    actual={(tuple(entry['pair']),entry['unit_kind']) for entry in manifest['fits']}
    if actual!=expected:raise ValueError('Frozen pair/kind coverage mismatch')
    for filename,expected_hash in manifest['code_sha256'].items():
        if _sha(Path(__file__).with_name(filename))!=expected_hash:raise ValueError('Supplement fitting/evaluation implementation changed after freeze')
    for entry in manifest['fits']:
        if _sha(output/entry['path'])!=entry['sha256']:raise ValueError('Supplemental map changed after freeze')
    return manifest


def evaluate_all(run,data,output=None):
    """Evaluate frozen post-hoc controls; no remapping, selection, p-values, or BH."""
    run=Path(run);output=Path(output) if output else run/'supplemental_causal_activation'
    frozen=_frozen_manifest(output)
    # Refuse partial comparison before opening any D4 numerical values.
    for name in sorted({n for pair in PAIRS for n in pair}):
        for suffix in ['manifest.json','effects.npz','references/manifest.json','references/measurements.npz']:
            if not (run/'causal'/name/'D4'/suffix).is_file():raise ValueError(f'All eight D4 collections/references must finish first: {name}/{suffix}')
    for entry in frozen['fits']:
        if not (run/'causal_alignment'/'_'.join(entry['pair'])/entry['unit_kind']/'eval.json').is_file():raise ValueError('All primary F4 evaluations must exist before descriptive comparison')
    canonical=load_rows(data,'D4');completed=[]
    for entry in frozen['fits']:
        pair=entry['pair'];left,right=pair;kind=entry['unit_kind'];fit=_read(output/entry['path'])
        primary_dir=run/'causal_alignment'/'_'.join(pair)/kind;primary=_read(primary_dir/'fit.json');old_eval=_read(primary_dir/'eval.json')
        if _sha(primary_dir/'fit.json')!=fit['source']['primary_D2_fit_sha256']:raise ValueError('Original primary fit changed')
        ma,a,rows=load_measurements(run/'causal'/left/'D4',canonical,causal=True)
        mb,b,_=load_measurements(run/'causal'/right/'D4',canonical,causal=True)
        if not np.array_equal(a['row_ids'],b['row_ids']):raise ValueError('D4 model row mismatch')
        for arrays,key in [(a,'a'),(b,'b')]:
            if arrays['unit_ids'].tolist()!=primary['source']['unit_ids_'+key] or arrays['locations'].tolist()!=primary['source']['locations'] or arrays['modes'].tolist()!=primary['source']['modes']:raise ValueError('D4 units/locations/modes differ from original D2 freeze')
        source={'supplement_fit_sha256':entry['sha256'],'primary_eval_sha256':_sha(primary_dir/'eval.json'),'D4_effects_sha256_a':ma['effects_sha256'],'D4_effects_sha256_b':mb['effects_sha256'],'freeze_manifest_sha256':_sha(output/'fit_manifest.json')}
        target=output/entry['path'];target=target.with_name('eval.json')
        if target.exists():
            result=_read(target)
            if result['source']!=source:raise ValueError('Existing descriptive evaluation sources changed')
        else:
            combined=copy.deepcopy(primary)
            for location in fit['location_order']:
                for name in CONTROL_NAMES:combined['locations'][location]['mappings'][name]=fit['locations'][location]['mappings'][name]
            ia,ib=fit['unit_indices_a'],fit['unit_indices_b'];core=primary['source']['primary_mode_indices']
            result=evaluate_causal_alignment(a['effects'][:,ia][...,core],b['effects'][:,ib][...,core],rows,combined)
            differences={}
            for location,measured in result['locations'].items():
                for name in ['semantic','causal','combined','random']:
                    if measured['wrapper_scores'][name]!=old_eval['locations'][location]['wrapper_scores'][name]:raise ValueError('Original primary wrapper scores failed exact replay')
                differences[location]={}
                for control in CONTROL_NAMES:
                    differences[location][control]={}
                    for baseline in ['semantic','combined','random']:
                        left_scores=measured['wrapper_scores'][control];right_scores=measured['wrapper_scores'][baseline]
                        delta={g:left_scores[g]-right_scores[g] if left_scores[g] is not None and right_scores[g] is not None else None for g in left_scores}
                        finite=[v for v in delta.values() if v is not None]
                        differences[location][control][baseline]={'mean_difference':float(np.mean(finite)) if finite else None,'wrapper_differences':delta,'n_valid_wrappers':len(finite),'descriptive_only':True}
            result.update(version=VERSION,posthoc=True,source=source,pair=pair,unit_kind=kind,descriptive_differences=differences,primary_family_modified=False,no_new_pvalues_or_qvalues=True,interpretation='Additional missing-baseline check after some D4 outcomes were observed; no causal-conservation success claim or retrospective preregistration.')
            write_once(target,result)
        completed.append({'pair':pair,'unit_kind':kind,'path':str(target.relative_to(output)),'sha256':_sha(target),'descriptive':{loc:v['descriptive'] for loc,v in result['locations'].items()}})
    summary={'version':VERSION,'status':'POSTHOC_BASELINE_CHECK_EVALUATED','posthoc':True,'n_evaluations':len(completed),'evaluations':completed,'fit_manifest_sha256':_sha(output/'fit_manifest.json'),'global_primary_test_family_modified':False,'no_new_pvalues_or_qvalues':True}
    write_once(output/'summary.json',summary)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['fit','evaluate']);parser.add_argument('--run',type=Path,default=ROOT/'results/followup-v2');parser.add_argument('--data',type=Path,default=ROOT/'data/followup-v2');parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv);result=fit_all(args.run,args.data,args.output) if args.stage=='fit' else evaluate_all(args.run,args.data,args.output)
    print(json.dumps({'status':result['status'],'files':result.get('n_fit_files',result.get('n_evaluations')),'posthoc':True,'primary_family_modified':False}))

if __name__=='__main__':main()
