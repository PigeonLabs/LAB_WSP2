"""CPU correctness for v2 views and interventions; no pilot evidence is altered."""
import json
import numpy as np
import pytest
import torch
from src.data import generate_dataset
from src.models import ModelConfig,build_model,ByteTokenizer
from src.hooks import SwiGLUHook
from src.experiment import sequence_margins,_shared_answer_prefix
from src.followup_engine import (capture_views,collect,load_collection,intervention_units,
    stratified_pairs,group_sequence_margins,collect_causal)


@pytest.fixture
def setup():
    torch.set_num_threads(1)
    model=build_model(ModelConfig(dim=16,hidden_dim=24,layers=1,heads=2,max_seq_len=256),71).eval()
    return model,ByteTokenizer(),generate_dataset(per_concept=12)


def test_span_and_boundary_match_manual_native_units(setup):
    model,tok,data=setup;rows=data['D1'][:2];selection={0:[2,4,8,12]}
    observed=capture_views(model,tok,rows,selection,device='cpu',batch_size=2)
    row=rows[0];ids=tok.encode(row['prompt'])+_shared_answer_prefix(tok,row)
    with torch.no_grad(),SwiGLUHook(model.layers[0].mlp,neurons=selection[0],capture_contribution=False) as hook:
        model(torch.tensor([ids]));values=hook.records['product'][0].numpy()
    start,end=row['span'];span=values[start:end]
    np.testing.assert_allclose(observed['answer_product'][0],values[-1],atol=1e-7)
    np.testing.assert_allclose(observed['span_product'][0],span.mean(0,dtype=np.float64),atol=1e-7)
    np.testing.assert_allclose(observed['span_sign_frequencies'].sum(-1),1.)
    np.testing.assert_allclose(observed['span_product_by_sign'].sum(-1),observed['span_product'],atol=1e-12)
    assert observed['answer_positions'][0]==len(ids)-1


def test_candidate_selection_is_discovery_only_and_resume_is_signed(setup,tmp_path):
    model,tok,data=setup
    with pytest.raises(ValueError,match='restricted to D1'):
        collect(model,tok,data['D2'],tmp_path/'bad',{'id':'test'},device='cpu')
    out=tmp_path/'D1';m=collect(model,tok,data['D1'],out,{'id':'test'},per_layer=4,device='cpu')
    loaded,arrays=load_collection(out)
    assert loaded==m and arrays['product'].shape==(48,4)
    assert collect(model,tok,data['D1'],out,{'id':'test'},per_layer=4,device='cpu')==m
    with pytest.raises(ValueError,match='inputs changed'):
        collect(model,tok,data['D1'],out,{'id':'changed'},per_layer=4,device='cpu')
    with (out/'measurements.npz').open('ab') as f:f.write(b'tamper')
    with pytest.raises(ValueError,match='checksum mismatch'):load_collection(out)


def test_unit_groups_and_stratified_donors_are_frozen(setup):
    _,_,data=setup;selection={0:list(range(8)),3:list(range(8,16))}
    units=intervention_units(selection)
    assert len(units)==6 and sum(u['kind']=='single' for u in units)==4
    assert units[2]['units_by_layer'][0]==[2,3,6,7]
    rows=stratified_pairs(data['D4'],pairs_per_task_wrapper=1)
    assert len(rows)==48 and len({r['group_id'] for r in rows})==6
    for row in rows:assert sum(r['pair_id']==row['pair_id'] and r['label']!=row['label'] for r in rows)==1


@pytest.mark.parametrize('location',['answer','span'])
def test_group_identity_zero_and_dose_equivalence(setup,location):
    model,tok,data=setup;rows=data['D2'][:3];units={0:[1,3]}
    baseline,_=sequence_margins(model,tok,rows,device='cpu')
    identity=group_sequence_margins(model,tok,rows,units,location,'scale',scale=1.,device='cpu')
    zero=group_sequence_margins(model,tok,rows,units,location,'zero',device='cpu')
    scale0=group_sequence_margins(model,tok,rows,units,location,'scale',scale=0.,device='cpu')
    np.testing.assert_array_equal(identity,baseline)
    np.testing.assert_array_equal(zero,scale0)
    assert not model.layers[0].mlp.down_proj._forward_pre_hooks


