"""Synthetic temporary artifacts test resume safety; no research data are changed."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from src.data import generate_dataset
from src.experiment import analyze_pair


@pytest.fixture
def completed_analysis(tmp_path):
    dataset=generate_dataset(per_concept=12)
    rng=np.random.default_rng(7)
    a,b=tmp_path/'a',tmp_path/'b'
    for directory in (a,b):
        directory.mkdir()
        for split in ('D2','D3'):
            values=rng.normal(size=(len(dataset[split]),4))
            np.savez_compressed(directory/f'{split}.npz',product=values,
                sign_regime=np.where(values>=0,0,2).astype(np.int8),
                layers=np.zeros(4,dtype=int),neuron_ids=np.arange(4),
                row_ids=np.asarray([r['id'] for r in dataset[split]]))
    out=tmp_path/'analysis'
    weight=np.eye(4)
    metrics=analyze_pair(a,b,dataset,out,'synthetic_test_only',weight_similarity=weight)
    return a,b,dataset,out,weight,metrics


def _hash(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def test_valid_resume_uses_verified_frozen_result_without_refitting(completed_analysis,monkeypatch):
    a,b,data,out,weight,metrics=completed_analysis
    import src.alignment
    monkeypatch.setattr(src.alignment,'fit_alignment',lambda *args,**kwargs:pytest.fail('Resume must not refit observed maps'))
    before={p.name:_hash(p) for p in out.iterdir()}
    resumed=analyze_pair(a,b,data,out,'synthetic_test_only',weight_similarity=weight)
    assert resumed==metrics
    assert {p.name:_hash(p) for p in out.iterdir()}==before


@pytest.mark.parametrize('model,split',[('a','D2'),('b','D2'),('a','D3'),('b','D3')])
def test_changed_source_npz_is_rejected_without_modifying_results(completed_analysis,model,split):
    a,b,data,out,weight,_=completed_analysis
    source=(a if model=='a' else b)/f'{split}.npz'
    with np.load(source) as original:arrays={k:original[k].copy() for k in original.files}
    arrays['product'][0,0]+=0.1
    np.savez_compressed(source,**arrays)
    before={p.name:_hash(p) for p in out.iterdir()}
    with pytest.raises(ValueError,match='Analysis inputs changed'):
        analyze_pair(a,b,data,out,'synthetic_test_only',weight_similarity=weight)
    assert {p.name:_hash(p) for p in out.iterdir()}==before


def test_changed_dataset_metadata_is_rejected(completed_analysis):
    a,b,data,out,weight,_=completed_analysis
    changed=copy.deepcopy(data)
    changed['D2'][0]['group_id']='changed-wrapper'
    with pytest.raises(ValueError,match='Analysis inputs changed'):
        analyze_pair(a,b,changed,out,'synthetic_test_only',weight_similarity=weight)


def test_changed_weight_baseline_matrix_is_rejected(completed_analysis):
    a,b,data,out,weight,_=completed_analysis
    changed=weight.copy();changed[0,0]=0.5
    with pytest.raises(ValueError,match='Analysis inputs changed'):
        analyze_pair(a,b,data,out,'synthetic_test_only',weight_similarity=changed)


def test_legacy_metrics_without_validation_sidecar_refuse_silent_resume(completed_analysis):
    a,b,data,out,weight,_=completed_analysis
    (out/'input_signature.json').unlink()
    original_hash=_hash(out/'metrics.json')
    with pytest.raises(ValueError,match='Historical analysis lacks verified input signature'):
        analyze_pair(a,b,data,out,'synthetic_test_only',weight_similarity=weight)
    assert _hash(out/'metrics.json')==original_hash
    assert not (out/'input_signature.json').exists()
