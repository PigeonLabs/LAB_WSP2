"""Sequential GPU pipeline. All raw results are versioned and resumable."""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import hashlib
import itertools
import json
from pathlib import Path
import time
import shutil
import numpy as np
import torch
from .data import generate_dataset, save_dataset
from .experiment import collect_model, collect_causal, analyze_pair, analyze_causal_pair
from .training import load_trained
from .models import model_mlps
from .alignment import weight_similarity

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'results/pilot-v1'
PAIRS = [('seed11','seed29'),('qwen','smol'),('qwen','olmo'),('smol','olmo')]

def dataset():
    cfg=json.loads((ROOT/'configs/pilot.json').read_text())
    ds=generate_dataset(cfg['seed'],cfg['data_counts'])
    # Preserve training-era metadata; the only correction is shared wrapper groups.
    path=ROOT/'data/pilot-v1-cluster-corrected'
    if not (path/'manifest.json').exists(): save_dataset(ds,path)
    return ds

def load(name):
    if name.startswith(('seed','untrained')):
        seed=int(name.removeprefix('seed').removeprefix('untrained'))
        kind='initial' if name.startswith('untrained') else 'final'
        path=RUN/f'training/seed_{seed}/{kind}.pt'
        model,tok=load_trained(path,'cuda')
        info={'id':name,'checkpoint':str(path.relative_to(ROOT)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        models=json.loads((ROOT/'configs/models.json').read_text())['models']
        item=next(x for x in models if {'qwen':'Qwen/','smol':'HuggingFaceTB/','olmo':'allenai/'}[name] in x['model_id'])
        tok=AutoTokenizer.from_pretrained(item['local_path'],local_files_only=True,trust_remote_code=False)
        if tok.pad_token_id is None: tok.pad_token=tok.eos_token
        model=AutoModelForCausalLM.from_pretrained(item['local_path'],local_files_only=True,trust_remote_code=False,dtype=torch.float32).to('cuda').eval()
        info={'id':name,'model_id':item['model_id'],'revision':item['revision'],'license':item['license']}
    return model,tok,info

def collect(name,ds,causal=False):
    out=RUN/('causal' if causal else 'collections')/name
    if (out/'manifest.json').exists():
        print(f'Resume completed {out}',flush=True)
        return
    model,tok,info=load(name)
    torch.cuda.reset_peak_memory_stats()
    start=time.monotonic()
    if causal:
        collect_causal(model,tok,ds,RUN/'collections'/name,out,per_layer=2,per_concept=128,batch_size=16)
    else:
        collect_model(model,tok,ds,out,info,per_layer=16,batch_size=16)
    runtime={'seconds':time.monotonic()-start,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'precision':'float32','model':info}
    (out/'runtime.json').write_text(json.dumps(runtime,indent=2))
    print(json.dumps(runtime),flush=True)
    del model
    torch.cuda.empty_cache()

def e1_weight():
    arrays=[]
    for name in ('seed11','seed29'):
        model,_,_=load(name)
        selection=json.loads((RUN/'collections'/name/'selection.json').read_text())['selection']
        gates=[];ups=[];downs=[]
        mlps=model_mlps(model)
        for layer,neurons in selection.items():
            m=mlps[int(layer)]
            gates.append(m.gate_proj.weight[neurons].detach().cpu().numpy())
            ups.append(m.up_proj.weight[neurons].detach().cpu().numpy())
            downs.append(m.down_proj.weight[:,neurons].detach().cpu().numpy())
        arrays.append((np.concatenate(gates),np.concatenate(ups),np.concatenate(downs,axis=1)))
        del model
        torch.cuda.empty_cache()
    return weight_similarity(*arrays[0],*arrays[1])

def execute(stage):
    torch.set_num_threads(8)
    ds=dataset()
    if stage in ('e1','e2','e4') and not torch.cuda.is_available():
        raise RuntimeError('GPU not accessible: rerun in authorized GPU environment; no silent CPU substitution')
    start=time.monotonic()
    if stage=='e1':
        for name in ('seed11','seed29','untrained11','untrained29'): collect(name,ds)
        analyze_pair(RUN/'collections/seed11',RUN/'collections/seed29',ds,RUN/'E1/trained','seed11_seed29',weight_similarity=e1_weight())
        analyze_pair(RUN/'collections/untrained11',RUN/'collections/untrained29',ds,RUN/'E1/untrained','untrained11_untrained29')
    elif stage=='e2':
        for name in ('qwen','smol','olmo'): collect(name,ds)
        for a,b in PAIRS[1:]: analyze_pair(RUN/'collections'/a,RUN/'collections'/b,ds,RUN/'E2'/f'{a}_{b}',f'{a}_{b}')
    elif stage=='e3':
        for a,b in PAIRS:
            analyze_pair(RUN/'collections'/a,RUN/'collections'/b,ds,RUN/'E3'/f'{a}_{b}',f'{a}_{b}')
    elif stage=='e4':
        for name in ('seed11','seed29','qwen','smol','olmo'): collect(name,ds,causal=True)
        for a,b in PAIRS:
            analyze_causal_pair(RUN/'causal'/a,RUN/'causal'/b,RUN/'collections'/a,RUN/'collections'/b,ds,RUN/'E4'/f'{a}_{b}',f'{a}_{b}')
    else: raise ValueError(stage)
    status_path=RUN/'stage_status.json'
    status=json.loads(status_path.read_text()) if status_path.exists() else {}
    status[stage.upper()]={'status':'MEASURED','seconds':time.monotonic()-start,'not_a_hypothesis_verdict':True}
    status_path.write_text(json.dumps(status,indent=2))
    print(json.dumps(status[stage.upper()]),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['e1','e2','e3','e4','pilot'])
    parser.add_argument('--resume',action='store_true',help='Completed matching artifacts are automatically reused; incompatible ones fail.')
    args=parser.parse_args()
    for stage in (['e1','e2','e3','e4'] if args.stage=='pilot' else [args.stage]): execute(stage)
