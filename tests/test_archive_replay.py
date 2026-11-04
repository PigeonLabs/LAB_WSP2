"""The published numerical archive must replay outside its original workspace."""
from pathlib import Path
import shutil
import numpy as np
import pytest
from scripts.validate_results import validate

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def relocated_snapshot(tmp_path_factory):
    root=tmp_path_factory.mktemp('published_snapshot_without_weights')
    shutil.copytree(ROOT/'configs',root/'configs')
    shutil.copytree(ROOT/'results/pilot-v1',root/'results/pilot-v1',
                    ignore=shutil.ignore_patterns('*.pt','*.jsonl','*.log'))
    (root/'reports').mkdir()
    (root/'data').mkdir()
    shutil.copy2(ROOT/'data/natural_reference.json',root/'data/natural_reference.json')
    for version in ['pilot-v1','pilot-v1-cluster-corrected']:
        (root/'data'/version).mkdir()
        shutil.copy2(ROOT/'data'/version/'manifest.json',root/'data'/version/'manifest.json')
    assert not list(root.rglob('*.pt'))
    assert not list(root.rglob('*.jsonl'))
    assert root.resolve()!=ROOT.resolve()
    return root


def test_all_results_replay_after_relocation_without_weights_or_unpacked_data(relocated_snapshot):
    result=validate(root=relocated_snapshot,require_complete=True)
    assert result['status']=='PASS_COMPLETE'
    assert not result['missing']
    assert len(result['checks'])==31
    assert len(result['optional_checkpoint_checks_not_available'])==4
    assert len(result['supplementary_models'])==5
    assert (relocated_snapshot/'reports/FINAL_VALIDATION.md').is_file()


def test_archived_weight_matrix_must_match_original_frozen_signature(relocated_snapshot):
    path=relocated_snapshot/'results/pilot-v1/E1/trained/weight_similarity.npy'
    original=path.read_bytes()
    matrix=np.load(path);matrix[0,0]+=0.01
    np.save(path,matrix)
    try:
        with pytest.raises(AssertionError,match='weight baseline matrix checksum mismatch'):
            validate(root=relocated_snapshot,require_complete=True)
    finally:path.write_bytes(original)
