"""Publish a completed stage using GitHub credentials, or queue the Codex connector.

Current-session uploads use the connected GitHub tool. Standalone runs can use
GH_TOKEN/GITHUB_TOKEN without storing credentials in this project.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('stage',choices=['E1','E2','E3','E4'])
parser.add_argument('--require-upload',action='store_true')
args=parser.parse_args()
token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
repo='PigeonLabs/LAB_WSP2'
if not token:
    request={'stage':args.stage,'repository':repo,'status':'QUEUED_NOT_UPLOADED','backend':'Codex connected GitHub tools','instruction':'Consume scripts/publish_manifest.py snapshot, commit and update main with expected head.'}
    dest=root/'artifacts'/f'publish_request_{args.stage}.json'
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(request,indent=2))
    print(json.dumps(request))
    sys.exit(2 if args.require_upload else 0)

def api(path,body=None,method=None):
    request=urllib.request.Request('https://api.github.com/repos/'+repo+path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'neuron-conservation-pilot'},
        method=method or ('GET' if body is None else 'POST'))
    with urllib.request.urlopen(request,timeout=120) as response:return json.load(response)

snapshot=json.loads(subprocess.check_output([sys.executable,str(root/'scripts/publish_manifest.py'),'--stage',args.stage],cwd=root))
head=api('/git/ref/heads/main')['object']['sha']
base_tree=api('/git/commits/'+head)['tree']['sha']
remote={x['path']:x['sha'] for x in api('/git/trees/'+base_tree+'?recursive=1')['tree'] if x['type']=='blob'}
entries=[]
for item in snapshot['text']+snapshot['binary']:
    content=(root/item['path']).read_bytes()
    gitsha=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
    if remote.get(item['path'])==gitsha:continue
    blob=api('/git/blobs',{'encoding':'base64','content':base64.b64encode(content).decode()})
    entries.append({'path':item['path'],'mode':'100644','type':'blob','sha':blob['sha']})
if not entries:
    print(json.dumps({'status':'UP_TO_DATE','commit':head}));sys.exit()
tree=api('/git/trees',{'base_tree':base_tree,'tree':entries})
commit=api('/git/commits',{'message':args.stage+': measured results and generated visual reports','tree':tree['sha'],'parents':[head]})
if api('/git/ref/heads/main')['object']['sha']!=head:
    raise SystemExit('Remote changed concurrently; refusing to overwrite. Retry from fresh remote head.')
api('/git/refs/heads/main',{'sha':commit['sha'],'force':False},'PATCH')
print(json.dumps({'status':'UPLOADED','stage':args.stage,'commit':commit['sha'],'files':len(entries)}))
