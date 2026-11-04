"""Post-hoc proxy ablation requested after v2 D3 results were observed.

Fits the original four-concept pooled-SD truth proxy on v2 D2, then compares it
with the frozen expanded proxy on identical candidates and within-task D3
metric. This is exploratory and never enters the primary confirmatory family.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .alignment import semantic_fingerprint, cosine_similarity, match_neurons
from .followup_analysis import within_task_correlation_matrices, _mapped_score, json_ready
from .followup_alignment_runner import (ROOT, PAIRS, POSITIONS, SEEDS, load_rows,
    load_measurements, write_once, _shared, _candidate_identity, _sha)
from .statistics import cluster_bootstrap


def old_proxy_fit(a,b,records):
    if any(row.get('split') != 'D2' for row in records):
        raise ValueError('Four-dimensional proxy may be fitted on D2 only')
    concepts = sorted({row['concept'] for row in records})
    if len(concepts) != 4:
        raise ValueError('This ablation requires the original four concept categories')
    fa = semantic_fingerprint(a,records,concepts=concepts)
    fb = semantic_fingerprint(b,records,concepts=concepts)
    mapping = match_neurons(cosine_similarity(fa,fb))
    return dict(mapping=mapping,features_a=fa,features_b=fb,concept_order=concepts,
                fit_split='D2',posthoc_after_D3_observed=True,
                definition='Original four pooled-within-label-SD positive/negative truth contrasts')


def run_ablation(run,data,pairs=PAIRS,positions=POSITIONS):
    run = Path(run)
    output = run/'exploratory_proxy_ablation'
    d2,d3 = load_rows(data,'D2'),load_rows(data,'D3')
    summaries,cohort_values = [],{}
    primary_before = _sha(run/'alignment/summary.json')
    for pair in pairs:
        left,right = pair
        cohort = 'independent_seeds' if left in SEEDS else 'cross_family'
        m2a,a2,r2 = load_measurements(run/'collections'/left/'final/D2',d2)
        m2b,b2,_ = load_measurements(run/'collections'/right/'final/D2',d2)
        m3a,a3,r3 = load_measurements(run/'collections'/left/'final/D3',d3)
        m3b,b3,_ = load_measurements(run/'collections'/right/'final/D3',d3)
        _shared(a2,b2);_shared(a3,b3)
        if _candidate_identity(a2)!=_candidate_identity(a3) or _candidate_identity(b2)!=_candidate_identity(b3):
            raise ValueError('Candidate set changed between D2 and D3')
        for position in positions:
            main = run/'alignment'/('_'.join(pair))/position
            frozen = json.loads((main/'fit.json').read_text())
            measured = json.loads((main/'eval.json').read_text())
            fit = old_proxy_fit(a2[position+'_product'],b2[position+'_product'],r2)
            fit.update(pair=list(pair),position=position,source=dict(
                D2_a_sha256=m2a['measurements_sha256'],D2_b_sha256=m2b['measurements_sha256'],
                candidates_a=_candidate_identity(a2),candidates_b=_candidate_identity(b2)))
            out = output/('_'.join(pair))/position
            write_once(out/'fit.json',fit)
            matrices = within_task_correlation_matrices(a3[position+'_product'],b3[position+'_product'],r3)
            old_scores = {g:_mapped_score(c,fit['mapping']) for g,c in matrices.items()}
            expanded = frozen['mappings']['semantic__flexible__hungarian']
            expanded_replay = {g:_mapped_score(c,expanded) for g,c in matrices.items()}
            expanded_saved = measured['wrapper_scores']['semantic__flexible__hungarian']
            for group in expanded_saved:
                if expanded_saved[group] is None or expanded_replay[group] is None:
                    if expanded_saved[group] != expanded_replay[group]:
                        raise ValueError('Expanded proxy replay support differs')
                elif not np.isclose(expanded_saved[group],expanded_replay[group],rtol=0,atol=1e-14):
                    raise ValueError('Expanded proxy replay failed')
            valid = [g for g in old_scores if old_scores[g] is not None and expanded_saved[g] is not None]
            if len(valid)!=len(matrices):
                raise ValueError('Cannot silently drop missing wrappers in proxy contrast')
            differences = {g:expanded_saved[g]-old_scores[g] for g in valid}
            desc = dict(old_four_dimensional=float(np.mean(list(old_scores.values()))),
                        expanded=float(np.mean(list(expanded_saved.values()))),
                        expanded_minus_old=float(np.mean(list(differences.values()))))
            by_task = {}
            for concept in sorted({r['concept'] for r in r3}):
                task_cells = {g:{c:m for c,m in cells.items() if c==concept} for g,cells in matrices.items()}
                old_task = {g:_mapped_score(c,fit['mapping']) for g,c in task_cells.items()}
                old_values = [x for x in old_task.values() if x is not None]
                new_mean = measured['by_task'][concept]['descriptive']['semantic__flexible__hungarian']['mean']
                old_mean = float(np.mean(old_values)) if len(old_values)==len(old_task) else None
                by_task[concept] = dict(old_mean=old_mean,expanded_mean=new_mean,
                                        expanded_minus_old=new_mean-old_mean if new_mean is not None and old_mean is not None else None,
                                        both_competence_passed=measured['task_competence'][concept]['both_passed'])
            result = dict(status='POST_HOC_EXPLORATORY',pair=list(pair),cohort=cohort,position=position,
                          fit_split='D2',evaluation_split='D3',fitted_after_D3_observed=True,
                          wrapper_scores=dict(old_four_dimensional=old_scores,expanded=expanded_saved,
                                              expanded_minus_old=differences),descriptive=desc,by_task=by_task,
                          reused_baselines={k:measured['descriptive'][k] for k in
                                            ('activation__flexible__hungarian','random__flexible')},
                          source=dict(fit_sha256=_sha(out/'fit.json'),
                                      D3_a_sha256=m3a['measurements_sha256'],D3_b_sha256=m3b['measurements_sha256'],
                                      expanded_fit_sha256=_sha(main/'fit.json'),primary_eval_sha256=_sha(main/'eval.json')),
                          limitations=['Requested after D3 observations: exploratory only; not a new independent confirmation.',
                                       'Controls data/candidates/metric for this proxy contrast only.',
                                       'Cannot attribute the overall pilot-v1 to followup-v2 difference solely to the semantic proxy.',
                                       'Existing repeated-random baseline reused; no new random realization selected.'])
            write_once(out/'comparison.json',result)
            cohort_values.setdefault((cohort,position),[]).append(differences)
            summaries.append(dict(pair=list(pair),cohort=cohort,position=position,descriptive=desc,
                                  path=str((out/'comparison.json').relative_to(run)),sha256=_sha(out/'comparison.json')))
            print(json.dumps(dict(stage='posthoc_proxy_ablation',pair=list(pair),position=position,**desc)),flush=True)
    cohorts = {}
    for (cohort,position),vectors in cohort_values.items():
        groups = sorted(vectors[0])
        if any(sorted(v)!=groups for v in vectors):
            raise ValueError('Pair wrapper support differs')
        joint = np.mean([[v[g] for g in groups] for v in vectors],axis=0)
        cohorts[f'{cohort}/{position}'] = dict(n_pairs=len(vectors),n_wrappers=len(groups),
            expanded_minus_old=cluster_bootstrap(joint,groups,n_boot=5000,seed=1729),
            wrapper_effects=dict(zip(groups,joint)),
            inference_scope='Exploratory, fixed observed models; pairs retained jointly within each wrapper',
            no_confirmatory_pvalue=True)
    assert _sha(run/'alignment/summary.json') == primary_before
    summary = dict(stage='F3_POST_HOC_PROXY_ABLATION',status='EXPLORATORY_MEASURED',
                   expected_comparisons=26,n_comparisons=len(summaries),comparisons=summaries,
                   cohorts=cohorts,excluded_from_confirmatory_family=True,
                   full_protocol_complete=len(summaries)==26,
                   primary_summary_sha256_unchanged=primary_before,
                   D4_read=False,random_controls_reused=True,
                   interpretation='A matched v2 proxy ablation; does not isolate every change between pilot-v1 and followup-v2.')
    if len(summaries)==26:
        write_once(output/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=ROOT/'results/followup-v2')
    parser.add_argument('--data',type=Path,default=ROOT/'data/followup-v2')
    args=parser.parse_args()
    result=run_ablation(args.root,args.data)
    print(json.dumps(dict(complete=result['full_protocol_complete'],n_comparisons=result['n_comparisons'])),flush=True)


if __name__=='__main__':
    main()
