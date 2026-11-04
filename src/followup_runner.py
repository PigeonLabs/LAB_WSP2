"""Serial, versioned followup measurements; never modifies pilot-v1 outputs."""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import torch
from .followup_data import load_dataset
from .followup_engine import collect, collect_causal, capture_views, load_collection
from .followup_analysis import json_ready

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'results/followup-v2'
SEEDS=[101,211,307,401,503]
NAMES=[f'seed{s}' for s in SEEDS]+['qwen','smol','olmo']

def write_once(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(json_ready(obj),indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    if path.exists():
        if path.read_text()!=text:raise ValueError(f'Refusing divergent existing evidence: {path}')
    else:path.write_text(text)

def prepared(ds,name,split):
    from .followup_calibration_runner import transform_for_model
    return transform_for_model(ds[split],name,ds['train'],RUN)

def model_load(name,checkpoint='final'):
    from .followup_calibration_runner import load_followup_model
    return load_followup_model(name,checkpoint=checkpoint,device='cuda')

def selection_for(name):
    p=RUN/'collections'/name/'final/D1/selection.json'
    return {int(k):v for k,v in json.loads(p.read_text())['selection'].items()}

def release(model):
    model.cpu();del model;torch.cuda.empty_cache()

def collections(stage,ds,names=None):
    names=NAMES if names is None else names
    for name in names:
        checkpoints=['final'] if stage=='discover' or not name.startswith('seed') else ['final','initial','middle']
        for checkpoint in checkpoints:
            model,tok,info=model_load(name,checkpoint)
            torch.cuda.reset_peak_memory_stats();start=time.monotonic()
            splits=['D1','D2'] if stage=='discover' else ['D3']
            for split in splits:
                chosen=None if split=='D1' else selection_for(name)
                rows=prepared(ds,name,split)
                out=RUN/'collections'/name/checkpoint/split
                m=collect(model,tok,rows,out,info,selection=chosen,per_layer=8,batch_size=16)
                print(json.dumps({'model':name,'checkpoint':checkpoint,'split':split,'n':m['n'],'seconds':m['elapsed_seconds']}),flush=True)
            p=RUN/'runtime'/f'{stage}_{name}_{checkpoint}.json'
            if not p.exists():write_once(p,{'seconds':time.monotonic()-start,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'model_info':info})
            release(model)

def positive(ds):
    from .followup_interventions import permute_swiglu_model,verify_permutation_control,group_hooks
    from .alignment import correlation_matrix,match_neurons
    from .experiment import _input,_shared_answer_prefix
    from .models import model_mlps
    out=RUN/'positive_control';out.mkdir(exist_ok=True)
    if (out/'summary.json').exists():return
    started=time.monotonic();torch.cuda.reset_peak_memory_stats()
    name='seed101';model,tok,info=model_load(name);clone,mapping=permute_swiglu_model(model,seed=907)
    chosen=selection_for(name);lookup={(r['source_layer'],r['source_neuron']):r['target_neuron'] for r in mapping}
    perm_selected={l:[lookup[l,n] for n in ns] for l,ns in chosen.items()}
    rows=prepared(ds,name,'D1');a=capture_views(model,tok,rows,chosen);b=capture_views(clone,tok,rows,perm_selected)
    results={};rng=np.random.default_rng(907)
    for location in ('answer','span'):
        x,y=a[location+'_product'],b[location+'_product'];score=correlation_matrix(x,y)
        match=match_neurons(score);correct=float(np.mean(match['source']==match['target']))
        random=[float(np.mean(np.diag(score[:,rng.permutation(len(score))]))) for _ in range(100)]
        results[location]={'recovered_fraction':correct,'matched_correlation':float(np.mean(score[match['source'],match['target']])),'random_mean':float(np.mean(random)),'random_sd':float(np.std(random,ddof=1)),'max_abs_product_difference':float(np.max(np.abs(x-y)))}
    # Explicit masks on actual padded examples exercise both intervention positions.
    sample=rows[:16];seqs=[tok.encode(r['prompt'])+_shared_answer_prefix(tok,r) for r in sample]
    kwargs,positions=_input(model,tok,seqs,'cuda');ids=kwargs['input_ids']
    units={l:ns[:4] for l,ns in chosen.items()}
    checks={'answer':verify_permutation_control(model,clone,mapping,ids,units,positions,atol=5e-5,rtol=1e-4)}
    mask=torch.zeros_like(ids,dtype=torch.bool)
    for i,r in enumerate(sample):mask[i,r['span'][0]:r['span'][1]]=True
    checks['span']=verify_permutation_control(model,clone,mapping,ids,units,mask,atol=5e-5,rtol=1e-4)
    negatives={}
    with torch.inference_mode():
        for location,pos in [('answer',positions),('span',mask)]:
            with group_hooks(model,units,pos,'zero'):left=model(ids).logits
            with group_hooks(clone,units,pos,'zero'):wrong=clone(ids).logits
            negatives[location]={'wrong_identity_mapping_max_abs_logit_difference':float((left-wrong).abs().max()),'equal_at_positive_control_tolerance':bool(torch.allclose(left,wrong,atol=5e-5,rtol=1e-4))}
    np.savez_compressed(out/'activations.npz',**{f'{which}_{location}':obj[location+'_product'] for which,obj in [('original',a),('permuted',b)] for location in ('answer','span')})
    write_once(out/'mapping.json',mapping)
    write_once(out/'summary.json',{'model_info':info,'n':len(rows),'candidates':len(a['layers']),'alignment':results,'intervention_checks':checks,'negative_checks':negatives,'passed':all(v['passed'] for v in checks.values()) and all(v['recovered_fraction']==1 for v in results.values()) and not any(v['equal_at_positive_control_tolerance'] for v in negatives.values()),'scope':'constructed within-model permutation symmetry; not independently learned conservation','random_replicates':100,'elapsed_seconds':time.monotonic()-started,'peak_allocated_bytes':torch.cuda.max_memory_allocated()})
    release(clone);release(model)

def causal(stage,ds,names=None):
    names=NAMES if names is None else names
    split='D2' if stage=='causal-fit' else 'D4'
    for name in names:
        model,tok,info=model_load(name);start=time.monotonic();torch.cuda.reset_peak_memory_stats()
        out=RUN/'causal'/name/split
        batch_size=16 if name.startswith('seed') else 64
        collect_causal(model,tok,prepared(ds,name,split),RUN/'collections'/name/'final/D1',out,info,pairs_per_task_wrapper=4,batch_size=batch_size,max_seconds=7200)
        p=RUN/'runtime'/f'{stage}_{name}.json'
        if not p.exists():write_once(p,{'seconds':time.monotonic()-start,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'model_info':info,'inference_batch_size':batch_size})
        release(model)

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['discover','heldout','positive','causal-fit','causal-test']);p.add_argument('--models',nargs='+',choices=NAMES,default=NAMES);args=p.parse_args()
    torch.set_num_threads(8)
    if not torch.cuda.is_available():raise RuntimeError('GPU required; no silent CPU substitution')
    ds=load_dataset(ROOT/'data/followup-v2')
    if args.stage in ('discover','heldout'):collections(args.stage,ds,args.models)
    elif args.stage=='positive':positive(ds)
    else:causal(args.stage,ds,args.models)

if __name__=='__main__':main()
