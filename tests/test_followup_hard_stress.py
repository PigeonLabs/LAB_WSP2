"""CPU-only data/oracle/replay tests; no hard-stress model outcomes are inspected."""
import copy
import json
import numpy as np
import pytest
from src.followup_data import load_dataset as load_original
from src.followup_hard_stress import (ROOT,generate_dataset,validate_dataset,
    original_bracket_strings,adjacent_type_mismatch,summarize,freeze_dataset,load_dataset)


@pytest.fixture(scope='module')
def evidence():
    original=load_original(ROOT/'data/followup-v2')
    return original,generate_dataset(original)


def test_all768_semantics_and_shortcut_exclusions(evidence):
    original,rows=evidence
    manifest=validate_dataset(rows,original)
    assert manifest['n']==768 and manifest['n_pairs']==384 and manifest['n_wrappers']==24
    assert manifest['length_rows']=={5:192,6:192,7:192,8:192}
    excluded=original_bracket_strings(original)
    for row in rows:
        brackets=row['semantic']['brackets']
        assert brackets not in excluded and not adjacent_type_mismatch(brackets)
        # Independent semantic oracle: iteratively remove matching typed pairs.
        previous=None;reduced=brackets
        while previous!=reduced:
            previous=reduced
            for pair in ('()','[]','{}'):reduced=reduced.replace(pair,'')
        assert (reduced=='')==bool(row['label'])


def test_deterministic_and_no_original_prompt_reuse(evidence):
    original,rows=evidence
    assert rows==generate_dataset(original)
    old={r['prompt'] for split in original.values() for r in split}
    assert not old.intersection(r['prompt'] for r in rows)
    assert len({r['semantic']['brackets'] for r in rows})==768


def test_detects_label_and_swap_metadata_corruption(evidence):
    original,rows=evidence
    bad=copy.deepcopy(rows);bad[0]['label']=1-bad[0]['label']
    with pytest.raises(ValueError,match='oracle'):validate_dataset(bad,original)
    bad=copy.deepcopy(rows);bad[0]['swapped_closing_indices']=[0,1]
    with pytest.raises(ValueError,match='declared closing swaps'):validate_dataset(bad,original)


def test_descriptive_wrapper_statistics_have24clusters_and_no_auto_verdict(evidence):
    _,rows=evidence
    margins=np.array([1. if r['label'] else -1. for r in rows])
    result=summarize(margins,rows)
    assert result['accuracy']==.5
    assert result['accuracy_cluster_bootstrap95']['n_clusters']==24
    assert result['accuracy_cluster_bootstrap95']['ci']==[.5,.5]
    assert result['accuracy_minus_half_cluster_bootstrap95']['ci']==[0.,0.]
    assert result['unadjusted_exploratory_signflip_vs_half']['pvalue']==1.
    assert 'verdict' not in result
    with pytest.raises(ValueError,match='finite'):summarize(np.full(768,np.nan),rows)


def test_freeze_and_load_preserve_bytes(evidence,tmp_path):
    original,rows=evidence
    (tmp_path/'data').mkdir()
    (tmp_path/'data/followup-v2').symlink_to(ROOT/'data/followup-v2',target_is_directory=True)
    manifest=freeze_dataset(tmp_path)
    loaded,again=load_dataset(tmp_path)
    assert loaded==rows and json.loads(json.dumps(manifest))==again
    assert freeze_dataset(tmp_path)==manifest
