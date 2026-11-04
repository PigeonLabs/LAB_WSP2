import copy
from dataclasses import replace
import itertools
import numpy as np
import pytest

from src.gemma_v3_statistics import (CELLS,CLAIMS,NumericalFailure,build_effect_panel,
    fit_epsilon,score_maps,bootstrap_maps,holm_four,null_centered_bootstrap_test,
    partial_match,choose_validation_map,h4_composite_p)


def rows(split='fit',families=8,lineages=None,lexical=1):
    result=[]
    for c in ('negation','numeric_comparison'):
        for f in range(families):
            for truth,code,lang in CELLS:
                for lex in range(lexical):
                    result.append(dict(id=f'{split}-{c}-{f}-{truth}-{code}-{lang}-{lex}',
                        family_id=f'{split}-{c}-{f}',lineage_id=f'{c}-lineage{f if lineages is None else f%lineages}',
                        concept=c,semantic_state=truth,answer_code=code,language=lang,lexical=lex,
                        split=split,fit_partition='train' if split=='fit' else None,
                        canonical_proposition_ids=['statement_true','statement_false']))
    return result


def panel(values,metadata):
    return build_effect_panel(values,metadata,metadata,unit_ids=[f'u{i}' for i in range(values.shape[1])],model_id='synthetic-model')


def strata(metadata):
    return sorted({(r['concept'],r['semantic_state'],r['answer_code'],r['language']) for r in metadata})


def test_complete_manifest_and_canonical_centering_are_mandatory():
    r=rows(lexical=2);x=np.random.default_rng(1).normal(size=(len(r),2,2))
    p=panel(x,r);q=panel(x+12.5,r)
    assert np.allclose(p.values.sum(-1),0,atol=1e-15)
    assert np.allclose(p.values,q.values)
    with pytest.raises(NumericalFailure):build_effect_panel(x[:-1],r[:-1],r,unit_ids=['u0','u1'],model_id='synthetic-model')
    bad=x.copy();bad[0,0,0]=np.nan
    with pytest.raises(NumericalFailure):panel(bad,r)
    with pytest.raises(NumericalFailure):build_effect_panel(x,r,r,unit_ids=['u0','u1'],model_id='synthetic-model',row_ids=list(reversed([z['id'] for z in r])))
    changed=copy.deepcopy(r);changed[0]['canonical_proposition_ids'].reverse()
    with pytest.raises(NumericalFailure):build_effect_panel(x,changed,r,unit_ids=['u0','u1'],model_id='synthetic-model')


def test_truth_sign_confound_is_zero_within_exact_condition():
    fit_rows=rows();test_rows=rows('test')
    # Generic answer-directed bias looks perfectly correlated if pooled over truth.
    truth=np.array([2*r['semantic_state']-1 for r in test_rows])
    x=truth[:,None,None]*np.array([[[1.,-1.],[2.,-2.]]])
    a,b=panel(x,test_rows),panel(3*x,test_rows)
    eps_a=fit_epsilon(panel(x,fit_rows));eps_b=fit_epsilon(panel(3*x,fit_rows))
    assert np.corrcoef(x[:,0,0],3*x[:,0,0])[0,1]==pytest.approx(1)
    result=score_maps(a,b,{'identity':[0,1]},eps_a,eps_b,
                      eligible_strata=strata(test_rows),source_layers=[5,27])
    assert result['scores']['identity']==0
    assert result['constant_source_hk_cells']>0


def test_positive_control_regularized_endpoint_and_unmatched_denominator():
    r=rows();rng=np.random.default_rng(2);x=rng.normal(size=(len(r),2,2))
    f=panel(x,r);eps=fit_epsilon(f);t=rows('test');a=panel(x,t)
    maps={'identity':[0,1],'half_unmatched':[0,-1],'empty':[-1,-1]}
    result=score_maps(a,a,maps,eps,eps,eligible_strata=strata(t),source_layers=[5,27])
    assert .95<result['scores']['identity']<1
    assert result['scores']['empty']==0
    # Compute one stratum manually to confirm epsilon is in nats, squared in variance.
    cell=a.cells.index((0,0,'en'));take=np.array(a.concepts)=='negation'
    xx=a.values[take,cell,0,0];v=np.var(xx)
    expected=v/(v+eps['epsilon'][0]**2)
    single=score_maps(a,a,{'single':[0,-1]},eps,eps,
                      eligible_strata=[('negation',0,0,'en')],source_layers=[5,27])
    assert single['scores']['single']==pytest.approx(expected/2)
    with pytest.raises(ValueError):fit_epsilon(a)
    assert eps['epsilon']==fit_epsilon(f)['epsilon']


def test_one_to_many_preserves_total_source_weight_and_invalid_map_fails():
    r=rows();x=np.random.default_rng(3).normal(size=(len(r),2,2));p=panel(x,r);e=fit_epsilon(p)
    maps={'many':{'source':[0,0,1,1],'target':[0,1,0,1]},
          'straight':[0,1],'cross':[1,0]}
    q=score_maps(p,p,maps,e,e,eligible_strata=strata(r),source_layers=[5,27],max_targets=4)
    assert q['scores']['many']==pytest.approx((q['scores']['straight']+q['scores']['cross'])/2)
    with pytest.raises(NumericalFailure):score_maps(p,p,{'bad':[0,9]},e,e,eligible_strata=strata(r),source_layers=[5,27])


