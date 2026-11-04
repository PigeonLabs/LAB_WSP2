"""Allowlisted immutable-stage publication for followup-v2; no weights or cache."""
import argparse, base64, gzip, hashlib, io, json, tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--stage',required=True);args=p.parse_args()
paths=[ROOT/'README.md',ROOT/'reports/pilot-v1-README.md',ROOT/'configs/followup_v2.json']
for folder in ('src','scripts','tests','configs'):
    paths += list((ROOT/folder).glob('*followup*'))
for folder in ('results/followup-v2','reports/followup-v2','artifacts/followup-v2/figures'):
    paths += [x for x in (ROOT/folder).rglob('*') if x.is_file() and 'chunks' not in x.parts and x.suffix in ('.py','.json','.jsonl','.md','.csv','.npz','.npy','.parquet','.svg','.png','.log')]
for data_name in ('followup-v2','followup-v2-hard-stress'):
 data=ROOT/'data'/data_name
 if data.exists():
    paths += list(data.glob('*.json'))
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w') as tar:
        for f in sorted(data.glob('*.jsonl')):
            b=f.read_bytes();info=tarfile.TarInfo(str(f.relative_to(ROOT)));info.size=len(b);info.mtime=0;tar.addfile(info,io.BytesIO(b))
    archive=ROOT/'data'/f'{data_name}.tar.gz';archive.write_bytes(gzip.compress(buf.getvalue(),mtime=0));paths.append(archive)
files=[]
for f in sorted(set(paths)):
    if not f.is_file():continue
    relative=f.relative_to(ROOT)
    if relative.parts[:2]==('results','followup-v2'):
        level=int(args.stage[1:]);parts=relative.parts[2:]
        required={'training':1,'training.log':1,'calibration':1,'calibration.log':1,'collections':2,'positive_control':2,'discover.log':2,'positive.log':2,'alignment':3,'heldout.log':3,'alignment_fit.log':3,'alignment_evaluate.log':3,'causal':4,'causal_alignment':4,'causal-fit.log':4,'causal-test.log':4,'causal_alignment_fit.log':4,'causal_alignment_evaluate.log':4,'transfers':5,'transfers.log':5,'statistics':6,'final_audit.json':6}
        if parts and required.get(parts[0],0)>level:continue
        if parts and parts[0]=='stages' and int(f.stem[1:])>level:continue
        if parts and parts[0]=='runtime':
            runtime_level=4 if f.name.startswith('causal-') else 3 if f.name.startswith('heldout_') else 2
            if runtime_level>level:continue
    b=f.read_bytes();rel=str(f.relative_to(ROOT));binary=f.suffix in ('.npz','.npy','.parquet','.png','.gz')
    row={'path':rel,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'binary':binary}
    if not binary and len(b)<150000:row['content']=b.decode()
    files.append(row)
result={'stage':args.stage,'files':files}
dest=ROOT/'artifacts/followup-v2'/('publish_'+args.stage+'.json');dest.write_text(json.dumps(result))
print(json.dumps({'manifest':str(dest),'bytes':dest.stat().st_size,'files':len(files)}))
