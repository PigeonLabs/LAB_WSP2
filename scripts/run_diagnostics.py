"""Supplementary measurement; uses existing selections and never refits maps."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
from src.runner import ROOT, RUN, load, dataset
from src.diagnostics import collect_diagnostics

torch.set_num_threads(8)
ds=dataset()
for name in ('seed11','seed29','qwen','smol','olmo'):
    model,tokenizer,info=load(name)
    started=time.monotonic()
    out=RUN/'diagnostics'/name
    manifest=collect_diagnostics(model,tokenizer,ds,RUN/'collections'/name,out,ROOT/'data/natural_reference.json',device='cuda')
    print(json.dumps({'model':name,'seconds':time.monotonic()-started,'manifest':manifest},default=str),flush=True)
    del model
    torch.cuda.empty_cache()
