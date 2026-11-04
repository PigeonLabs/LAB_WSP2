"""Supplementary answer-bias diagnostics using the SAME frozen F4 maps.

Written before real D4 observation. No map, unit, mixture weight, threshold, or
primary test is selected here. For binary yes/no candidates, multiplying the
truth-oriented effect by (2*label-1) gives the effect on yes-versus-no log odds.
A generic answer bias can produce apparent truth-oriented correspondence; the
within-label diagnostic removes between-label variation from that correlation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .followup_analysis import (_effect_array, _effect_cells, _mapped_score,
                               _metadata, json_ready)
from .followup_alignment_runner import (ROOT, PAIRS, SEEDS, PRIMARY_CAUSAL_MODES,
    load_rows, load_measurements, write_once, _sha, _shared, wilson_gate)
from .statistics import cluster_bootstrap


DIAGNOSTIC_VERSION = 'answer-bias-diagnostic-v1'
DIAGNOSTIC_SETTINGS = dict(primary_modes=['zero','mean','patch'],
    minimum_examples_per_cell=3,constant_standard_deviation_tolerance=1e-10,
    task_and_mode_weighting='equal',random_maps='reuse frozen D2 maps',
    orientation='truth effect times (2*label-1)',
    within_label='concept crossed with binary truth label',
    cohort_bootstrap_replicates=5000,cohort_bootstrap_seed=1729)


def _analysis_provenance():
    return dict(analysis_version=DIAGNOSTIC_VERSION,analysis_settings=DIAGNOSTIC_SETTINGS,
                analysis_code_sha256=_sha(Path(__file__)),
                numerical_helper_sha256=_sha(Path(__file__).with_name('followup_analysis.py')))


def _measurement(cells,mappings,random_mappings):
    scores,support = {},{}
    for name,mapping in mappings.items():
        rows,cols = np.asarray(mapping['source'],int),np.asarray(mapping['target'],int)
        scores[name] = {group:_mapped_score(matrices,mapping) for group,matrices in cells.items()}
        support[name] = {}
        for group,matrices in cells.items():
            eligible = len(rows)*len(matrices)
            finite = sum(int(np.isfinite(matrix[rows,cols]).sum()) for matrix in matrices.values())
            support[name][group] = dict(finite_neuron_task_mode_cells=finite,
                                        eligible_neuron_task_mode_cells=eligible,
                                        invalid_constant_or_insufficient_cells=eligible-finite,
                                        finite_fraction=finite/eligible if eligible else None)
    random_draws = [{group:_mapped_score(matrices,mapping) for group,matrices in cells.items()}
                    for mapping in random_mappings]
    scores['random'] = {}
    for group in cells:
        values = [draw[group] for draw in random_draws if draw[group] is not None]
        scores['random'][group] = float(np.mean(values)) if values else None
    random_means = []
    for draw in random_draws:
        valid = [v for v in draw.values() if v is not None]
        random_means.append(float(np.mean(valid)) if valid else None)
    descriptive = {}
    for name,wrapper_scores in scores.items():
        valid = [v for v in wrapper_scores.values() if v is not None]
        descriptive[name] = dict(mean=float(np.mean(valid)) if valid else None,
                                  n_valid_wrappers=len(valid),n_wrappers=len(wrapper_scores),
                                  status='NO_IDENTIFIABLE_VARIATION' if not valid else
                                         'PARTIAL_WRAPPER_SUPPORT' if len(valid)<len(wrapper_scores) else 'DESCRIPTIVE')
    return dict(wrapper_scores=scores,descriptive=descriptive,support=support,
                random_controls=dict(n_frozen_draws=len(random_draws),draw_means=random_means),
                metric='within-task and wrapper Pearson; core intervention modes equally weighted')


def evaluate_bias_diagnostics(effects_a,effects_b,records,fitted,*,split='D4'):
    """Return three views without modifying maps or using test information to fit.

    within_label retains truth orientation but treats concept x truth as a cell;
    balanced labels give equal label weight. For binary labels, Pearson within
    each label is invariant to the shared sign change to yes orientation.
    """
    if split!='D4' or fitted.get('fit_split')!='D2':
        raise ValueError('Diagnostics require D4 and frozen D2 maps')
    if list(fitted.get('modes',[])) != list(PRIMARY_CAUSAL_MODES):
        raise ValueError('Diagnostic primary modes must be zero/mean/patch only')
    a,b = _effect_array(effects_a),_effect_array(effects_b)
    concepts,labels,groups,_ = _metadata(records,len(a),split)
    locations = fitted.get('location_order',list(fitted['locations']))
    if a.shape[0]!=b.shape[0] or a.shape[2:]!=b.shape[2:] or a.shape[2]!=len(locations) or a.shape[-1]!=3:
        raise ValueError('Effects disagree with frozen locations/core modes')
    # Dataset-oracle labels identify answer orientation, not selected outcomes.
    orientation = (2*labels-1)[:,None,None]
    within_rows = [dict(r,concept=f'{r["concept"]}|truth={r["label"]}') for r in records]
    output = {}
    for index,name in enumerate(locations):
        fit = fitted['locations'][name]
        if len(fit['random_mappings'])<100:
            raise ValueError('At least 100 frozen random controls required')
        left,right = a[:,:,index],b[:,:,index]
        views = {
            'truth_oriented':_effect_cells(left,right,records,'D4'),
            'yes_oriented':_effect_cells(left*orientation,right*orientation,records,'D4'),
            'within_label':_effect_cells(left,right,within_rows,'D4'),
        }
        output[name] = {view:_measurement(cells,fit['mappings'],fit['random_mappings'])
                        for view,cells in views.items()}
    return dict(status='SUPPLEMENTARY_ANSWER_BIAS_DIAGNOSTIC',locations=output,
                fit_split='D2',evaluation_split='D4',maps_refitted=False,
                primary_modes=list(PRIMARY_CAUSAL_MODES),excluded_from_confirmatory_family=True,
                direction_transform='yes_oriented = truth_oriented * (2*label - 1)',
                limitations=['Diagnostic views are not new primary endpoints and have no confirmatory p-values.',
                             'Constant or fewer-than-three-example cells remain undefined, never zero evidence.',
                             'Views can have different identifiable unit/cell support; inspect support counts.',
                             'Within-label attenuation is consistent with answer-orientation confounding, not proof of its exclusive cause.',
                             'Task competence remains necessary for functional conservation claims.'])


def _joint_descriptive(evaluations,view,method):
    """Conditional wrapper uncertainty only; no pair-level pseudoreplication."""
    names = sorted(evaluations)
    groups = sorted(evaluations[names[0]][view]['wrapper_scores'][method])
    vectors = []
    missing_pairs = []
    for pair in names:
        scores = evaluations[pair][view]['wrapper_scores'][method]
        if sorted(scores)!=groups:
            raise ValueError('Do not silently intersect diagnostic wrapper supports')
        if any(scores[g] is None for g in groups):
            missing_pairs.append(pair)
        else:
            vectors.append([scores[g] for g in groups])
    if missing_pairs:
        return dict(mean=None,ci=None,status='INCOMPLETE_IDENTIFIABLE_SUPPORT',
                    missing_pairs=missing_pairs,n_pairs=len(names),n_wrappers=len(groups))
    average = np.mean(vectors,0)
    result = cluster_bootstrap(average,groups,n_boot=5000,seed=1729)
    result.update(n_pairs=len(names),descriptive_only=True,pairs_resampled_independently=False)
    return result


def run_diagnostics(run,data,pairs=PAIRS):
    run = Path(run)
    manifest_path = run/'causal_alignment/fit_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get('full_protocol_complete') or manifest.get('n_fits')!=26:
        raise ValueError('All 26 F4 fits must be frozen before diagnostics')
    for entry in manifest['fits']:
        if _sha(run/entry['path'])!=entry['sha256']:
            raise ValueError('Frozen causal fit checksum mismatch')
    # Independent pair subsets may run while other models are still collecting.
    # The global completion summary still requires all 26 pair/kind outputs.
    for model in sorted({x for pair in pairs for x in pair}):
        if not (run/'causal'/model/'D4/manifest.json').exists():
            raise ValueError(f'D4 not complete for {model}')
    canonical = load_rows(data,'D4')
    output = run/'exploratory_causal_diagnostics'
    completed,cohorts = [],{}
    for pair in pairs:
        left,right = pair
        cohort = 'independent_seeds' if left in SEEDS else 'cross_family'
        ma,a,rows = load_measurements(run/'causal'/left/'D4',canonical,causal=True)
        mb,b,_ = load_measurements(run/'causal'/right/'D4',canonical,causal=True)
        _shared(a,b)
        gate_a,gate_b = wilson_gate(a['margins'],a['concepts']),wilson_gate(b['margins'],b['concepts'])
        for kind in ('single','group'):
            fitpath = run/'causal_alignment'/('_'.join(pair))/kind/'fit.json'
            fitted = json.loads(fitpath.read_text())
            for key,array in [('unit_ids_a',a['unit_ids']),('unit_ids_b',b['unit_ids']),
                              ('modes',a['modes']),('locations',a['locations'])]:
                if fitted['source'][key]!=array.tolist():
                    raise ValueError('D4 unit/mode/location identity differs from frozen fit')
            if not np.array_equal(a['locations'],b['locations']) or not np.array_equal(a['modes'],b['modes']):
                raise ValueError('Model mode/location ordering differs')
            core = fitted['source']['primary_mode_indices']
            aa = a['effects'][:,fitted['unit_indices_a']][...,core]
            bb = b['effects'][:,fitted['unit_indices_b']][...,core]
            path=output/('_'.join(pair))/kind/'diagnostics.json'
            source=dict(effects_sha256_a=ma['effects_sha256'],effects_sha256_b=mb['effects_sha256'],
                        frozen_fit_sha256=_sha(fitpath),fit_manifest_sha256=_sha(manifest_path),
                        **_analysis_provenance())
            if path.exists():
                result=json.loads(path.read_text())
                if result.get('source')!=source:
                    raise ValueError('Existing diagnostic source checksum mismatch')
            else:
                result = evaluate_bias_diagnostics(aa,bb,rows,fitted)
                result.update(pair=list(pair),unit_kind=kind,cohort=cohort,
                              task_competence={c:dict(model_a=gate_a[c],model_b=gate_b[c],
                                                     both_passed=gate_a[c]['passed'] and gate_b[c]['passed']) for c in gate_a},
                              source=source)
                write_once(path,result)
            for location,views in result['locations'].items():
                cohorts.setdefault((cohort,kind,location),{})['_'.join(pair)]=views
            completed.append(dict(pair=list(pair),unit_kind=kind,path=str(path.relative_to(run)),sha256=_sha(path),
                locations={location:{view:values['descriptive'] for view,values in views.items()}
                           for location,views in result['locations'].items()}))
            print(json.dumps(dict(stage='supplementary_causal_diagnostics',pair=list(pair),kind=kind)),flush=True)
    cohort_summary={}
    for (cohort,kind,location),pairs_ in cohorts.items():
        cohort_summary[f'{cohort}/{kind}/{location}'] = {
            view:{method:_joint_descriptive(pairs_,view,method) for method in ('semantic','causal','combined','random')}
            for view in ('truth_oriented','yes_oriented','within_label')}
    # Recheck every frozen map: a diagnostic must never change the intervention fit.
    for entry in manifest['fits']:
        assert _sha(run/entry['path'])==entry['sha256']
    summary=dict(stage='SUPPLEMENTARY_CAUSAL_ANSWER_BIAS_DIAGNOSTICS',status='MEASURED_DESCRIPTIVE',
                 evaluations=completed,n_evaluations=len(completed),expected_evaluations=26,
                 full_protocol_complete=len(completed)==26,cohorts=cohort_summary,
                 excluded_from_confirmatory_family=True,maps_refitted=False,
                 fit_manifest_sha256_unchanged=_sha(manifest_path),
                 interpretation='Compare identifiable correlation support and response orientation; no new primary claims.')
    if len(completed)==26:
        write_once(output/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=ROOT/'results/followup-v2')
    parser.add_argument('--data',type=Path,default=ROOT/'data/followup-v2')
    args=parser.parse_args()
    result=run_diagnostics(args.root,args.data)
    print(json.dumps(dict(complete=result['full_protocol_complete'],n_evaluations=result['n_evaluations'])),flush=True)


if __name__=='__main__':
    main()
