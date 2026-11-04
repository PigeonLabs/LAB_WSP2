import copy
import hashlib
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


def test_subset_readiness_and_reuse_require_requested_models_and_current_provenance(tmp_path,monkeypatch):
    from src import followup_causal_diagnostics as diagnostic
    from src.followup_alignment_runner import PAIRS
    rows,template=fixture()
    data=tmp_path/'data';data.mkdir()
    (data/'D4.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    entries=[]
    for pair in PAIRS:
        for kind,index in [('single',0),('group',1)]:
            fit=copy.deepcopy(template)
            fit.update(unit_indices_a=[index],unit_indices_b=[index],source=dict(
                unit_ids_a=['u0','u1'],unit_ids_b=['u0','u1'],modes=['zero','mean','patch'],
                locations=['answer'],primary_mode_indices=[0,1,2]))
            local=fit['locations']['answer']
            single=dict(source=[0],target=[0])
            local['mappings']={k:copy.deepcopy(single) for k in ('semantic','causal','combined')}
            local['random_mappings']=[copy.deepcopy(single) for _ in range(100)]
            path=tmp_path/'causal_alignment'/('_'.join(pair))/kind/'fit.json'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(json_ready(fit)))
            entries.append(dict(path=str(path.relative_to(tmp_path)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest=tmp_path/'causal_alignment/fit_manifest.json'
    manifest.write_text(json.dumps(dict(full_protocol_complete=True,n_fits=26,fits=entries)))
    arrays=dict(effects=np.random.default_rng(9).normal(size=(len(rows),2,1,3)),
                row_ids=np.array([r['id'] for r in rows]),groups=np.array([r['group_id'] for r in rows]),
                concepts=np.array([r['concept'] for r in rows]),labels=np.array([r['label'] for r in rows]),
                margins=np.ones(len(rows)),unit_ids=np.array(['u0','u1']),locations=np.array(['answer']),
                modes=np.array(['zero','mean','patch']))
    for name in ('seed101','seed211'):
        path=tmp_path/'causal'/name/'D4';path.mkdir(parents=True)
        np.savez(path/'effects.npz',**arrays)
        (path/'manifest.json').write_text(json.dumps(dict(effects_sha256=hashlib.sha256((path/'effects.npz').read_bytes()).hexdigest())))
    # Other six model manifests intentionally do not exist: this pair is independent.
    result=diagnostic.run_diagnostics(tmp_path,data,pairs=[('seed101','seed211')])
    assert result['n_evaluations']==2 and not result['full_protocol_complete']
    assert not (tmp_path/'exploratory_causal_diagnostics/summary.json').exists()
    def refuse_recalculation(*args,**kwargs):
        raise AssertionError('Unchanged verified diagnostic should have been reused')
    monkeypatch.setattr(diagnostic,'evaluate_bias_diagnostics',refuse_recalculation)
    replay=diagnostic.run_diagnostics(tmp_path,data,pairs=[('seed101','seed211')])
    assert json_ready(replay)==json_ready(result)
    monkeypatch.setattr(diagnostic,'DIAGNOSTIC_VERSION','changed-settings-version')
    with pytest.raises(ValueError,match='source checksum mismatch'):
        diagnostic.run_diagnostics(tmp_path,data,pairs=[('seed101','seed211')])
    monkeypatch.setattr(diagnostic,'DIAGNOSTIC_VERSION','answer-bias-diagnostic-v1')
    path=tmp_path/'causal/seed101/D4'
    arrays['effects'][0,0,0,0]+=1
    np.savez(path/'effects.npz',**arrays)
    (path/'manifest.json').write_text(json.dumps(dict(effects_sha256=hashlib.sha256((path/'effects.npz').read_bytes()).hexdigest())))
    with pytest.raises(ValueError,match='source checksum mismatch'):
        diagnostic.run_diagnostics(tmp_path,data,pairs=[('seed101','seed211')])
    (tmp_path/'causal/seed211/D4/manifest.json').unlink()
    with pytest.raises(ValueError,match='D4 not complete for seed211'):
        diagnostic.run_diagnostics(tmp_path,data,pairs=[('seed101','seed211')])
