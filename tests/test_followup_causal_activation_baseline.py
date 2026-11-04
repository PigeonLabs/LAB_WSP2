"""Offline synthetic checks for the separate post-hoc F4 activation baseline."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from src.followup_analysis import json_ready
from src.followup_causal_activation_baseline import (fit_activation_maps,member_mean_activations,
    fit_all,PAIRS,CONTROL_NAMES)


def records(n_wrappers=24):
    return [{'id':f'D2:{g}:{task}:{j}', 'split':'D2','group_id':f'D2:wrapper:t{g:02d}',
             'concept':task,'label':j%2,'semantic':{}} for g in range(n_wrappers)
             for task in ['arithmetic','comparison','negation','syntax'] for j in range(8)]


def test_known_permutation_and_validation_rows_never_affect_either_map():
    rows=records();rng=np.random.default_rng(21);a=rng.normal(size=(len(rows),4,2));permutation=[2,0,3,1];b=a[:,permutation].copy()
    train=[f'D2:wrapper:t{i:02d}' for i in range(12)]
    first=fit_activation_maps(a,b,rows,train)
    for location in first['locations'].values():
        for name in CONTROL_NAMES:
            mapping=location['mappings'][name]
            assert mapping['target'].tolist()==np.argsort(permutation).tolist()
    half=np.array([r['group_id'] not in train for r in rows]);aa=a.copy();bb=b.copy()
    aa[half]=rng.normal(1000,100,size=aa[half].shape);bb[half]=rng.normal(-900,100,size=bb[half].shape)
    second=fit_activation_maps(aa,bb,rows,train)
    assert json_ready(first)==json_ready(second)


def test_task_centering_uses_only_train_task_means():
    rows=records();rng=np.random.default_rng(4);a=rng.normal(size=(len(rows),3,2));b=a.copy()
    tasks=np.array([r['concept'] for r in rows])
    for i,task in enumerate(sorted(set(tasks))):
        a[tasks==task]+=100*i;b[tasks==task]-=80*i
    fitted=fit_activation_maps(a,b,rows,[f'D2:wrapper:t{i:02d}' for i in range(12)])
    for location in fitted['locations'].values():
        np.testing.assert_allclose(np.diag(location['similarities']['activation_task_centered']),1.,atol=1e-12)
        assert np.mean(np.diag(location['similarities']['activation_raw']))<-.99


def test_fitting_rejects_heldout_or_wrong_wrapper_partition():
    rows=records();a=np.ones((len(rows),2,2))
    with pytest.raises(ValueError,match='D2 records only'):
        fit_activation_maps(a,a,[dict(r,split='D4') for r in rows],[f'D2:wrapper:t{i:02d}' for i in range(12)])
    with pytest.raises(ValueError,match='first half'):
        fit_activation_maps(a,a,rows,[f'D2:wrapper:t{i:02d}' for i in range(12,24)])


def test_group_activation_is_mean_of_frozen_member_columns():
    reference={'layers':np.array([1,1,2]),'neuron_ids':np.array([3,7,5]),'answer_product':np.array([[2.,4.,9.],[6.,8.,1.]])}
    units=[{'units_by_layer':{'1':[3,7]}},{'units_by_layer':{'2':[5]}}]
    np.testing.assert_array_equal(member_mean_activations(reference,units,[0,1],'answer'),[[3.,9.],[7.,1.]])
    with pytest.raises(ValueError,match='absent D1'):
        member_mean_activations(reference,[{'units_by_layer':{'1':[99]}}],[0],'answer')


def _save_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


def test_all26_maps_freeze_without_opening_d4_or_mutating_primary(tmp_path,monkeypatch):
    run=tmp_path/'run';data=tmp_path/'data';data.mkdir();rows=records()
    (data/'D2.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    units=[]
    for layer in range(4):
        for n in [3,7]:units.append({'id':f'L{layer}N{n}','kind':'single','units_by_layer':{str(layer):[n]}})
        units.append({'id':f'L{layer}group','kind':'group','units_by_layer':{str(layer):[2,3,6,7]}})
    rng=np.random.default_rng(44);reference_hashes={}
    for name in sorted({n for pair in PAIRS for n in pair}):
        folder=run/'causal'/name/'D2';reference=folder/'references';reference.mkdir(parents=True)
        _save_json(folder/'manifest.json',{'plan':{'units':units},'effects_sha256':'0'*64})
        p=reference/'measurements.npz'
        np.savez_compressed(p,answer_product=rng.normal(size=(len(rows),32)),span_product=rng.normal(size=(len(rows),32)),layers=np.repeat(np.arange(4),8),neuron_ids=np.tile(np.arange(8),4),row_ids=np.array([r['id'] for r in rows]),groups=np.array([r['group_id'] for r in rows]),concepts=np.array([r['concept'] for r in rows]),labels=np.array([r['label'] for r in rows]))
        reference_hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        _save_json(reference/'manifest.json',{'measurements_sha256':reference_hashes[name]})
    for pair in PAIRS:
        for kind in ['single','group']:
            ids=[i for i,u in enumerate(units) if u['kind']==kind]
            _save_json(run/'causal_alignment'/'_'.join(pair)/kind/'fit.json',{'pair':list(pair),'unit_kind':kind,'train_wrappers':[f'D2:wrapper:t{i:02d}' for i in range(12)],'unit_indices_a':ids,'unit_indices_b':ids,'location_order':['answer','span'],'modes':['zero','mean','patch'],'source':{'reference_sha256_a':reference_hashes[pair[0]],'reference_sha256_b':reference_hashes[pair[1]],'effects_sha256_a':'0'*64,'effects_sha256_b':'0'*64,'unit_ids_a':[u['id'] for u in units],'unit_ids_b':[u['id'] for u in units]}})
    primary={str(p):p.read_bytes() for p in (run/'causal_alignment').rglob('*') if p.is_file()}
    original_read_text,original_read_bytes=Path.read_text,Path.read_bytes;opened=[]
    def text(path,*args,**kwargs):
        assert 'D4' not in path.parts and path.name!='eval.json';opened.append(str(path));return original_read_text(path,*args,**kwargs)
    def binary(path,*args,**kwargs):
        assert 'D4' not in path.parts and path.name!='eval.json';opened.append(str(path));return original_read_bytes(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',text);monkeypatch.setattr(Path,'read_bytes',binary)
    result=fit_all(run,data)
    assert result['n_fit_files']==26 and result['n_location_control_maps']==104
    assert result['D4_read_during_fitting'] is False
    assert result['global_primary_test_family_modified'] is False
    assert all(original_read_bytes(Path(p))==payload for p,payload in primary.items())
    assert opened and not list(data.glob('D4*'))
