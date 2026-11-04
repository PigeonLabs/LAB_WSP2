import copy
import hashlib
import json
import numpy as np
import pytest

from src.followup_analysis import (expanded_semantic_profile, fit_pair, evaluate_pair,
    within_task_correlation_matrices, aggregate_pairs, apply_global_bh, json_ready,
    fit_causal_alignment, evaluate_causal_alignment)


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
    assert result['tests']['a']['qvalue'] == pytest.approx(.04)
    assert result['tests']['b']['qvalue'] == pytest.approx(.08)
    assert result['tests']['unmeasured']['qvalue'] is None


def test_missing_wrappers_not_silently_intersected_or_filled():
    pair = {'wrapper_scores':{'m':{'w0':.2,'w1':None},'b':{'w0':.1,'w1':.1}}}
    result = aggregate_pairs({'p':pair},{'c':('m','b')})
    assert result['tests']['c']['pvalue'] is None
    other = copy.deepcopy(pair)
    other['wrapper_scores']['m']['w2'] = 0
    with pytest.raises(ValueError):
        aggregate_pairs({'p':other},{'c':('m','b')})


def test_span_route_products_preserve_mixed_sign_paths():
    rows,a = fixture()
    # Half the average product is assigned to each of two token-level routes.
    # This is not representable by a single sign of the span mean.
    routes = np.zeros(a.shape+(5,))
    routes[:,:,0],routes[:,:,3] = a*.5,a*.5
    profile = expanded_semantic_profile(a,rows,route_products=routes)
    assert len(profile['feature_names']) == 4*len(expanded_semantic_profile(a,rows)['feature_names'])
    assert np.any(profile['features'][:, :6])
    assert np.any(profile['features'][:, -6:])
    with pytest.raises(ValueError):
        expanded_semantic_profile(a,rows,route_products=routes+1)


def test_causal_weight_uses_separate_d2_wrappers_then_fixed_d4_evaluation():
    rows,_ = fixture('D2',wrappers=4)
    rng = np.random.default_rng(23)
    a = rng.normal(size=(len(rows),3,2,3))
    a[:,:,:,-1] = 0 # identity scaling is an exact-zero negative control.
    permutation = np.array([1,2,0])
    b = a[:,permutation]*2
    fit = fit_causal_alignment(a,b,rows,np.eye(3),location_names=['answer','span'],
                               mode_names=['zero','mean','scale_1'])
    assert set(fit['train_wrappers']).isdisjoint(fit['validation_wrappers'])
    assert len(fit['train_wrappers']) == len(fit['validation_wrappers']) == 2
    assert all(x['selected_causal_weight'] > 0 for x in fit['locations'].values())
    frozen = json.dumps(json_ready(fit),sort_keys=True)
    held_rows = [dict(r,split='D4',wrapper_id=r['wrapper_id'].replace('D2','D4')) for r in rows]
    held = rng.normal(size=a.shape)
    held[:,:,:,-1] = 0
    evaluation = evaluate_causal_alignment(held,held[:,permutation]*2,held_rows,fit)
    assert json.dumps(json_ready(fit),sort_keys=True) == frozen
    for location in evaluation['locations'].values():
        assert location['descriptive']['combined']['mean'] == pytest.approx(1)
        assert location['per_mode']['scale_1']['descriptive']['combined']['mean'] is None
        assert location['random_controls']['n_draws'] == 100
    with pytest.raises(ValueError):
        fit_causal_alignment(held,held[:,permutation],held_rows,np.eye(3),split='D4')


def _write_collection_fixture(path,rows,values):
    path.mkdir(parents=True,exist_ok=True)
    signs = np.where(values >= 0,0,1)
    routes = np.stack([np.where(signs == k,values,0.) for k in range(5)],-1)
    arrays = dict(answer_product=values,span_product=values,answer_sign_regime=signs,
                  span_product_by_sign=routes,layers=np.array([0,0,0,1,1,1]),
                  neuron_ids=np.array([0,1,2,0,1,2]),margins=np.ones(len(rows)),
                  row_ids=np.array([r['id'] for r in rows]),groups=np.array([r['group_id'] for r in rows]),
                  concepts=np.array([r['concept'] for r in rows]),labels=np.array([r['label'] for r in rows]))
    np.savez(path/'measurements.npz',**arrays)
    manifest = dict(measurements_sha256=hashlib.sha256((path/'measurements.npz').read_bytes()).hexdigest())
    (path/'manifest.json').write_text(json.dumps(manifest))
    return arrays


