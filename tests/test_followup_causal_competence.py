"""Constructed descriptive aggregation fixtures, never real/partial D4 outcomes."""
import copy
import itertools
import json
from pathlib import Path
import numpy as np
import pytest
from scripts.followup_causal_competence import (CONCEPTS,KINDS,METHODS,POSITIONS,
    sha_file,load_complete_evidence,aggregate,render_report,validate_gate)
from src.followup_alignment_runner import wilson_gate


def make_fixture(root):
    seeds=[101,211,307,401,503];names=[f'seed{x}' for x in seeds]
    (root/'configs').mkdir();(root/'configs/followup_v2.json').write_text(json.dumps({'training':{'seeds':seeds}}))
    run=root/'results/followup-v2';entries=[]
    cohorts={'independent_seeds':list(itertools.combinations(names,2)),
             'cross_family':list(itertools.combinations(('qwen','smol','olmo'),2))}
    for cohort,pairs in cohorts.items():
        for index,pair in enumerate(pairs):
            for kind in KINDS:
                gates={}
                for concept in CONCEPTS:
                    members=[]
                    for name in pair:
                        passed=concept in ('comparison','syntax') or concept=='arithmetic' and name in names[:2]
                        wins=80 if passed else 50;margins=np.array([1.]*wins+[-1.]*(100-wins))
                        members.append(wilson_gate(margins,np.array([concept]*100))[concept])
                    gates[concept]={'model_a':members[0],'model_b':members[1],'both_passed':members[0]['passed'] and members[1]['passed']}
                by_task={}
                for concept in CONCEPTS:
                    by_task[concept]={'locations':{}}
                    for position in POSITIONS:
                        descriptors={}
                        for method in METHODS:
                            missing=concept=='arithmetic' and index==0 and method=='causal'
                            valid=0 if missing else 12 if index==0 and method=='semantic' else 24
                            descriptors[method]={'mean':None if missing else .1+index*.01,'n_valid_wrappers':valid,'n_wrappers':24}
                        by_task[concept]['locations'][position]={'descriptive':descriptors}
                evidence={'pair':list(pair),'cohort':cohort,'unit_kind':kind,'evaluation_split':'D4','fit_split':'D2',
                    'task_competence':gates,'competent_tasks':sorted(c for c in CONCEPTS if gates[c]['both_passed']),'by_task':by_task}
                relative=Path('causal_alignment')/'_'.join(pair)/kind/'eval.json';path=run/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(evidence))
                entries.append({'pair':list(pair),'unit_kind':kind,'path':str(relative),'sha256':sha_file(path)})
    summary={'full_protocol_complete':True,'n_evaluations':26,'expected_evaluations':26,'evaluations':entries}
    (run/'causal_alignment/summary.json').write_text(json.dumps(summary))
    return run


def find_row(result,cohort='independent_seeds',concept='arithmetic',subset='all_pairs'):
    return next(r for r in result['rows'] if r['cohort']==cohort and r['unit_kind']=='single' and r['position']=='answer' and r['concept']==concept and r['subset']==subset)


def test_fixed26_sources_and64_strata_keep_missing_support(tmp_path):
    make_fixture(tmp_path)
    evidence,summary,sources=load_complete_evidence(tmp_path);result=aggregate(evidence,summary,sources)
    assert result['n_source_evaluations']==26 and result['n_strata']==64
    all_pairs=find_row(result)
    assert all_pairs['methods']['semantic']['mean']==pytest.approx(.145)
    assert all_pairs['methods']['semantic']['n_complete_wrapper_pairs']==9
    assert all_pairs['methods']['semantic']['n_valid_wrapper_cells']==228
    assert all_pairs['methods']['causal']['mean']==pytest.approx(.15)
    assert all_pairs['methods']['causal']['n_available_pairs']==9
    assert all_pairs['methods']['causal']['n_missing_pairs']==1
    eligible=find_row(result,subset='both_passed')
    assert eligible['n_pairs_in_subset']==1 and eligible['methods']['semantic']['mean']==pytest.approx(.1)
    assert eligible['methods']['causal']['mean'] is None
    assert eligible['methods']['causal']['n_missing_pairs']==1
    empty=find_row(result,cohort='cross_family',concept='negation',subset='both_passed')
    assert empty['n_pairs_in_subset']==0
    assert all(v['mean'] is None and v['wrapper_coverage_fraction'] is None for v in empty['methods'].values())
    assert result['new_tests_or_intervals'] is False and result['primary_family_modified'] is False
    markdown=render_report(result)
    assert 'HARD_STRESS_REPORT.md' in markdown and 'N/A' in markdown
    assert len([line for line in markdown.splitlines() if line.startswith('| arithmetic |')])==16


def test_partial_summary_refused_before_any_eval_read(tmp_path):
    folder=tmp_path/'results/followup-v2/causal_alignment';folder.mkdir(parents=True)
    (folder/'summary.json').write_text(json.dumps({'full_protocol_complete':False,'n_evaluations':1,'evaluations':[{'path':'missing.json'}]}))
    with pytest.raises(RuntimeError,match='all26'):load_complete_evidence(tmp_path)
    assert not (folder/'competence_descriptive.json').exists()


def test_evaluation_hash_and_gate_corruption_are_rejected(tmp_path):
    run=make_fixture(tmp_path);summary_path=run/'causal_alignment/summary.json';summary=json.loads(summary_path.read_text())
    path=run/summary['evaluations'][0]['path'];evidence=json.loads(path.read_text())
    evidence['task_competence']['syntax']['both_passed']=False;path.write_text(json.dumps(evidence))
    with pytest.raises(ValueError,match='hash mismatch'):load_complete_evidence(tmp_path)
    summary['evaluations'][0]['sha256']=sha_file(path);summary_path.write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='Both-passed'):load_complete_evidence(tmp_path)


def test_duplicate_pair_kind_cannot_fake_completion(tmp_path):
    run=make_fixture(tmp_path);path=run/'causal_alignment/summary.json';summary=json.loads(path.read_text())
    summary['evaluations'][-1]=copy.deepcopy(summary['evaluations'][0]);path.write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='duplicate'):load_complete_evidence(tmp_path)