def test_joint_bootstrap_does_not_inflate_lineage_count_or_decouple_arms():
    r=rows(families=8,lineages=4);x=np.random.default_rng(4).normal(size=(len(r),2,2));p=panel(x,r);e=fit_epsilon(p)
    args=dict(eligible_strata=strata(r),source_layers=[5,27],
              comparisons={'same':dict(arm='a',baseline='b')},n_boot=80,minimum_lineages=40)
    result=bootstrap_maps(p,p,{'a':[0,1],'b':[0,1]},e,e,**args)
    assert result['lineage_counts']=={'negation':4,'numeric_comparison':4}
    assert result['status']=='EXPLORATORY_FEW_LINEAGES'
    assert np.array_equal(result['bootstrap_scores'][:,0],result['bootstrap_scores'][:,1])
    assert result['comparisons']['same']['confidence_interval']==[0.,0.]
    assert result['comparisons']['same']['p_value']==1
    one=rows(families=8,lineages=1);p1=panel(x,one);e1=fit_epsilon(p1)
    blocked=bootstrap_maps(p1,p1,{'a':[0,1]},e1,e1,eligible_strata=strata(one),source_layers=[5,27],comparisons={},n_boot=20)
    assert blocked['measured_inferential_p'] is False
    assert blocked['bootstrap_scores'] is None


def test_cross_concept_lineage_not_split_into_false_independent_clusters():
    r=rows();x=np.random.default_rng(5).normal(size=(len(r),2,2));p=panel(x,r);e=fit_epsilon(p)
    p=replace(p,lineage_ids=tuple('shared-lineage' for _ in p.lineage_ids))
    with pytest.raises(NumericalFailure,match='spans concept'):
        bootstrap_maps(p,p,{'a':[0,1]},e,e,eligible_strata=strata(r),source_layers=[5,27],comparisons={},n_boot=20)


def test_null_centering_boundary_and_finite_scope_are_explicit():
    rng=np.random.default_rng(6)
    boot=.2+rng.normal(0,.02,5000)
    test=null_centered_bootstrap_test(.2,boot)
    assert test['p_value']<.001
    assert 'asymptotic' in test['method'] and 'not simultaneous' in test['interval_scope']
    boundary=null_centered_bootstrap_test(0.,rng.normal(0,.02,5000))
    assert .45<boundary['p_value']<.55


def test_holm_keeps_all_four_and_unmeasured_placeholder_is_not_observed_p():
    result=holm_four({CLAIMS[0]:dict(measured=True,p_value=.01),
                      CLAIMS[1]:dict(measured=True,p_value=.04),
                      CLAIMS[2]:dict(measured=False,scientific_status='BLOCKED_DEPENDENCY')})
    assert result['family_size']==4
    assert result['claims'][CLAIMS[0]]['holm_adjusted_p']==pytest.approx(.04)
    assert result['claims'][CLAIMS[1]]['holm_adjusted_p']==pytest.approx(.12)
    blocked=result['claims'][CLAIMS[2]]
    assert blocked['holm_input_p']==1 and blocked['p_value'] is None
    assert blocked['holm_adjusted_p'] is None and blocked['multiplicity_placeholder']
    assert not blocked['reject_null']
    assert h4_composite_p(.01,.2,.03)==.2


def test_partial_map_and_validation_tie_preserve_unmatched_option():
    dense=partial_match([[.9,.1],[.2,.8]],.5)
    sparse=partial_match([[.9,.1],[.2,.8]],.85)
    assert len(sparse['source'])==1
    selected=choose_validation_map({'dense':dense,'sparse':sparse},{'dense':.2,'sparse':.2})
    assert selected['selected']=='sparse'
    with pytest.raises(ValueError):choose_validation_map({'a':dense},{'a':.1},split='test')


def test_actual_eight_source_sixteen_target_dimensions_and_model_epsilon_provenance():
    r=rows();rng=np.random.default_rng(17)
    source=rng.normal(size=(len(r),8,2))
    target=np.concatenate([rng.normal(size=source.shape),source],axis=1)
    a=replace(panel(source,r),model_id='Gemma-test-revision')
    b=replace(panel(target,r),model_id='Qwen-test-revision')
    ea,eb=fit_epsilon(a),fit_epsilon(b)
    value=score_maps(a,b,{'known_map':list(range(8,16))},ea,eb,
                     eligible_strata=strata(r),source_layers=[5]*4+[27]*4)
    assert value['source_denominator']==8 and value['layer_denominator']==2
    assert value['scores']['known_map']>.95
    bad=dict(ea,model_id='other-model')
    with pytest.raises(NumericalFailure):score_maps(a,b,{'known_map':list(range(8,16))},bad,eb,
                                                   eligible_strata=strata(r),source_layers=[5]*4+[27]*4)
