import copy
import json

import numpy as np
import pytest

from src.followup_analysis import json_ready
from src.followup_causal_diagnostics import evaluate_bias_diagnostics


def fixture():
    rows=[dict(id=f'{w}-{c}-{i}',split='D4',group_id=f'w{w}',concept=c,label=i%2)
          for w in range(4) for c in ('comparison','syntax') for i in range(8)]
    identity=dict(source=np.array([0,1]),target=np.array([0,1]))
    reverse=dict(source=np.array([0,1]),target=np.array([1,0]))
    fit=dict(fit_split='D2',modes=['zero','mean','patch'],location_order=['answer'],
             locations={'answer':dict(mappings={k:copy.deepcopy(identity) for k in ('semantic','causal','combined')},
                                      random_mappings=[copy.deepcopy(identity if i%2 else reverse) for i in range(100)])})
    return rows,fit


def test_generic_yes_bias_creates_artificial_truth_correlation_but_no_within_label_variation():
    rows,fit=fixture()
    labels=np.array([r['label'] for r in rows])
    generic_yes_effect=np.array([[1.,.5,.25],[2.,1.,.5]])
    # No task-specific causal computation: each intervention only shifts yes log odds.
    a=(2*labels-1)[:,None,None,None]*generic_yes_effect[None,:,None,:]
    b=a*3
    before=json.dumps(json_ready(fit),sort_keys=True)
    output=evaluate_bias_diagnostics(a,b,rows,fit)
    local=output['locations']['answer']
    assert local['truth_oriented']['descriptive']['combined']['mean']==pytest.approx(1.)
    for view in ('yes_oriented','within_label'):
        summary=local[view]['descriptive']['combined']
        assert summary['mean'] is None
        assert summary['n_valid_wrappers']==0
        assert summary['status']=='NO_IDENTIFIABLE_VARIATION'
        assert all(x['finite_neuron_task_mode_cells']==0 for x in local[view]['support']['combined'].values())
        assert local[view]['descriptive']['random']['mean'] is None
    assert json.dumps(json_ready(fit),sort_keys=True)==before


def test_real_within_label_variation_is_preserved_and_neutral_modes_rejected():
    rows,fit=fixture()
    rng=np.random.default_rng(1)
    a=rng.normal(size=(len(rows),2,1,3))
    output=evaluate_bias_diagnostics(a,a*2,rows,fit)
    for view in ('truth_oriented','yes_oriented','within_label'):
        assert output['locations']['answer'][view]['descriptive']['combined']['mean']==pytest.approx(1.)
    bad=copy.deepcopy(fit);bad['modes']=['zero','mean','scale_1']
    with pytest.raises(ValueError):evaluate_bias_diagnostics(a,a,rows,bad)
    bad=copy.deepcopy(fit);bad['fit_split']='D4'
    with pytest.raises(ValueError):evaluate_bias_diagnostics(a,a,rows,bad)


def test_insufficient_within_label_sample_is_missing_not_zero():
    rows,fit=fixture()
    # Each task/wrapper now has only two examples of each truth label.
    take=[i for i,r in enumerate(rows) if int(r['id'].split('-')[-1])<4]
    rows=[rows[i] for i in take]
    a=np.random.default_rng(5).normal(size=(len(rows),2,1,3))
    result=evaluate_bias_diagnostics(a,a,rows,fit)
    assert result['locations']['answer']['truth_oriented']['descriptive']['combined']['mean']==pytest.approx(1.)
    assert result['locations']['answer']['within_label']['descriptive']['combined']['mean'] is None