def test_runner_fit_freeze_replay_and_candidate_identity(tmp_path,monkeypatch):
    from src import followup_alignment_runner as runner
    original_fit = runner.fit_pair
    monkeypatch.setattr(runner,'fit_pair',lambda *a,**kw:original_fit(*a,**kw,null_permutations=2))
    data = tmp_path/'data'
    data.mkdir()
    for split in ('D2','D3'):
        rows,a = fixture(split)
        rows = [dict(r,id=f'{split}-{i}',group_id=r['wrapper_id']) for i,r in enumerate(rows)]
        (data/f'{split}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        for name,values in [('seed101',a),('seed211',a[:,[2,0,1,5,3,4]])]:
            _write_collection_fixture(tmp_path/'collections'/name/'final'/split,rows,values)
    fit_result = runner.fit_all(tmp_path,data,pairs=[('seed101','seed211')],positions=['answer'])
    assert not fit_result['full_protocol_complete']
    fitpath = tmp_path/'alignment/seed101_seed211/answer/fit.json'
    frozen = fitpath.read_bytes()
    result = runner.evaluate_all(tmp_path,data,pairs=[('seed101','seed211')],positions=['answer'],checkpoints=['final'])
    assert result['n_final_evaluations'] == 1
    assert result['n_trajectory_evaluations'] == 0
    assert len(result['confirmatory_tests']) == 2
    assert fitpath.read_bytes() == frozen
    repeat = runner.evaluate_all(tmp_path,data,pairs=[('seed101','seed211')],positions=['answer'],checkpoints=['final'])
    assert json_ready(result) == json_ready(repeat)
    assert not (tmp_path/'alignment/summary.json').exists()


def test_causal_runner_selects_only_independent_core_modes(tmp_path):
    from src import followup_alignment_runner as runner
    data = tmp_path/'data'
    data.mkdir()
    modes = ['zero','mean','patch','scale_0','scale_0.5','scale_1','scale_1.5','scale_2']
    units = [dict(id='s0',kind='single',units_by_layer={'0':[0]}),
             dict(id='s1',kind='single',units_by_layer={'1':[0]}),
             dict(id='g0',kind='group',units_by_layer={'0':[1,2]})]
    rng = np.random.default_rng(97)
    for split in ('D2','D4'):
        rows,values = fixture(split)
        rows = [dict(r,id=f'{split}-{i}',group_id=r['wrapper_id']) for i,r in enumerate(rows)]
        (data/f'{split}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        effects = rng.normal(size=(len(rows),3,2,len(modes)))
        effects[...,3] = effects[...,0]
        effects[...,5] = 0
        for name in ('seed101','seed211'):
            out = tmp_path/'causal'/name/split
            reference = _write_collection_fixture(out/'references',rows,values)
            arrays = {k:reference[k] for k in ('row_ids','groups','concepts','labels','margins')}
            arrays.update(effects=effects,unit_ids=np.array(['s0','s1','g0']),
                          unit_kinds=np.array(['single','single','group']),locations=np.array(['answer','span']),
                          modes=np.array(modes))
            np.savez(out/'effects.npz',**arrays)
            (out/'manifest.json').write_text(json.dumps(dict(
                effects_sha256=hashlib.sha256((out/'effects.npz').read_bytes()).hexdigest(),plan=dict(units=units))))
    runner.fit_causal_all(tmp_path,data,pairs=[('seed101','seed211')])
    fitpath = tmp_path/'causal_alignment/seed101_seed211/single/fit.json'
    fit = json.loads(fitpath.read_text())
    assert fit['modes'] == ['zero','mean','patch']
    assert fit['source']['primary_mode_indices'] == [0,1,2]
    frozen = fitpath.read_bytes()
    result = runner.evaluate_causal_all(tmp_path,data,pairs=[('seed101','seed211')])
    assert result['n_evaluations'] == 2
    assert len(result['confirmatory_tests']) == 4
    assert fitpath.read_bytes() == frozen
    measured = json.loads((fitpath.parent/'eval.json').read_text())
    assert list(measured['locations']['answer']['per_mode']) == ['zero','mean','patch']
    supplementary = measured['supplementary_dose_response']['model_a']
    assert supplementary['identity_scale_1_max_absolute_effect'] == 0
    assert supplementary['zero_vs_scale_0_max_absolute_difference'] == 0


def test_partial_causal_cohorts_cannot_collide_with_complete_cohorts(tmp_path):
    from src.followup_alignment_runner import _causal_cohort_path,write_once
    subset=['qwen_smol']
    full=['qwen_smol','qwen_olmo','smol_olmo']
    partial_path=_causal_cohort_path(tmp_path,'cross_family','single','answer',subset)
    full_path=_causal_cohort_path(tmp_path,'cross_family','single','answer',full)
    assert partial_path!=full_path
    assert full_path==_causal_cohort_path(tmp_path,'cross_family','single','answer',list(reversed(full)))
    write_once(partial_path,{'n_pairs':1,'effect':.2})
    frozen=partial_path.read_bytes()
    write_once(full_path,{'n_pairs':3,'effect':.1})
    assert partial_path.read_bytes()==frozen
    assert json.loads(full_path.read_text())['n_pairs']==3
