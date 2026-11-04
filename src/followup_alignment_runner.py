"""CPU-only F3/F4 fitting and replay from preserved measurement arrays.

Run fit before D3 collection; run causal-fit before D4 collection. Existing
evidence is never silently replaced. JSON includes frozen maps and raw random
controls; compact summaries reference those files instead of duplicating them.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import time
from pathlib import Path

import numpy as np

from .followup_analysis import (fit_pair, evaluate_pair, aggregate_pairs, json_ready,
    expanded_semantic_profile, fit_causal_alignment, evaluate_causal_alignment,
    dose_response_diagnostics)
from .alignment import cosine_similarity


SEEDS = ['seed101', 'seed211', 'seed307', 'seed401', 'seed503']
BASES = ['qwen', 'smol', 'olmo']
PAIRS = list(itertools.combinations(SEEDS, 2))+list(itertools.combinations(BASES, 2))
POSITIONS = ('answer', 'span')
PRIMARY_CAUSAL_MODES = ('zero','mean','patch')
ROOT = Path(__file__).resolve().parents[1]


def write_once(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(json_ready(obj), indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f'Refusing to overwrite divergent evidence: {path}')
    else:
        path.write_text(text)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def annotate_subtype(row):
    """Fixed semantic-input annotations; never inspect activation or answer truth."""
    row = dict(row)
    semantic = row.get('semantic', {})
    if 'subtype' in row:
        return row
    concept = row['concept']
    if concept == 'arithmetic' and {'a', 'b'} <= semantic.keys():
        subtype = 'ones_carry' if semantic['a'] % 10+semantic['b'] % 10 >= 10 else 'no_ones_carry'
    elif concept == 'comparison':
        subtype = str(semantic.get('relation', 'all'))
    elif concept == 'negation':
        ast = semantic.get('ast')
        subtype = str(ast[0]) if isinstance(ast, list) and ast else 'atomic'
    elif concept == 'syntax':
        subtype = 'curly_present' if '{' in semantic.get('brackets', '') else 'curly_absent'
    else:
        subtype = 'all'
    row['subtype'] = subtype
    return row


def load_rows(data, split):
    return [annotate_subtype(json.loads(line)) for line in (Path(data)/f'{split}.jsonl').read_text().splitlines()]


def load_measurements(directory, canonical_rows, *, causal=False):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    filename, hashkey = ('effects.npz', 'effects_sha256') if causal else ('measurements.npz', 'measurements_sha256')
    raw = directory/filename
    if _sha(raw) != manifest[hashkey]:
        raise ValueError(f'Checksum mismatch: {raw}')
    with np.load(raw, allow_pickle=False) as npz:
        arrays = {k: npz[k] for k in npz.files}
    by_id = {r['id']:r for r in canonical_rows}
    ids = arrays['row_ids'].tolist()
    if len(set(ids)) != len(ids) or not set(ids) <= by_id.keys():
        raise ValueError('Unknown or duplicate observation IDs')
    rows = [by_id[identity] for identity in ids]
    for field, key in [('concepts','concept'), ('labels','label'), ('groups','group_id')]:
        if not np.array_equal(arrays[field], np.asarray([r[key] for r in rows])):
            raise ValueError(f'Canonical metadata mismatch: {field}')
    return manifest, arrays, rows


def _shared(a, b):
    if not np.array_equal(a['row_ids'], b['row_ids']):
        raise ValueError('Pair models must be evaluated on identically ordered original items')


def _candidate_identity(arrays):
    return dict(layers=arrays['layers'].tolist(), neuron_ids=arrays['neuron_ids'].tolist())


def _provenance(ma, mb, a, b):
    return dict(measurements_sha256_a=ma['measurements_sha256'],
                measurements_sha256_b=mb['measurements_sha256'],
                candidates_a=_candidate_identity(a), candidates_b=_candidate_identity(b))


def _fit_path(run, pair, position):
    return Path(run)/'alignment'/('_'.join(pair))/position/'fit.json'


def fit_all(run, data, pairs=PAIRS, positions=POSITIONS):
    run = Path(run)
    rows = load_rows(data, 'D2')
    completed = []
    for pair in pairs:
        left, right = pair
        ma,a,rs = load_measurements(run/'collections'/left/'final/D2',rows)
        mb,b,_ = load_measurements(run/'collections'/right/'final/D2',rows)
        _shared(a,b)
        provenance = _provenance(ma,mb,a,b)
        for position in positions:
            path = _fit_path(run,pair,position)
            if path.exists():
                fit = json.loads(path.read_text())
                if fit.get('source') != provenance:
                    raise ValueError(f'Existing fit input identity changed: {path}')
            else:
                then = time.monotonic()
                signed = (dict(signs_a=a['answer_sign_regime'],signs_b=b['answer_sign_regime'])
                          if position == 'answer' else
                          dict(route_products_a=a['span_product_by_sign'],route_products_b=b['span_product_by_sign']))
                fit = fit_pair(a[position+'_product'],b[position+'_product'],rs,
                               layers_a=a['layers'],layers_b=b['layers'],**signed)
                fit.update(source=provenance, pair=list(pair), position=position,
                           protocol='followup-v2', fit_checkpoint='final',
                           reuse_policy='Same final-D2 fit on fixed final-D1 candidates for initial/middle/final D3 trajectory',
                           semantic_subtypes='Fixed input-derived carry/relation/root-operator/bracket-kind categories')
                write_once(path,fit)
                print(json.dumps(dict(stage='F3 fit',pair=list(pair),position=position,
                                      seconds=round(time.monotonic()-then,3),path=str(path))),flush=True)
            completed.append(dict(pair=list(pair),position=position,path=str(path.relative_to(run)),sha256=_sha(path)))
    manifest = dict(stage='F3',status='D2_MAPS_FROZEN',n_fits=len(completed),fits=completed,
                    test_data_used=False,expected_full_fits=26,
                    full_protocol_complete=len(completed)==26)
    # A subset invocation never declares the full freeze complete.
    if len(completed) == 26:
        write_once(run/'alignment/fit_manifest.json',manifest)
    return manifest


def wilson_gate(margins, concepts, *, minimum=.70):
    margins, concepts = np.asarray(margins), np.asarray(concepts)
    output = {}
    z = 1.959963984540054
    for concept in sorted(set(concepts.tolist())):
        values = margins[concepts == concept]
        n = len(values)
        wins = int((values > 0).sum())
        p = wins/n
        center = (p+z*z/(2*n))/(1+z*z/n)
        half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
        output[concept] = dict(n=n,correct=wins,accuracy=p,wilson95=[center-half,center+half],
                               passed=bool(p >= minimum and center-half > .5),
                               ties_counted_incorrect=int((values == 0).sum()))
    return output


def _compact_eval(evaluation):
    return {key:value for key,value in evaluation.items() if key != 'random_controls'}


def _primary_contrasts():
    return {'activation_minus_random':('activation__flexible__hungarian','random__flexible'),
            'semantic_minus_activation':('semantic__flexible__hungarian','activation__flexible__hungarian')}


def evaluate_all(run, data, pairs=PAIRS, positions=POSITIONS, checkpoints=('final','initial','middle')):
    run = Path(run)
    rows = load_rows(data, 'D3')
    evaluations = {}
    confirmatory = {}
    completed = []
    for pair in pairs:
        left,right = pair
        cohort = 'independent_seeds' if left in SEEDS else 'cross_family'
        for checkpoint in checkpoints:
            if cohort == 'cross_family' and checkpoint != 'final':
                continue
            ma,a,rs = load_measurements(run/'collections'/left/checkpoint/'D3',rows)
            mb,b,_ = load_measurements(run/'collections'/right/checkpoint/'D3',rows)
            _shared(a,b)
            gate_a,gate_b = wilson_gate(a['margins'],a['concepts']),wilson_gate(b['margins'],b['concepts'])
            gates = {c:dict(model_a=gate_a[c],model_b=gate_b[c],both_passed=gate_a[c]['passed'] and gate_b[c]['passed']) for c in gate_a}
            for position in positions:
                path = _fit_path(run,pair,position)
                fitted = json.loads(path.read_text())
                if (_candidate_identity(a) != fitted['source']['candidates_a'] or
                    _candidate_identity(b) != fitted['source']['candidates_b']):
                    raise ValueError('Checkpoint candidates differ from frozen final-D1 candidates')
                out = path.parent/('eval.json' if checkpoint == 'final' else f'eval_{checkpoint}.json')
                source = dict(measurements_sha256_a=ma['measurements_sha256'],
                              measurements_sha256_b=mb['measurements_sha256'],fit_sha256=_sha(path))
                if out.exists():
                    result = json.loads(out.read_text())
                    if result.get('source') != source:
                        raise ValueError('Existing evaluation source mismatch')
                else:
                    then = time.monotonic()
                    result = evaluate_pair(a[position+'_product'],b[position+'_product'],rs,fitted)
                    result['by_task'] = {}
                    for concept in sorted(gates):
                        ix = np.asarray([r['concept']==concept for r in rs])
                        subset = [r for r,keep in zip(rs,ix) if keep]
                        task = evaluate_pair(a[position+'_product'][ix],b[position+'_product'][ix],subset,fitted)
                        result['by_task'][concept] = _compact_eval(task)
                    result.update(source=source,pair=list(pair),position=position,checkpoint=checkpoint,
                                  cohort=cohort,task_competence=gates,
                                  competent_tasks=[c for c in gates if gates[c]['both_passed']],
                                  competence_caveat='Low task competence prevents falsification of functional conservation.')
                    # Pair-level tests are conditional descriptive tests, not independent seed replication.
                    pair_stats = aggregate_pairs({'_'.join(pair):result},_primary_contrasts(),correct=False)
                    result['comparisons'] = pair_stats['tests']
                    write_once(out,result)
                    print(json.dumps(dict(stage='F3 evaluate',pair=list(pair),position=position,
                                          checkpoint=checkpoint,seconds=round(time.monotonic()-then,3))),flush=True)
                key = (cohort,position,checkpoint)
                evaluations.setdefault(key,{})['_'.join(pair)] = result
                if checkpoint == 'final':
                    for contrast,test in result['comparisons'].items():
                        name = f'F3/{"_".join(pair)}/{position}/{contrast}'
                        confirmatory[name] = dict(test,descriptive_pair=True,
                                                 competence_passed_tasks=result['competent_tasks'])
                completed.append(dict(pair=list(pair),position=position,checkpoint=checkpoint,
                                      path=str(out.relative_to(run)),sha256=_sha(out),
                                      primary=result['descriptive'],competent_tasks=result['competent_tasks']))
    cohorts = {}
    for (cohort,position,checkpoint),pairs_ in evaluations.items():
        key = f'{cohort}/{position}/{checkpoint}'
        stats = aggregate_pairs(pairs_,_primary_contrasts(),correct=False)
        cohorts[key] = stats
        write_once(run/'alignment/cohorts'/cohort/position/f'{checkpoint}.json',stats)
    summary = dict(stage='F3',status='MEASURED',evaluations=completed,cohorts=cohorts,
                   confirmatory_tests=confirmatory,correction='PENDING_F6_GLOBAL_BH',
                   n_final_evaluations=sum(x['checkpoint']=='final' for x in completed),
                   n_trajectory_evaluations=sum(x['checkpoint']!='final' for x in completed),
                   expected_final=26,expected_trajectory=40,
                   full_protocol_complete=(sum(x['checkpoint']=='final' for x in completed)==26 and
                                           sum(x['checkpoint']!='final' for x in completed)==40),
                   inference_scope='Fixed observed models; shared wrappers resampled jointly, pairs not independent.')
    if summary['full_protocol_complete']:
        write_once(run/'alignment/summary.json',summary)
    return summary


def _unit_profile(reference, records, units, indices, position, train_groups):
    keep = np.asarray([r['group_id'] in train_groups for r in records])
    rows = [r for r, take in zip(records, keep) if take]
    profile = expanded_semantic_profile(reference[position+'_product'][keep], rows)
    coordinates = {(int(layer),int(neuron)):i for i,(layer,neuron) in
                   enumerate(zip(reference['layers'],reference['neuron_ids']))}
    features = []
    for index in indices:
        unit = units[index]
        member_columns = []
        for layer,neurons in unit['units_by_layer'].items():
            for neuron in neurons:
                key = (int(layer),int(neuron))
                if key not in coordinates:
                    raise ValueError('Causal unit not contained in frozen reference candidates')
                member_columns.append(coordinates[key])
        if len(set(member_columns)) != len(member_columns):
            raise ValueError('Duplicate group members')
        features.append(profile['features'][member_columns].mean(0))
    return np.asarray(features)


def _causal_source(ma,mb,a,b):
    return dict(effects_sha256_a=ma['effects_sha256'],effects_sha256_b=mb['effects_sha256'],
                unit_ids_a=a['unit_ids'].tolist(),unit_ids_b=b['unit_ids'].tolist(),
                modes=a['modes'].tolist(),locations=a['locations'].tolist())


def _causal_cohort_path(run,cohort,kind,location,pair_names):
    """Pair subsets and complete cohorts must never share an artifact identity."""
    names=sorted(pair_names)
    expected=sorted('_'.join(pair) for pair in PAIRS
                    if ('independent_seeds' if pair[0] in SEEDS else 'cross_family')==cohort)
    if names==expected:
        return Path(run)/'causal_alignment/cohorts'/cohort/kind/f'{location}.json'
    return Path(run)/'causal_alignment/subsets'/('__'.join(names))/'cohorts'/cohort/kind/f'{location}.json'


def fit_causal_all(run,data,pairs=PAIRS):
    run = Path(run)
    canonical = load_rows(data,'D2')
    completed = []
    for pair in pairs:
        left,right = pair
        ma,a,rows = load_measurements(run/'causal'/left/'D2',canonical,causal=True)
        mb,b,_ = load_measurements(run/'causal'/right/'D2',canonical,causal=True)
        _shared(a,b)
        if not np.array_equal(a['locations'],b['locations']) or not np.array_equal(a['modes'],b['modes']):
            raise ValueError('Causal model modes/locations differ')
        mra,ra,rrows = load_measurements(run/'causal'/left/'D2/references',canonical)
        mrb,rb,_ = load_measurements(run/'causal'/right/'D2/references',canonical)
        _shared(a,ra);_shared(a,rb)
        groups = sorted(set(r['group_id'] for r in rows))
        train_groups = groups[:len(groups)//2]
        source = _causal_source(ma,mb,a,b)
        core = [a['modes'].tolist().index(mode) for mode in PRIMARY_CAUSAL_MODES]
        source.update(reference_sha256_a=mra['measurements_sha256'],reference_sha256_b=mrb['measurements_sha256'])
        source.update(primary_modes=list(PRIMARY_CAUSAL_MODES),primary_mode_indices=core)
        for kind in ('single','group'):
            ia,ib = np.flatnonzero(a['unit_kinds']==kind),np.flatnonzero(b['unit_kinds']==kind)
            if not len(ia) or not len(ib):
                raise ValueError('Missing preregistered single/group units')
            path = run/'causal_alignment'/('_'.join(pair))/kind/'fit.json'
            if path.exists():
                fitted = json.loads(path.read_text())
                if fitted.get('source') != source:
                    raise ValueError('Existing causal fit input identity changed')
            else:
                then = time.monotonic()
                semantic = []
                for location in a['locations'].tolist():
                    fa = _unit_profile(ra,rrows,ma['plan']['units'],ia,location,train_groups)
                    fb = _unit_profile(rb,rrows,mb['plan']['units'],ib,location,train_groups)
                    semantic.append(cosine_similarity(fa,fb))
                fitted = fit_causal_alignment(a['effects'][:,ia][...,core],b['effects'][:,ib][...,core],rows,np.asarray(semantic),
                                              location_names=a['locations'].tolist(),mode_names=list(PRIMARY_CAUSAL_MODES))
                fitted.update(source=source,pair=list(pair),unit_kind=kind,
                              unit_indices_a=ia.tolist(),unit_indices_b=ib.tolist(),
                              semantic_definition='Mean member-neuron expanded semantic features; fit on D2 causal-train wrappers only')
                write_once(path,fitted)
                print(json.dumps(dict(stage='F4 fit',pair=list(pair),kind=kind,
                                      seconds=round(time.monotonic()-then,3))),flush=True)
            completed.append(dict(pair=list(pair),unit_kind=kind,path=str(path.relative_to(run)),sha256=_sha(path)))
    manifest = dict(stage='F4',status='D2_CAUSAL_MAPS_AND_WEIGHTS_FROZEN',n_fits=len(completed),
                    fits=completed,test_data_used=False,expected_full_fits=26,
                    full_protocol_complete=len(completed)==26)
    if manifest['full_protocol_complete']:
        write_once(run/'causal_alignment/fit_manifest.json',manifest)
    return manifest


def _compact_causal(evaluation):
    result = dict(evaluation,locations={})
    for name,location in evaluation['locations'].items():
        result['locations'][name] = {k:v for k,v in location.items() if k not in ('random_controls','per_mode')}
        result['locations'][name]['per_mode'] = {mode:{k:v for k,v in measured.items() if k!='random_controls'}
                                                for mode,measured in location.get('per_mode',{}).items()}
    return result


def evaluate_causal_all(run,data,pairs=PAIRS):
    run = Path(run)
    canonical = load_rows(data,'D4')
    collected,confirmatory,completed = {},{},[]
    for pair in pairs:
        left,right = pair
        cohort = 'independent_seeds' if left in SEEDS else 'cross_family'
        ma,a,rows = load_measurements(run/'causal'/left/'D4',canonical,causal=True)
        mb,b,_ = load_measurements(run/'causal'/right/'D4',canonical,causal=True)
        _shared(a,b)
        gate_a,gate_b = wilson_gate(a['margins'],a['concepts']),wilson_gate(b['margins'],b['concepts'])
        gates = {c:dict(model_a=gate_a[c],model_b=gate_b[c],both_passed=gate_a[c]['passed'] and gate_b[c]['passed']) for c in gate_a}
        for kind in ('single','group'):
            fitpath = run/'causal_alignment'/('_'.join(pair))/kind/'fit.json'
            fitted = json.loads(fitpath.read_text())
            identity = _causal_source(ma,mb,a,b)
            for key in ('unit_ids_a','unit_ids_b','modes','locations'):
                if identity[key] != fitted['source'][key]:
                    raise ValueError('D4 intervention identity differs from D2 frozen fit')
            source = dict(effects_sha256_a=ma['effects_sha256'],effects_sha256_b=mb['effects_sha256'],
                          fit_sha256=_sha(fitpath))
            out = fitpath.parent/'eval.json'
            if out.exists():
                measured = json.loads(out.read_text())
                if measured.get('source') != source:
                    raise ValueError('Existing causal evaluation source mismatch')
            else:
                then = time.monotonic()
                core = fitted['source']['primary_mode_indices']
                aa,bb = a['effects'][:,fitted['unit_indices_a']][...,core],b['effects'][:,fitted['unit_indices_b']][...,core]
                measured = evaluate_causal_alignment(aa,bb,rows,fitted)
                measured.update(source=source,pair=list(pair),unit_kind=kind,cohort=cohort,
                                task_competence=gates,competent_tasks=[c for c in gates if gates[c]['both_passed']])
                measured['supplementary_dose_response'] = dict(
                    model_a=dose_response_diagnostics(a['effects'][:,fitted['unit_indices_a']],a['modes'].tolist()),
                    model_b=dose_response_diagnostics(b['effects'][:,fitted['unit_indices_b']],b['modes'].tolist()))
                measured['by_task'] = {}
                for concept in sorted(gates):
                    mask = np.asarray([r['concept']==concept for r in rows])
                    task = evaluate_causal_alignment(aa[mask],bb[mask],[r for r,k in zip(rows,mask) if k],fitted)
                    measured['by_task'][concept] = _compact_causal(task)
                measured['comparisons'] = {}
                for location,local in measured['locations'].items():
                    stats = aggregate_pairs({'_'.join(pair):local},{'combined_minus_semantic':('combined','semantic')},correct=False)
                    measured['comparisons'][location] = stats['tests']['combined_minus_semantic']
                write_once(out,measured)
                print(json.dumps(dict(stage='F4 evaluate',pair=list(pair),kind=kind,
                                      seconds=round(time.monotonic()-then,3))),flush=True)
            for location,local in measured['locations'].items():
                collected.setdefault((cohort,kind,location),{})['_'.join(pair)] = local
                name = f'F4/{"_".join(pair)}/{location}/{kind}/combined_minus_semantic'
                confirmatory[name] = dict(measured['comparisons'][location],descriptive_pair=True,
                                         competence_passed_tasks=measured['competent_tasks'])
            completed.append(dict(pair=list(pair),unit_kind=kind,path=str(out.relative_to(run)),sha256=_sha(out),
                                  locations={k:v['descriptive'] for k,v in measured['locations'].items()},
                                  selected_weights={k:v['selected_causal_weight'] for k,v in measured['locations'].items()},
                                  competent_tasks=measured['competent_tasks']))
    cohorts,cohort_artifacts = {},{}
    for (cohort,kind,location),pairs_ in collected.items():
        stats = aggregate_pairs(pairs_,{'combined_minus_semantic':('combined','semantic')},correct=False)
        key=f'{cohort}/{kind}/{location}'
        cohorts[key] = stats
        cohort_path=_causal_cohort_path(run,cohort,kind,location,pairs_)
        write_once(cohort_path,stats)
        cohort_artifacts[key]=dict(path=str(cohort_path.relative_to(run)),sha256=_sha(cohort_path),
                                   pair_names=sorted(pairs_))
    summary = dict(stage='F4',status='MEASURED',evaluations=completed,cohorts=cohorts,
                   confirmatory_tests=confirmatory,correction='PENDING_F6_GLOBAL_BH',
                   expected_evaluations=26,n_evaluations=len(completed),full_protocol_complete=len(completed)==26,
                   cohort_artifacts=cohort_artifacts,
                   cohort_artifact_policy='Complete cohorts use canonical paths; partial cohorts use explicitly named subsets/ paths. Earlier qwen_smol snapshots were preserved by recorded relocation.',
                   inference_scope='Fixed observed models and units; shared wrappers retained jointly.')
    if summary['full_protocol_complete']:
        write_once(run/'causal_alignment/summary.json',summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage',choices=['fit','evaluate','causal-fit','causal-evaluate'])
    parser.add_argument('--root',type=Path,default=ROOT/'results/followup-v2')
    parser.add_argument('--data',type=Path,default=ROOT/'data/followup-v2')
    parser.add_argument('--pairs',nargs='*',help='Optional names e.g. seed101_seed211')
    parser.add_argument('--positions',nargs='+',choices=POSITIONS,default=list(POSITIONS))
    args = parser.parse_args()
    pairs = PAIRS if not args.pairs else [tuple(pair.split('_')) for pair in args.pairs]
    if any(pair not in PAIRS for pair in pairs):
        raise ValueError('Pair is not in the frozen followup protocol')
    if args.stage in ('fit','evaluate'):
        result = (fit_all if args.stage=='fit' else evaluate_all)(args.root,args.data,pairs,args.positions)
    else:
        result = (fit_causal_all if args.stage=='causal-fit' else evaluate_causal_all)(args.root,args.data,pairs)
    print(json.dumps({'stage':args.stage,'complete':result['full_protocol_complete']}),flush=True)


if __name__ == '__main__':
    main()
