#!/usr/bin/env python3
"""Replay post-hoc controls, competence strata and BH/BY without model calls.

Portable CLI: python scripts/validate_followup_supplemental.py --root ARCHIVE.
Only the output audit JSON is written; frozen maps and primary evidence are read.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_followup_results import equal, load_npz, load_portable_followup, read_json, sha_file, validate_rows
from scripts.followup_causal_competence import aggregate, load_complete_evidence
from scripts.followup_dependence_sensitivity import sensitivity
from src.followup_analysis import _effect_cells, _mapped_score


def verify_hash(path, expected):
    if sha_file(path) != expected:
        raise ValueError(f'Checksum mismatch: {path}')


def replay(root):
    root = Path(root).resolve()
    run = root / 'results/followup-v2'
    directory = run / 'supplemental_causal_activation'
    summary = read_json(directory / 'summary.json')
    manifest = read_json(directory / 'fit_manifest.json')
    if summary['n_evaluations'] != 26 or len(summary['evaluations']) != 26:
        raise ValueError('All 26 supplemental evaluations required')
    if manifest['n_fit_files'] != 26 or len(manifest['fits']) != 26 or manifest['n_location_control_maps'] != 104:
        raise ValueError('All 104 supplemental maps required')
    verify_hash(directory / 'fit_manifest.json', summary['fit_manifest_sha256'])
    for filename, digest in manifest['code_sha256'].items():
        verify_hash(root / 'src' / filename, digest)
    fit_entries = {(tuple(x['pair']), x['unit_kind']): x for x in manifest['fits']}
    if len(fit_entries) != 26:
        raise ValueError('Duplicated fit identities')
    dataset, _ = load_portable_followup(root)
    cache = {}
    count = 0
    seen = set()
    for entry in summary['evaluations']:
        identity = tuple(entry['pair']), entry['unit_kind']
        if identity in seen or identity not in fit_entries:
            raise ValueError('Unexpected or repeated evaluation identity')
        seen.add(identity)
        fit_entry = fit_entries[identity]
        verify_hash(directory / fit_entry['path'], fit_entry['sha256'])
        verify_hash(directory / entry['path'], entry['sha256'])
        fit = read_json(directory / fit_entry['path'])
        result = read_json(directory / entry['path'])
        primary_dir = run / 'causal_alignment' / '_'.join(entry['pair']) / entry['unit_kind']
        primary = read_json(primary_dir / 'fit.json')
        primary_eval = read_json(primary_dir / 'eval.json')
        verify_hash(primary_dir / 'fit.json', fit['source']['primary_D2_fit_sha256'])
        verify_hash(primary_dir / 'eval.json', result['source']['primary_eval_sha256'])
        verify_hash(directory / 'fit_manifest.json', result['source']['freeze_manifest_sha256'])
        equal(result['source']['supplement_fit_sha256'], fit_entry['sha256'])
        arrays = []
        for side, name in zip(('a', 'b'), entry['pair']):
            path = run / 'causal' / name / 'D4'
            if name not in cache:
                metadata = read_json(path / 'manifest.json')
                verify_hash(path / 'effects.npz', metadata['effects_sha256'])
                values = load_npz(path / 'effects.npz')
                records = validate_rows(values, dataset['D4'])
                cache[name] = metadata, values, records
            metadata, values, records = cache[name]
            equal(metadata['effects_sha256'], result['source']['D4_effects_sha256_' + side])
            equal(values['unit_ids'], primary['source']['unit_ids_' + side])
            equal(values['locations'], primary['source']['locations'])
            equal(values['modes'], primary['source']['modes'])
            arrays.append(values)
        equal(arrays[0]['row_ids'], arrays[1]['row_ids'])
        core = primary['source']['primary_mode_indices']
        a = arrays[0]['effects'][:, fit['unit_indices_a']][..., core]
        b = arrays[1]['effects'][:, fit['unit_indices_b']][..., core]
        for li, location in enumerate(fit['location_order']):
            cells = _effect_cells(a[:, :, li], b[:, :, li], records, 'D4')
            saved = result['locations'][location]
            for baseline in ('semantic', 'causal', 'combined', 'random'):
                equal(saved['wrapper_scores'][baseline], primary_eval['locations'][location]['wrapper_scores'][baseline])
            for name in ('activation_raw', 'activation_task_centered'):
                mapping = fit['locations'][location]['mappings'][name]
                scores = {group: _mapped_score(cell, mapping) for group, cell in cells.items()}
                equal(scores, saved['wrapper_scores'][name])
                valid = [v for v in scores.values() if v is not None]
                descriptor = dict(mean=float(np.mean(valid)) if valid else None, n_valid_wrappers=len(valid), n_wrappers=len(scores))
                equal(descriptor, saved['descriptive'][name])
                for baseline in ('semantic', 'combined', 'random'):
                    other = saved['wrapper_scores'][baseline]
                    delta = {g: scores[g] - other[g] if scores[g] is not None and other[g] is not None else None for g in scores}
                    valid_delta = [v for v in delta.values() if v is not None]
                    expected = dict(mean_difference=float(np.mean(valid_delta)) if valid_delta else None, wrapper_differences=delta, n_valid_wrappers=len(valid_delta), descriptive_only=True)
                    equal(expected, result['descriptive_differences'][location][name][baseline])
                count += 1
    if count != 104:
        raise ValueError('Map replay count differs from frozen scope')
    competence = run / 'causal_alignment/competence_descriptive.json'
    equal(aggregate(*load_complete_evidence(root)), read_json(competence))
    global_path = run / 'statistics/global_tests.json'
    dependence = run / 'statistics/dependence_sensitivity.json'
    equal(sensitivity(read_json(global_path), sha_file(global_path)), read_json(dependence))
    return dict(status='PASS', supplemental_evaluations=26,
                supplemental_location_control_maps_replayed=count,
                primary_wrapper_scores_unchanged=True, competence_strata_replayed=64,
                independent_BH_BY_replayed=True,
                source_sha256={
                    'supplemental_summary': sha_file(directory / 'summary.json'),
                    'supplemental_fit_manifest': sha_file(directory / 'fit_manifest.json'),
                    'competence_descriptive': sha_file(competence),
                    'global_tests': sha_file(global_path),
                    'dependence_sensitivity': sha_file(dependence),
                    'audit_script': sha_file(__file__)},
                scope='CPU-only read-only replay of supplemental frozen maps/observed effects, competence descriptives and dependency corrections; no new tests/refits/model calls')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = replay(args.root)
    output = args.output or args.root / 'results/followup-v2/supplemental_replay_audit.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
