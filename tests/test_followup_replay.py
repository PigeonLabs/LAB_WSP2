import copy
import json
from pathlib import Path
import numpy as np
import pytest
from scripts.validate_followup_results import (Audit,validate_collection,validate_causal,
    replay_global_bh,sha_file,json_hash,complete_pairs,equal)
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
    (run/'preservation_before.json').write_text(json.dumps({'files':{'old.txt':sha_file(tmp_path/'old.txt'),'README.md':'old hash'}}))
    auditor=Audit(tmp_path);assert auditor.preservation()==1
    auditor.pending=['F6 missing'];assert auditor.result(False)['status']=='PARTIAL';assert auditor.result(True)['exit_code']==1
    (tmp_path/'old.txt').write_text('changed')
    with pytest.raises(ValueError,match='Preserved'):auditor.preservation()


def test_donor_pairs_must_remain_complete(rows):
    assert complete_pairs(rows)==len(rows)//2
    with pytest.raises(ValueError,match='incomplete'):complete_pairs(rows[:-1])
