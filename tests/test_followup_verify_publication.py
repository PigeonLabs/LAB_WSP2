"""Offline publication audit tests; no test calls a live network endpoint."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from scripts.followup_verify_publication import (ORIGINAL_COMMIT,PRESERVED_README,
    git_blob_sha1,tree_blobs,verify_snapshot,fetch_commit_tree,manifest_entries)

NEW_COMMIT='2'*40


def tree(files,sha):
    return {'sha':sha,'truncated':False,'tree':[{'path':path,'type':'blob','mode':'100644','sha':git_blob_sha1(content)} for path,content in files.items()]}


@pytest.fixture
def snapshot(tmp_path):
    original={'README.md':b'original readme\n','results/pilot-v1/value.json':b'{"value":1}\n'}
    published={**original,'README.md':b'final readme\n',PRESERVED_README:original['README.md'],'results/followup-v2/final.json':b'{"value":2}\n'}
    files=[]
    for path in ['README.md',PRESERVED_README,'results/followup-v2/final.json']:
        content=published[path];destination=tmp_path/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(content)
        files.append({'path':path,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'binary':False,'content':content.decode()})
    return tmp_path,{'stage':'F6','files':files},tree(original,'a'*40),tree(published,'b'*40)


def verify(fixture):
    root,manifest,old,new=fixture
    return verify_snapshot(root,manifest,old,new,published_commit=NEW_COMMIT)


def test_valid_snapshot_preserves_original_and_matches_all_manifest_blobs(snapshot):
    result=verify(snapshot)
    assert result['status']=='PASS'
    assert result['counts']['original_blobs_preserved']==1
    assert result['counts']['manifest_files_verified']==3
    assert result['allowed_original_replacements']==['README.md']


def test_changed_original_file_is_rejected(snapshot):
    snapshot[3]['tree'][1]['sha']='c'*40
    result=verify(snapshot)
    assert result['status']=='FAIL'
    assert any(e['code']=='ORIGINAL_BLOB_CHANGED' for e in result['errors'])


def test_missing_new_manifest_file_is_rejected(snapshot):
    snapshot[3]['tree']=[e for e in snapshot[3]['tree'] if e['path']!='results/followup-v2/final.json']
    result=verify(snapshot)
    assert any(e['code']=='PUBLISHED_BLOB_MISSING' for e in result['errors'])


def test_preserved_readme_must_be_exact_original_blob(snapshot):
    next(e for e in snapshot[3]['tree'] if e['path']==PRESERVED_README)['sha']='d'*40
    result=verify(snapshot)
    assert any(e['code']=='ORIGINAL_README_NOT_PRESERVED' for e in result['errors'])


def test_local_manifest_snapshot_change_is_rejected(snapshot):
    (snapshot[0]/'README.md').write_bytes(b'changed after snapshot\n')
    result=verify(snapshot)
    assert any(e['code']=='LOCAL_SNAPSHOT_MISMATCH' for e in result['errors'])
    assert any(e['code']=='PUBLISHED_BLOB_MISMATCH' for e in result['errors'])


@pytest.mark.parametrize('mutation',[lambda t:t.update(truncated=True),
    lambda t:t['tree'].append(copy.deepcopy(t['tree'][0])),
    lambda t:t['tree'][0].update(type='commit',mode='160000'),
    lambda t:t['tree'][0].update(mode='120000')])
def test_ambiguous_truncated_or_nonregular_tree_is_refused(snapshot,mutation):
    mutation(snapshot[3])
    with pytest.raises(ValueError):verify(snapshot)


def test_commit_lookup_uses_exact_sha_and_recursive_tree_offline(snapshot):
    calls=[];published=snapshot[3]
    def fake(url):
        calls.append(url)
        if '/commits/' in url:return {'sha':NEW_COMMIT,'commit':{'tree':{'sha':published['sha']}}}
        return published
    assert fetch_commit_tree('PigeonLabs/LAB_WSP2',NEW_COMMIT,fetch=fake)==published
    assert calls==[f'https://api.github.com/repos/PigeonLabs/LAB_WSP2/commits/{NEW_COMMIT}',f'https://api.github.com/repos/PigeonLabs/LAB_WSP2/git/trees/{published["sha"]}?recursive=1']
    with pytest.raises(ValueError,match='exact lowercase'):fetch_commit_tree('PigeonLabs/LAB_WSP2','main',fetch=fake)


def test_duplicate_or_traversal_manifest_paths_are_refused(snapshot):
    manifest=copy.deepcopy(snapshot[1]);manifest['files'].append(copy.deepcopy(manifest['files'][0]))
    with pytest.raises(ValueError,match='Duplicate manifest'):manifest_entries(manifest)
    manifest=copy.deepcopy(snapshot[1]);manifest['files'][0]['path']='../README.md'
    with pytest.raises(ValueError,match='Ambiguous'):manifest_entries(manifest)


def test_import_has_no_network_side_effect(monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k:pytest.fail('Import must not access network'))
    path=Path(__file__).parents[1]/'scripts/followup_verify_publication.py'
    spec=importlib.util.spec_from_file_location('isolated_publication_checker',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.ORIGINAL_COMMIT==ORIGINAL_COMMIT
