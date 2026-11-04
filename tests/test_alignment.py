import itertools
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import numpy as np
import pytest

from src.alignment import (
    _assignment, correlation_matrix, cosine_similarity, semantic_fingerprint,
    match_neurons, random_matching, fit_alignment, calibration_threshold,
)


def records(n=128, split='D2'):
    return [dict(concept=['arith','logic'][i%2], label=(i//2)%2, split=split)
            for i in range(n)]


def test_exact_assignment_rectangular_and_transposed():
    rng = np.random.default_rng(1)
    for shape in [(3, 5), (5, 3), (4, 4)]:
        s = rng.normal(size=shape)
        r, c = _assignment(s)
        z = s if shape[0] <= shape[1] else s.T
        optimum = max(sum(z[i, p[i]] for i in range(z.shape[0]))
                      for p in itertools.permutations(range(z.shape[1]), z.shape[0]))
        assert np.isclose(s[r, c].sum(), optimum)


def test_recovery_of_permuted_correspondence_and_constant_columns():
    a = np.random.default_rng(2).normal(size=(100, 8))
    p = np.array([2, 0, 5, 3, 1, 7, 4, 6])
    s = correlation_matrix(a, a[:, p]*3+10)
    result = match_neurons(s)
    assert np.array_equal(p[result['target']], result['source'])
    assert np.allclose(result['similarity'], 1)
    assert np.allclose(correlation_matrix(np.ones((10, 2)), np.ones((10, 3))), 0)


def test_rank_ties_and_monotonic_transform():
    x = np.array([[0, 2], [1, 3], [1, 5], [4, 9]], dtype=float)
    assert np.allclose(np.diag(correlation_matrix(x, np.exp(x), rank=True)), 1)


def test_partial_assignment_optimizes_unmatched_choices():
    result = match_neurons([[.9, .8], [.79, -.9]], threshold=.75, mode='partial')
    assert result['source'].tolist() == [0]
    assert result['target'].tolist() == [0]
    assert result['unmatched_source_fraction'] == .5
    assert len(match_neurons([[-.2, .1]], threshold=.5, mode='partial')['source']) == 0


def test_one_to_many_allows_shared_target():
    result = match_neurons([[.9,.8],[.95,.1]], threshold=.7,
                           mode='one_to_many', max_matches=2)
    assert list(zip(result['source'], result['target'])) == [(0,0),(0,1),(1,0)]


def test_semantics_keep_opposite_effects_distinct_and_sign_routes_distinct():
    rs = records()
    y = np.array([r['label'] for r in rs])*2-1
    noise = np.random.default_rng(3).normal(0,.1,len(rs))
    a = np.stack([y+noise,-y+noise], axis=1)
    f = semantic_fingerprint(a, rs)
    assert cosine_similarity(f,f)[0,1] < -.99
    f0 = semantic_fingerprint(a,rs,np.zeros_like(a,dtype=int))
    f3 = semantic_fingerprint(a,rs,np.full_like(a,3,dtype=int))
    assert np.allclose(cosine_similarity(f0,f3),0)


def test_heldout_records_cannot_fit_or_calibrate():
    a = np.ones((128, 2))
    for split in ('D3','D4'):
        with pytest.raises(ValueError):
            fit_alignment(a,a,records(split=split),split=split)
        with pytest.raises(ValueError):
            fit_alignment(a,a,records(split=split),split='D2')
        with pytest.raises(ValueError):
            calibration_threshold(a,a,split=split)


def test_neutral_zero_route_is_accepted_without_fabricating_activation():
    rs = records()
    a = np.zeros((len(rs), 2))
    assert np.allclose(semantic_fingerprint(a, rs, np.full_like(a, 4)), 0)
    with pytest.raises(ValueError):
        semantic_fingerprint(a+1, rs, np.full_like(a, 4))


def test_independent_noise_does_not_gain_large_partial_coverage():
    rng = np.random.default_rng(4)
    a,b = rng.normal(size=(400,32)),rng.normal(size=(400,40))
    threshold = calibration_threshold(a,b,permutations=40,seed=4)
    result = match_neurons(correlation_matrix(a,b),threshold=threshold,mode='partial')
    assert threshold > .1
    assert result['coverage'] < .25


def test_random_matching_is_reproducible_without_replacement():
    a,b = random_matching(20,10,42),random_matching(20,10,42)
    assert np.array_equal(a['target'],b['target'])
    assert len(set(a['source'])) == 10
    assert len(set(a['target'])) == 10


def test_label_shuffle_destroys_known_concept_feature_correspondence():
    rs = records(400)
    rng = np.random.default_rng(9)
    labels = np.array([r['label'] for r in rs])*2-1
    concepts = np.array([r['concept'] for r in rs])
    signal = np.stack([labels*(concepts=='arith'), labels*(concepts=='logic')],axis=1)
    a = signal+rng.normal(0,.1,signal.shape)
    true = fit_alignment(a,a,rs,method='semantic')
    null = fit_alignment(a,a,rs,method='label_shuffled',seed=7)
    assert true['similarity'].mean() > .99
    assert null['similarity'].mean() < .8


def test_label_shuffled_alignment_is_stable_across_python_hash_seeds():
    """A fixed NumPy seed must control the entire negative-control realization.

    Running fresh interpreters is necessary: changing PYTHONHASHSEED after
    interpreter startup does not change string/set hashing in that process.
    Compare the complete fitted similarity matrix and chosen correspondence,
    not merely an aggregate that could hide a changed control realization.
    """
    program = textwrap.dedent('''
        import json
        import numpy as np
        from src.alignment import similarity_for_method, match_neurons
        rng = np.random.default_rng(58013)
        concepts = ['arithmetic', 'comparison', 'negation', 'syntax']
        records = [dict(concept=concepts[i % 4], label=(i // 4) % 2,
                        split='D2') for i in range(256)]
        a = rng.normal(size=(256, 11))
        b = rng.normal(size=(256, 13))
        scores = similarity_for_method(a, b, records, 'label_shuffled', seed=1729)
        matching = match_neurons(scores)
        print(json.dumps({'similarity': scores.tolist(),
                          'source': matching['source'].tolist(),
                          'target': matching['target'].tolist()}, sort_keys=True))
    ''')
    outputs = []
    for hash_seed in ('0', '1', '2', '13'):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed, OPENBLAS_NUM_THREADS='1',
                   OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        completed = subprocess.run([sys.executable, '-c', program], env=env,
                                   cwd=Path(__file__).resolve().parents[1],
                                   check=True, capture_output=True, text=True)
        outputs.append(completed.stdout)
    assert all(output == outputs[0] for output in outputs[1:])
