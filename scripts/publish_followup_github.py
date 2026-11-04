"""Standalone stage uploader; the current Codex run uses its GitHub connector.

Without a token, a queue request is explicitly NOT an upload. No credentials
are written to any file, log, report, or published artifact.
"""
import argparse,base64,hashlib,json,os,subprocess,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('stage',choices=[f'F{i}' for i in range(7)]);p.add_argument('--require-upload',action='store_true');a=p.parse_args()
subprocess.run([sys.executable,str(ROOT/'scripts/followup_publish_manifest.py'),'--stage',a.stage],check=True)
snapshot=json.loads((ROOT/'artifacts/followup-v2'/f'publish_{a.stage}.json').read_text())
token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
if not token:
    request={'stage':a.stage,'status':'QUEUED_NOT_UPLOADED','repository':'PigeonLabs/LAB_WSP2','backend':'connected GitHub tools','manifest':f'artifacts/followup-v2/publish_{a.stage}.json'}
    (ROOT/'artifacts/followup-v2'/f'publish_request_{a.stage}.json').write_text(json.dumps(request,indent=2))
    print(json.dumps(request));sys.exit(2 if a.require_upload else 0)
def api(path,body=None,method=None):
    request=urllib.request.Request('https://api.github.com/repos/PigeonLabs/LAB_WSP2'+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'WSP2-followup'},method=method or ('GET' if body is None else 'POST'))
    with urllib.request.urlopen(request,timeout=120) as response:return json.load(response)
head=api('/git/ref/heads/main')['object']['sha'];tree=api('/git/commits/'+head)['tree']['sha']
remote={x['path']:x['sha'] for x in api('/git/trees/'+tree+'?recursive=1')['tree'] if x['type']=='blob'}
entries=[]
for item in snapshot['files']:
    path=ROOT/item['path'];data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=item['sha256']:raise RuntimeError('File changed after publication snapshot')
    sha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if remote.get(item['path'])==sha:continue
    blob=api('/git/blobs',{'encoding':'base64','content':base64.b64encode(data).decode()})
    entries.append({'path':item['path'],'mode':'100644','type':'blob','sha':blob['sha']})
if not entries:print(json.dumps({'status':'UP_TO_DATE','commit':head}));sys.exit()
new_tree=api('/git/trees',{'base_tree':tree,'tree':entries})['sha']
commit=api('/git/commits',{'message':a.stage+': followup measurements and visual reports','tree':new_tree,'parents':[head]})['sha']
if api('/git/ref/heads/main')['object']['sha']!=head:raise RuntimeError('Remote changed concurrently; retry without force')
api('/git/refs/heads/main',{'sha':commit,'force':False},'PATCH')
print(json.dumps({'status':'UPLOADED','stage':a.stage,'commit':commit,'files':len(entries)}))
