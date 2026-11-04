"""Fresh independent initialization for the frozen followup-v2 protocol."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch
from src.followup_data import load_dataset
from src.training import train_independent

torch.set_num_threads(8)
if not torch.cuda.is_available():raise RuntimeError('Actual GPU required')
cfg=json.loads((ROOT/'configs/followup_v2.json').read_text())
ds=load_dataset(ROOT/'data/followup-v2')
start=time.monotonic();torch.cuda.reset_peak_memory_stats()
results=train_independent(cfg['training'],ds['train'],ROOT/'results/followup-v2/training')
runtime={'seconds':time.monotonic()-start,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'seeds':[m['seed'] for m in results],'all_planned_steps_completed':all(m['steps']==m['planned_steps'] for m in results)}
path=ROOT/'results/followup-v2/training/runtime.json'
if not path.exists():path.write_text(json.dumps(runtime,indent=2))
print(json.dumps(runtime),flush=True)
