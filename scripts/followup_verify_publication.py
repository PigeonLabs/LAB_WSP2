#!/usr/bin/env python3
"""Read-only public GitHub publication audit; network is used only by main().

Compare a final immutable commit with the original pilot commit and an exact
local F6 publication manifest. No credentials are read, printed, or required.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_REPO='PigeonLabs/LAB_WSP2'
ORIGINAL_COMMIT='127db6cdfb75d13b6ce70b4514ef82ed2f044bc0'
PRESERVED_README='reports/pilot-v1-README.md'
SHA1=re.compile(r'^[0-9a-f]{40}$')
SHA256=re.compile(r'^[0-9a-f]{64}$')


def _sha(value,label):
    if not isinstance(value,str) or not SHA1.fullmatch(value):raise ValueError(f'{label} must be an exact lowercase 40-character commit/object SHA, not a branch or URL')
    return value


def _path(value):
    if not isinstance(value,str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Repository paths must be nonempty forward-slash strings')
    path=PurePosixPath(value)
    if path.is_absolute() or any(x in ('','.','..') for x in value.split('/')) or str(path)!=value:
        raise ValueError(f'Ambiguous repository path: {value!r}')
    return value


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError(f'Duplicate JSON key: {key}')
        result[key]=value
    return result


def load_json_bytes(payload):
    return json.loads(payload.decode('utf-8'),object_pairs_hook=_object)


def git_blob_sha1(content):
    return hashlib.sha1(b'blob '+str(len(content)).encode('ascii')+b'\0'+content).hexdigest()


def tree_blobs(payload,expected_sha=None):
    """Validate a complete recursive tree and return only regular-file blobs.

    Structural directory entries are accepted; symlinks, gitlinks, unknown entry
    types/modes, duplicate paths, and truncated trees cannot support this audit.
    """
    if not isinstance(payload,dict) or payload.get('truncated') is not False:
        raise ValueError('A complete recursive GitHub tree with truncated=false is required')
    actual=_sha(payload.get('sha'),'Tree SHA')
    if expected_sha is not None and actual!=_sha(expected_sha,'Expected tree SHA'):raise ValueError('GitHub returned a different tree SHA')
    if not isinstance(payload.get('tree'),list):raise ValueError('Missing recursive tree entries')
    blobs={};seen=set()
    for entry in payload['tree']:
        if not isinstance(entry,dict):raise ValueError('Malformed tree entry')
        path=_path(entry.get('path'))
        if path in seen:raise ValueError(f'Duplicate recursive-tree path: {path}')
        seen.add(path);sha=_sha(entry.get('sha'),'Entry SHA');kind=entry.get('type');mode=entry.get('mode')
        if kind=='tree':
            if mode!='040000':raise ValueError(f'Invalid directory mode for {path}')
            continue
        if kind!='blob' or mode not in ('100644','100755'):
            raise ValueError(f'Non-regular blob or unsupported tree entry at {path}: type={kind}, mode={mode}')
        blobs[path]={'sha':sha,'mode':mode}
    return blobs


def manifest_entries(manifest):
    if not isinstance(manifest,dict) or manifest.get('stage')!='F6':raise ValueError('Final publication requires an unambiguous F6 manifest')
    files=manifest.get('files')
    if not isinstance(files,list) or not files:raise ValueError('Manifest files must be a nonempty list')
    seen=set();entries=[]
    for row in files:
        if not isinstance(row,dict):raise ValueError('Malformed manifest entry')
        path=_path(row.get('path'))
        if path in seen:raise ValueError(f'Duplicate manifest path: {path}')
        seen.add(path)
        if not isinstance(row.get('sha256'),str) or not SHA256.fullmatch(row['sha256']):raise ValueError(f'Invalid SHA256 for {path}')
        if isinstance(row.get('bytes'),bool) or not isinstance(row.get('bytes'),int) or row['bytes']<0:raise ValueError(f'Invalid byte count for {path}')
        if not isinstance(row.get('binary'),bool):raise ValueError(f'Missing binary flag for {path}')
        if 'content' in row:
            if row['binary'] or not isinstance(row['content'],str):raise ValueError(f'Ambiguous embedded content for {path}')
            embedded=row['content'].encode('utf-8')
            if hashlib.sha256(embedded).hexdigest()!=row['sha256'] or len(embedded)!=row['bytes']:raise ValueError(f'Embedded content contradicts manifest checksum for {path}')
        entries.append(row)
    return entries


def verify_snapshot(root,manifest,original_tree,published_tree,*,repository=DEFAULT_REPO,original_commit=ORIGINAL_COMMIT,published_commit):
    """Offline-verifiable core: never makes requests or changes an input file."""
    repository=_repo(repository)
    _sha(original_commit,'Original commit');_sha(published_commit,'Published commit')
    if original_commit==published_commit:raise ValueError('Original and final commits must differ')
    root=Path(root).resolve();old=tree_blobs(original_tree);new=tree_blobs(published_tree);entries=manifest_entries(manifest)
    errors=[];preserved=0;checked=0;verified=0;receipts=[]
    def error(code,path,**details):errors.append({'code':code,'path':path,**details})
    if 'README.md' not in old:raise ValueError('Original commit has no regular root README blob to preserve')
    for path,entry in old.items():
        if path=='README.md':continue
        if path not in new:error('ORIGINAL_BLOB_MISSING',path,expected=entry)
        elif new[path]!=entry:error('ORIGINAL_BLOB_CHANGED',path,expected=entry,actual=new[path])
        else:preserved+=1
    if new.get(PRESERVED_README)!=old['README.md']:
        error('ORIGINAL_README_NOT_PRESERVED',PRESERVED_README,expected=old['README.md'],actual=new.get(PRESERVED_README))
    if 'README.md' not in new:error('CURRENT_README_MISSING','README.md')
    for row in entries:
        path=row['path'];candidate=root/path;checked+=1
        if candidate.is_symlink() or any(p.is_symlink() for p in candidate.parents if p!=root and root in p.parents):
            error('LOCAL_SYMLINK_REFUSED',path);continue
        resolved=candidate.resolve()
        if not resolved.is_relative_to(root):error('LOCAL_PATH_OUTSIDE_ROOT',path);continue
        if not candidate.is_file():error('LOCAL_FILE_MISSING',path);continue
        content=candidate.read_bytes();sha256=hashlib.sha256(content).hexdigest();blob=git_blob_sha1(content)
        local_ok=sha256==row['sha256'] and len(content)==row['bytes']
        if not local_ok:error('LOCAL_SNAPSHOT_MISMATCH',path,expected_sha256=row['sha256'],actual_sha256=sha256,expected_bytes=row['bytes'],actual_bytes=len(content))
        remote=new.get(path)
        if remote is None:error('PUBLISHED_BLOB_MISSING',path)
        elif remote['sha']!=blob:error('PUBLISHED_BLOB_MISMATCH',path,expected_git_blob_sha1=blob,actual_git_blob_sha1=remote['sha'])
        if local_ok and remote is not None and remote['sha']==blob:verified+=1
        receipts.append({'path':path,'sha256':sha256,'git_blob_sha1':blob,'bytes':len(content)})
    return {'status':'PASS' if not errors else 'FAIL','repository':repository,'original_commit':original_commit,'published_commit':published_commit,'original_tree_sha':original_tree['sha'],'published_tree_sha':published_tree['sha'],'manifest_stage':manifest['stage'],'allowed_original_replacements':['README.md'],'original_readme_preservation_path':PRESERVED_README,'counts':{'original_regular_blobs':len(old),'original_blobs_required_unchanged':len(old)-1,'original_blobs_preserved':preserved,'published_regular_blobs':len(new),'manifest_files':len(entries),'local_files_checked':checked,'manifest_files_verified':verified,'errors':len(errors)},'errors':errors,'files':receipts,'scope':'Exact Git blob and local snapshot equality; does not validate scientific interpretation or refit any experiment.'}


def _repo(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value) or any(x in ('.','..') for x in value.split('/')):
        raise ValueError('Repository must be owner/name, not a URL')
    return value


def fetch_json(url,timeout=20):
    """Public, unauthenticated GET only; no environment credentials are inspected."""
    request=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'LAB-WSP2-publication-audit','X-GitHub-Api-Version':'2022-11-28'},method='GET')
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            if response.geturl().split('/')[2]!='api.github.com':raise ValueError('Unexpected API redirect host')
            content=response.read(16*1024*1024+1)
            if len(content)>16*1024*1024:raise ValueError('API response exceeds audit size limit')
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Public GitHub API returned HTTP {exc.code}; no response body or credentials logged') from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Public GitHub API request failed: {type(exc.reason).__name__}') from None
    return load_json_bytes(content)


def fetch_commit_tree(repository,commit,fetch=fetch_json):
    repository=_repo(repository);commit=_sha(commit,'Commit')
    base=f'https://api.github.com/repos/{repository}'
    payload=fetch(f'{base}/commits/{commit}')
    if not isinstance(payload,dict) or payload.get('sha')!=commit:raise ValueError('GitHub did not return the exact requested commit')
    try:tree=_sha(payload['commit']['tree']['sha'],'Commit tree SHA')
    except (KeyError,TypeError):raise ValueError('Commit response has no unambiguous tree SHA') from None
    result=fetch(f'{base}/git/trees/{tree}?recursive=1')
    tree_blobs(result,tree)
    return result


def _write_audit(path,audit):
    path=Path(path);text=json.dumps(audit,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    if path.exists():
        if path.read_text()!=text:raise FileExistsError('Audit output already exists with different content; choose a new output path')
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--manifest',type=Path,default=ROOT/'artifacts/followup-v2/publish_F6.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repo',default=DEFAULT_REPO)
    parser.add_argument('--original-commit',default=ORIGINAL_COMMIT)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args(argv)
    source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    safe_output=False
    audit={'status':'ERROR','repository':args.repo,'original_commit':args.original_commit,'published_commit':args.commit,'source_sha256':source_hash,'errors':[]}
    try:
        repository=_repo(args.repo);_sha(args.commit,'Published commit');_sha(args.original_commit,'Original commit')
        raw=args.manifest.read_bytes();manifest=load_json_bytes(raw);entries=manifest_entries(manifest)
        output=args.output.resolve()
        if output==args.manifest.resolve() or any(output==(args.root/row['path']).resolve() for row in entries):raise ValueError('Audit output must not overwrite the manifest or a published input artifact')
        safe_output=True
        original=fetch_commit_tree(repository,args.original_commit);published=fetch_commit_tree(repository,args.commit)
        audit=verify_snapshot(args.root,manifest,original,published,repository=repository,original_commit=args.original_commit,published_commit=args.commit)
        audit.update(source_sha256=source_hash,manifest_sha256=hashlib.sha256(raw).hexdigest(),manifest_path=str(args.manifest))
    except Exception as exc:
        audit['errors']=[{'code':'AUDIT_REFUSED','exception':type(exc).__name__,'message':str(exc)}]
    if not safe_output:
        print(json.dumps({'status':'ERROR','errors':audit['errors']},ensure_ascii=False));return 2
    try:_write_audit(args.output,audit)
    except (OSError,ValueError) as exc:
        print(json.dumps({'status':'ERROR','exception':type(exc).__name__,'message':str(exc)}));return 2
    print(json.dumps({'status':audit['status'],'counts':audit.get('counts'),'errors':audit['errors'],'output':str(args.output)},ensure_ascii=False))
    return 0 if audit['status']=='PASS' else 1


if __name__=='__main__':sys.exit(main())
