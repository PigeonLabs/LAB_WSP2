"""Explicit v3 evidence allowlist for stage-by-stage GitHub Git Data publication.

No credentials, model weights, cache, environment secrets or unrelated files.
Large raw arrays and public API snapshots are in deterministic tar.gz archives.
The active agent publishes this manifest through the connected GitHub API,
using an expected-head lease; standalone execution only creates a manifest.
"""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'followup-v3-gemma-map'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['G1','G6'], required=True)
    args=parser.parse_args()
    candidates={ROOT/'README.md'}
    for directory, pattern in [('src','gemma_v3*.py'),('scripts','*gemma_v3*.py'),
            ('scripts','gemma_v3_reference.cpp'),('tests','test_gemma_v3*.py'),
            ('configs','gemma_v3*.json')]:
        candidates.update((ROOT/directory).glob(pattern))
    for directory in [f'reports/{PREFIX}','reports/v3',f'data/{PREFIX}',f'results/{PREFIX}']:
        candidates.update(p for p in (ROOT/directory).rglob('*') if p.is_file() and
            p.suffix in {'.md','.json','.jsonl','.log','.xml','.gz','.npz'})
    for directory in [f'artifacts/{PREFIX}/figures',f'artifacts/{PREFIX}/patches',f'artifacts/{PREFIX}/code_snapshots']:
        candidates.update(p for p in (ROOT/directory).rglob('*') if p.is_file() and
            p.suffix in {'.png','.svg','.json','.patch','.py'})
    # These are staging aids, not measured results. Raw NPZ is intentionally retained.
    candidates={p for p in candidates if 'report_inputs' not in p.parts and '__pycache__' not in p.parts}
    rows=[]
    for path in sorted(candidates):
        if not path.is_file(): raise ValueError(f'Missing publication input: {path}')
        content=path.read_bytes()
        row=dict(path=str(path.relative_to(ROOT)),bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            git_blob_sha1=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest())
        if len(content)<150000 and path.suffix not in {'.png','.gz','.npz'}:
            row['content']=content.decode('utf-8')
        rows.append(row)
    target=ROOT/f'artifacts/{PREFIX}/publish_{args.stage}.json'
    target.write_text(json.dumps(dict(stage=args.stage,files=rows),ensure_ascii=False)+'\n')
    print(json.dumps(dict(manifest=str(target.relative_to(ROOT)),files=len(rows),bytes=sum(r['bytes'] for r in rows),blob_files=sum('content' not in r for r in rows))))

if __name__=='__main__':main()
