"""Allowlisted reviewable GitHub snapshot, consumed by the connected GitHub publisher.

Weights/caches/venvs/credentials are never included. Raw numerical data are included.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--stage',choices=['E1','E2','E3','E4'],default='E4')
parser.add_argument('--file')
args=parser.parse_args()
if args.file:
    p=root/args.file
    if not p.resolve().is_relative_to(root) or any(x in p.parts for x in ('cache','.venv','.git','.aws','.codex','.agents')):
        raise SystemExit('Path outside publication allowlist')
    print(json.dumps({'path':args.file,'content':base64.b64encode(p.read_bytes()).decode()}))
    raise SystemExit

level=int(args.stage[1])
paths=[root/p for p in ['MASTER.md','README.md','literature_review.md','Makefile','pyproject.toml','.gitignore'] if (root/p).exists()]
for folder in ['src','tests','scripts','configs','reports','artifacts/figures']:
    paths += [p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.md','.json','.svg')]
for p in (root/'results').rglob('*'):
    if not p.is_file() or p.suffix not in ('.json','.jsonl','.csv','.npz','.npy','.parquet','.log'): continue
    rel=p.relative_to(root).parts
    if any(x in ('E1','E2','E3','E4') and int(x[1])>level for x in rel): continue
    if level==1 and any(x in ('qwen','smol','olmo') for x in rel): continue
    if level<4 and 'causal' in rel: continue
    if p.suffix=='.log' and p.name[:2] in ('e1','e2','e3','e4') and int(p.name[1])>level: continue
    paths.append(p)
for d in ('pilot-v1','pilot-v1-cluster-corrected'):
    source=root/'data'/d
    if not source.exists(): continue
    paths.append(source/'manifest.json')
    archive=root/'data'/f'{d}.tar.gz'
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as tar:
        for p in sorted(source.glob('*.jsonl')):
            content=p.read_bytes(); info=tarfile.TarInfo(f'data/{d}/{p.name}')
            info.size=len(content);info.mtime=0;tar.addfile(info,io.BytesIO(content))
    archive.write_bytes(gzip.compress(buffer.getvalue(),mtime=0))
    paths.append(archive)
if (root/'data/natural_reference.json').exists():paths.append(root/'data/natural_reference.json')
text=[];binary=[]
for p in sorted(set(paths)):
    content=p.read_bytes();rel=str(p.relative_to(root))
    item={'path':rel,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
    if p.suffix in ('.npz','.npy','.parquet','.gz'):binary.append(item)
    else:
        item['content']=content.decode();text.append(item)
print(json.dumps({'stage':args.stage,'text':text,'binary':binary}))
