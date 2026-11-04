import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from src.data import generate_dataset, save_dataset
from src.training import train_independent

root = Path(__file__).resolve().parents[1]
os.chdir(root)
torch.set_num_threads(8)
config = json.loads((root / 'configs/pilot.json').read_text())
data_path = root / 'data/pilot-v1'
if (data_path / 'manifest.json').exists():
    if not (data_path / 'train.jsonl').exists():
        raise SystemExit('This is an archived published result tree. Create a fresh reproduction with scripts/new_run.py DESTINATION; raw dataset JSONL is also available in data/pilot-v1.tar.gz.')
    dataset = {s: [json.loads(line) for line in (data_path / f'{s}.jsonl').read_text().splitlines()] for s in ('train','D1','D2','D3','D4')}
    manifest = json.loads((data_path / 'manifest.json').read_text())
else:
    dataset = generate_dataset(config['seed'], config['data_counts'])
    manifest = save_dataset(dataset, data_path)
print(json.dumps(manifest), flush=True)
assert torch.cuda.is_available(), 'GPU unavailable; main run must not silently fall back to CPU'
print(json.dumps(train_independent(config['training'], dataset['train'], root / 'results/pilot-v1/training', 'cuda')), flush=True)
