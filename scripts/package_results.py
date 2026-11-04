"""Materialize MASTER-named outputs from immutable measured source artifacts."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from src.runner import ROOT, RUN, dataset
from src.alignment import semantic_fingerprint

out=RUN/'deliverables'
out.mkdir(exist_ok=True)
def write_parquet(frame,path):
    if not path.exists(): frame.to_parquet(path,index=False)
def combine(paths):
    return pd.concat([pd.read_parquet(p).assign(model=p.parent.name) for p in paths],ignore_index=True)

collections=RUN/'collections'
paths=[collections/n/'neuron_profiles.parquet' for n in ('seed11','seed29')]
if all(p.exists() for p in paths):write_parquet(combine(paths),out/'E1_neuron_profiles.parquet')
for stage,csvname in [('E1','matches.csv'),('E3','matches.csv'),('E4','alignment_results.csv')]:
    files=sorted((RUN/stage).glob('*/'+csvname))
    if files:
        frame=pd.concat([pd.read_csv(p).assign(pair=p.parent.name) for p in files],ignore_index=True)
        name={'E1':'E1_matches.csv','E3':'E3_alignment_comparison.csv','E4':'E4_alignment_results.csv'}[stage]
        if not (out/name).exists():frame.to_csv(out/name,index=False)
    metrics={p.parent.name:json.loads(p.read_text()) for p in sorted((RUN/stage).glob('*/metrics.json'))}
    if metrics and not (out/f'{stage}_metrics.json').exists():(out/f'{stage}_metrics.json').write_text(json.dumps(metrics,indent=2))

ds=dataset();profile=[]
for name in ('seed11','seed29','qwen','smol','olmo'):
    p=collections/name/'D2.npz'
    if not p.exists():continue
    a=np.load(p)
    f=semantic_fingerprint(a['product'],ds['D2'])
    sign=semantic_fingerprint(a['product'],ds['D2'],a['sign_regime'])
    for j,(layer,neuron) in enumerate(zip(a['layers'],a['neuron_ids'])):
        profile.append({'model':name,'layer':int(layer),'neuron':int(neuron),'fingerprint':f[j].tolist(),'sign_fingerprint':sign[j].tolist(),'primary_function':'UNKNOWN','scope':'D2 truth-contrast proxy; unique main function not established'})
if profile:write_parquet(pd.DataFrame(profile),out/'E3_semantic_profiles.parquet')
paths=sorted((RUN/'causal').glob('*/causal_effects.parquet'))
if len(paths)==5:write_parquet(combine(paths),out/'E4_causal_effects.parquet')
index={str(p.relative_to(ROOT)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file() and p.name!='manifest.json'}
(out/'manifest.json').write_text(json.dumps({'source':'Derived copies only; original collection and pair files remain authoritative','files':index},indent=2))
print(json.dumps({'outputs':len(index),'bytes':sum(x['bytes'] for x in index.values())}))
