import copy
import json
import numpy as np
import pytest

from src.followup_analysis import (expanded_semantic_profile, fit_pair, evaluate_pair,
    within_task_correlation_matrices, aggregate_pairs, apply_global_bh, json_ready)


def fixture(split='D2', wrappers=4):
    rows = [dict(split=split, wrapper_id=f'{split}_w{w}', concept=c,
                 subtype=s, label=y)
            for w in range(wrappers) for c in ('arithmetic', 'logic')
            for s in ('a', 'b') for y in (0, 1) for _ in range(3)]
    rng = np.random.default_rng(7)
    a = rng.normal(size=(len(rows), 6))
    y = np.array([r['label'] for r in rows])*2-1
    a[:, 0] += 3*y
    return rows, a


def test_expanded_profiles_use_subtypes_and_unknown_constants():
    rows, a = fixture()
    a[:, -1] = 4
    profile = expanded_semantic_profile(a, rows)
    assert any('/a/' in x for x in profile['feature_names'])
    assert profile['primary'][0] != 'UNKNOWN'
    assert profile['primary'][-1] == 'UNKNOWN'
    assert np.all(profile['stability'][0] == 1)
    with pytest.raises(ValueError):
        expanded_semantic_profile(a, [dict(r, split='D3') for r in rows], split='D3')


def test_task_identity_shortcut_does_not_count_as_within_task_correlation():
    rows, a = fixture('D3', wrappers=1)
    concept = np.array([r['concept'] == 'logic' for r in rows])
    a = np.column_stack([100*concept, np.arange(len(rows))])
    b = a.copy()
    matrices = within_task_correlation_matrices(a,b,rows)
    for cells in matrices.values():
        for matrix in cells.values():
            assert np.isnan(matrix[0,0])
            assert matrix[1,1] == pytest.approx(1.)


def test_maps_frozen_before_independent_evaluation_and_layer_constraints():
    rows, a = fixture()
    permutation = np.array([2,0,1,5,3,4])
    b = a[:, permutation]
    layers = [0,0,0,1,1,1]
    fitted = fit_pair(a,b,rows,layers_a=layers,layers_b=layers,
                      methods=('activation',),modes=('hungarian','partial','one_to_many'),
                      n_random=100,null_permutations=3)
    assert len(fitted['random_mappings']['layer']) == 100
    mapping = fitted['mappings']['activation__layer__hungarian']
    assert np.array_equal(permutation[mapping['target']],mapping['source'])
    for mapping in fitted['mappings'].values():
        if mapping['scope'] == 'layer':
            assert np.array_equal(np.asarray(layers)[mapping['source']],np.asarray(layers)[mapping['target']])
    held_rows, held_a = fixture('D3')
    result = evaluate_pair(held_a,held_a[:,permutation],held_rows,fitted)
    assert result['descriptive']['activation__layer__hungarian']['mean'] == pytest.approx(1.)
    assert result['random_controls']['layer']['n_draws'] == 100
    with pytest.raises(ValueError):
        fit_pair(a,b,[dict(r,split='D3') for r in rows],layers_a=layers,layers_b=layers,
                 methods=('activation',),split='D3')
    with pytest.raises(ValueError):
        fit_pair(a,b,rows,layers_a=layers,layers_b=layers,n_random=99)
    json.dumps(json_ready(result),allow_nan=False)


def test_joint_wrapper_bootstrap_does_not_pseudoreplicate_shared_pairs():
    groups = [f'w{i:02d}' for i in range(24)]
    differences = np.linspace(-.2,.5,24)
    pair = {'wrapper_scores': {'method':dict(zip(groups,differences)),
                              'baseline':dict.fromkeys(groups,0.)}}
    single = aggregate_pairs({'a':pair},{'primary':('method','baseline')},n_boot=500)
    ten = aggregate_pairs({f'pair{i}':copy.deepcopy(pair) for i in range(10)},
                          {'primary':('method','baseline')},n_boot=500)
    x,y = single['tests']['primary'],ten['tests']['primary']
    assert y['n_clusters'] == 24
    assert y['n_pairs'] == 10
    assert y['pvalue'] == x['pvalue']
    assert y['bootstrap']['ci'] == pytest.approx(x['bootstrap']['ci'])
    assert y['method'] == 'monte_carlo'


def test_global_bh_combines_all_confirmatory_comparisons():
    result = apply_global_bh({'a':{'pvalue':.01},'b':{'pvalue':.04},
                              'c':{'pvalue':.2},'unmeasured':{'pvalue':None}})
    assert result['family_size'] == 4
    assert result['finite_pvalue_count'] == 3
    assert result['tests']['a']['qvalue'] == pytest.approx(.03)
    assert result['tests']['b']['qvalue'] == pytest.approx(.06)
    assert result['tests']['unmeasured']['qvalue'] is None


def test_missing_wrappers_not_silently_intersected_or_filled():
    pair = {'wrapper_scores':{'m':{'w0':.2,'w1':None},'b':{'w0':.1,'w1':.1}}}
    result = aggregate_pairs({'p':pair},{'c':('m','b')})
    assert result['tests']['c']['pvalue'] is None
    other = copy.deepcopy(pair)
    other['wrapper_scores']['m']['w2'] = 0
    with pytest.raises(ValueError):
        aggregate_pairs({'p':other},{'c':('m','b')})
