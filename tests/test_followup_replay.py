import copy
import json
import hashlib
import io
import tarfile
import shutil
from pathlib import Path
import numpy as np
import pytest
from scripts.validate_followup_results import (Audit,validate_collection,validate_causal,
    replay_global_bh,sha_file,json_hash,complete_pairs,equal,portable_bytes,load_portable_followup)
from src.followup_data import generate_dataset
from src.followup_calibration import transform_records
from src.followup_analysis import apply_global_bh


def write_collection(directory,rows):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    n,k=len(rows),2;rng=np.random.default_rng(12);product=rng.normal(size=(n,k))
    arrays={f'{location}_{quantity}':product.copy() if quantity!='contribution_norm' else abs(product)
            for location in ('answer','span') for quantity in ('product','gate','up','contribution_norm')}
    arrays['answer_gate']=np.ones_like(product);arrays['answer_up']=product/(1/(1+np.exp(-1)))
    signs=(product<0).astype(int)
    arrays.update(span_sign_frequencies=np.stack([(signs==i).astype(float) for i in range(5)],axis=-1),span_product_by_sign=np.stack([np.where(signs==i,product,0) for i in range(5)],axis=-1),
        answer_sign_regime=signs,layers=np.zeros(k,int),neuron_ids=np.array([1,2]),
        margins=np.linspace(-1,1,n),answer_token_counts=np.ones((n,2),int),
        row_ids=np.array([r['id'] for r in rows]),groups=np.array([r['group_id'] for r in rows]),concepts=np.array([r['concept'] for r in rows]),labels=np.array([r['label'] for r in rows]),
        prompt_token_lengths=np.ones(n,int)*10,span_token_lengths=np.ones(n,int)*8,answer_positions=np.ones(n,int)*9)
    np.savez_compressed(directory/'measurements.npz',**arrays)
    selection={'0':[1,2]};plan={'split':rows[0]['split'],'records_sha256':json_hash(rows),'selection':selection}
    manifest={'signature':json_hash(plan),'plan':plan,'selection':selection,'n':n,'neurons':k,
              'measurements_sha256':sha_file(directory/'measurements.npz'),
              'competence':{c:{'n':int(sum(arrays['concepts']==c)),'accuracy':float(np.mean(arrays['margins'][arrays['concepts']==c]>0))} for c in set(arrays['concepts'])}}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    return manifest,arrays


@pytest.fixture
def rows():
    ds=generate_dataset(train_size=192,eval_size=192)
    return transform_records(ds['D4'],'default',ds['train'])


def test_collection_replays_without_weights_and_detects_rehashed_axis_error(tmp_path,rows):
    manifest,arrays=write_collection(tmp_path,rows)
    actual=validate_collection(tmp_path,rows)
    assert actual[2]['n']==len(rows)
    arrays['labels'][0]=1-arrays['labels'][0]
    np.savez_compressed(tmp_path/'measurements.npz',**arrays)
    manifest['measurements_sha256']=sha_file(tmp_path/'measurements.npz')
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='labels'):validate_collection(tmp_path,rows)


def causal_fixture(tmp_path,rows):
    _,reference=write_collection(tmp_path/'references',rows)
    n=len(rows);modes=['zero','scale_0','scale_1'];units=[{'id':'u0','kind':'single','units_by_layer':{'0':[1]}}]
    plan={'split':'D4','records_sha256':json_hash(rows),'locations':['answer','span'],'modes':modes,'units':units}
    signature=json_hash(plan);effect=np.zeros((n,1,2,3));effect[:,:,:,0]=.1;effect[:,:,:,1]=.1
    arrays={k:reference[k] for k in ('margins','row_ids','groups','concepts','labels','answer_token_counts')}
    arrays.update(effects=effect,unit_ids=np.array(['u0']),unit_kinds=np.array(['single']),locations=np.array(plan['locations']),modes=np.array(modes))
    np.savez_compressed(tmp_path/'effects.npz',**arrays)
    (tmp_path/'chunks').mkdir()
    for li in range(2):
        for mi in range(3):
            np.savez_compressed(tmp_path/'chunks'/f'unit000_location{li}_mode{mi}.npz',signature=np.asarray(signature),margin_intervened=reference['margins']-effect[:,0,li,mi],seconds=np.asarray(.1))
    manifest={'signature':signature,'plan':plan,'n':n,'num_units':1,'effects_sha256':sha_file(tmp_path/'effects.npz')}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    return manifest,arrays


def test_causal_chunk_replay_identity_and_zero_scale(tmp_path,rows):
    manifest,arrays=causal_fixture(tmp_path,rows)
    validate_causal(tmp_path,rows)
    arrays['effects'][:,:,:,2]=.01
    np.savez_compressed(tmp_path/'effects.npz',**arrays);manifest['effects_sha256']=sha_file(tmp_path/'effects.npz')
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='scale1'):validate_causal(tmp_path,rows)