def test_causal_checkpoint_resume_keeps_original_measurements(setup,tmp_path):
    model,tok,data=setup;info={'id':'tiny_test_only'};d1=tmp_path/'D1';out=tmp_path/'causal'
    m=collect(model,tok,data['D1'],d1,info,per_layer=4,device='cpu')
    units=intervention_units(m['selection'])[:1]
    with pytest.raises(TimeoutError,match='checkpointed'):
        collect_causal(model,tok,data['D2'],d1,out,info,units=units,locations=('answer',),modes=('zero','mean','patch','scale_1'),pairs_per_task_wrapper=1,device='cpu',max_seconds=0.)
    chunk=next((out/'chunks').glob('*.npz'));before=chunk.read_bytes()
    final=collect_causal(model,tok,data['D2'],d1,out,info,units=units,locations=('answer',),modes=('zero','mean','patch','scale_1'),pairs_per_task_wrapper=1,device='cpu')
    assert chunk.read_bytes()==before
    values=np.load(out/'effects.npz')
    assert values['effects'].shape==(48,1,1,4)
    np.testing.assert_array_equal(values['effects'][:,:,:,3],0.)
    assert final['n']==48
    with pytest.raises(ValueError,match='inputs changed'):
        collect_causal(model,tok,data['D2'],d1,out,info,units=units,locations=('span',),modes=('zero',),pairs_per_task_wrapper=1,device='cpu')


def test_signature_survives_json_roundtrip_for_multidigit_layers():
    from src.followup_engine import _digest
    plan={'selection':{5:[1,2],11:[3,4],22:[5,6]},'units':[{'units_by_layer':{5:[1],11:[3]}}]}
    assert _digest(plan)==_digest(json.loads(json.dumps(plan)))


def test_runner_collection_call_contract_without_gpu(setup,tmp_path,monkeypatch):
    import src.followup_runner as runner
    model,tok,data=setup;calls=[];selection={0:[0,1,2,3]}
    monkeypatch.setattr(runner,'RUN',tmp_path)
    monkeypatch.setattr(runner,'NAMES',['seed101','qwen'])
    monkeypatch.setattr(runner,'model_load',lambda name,checkpoint='final':(model,tok,{'id':name,'checkpoint':checkpoint}))
    monkeypatch.setattr(runner,'prepared',lambda ds,name,split:ds[split])
    monkeypatch.setattr(runner,'selection_for',lambda name:selection)
    monkeypatch.setattr(runner,'release',lambda model:None)
    monkeypatch.setattr(torch.cuda,'reset_peak_memory_stats',lambda:None)
    monkeypatch.setattr(torch.cuda,'max_memory_allocated',lambda:0)
    def record(model,tok,rows,out,info,**kwargs):
        calls.append((info['id'],info['checkpoint'],rows[0]['split'],kwargs['selection']))
        return {'n':len(rows),'elapsed_seconds':0.}
    monkeypatch.setattr(runner,'collect',record)
    runner.collections('discover',data)
    assert calls==[('seed101','final','D1',None),('seed101','final','D2',selection),('qwen','final','D1',None),('qwen','final','D2',selection)]
    calls.clear();runner.collections('heldout',data)
    assert calls==[('seed101','final','D3',selection),('seed101','initial','D3',selection),('seed101','middle','D3',selection),('qwen','final','D3',selection)]


def test_runner_positive_control_cpu_smoke(setup,tmp_path,monkeypatch):
    import src.followup_runner as runner
    import src.experiment as experiment
    model,tok,data=setup;selection={0:list(range(8))}
    original_input=experiment._input
    monkeypatch.setattr(runner,'RUN',tmp_path)
    monkeypatch.setattr(runner,'model_load',lambda name,checkpoint='final':(model,tok,{'id':name,'test_only':True}))
    monkeypatch.setattr(runner,'prepared',lambda ds,name,split:ds[split])
    monkeypatch.setattr(runner,'selection_for',lambda name:selection)
    monkeypatch.setattr(runner,'release',lambda model:None)
    monkeypatch.setattr(runner,'capture_views',lambda model,tok,rows,chosen:capture_views(model,tok,rows,chosen,device='cpu'))
    monkeypatch.setattr(experiment,'_input',lambda model,tok,seqs,device:original_input(model,tok,seqs,'cpu'))
    monkeypatch.setattr(torch.cuda,'reset_peak_memory_stats',lambda:None)
    monkeypatch.setattr(torch.cuda,'max_memory_allocated',lambda:0)
    runner.positive(data)
    measured=json.loads((tmp_path/'positive_control/summary.json').read_text())
    assert measured['passed']
    assert all(row['recovered_fraction']==1 for row in measured['alignment'].values())
    assert all(row['passed'] for row in measured['intervention_checks'].values())
