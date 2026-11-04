"""Write the actual run environment; no secret environment values are collected."""
import importlib.metadata
import json
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import torch

root = Path(__file__).resolve().parents[1]
out = root / 'results/pilot-v1/environment.json'
if out.exists():
    raise SystemExit('Environment record exists; preserve it and use a distinct run directory.')
gpu = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
packages = {}
for package in ['torch','transformers','numpy','scipy','pandas','pyarrow','matplotlib','pytest','huggingface-hub']:
    try: packages[package] = importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError: packages[package] = None
result = {
    'timestamp_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
    'python': platform.python_version(), 'platform': platform.platform(),
    'packages': packages, 'cuda': torch.version.cuda,
    'cuda_available': torch.cuda.is_available(),
    'gpu_name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    'gpu_total_bytes': torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None,
    'nvidia_smi': gpu.stdout or gpu.stderr,
    'disk': dict(zip(['total','used','free'],shutil.disk_usage(root))),
    'git_commit_at_start': 'bdd9032145f42b3c02beb5bd524491edac1b666a',
    'environment_note': 'Project venv borrows installed packages read-only via .pth; local scipy/numpy installed. No global package/driver changes.',
    'sandbox_probe': 'nvidia-smi and outbound DNS fail in sandbox; approved execution exposes GPU/network normally.'
}
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