def test_causal_zero_scale_inconsistency_detected(tmp_path,rows):
    manifest,arrays=causal_fixture(tmp_path,rows)
    arrays['effects'][:,:,:,1]=.2
    np.savez_compressed(tmp_path/'effects.npz',**arrays);manifest['effects_sha256']=sha_file(tmp_path/'effects.npz')
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='zero != scale0'):validate_causal(tmp_path,rows)


def test_global_bh_replays_whole_family_including_unavailable_tests():
    payload=apply_global_bh({'F3/a':{'pvalue':.01},'F4/b':{'pvalue':.03},'F5/c':{'pvalue':None}})
    replay_global_bh(payload)
    payload['tests']['F3/a']['qvalue']=.01
    with pytest.raises(ValueError,match='qvalue'):replay_global_bh(payload)


def test_archive_relative_preservation_and_missing_completion(tmp_path):
    run=tmp_path/'results/followup-v2';run.mkdir(parents=True)
    (tmp_path/'old.txt').write_text('original');(tmp_path/'README.md').write_text('new description')
    (tmp_path/'reports').mkdir();(tmp_path/'reports/pilot-v1-README.md').write_text('old description')
    (run/'preservation_before.json').write_text(json.dumps({'files':{'old.txt':sha_file(tmp_path/'old.txt'),'README.md':sha_file(tmp_path/'reports/pilot-v1-README.md')}}))
    auditor=Audit(tmp_path);assert auditor.preservation()['verified_count']==2
    auditor.pending=['F6 missing'];assert auditor.result(False)['status']=='PARTIAL';assert auditor.result(True)['exit_code']==1
    (tmp_path/'old.txt').write_text('changed')
    with pytest.raises(ValueError,match='Preserved'):auditor.preservation()


def test_donor_pairs_must_remain_complete(rows):
    assert complete_pairs(rows)==len(rows)//2
    with pytest.raises(ValueError,match='incomplete'):complete_pairs(rows[:-1])


def test_archive_causal_fallback_requires_wholly_absent_chunks(tmp_path,rows):
    causal_fixture(tmp_path,rows)
    shutil.rmtree(tmp_path/'chunks')
    # Publication omits all chunks but retains complete hash-bound effects/references.
    validate_causal(tmp_path,rows)
    (tmp_path/'chunks').mkdir()
    with pytest.raises(ValueError,match='Partial chunk directory'):
        validate_causal(tmp_path,rows)


def _tar_members(path,members):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(path,'w:gz') as tar:
        for name,payload in members.items():
            info=tarfile.TarInfo(name);info.size=len(payload);tar.addfile(info,io.BytesIO(payload))


def test_relocated_archive_without_raw_jsonl_weights_pngs(tmp_path):
    from src.followup_data import freeze_dataset
    root=tmp_path/'relocated';root.mkdir()
    ds=generate_dataset(train_size=192,eval_size=192)
    freeze_dataset(ds,root/'data/followup-v2')
    members={str(p.relative_to(root)):p.read_bytes() for p in (root/'data/followup-v2').glob('*.jsonl')}
    _tar_members(root/'data/followup-v2.tar.gz',members)
    for path in (root/'data/followup-v2').glob('*.jsonl'):path.unlink()
    loaded,storage=load_portable_followup(root)
    assert loaded==ds and all(item['storage']=='tar_member' for item in storage)
    legacy=b'{"original":true}\n'
    _tar_members(root/'data/pilot-v1.tar.gz',{'data/pilot-v1/D1.jsonl':legacy})
    (root/'reports').mkdir();(root/'reports/pilot-v1-README.md').write_text('preserved README')
    (root/'README.md').write_text('current README')
    (root/'old-source.py').write_text('original source')
    run=root/'results/followup-v2';run.mkdir(parents=True)
    snapshot={'files':{'README.md':sha_file(root/'reports/pilot-v1-README.md'),
        'old-source.py':sha_file(root/'old-source.py'),
        'data/pilot-v1/D1.jsonl':hashlib.sha256(legacy).hexdigest(),
        'results/pilot-v1/training/seed_11/final.pt':'not-published',
        'artifacts/figures/old.png':'not-published'}}
    (run/'preservation_before.json').write_text(json.dumps(snapshot))
    auditor=Audit(root);coverage=auditor.preservation()
    assert coverage['verified_count']==3 and coverage['optional_omitted_count']==2
    assert any(row['storage']=='tar_member' for row in coverage['verified'])
    assert not list(root.rglob('*.pt')) and not list(root.rglob('*.jsonl')) and not list(root.rglob('*.png'))
    (root/'old-source.py').unlink()
    with pytest.raises(ValueError,match='Unexpected missing'):auditor.preservation()


