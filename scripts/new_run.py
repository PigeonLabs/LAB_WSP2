"""Create a clean reproduction workspace without overwriting archived evidence."""
import argparse
from pathlib import Path
import shutil

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('destination',type=Path)
args=parser.parse_args()
dest=args.destination.resolve()
if dest.exists():raise SystemExit('Destination exists; choose a new empty run directory.')
dest.mkdir(parents=True)
for folder in ('src','tests','scripts','configs'):
    shutil.copytree(root/folder,dest/folder,ignore=shutil.ignore_patterns('__pycache__','verdicts.json'))
for name in ('MASTER.md','literature_review.md','Makefile','pyproject.toml','.gitignore'):
    shutil.copy2(root/name,dest/name)
(dest/'results').mkdir()
print(f'Fresh workspace created: {dest}')
print('Create a venv here, install this package, then run make pilot. Archived measurements and model weights are intentionally not copied.')