def test_archived_member_hash_corruption_and_saved_readme_are_not_optional(tmp_path):
    run=tmp_path/'results/followup-v2';run.mkdir(parents=True)
    (tmp_path/'reports').mkdir();(tmp_path/'reports/pilot-v1-README.md').write_text('saved')
    _tar_members(tmp_path/'data/pilot-v1.tar.gz',{'data/pilot-v1/D1.jsonl':b'changed'})
    snapshot={'files':{'README.md':sha_file(tmp_path/'reports/pilot-v1-README.md'),
        'data/pilot-v1/D1.jsonl':hashlib.sha256(b'original').hexdigest()}}
    (run/'preservation_before.json').write_text(json.dumps(snapshot))
    with pytest.raises(ValueError,match='artifact changed'):Audit(tmp_path).preservation()
    (tmp_path/'reports/pilot-v1-README.md').write_text('tampered')
    with pytest.raises(ValueError,match='Saved original README'):Audit(tmp_path).preservation()


def test_hard_stress_replay_from_tar_without_model_weights(tmp_path):
    from src.followup_hard_stress import ROOT,summarize
    from src.followup_calibration import transform_records
    # Synthetic margins in an isolated test fixture, not research outcomes.
    for dataset in ('followup-v2','followup-v2-hard-stress'):
        (tmp_path/'data'/dataset).mkdir(parents=True)
        shutil.copy2(ROOT/'data'/dataset/'manifest.json',tmp_path/'data'/dataset/'manifest.json')
        shutil.copy2(ROOT/'data'/f'{dataset}.tar.gz',tmp_path/'data'/f'{dataset}.tar.gz')
    auditor=Audit(tmp_path);auditor.dataset,_=load_portable_followup(tmp_path)
    raw,_=portable_bytes(tmp_path,'data/followup-v2-hard-stress/hard_stress.jsonl')
    rows=[json.loads(line) for line in raw.decode().splitlines()]
    manifest=json.loads((tmp_path/'data/followup-v2-hard-stress/manifest.json').read_text())
    folder=auditor.run/'hard_stress/seed101/final';folder.mkdir(parents=True)
    lockpath=auditor.run/'calibration/seed101/lock.json';lockpath.parent.mkdir(parents=True);lockpath.write_text(json.dumps({'variant':'default'}))
    margins=np.array([1. if r['label'] else -1. for r in rows])
    np.savez_compressed(folder/'measurements.npz',margins=margins,answer_token_counts=np.ones((len(rows),2),int),row_ids=np.array([r['id'] for r in rows]),groups=np.array([r['group_id'] for r in rows]),labels=np.array([r['label'] for r in rows]),bracket_pairs=np.array([r['bracket_pairs'] for r in rows]),valid_max_stack_depth=np.array([r['valid_max_stack_depth'] for r in rows]))
    summary={'name':'seed101','checkpoint':'final','measurements_sha256':sha_file(folder/'measurements.npz'),
        'metrics':summarize(margins,rows),'lock_sha256':sha_file(lockpath),'data_sha256':manifest['file_sha256'],
        'records_sha256':json_hash(transform_records(rows,'default',auditor.dataset['train']),compact=True),
        'prompt_variant':'default','primary_family_membership':False,'no_retraining_or_primary_refitting':True}
    (folder/'summary.json').write_text(json.dumps(summary))
    auditor.replay_hard_stress()
    assert auditor.hard_stress_coverage['verified_evaluations']==1
    assert auditor.hard_stress_coverage['data_storage']['storage']=='tar_member'
    assert not list(tmp_path.rglob('*.pt')) and not list((tmp_path/'data').rglob('*.jsonl'))
    summary['metrics']['accuracy']=.123
    (folder/'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='statistics replay'):auditor.replay_hard_stress()


def test_vectorized_archive_replay_matches_original_estimand():
    from src.followup_analysis import fit_pair,evaluate_pair,json_ready
    from scripts.validate_followup_results import fast_evaluate_pair
    from tests.test_followup_analysis import fixture
    rows,a=fixture('D2',wrappers=4);a[:,-1]=1
    b=a[:,[2,0,1,5,3,4]]
    fitted=fit_pair(a,b,rows,layers_a=[0,0,0,1,1,1],layers_b=[0,0,0,1,1,1],methods=('activation',),n_random=100,null_permutations=2)
    held,x=fixture('D3',wrappers=4);x[:,-1]=1;y=x[:,[2,0,1,5,3,4]]
    equal(json_ready(fast_evaluate_pair(x,y,held,fitted)),json_ready(evaluate_pair(x,y,held,fitted)),'vectorized independent replay')
