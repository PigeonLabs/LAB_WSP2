"""Native-neuron alignment fitted only on discovery/calibration data.

Matrices contain examples in rows and native neurons in columns. Semantic
features are signed standardized positive/negative contrasts, not explanations
or evidence of causal equivalence. No held-out arrays are accepted by fit APIs.
"""
from __future__ import annotations

import numpy as np


def _matrix(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("Expected a finite examples-by-neurons matrix")
    return x


def _rank_columns(x):
    """Average ranks for ties, equivalent to scipy.stats.rankdata(axis=0)."""
    result = np.empty_like(x, dtype=np.float64)
    for col in range(x.shape[1]):
        order = np.argsort(x[:, col], kind="stable")
        values = x[order, col]
        starts = np.r_[0, np.flatnonzero(np.diff(values)) + 1]
        ends = np.r_[starts[1:], len(values)]
        for lo, hi in zip(starts, ends):
            result[order[lo:hi], col] = (lo + hi - 1) / 2 + 1
    return result


def cosine_similarity(a, b):
    """Row-wise cosine similarity. Zero vectors have zero similarity."""
    a, b = _matrix(a), _matrix(b)
    if a.shape[1] != b.shape[1]:
        raise ValueError("Fingerprint dimensions must agree")
    a = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
    b = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-12)
    return np.clip(a @ b.T, -1, 1)


def correlation_matrix(a, b, rank=False):
    a, b = _matrix(a), _matrix(b)
    if len(a) != len(b) or len(a) < 2:
        raise ValueError("At least two corresponding examples are required")
    if rank:
        a, b = _rank_columns(a), _rank_columns(b)
    return cosine_similarity((a-a.mean(0)).T, (b-b.mean(0)).T)


def semantic_fingerprint(activations, records, sign_regimes=None, concepts=None):
    """Return neuron x concept standardized binary-label contrasts.

    With sign_regimes, include one contrast per concept and sign regime, using
    zero outside that regime. This preserves route frequency and signed product
    magnitude instead of conditioning on arbitrarily tiny subsets. Regimes are
    integers 0..4, convention 0=++ 1=+- 2=-+ 3=-- and 4=exact zero (neutral).
    Neutral products are zero and contribute to no signed route. The convention must be shared
    by both models; no cross-model gate/value swaps are assumed.
    """
    a = _matrix(activations)
    if len(records) != len(a):
        raise ValueError("Record count mismatch")
    labels = np.asarray([r['label'] for r in records])
    names = np.asarray([r['concept'] for r in records])
    if not np.isin(labels, [0, 1]).all():
        raise ValueError("Binary positive/negative labels required")
    concepts = sorted(set(names)) if concepts is None else list(concepts)
    sources = [a]
    if sign_regimes is not None:
        signs = np.asarray(sign_regimes)
        if signs.shape != a.shape or not np.isin(signs, range(5)).all():
            raise ValueError("Sign regimes must match activation shape and be 0..4")
        if np.any((signs == 4) & (a != 0)):
            raise ValueError("Neutral sign regime requires exactly zero product")
        sources = [np.where(signs == k, a, 0.0) for k in range(4)]
    features = []
    for values in sources:
        for concept in concepts:
            pos = values[(names == concept) & (labels == 1)]
            neg = values[(names == concept) & (labels == 0)]
            if min(len(pos), len(neg)) < 2:
                raise ValueError(f"Need >=2 examples of both labels for {concept}")
            pooled = np.sqrt(((len(pos)-1)*pos.var(0, ddof=1) +
                              (len(neg)-1)*neg.var(0, ddof=1)) /
                             (len(pos)+len(neg)-2))
            # A tiny scale floor prevents numeric noise in constant neurons.
            floor = np.maximum(values.std(0)*1e-6, 1e-10)
            features.append((pos.mean(0)-neg.mean(0))/np.maximum(pooled, floor))
    return np.stack(features, axis=1)


def weight_similarity(gate_a, up_a, down_a, gate_b, up_b, down_b):
    """One-layer permutation weight baseline, NOT full Git Re-Basin.

    gate/up are [neurons,residual_dim], down is [residual_dim,neurons]. Only
    meaningful with shared residual coordinates; independently trained residual
    bases may differ. Report that limitation rather than calling this Re-Basin.
    """
    a = np.concatenate([_matrix(gate_a), _matrix(up_a), _matrix(down_a).T], axis=1)
    b = np.concatenate([_matrix(gate_b), _matrix(up_b), _matrix(down_b).T], axis=1)
    return cosine_similarity(a, b)


def _assignment(scores):
    """Exact rectangular maximum assignment, no optional dependency required."""
    scores = _matrix(scores)
    transpose = scores.shape[0] > scores.shape[1]
    costs = -scores.T if transpose else -scores
    n, m = costs.shape
    if n == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    # Shortest augmenting-path Hungarian algorithm, O(n^2 m).
    u, v = np.zeros(n+1), np.zeros(m+1)
    p, way = np.zeros(m+1, dtype=int), np.zeros(m+1, dtype=int)
    for i in range(1, n+1):
        p[0] = i
        minv, used = np.full(m+1, np.inf), np.zeros(m+1, dtype=bool)
        j0 = 0
        while True:
            used[j0] = True
            i0 = p[j0]
            cur = costs[i0-1] - u[i0] - v[1:]
            improve = (~used[1:]) & (cur < minv[1:])
            minv[1:][improve] = cur[improve]
            way[1:][improve] = j0
            available = np.where(~used[1:], minv[1:], np.inf)
            j1 = int(np.argmin(available)) + 1
            delta = minv[j1]
            u[p[used]] += delta
            v[used] -= delta
            minv[~used] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    cols = np.flatnonzero(p[1:])
    rows = p[cols+1]-1
    if transpose:
        rows, cols = cols, rows
    order = np.argsort(rows)
    return rows[order], cols[order]


def _result(scores, rows, cols, mode, threshold):
    rows, cols = np.asarray(rows, dtype=int), np.asarray(cols, dtype=int)
    n, m = scores.shape
    source_coverage = len(np.unique(rows))/n if n else 0.0
    target_coverage = len(np.unique(cols))/m if m else 0.0
    return dict(source=rows, target=cols, similarity=scores[rows, cols],
                coverage=source_coverage, target_coverage=target_coverage,
                unmatched_source_fraction=1-source_coverage,
                unmatched_target_fraction=1-target_coverage,
                mode=mode, threshold=threshold)


def match_neurons(similarity, threshold=None, mode='hungarian', max_matches=3):
    """Match without a compulsory one-to-one conservation assumption.

    Partial matching uses dummy targets with score threshold; it optimizes total
    excess over threshold. It is not a full assignment followed by filtering.
    one_to_many permits shared targets and keeps up to max_matches per source.
    """
    s = _matrix(similarity)
    n, m = s.shape
    if mode == 'hungarian':
        rows, cols = _assignment(s)
        if threshold is not None:
            keep = s[rows, cols] > threshold
            rows, cols = rows[keep], cols[keep]
    elif mode == 'partial':
        if threshold is None:
            raise ValueError("Partial matching requires calibration threshold")
        extended = np.concatenate([s, np.full((n, n), threshold)], axis=1)
        rows, cols = _assignment(extended)
        keep = cols < m
        rows, cols = rows[keep], cols[keep]
        keep = s[rows, cols] > threshold
        rows, cols = rows[keep], cols[keep]
    elif mode == 'one_to_many':
        if threshold is None or max_matches < 1:
            raise ValueError("One-to-many needs threshold and positive max_matches")
        pairs = [(i, j) for i in range(n)
                 for j in np.argsort(-s[i], kind='stable')[:max_matches]
                 if s[i, j] > threshold]
        rows, cols = zip(*pairs) if pairs else ([], [])
    else:
        raise ValueError(f"Unknown matching mode {mode}")
    return _result(s, rows, cols, mode, threshold)


def random_matching(n_a, n_b, seed=1729):
    rng = np.random.default_rng(seed)
    count = min(n_a, n_b)
    rows, cols = rng.permutation(n_a)[:count], rng.permutation(n_b)[:count]
    return _result(np.zeros((n_a, n_b)), rows, cols, 'random', None)


def _fit_guard(records, split):
    if split not in ('D1', 'D2'):
        raise ValueError("Alignment fitting accepts D1/D2 only; held-out data forbidden")
    if records is not None and any(r.get('split', split) != split for r in records):
        raise ValueError("Record split disagrees with declared fitting split")


def similarity_for_method(a, b, records, method, signs_a=None, signs_b=None, seed=1729):
    if method in ('activation', 'rank'):
        return correlation_matrix(a, b, rank=method == 'rank')
    if method in ('semantic', 'sign_semantic', 'label_shuffled'):
        records_b = records
        if method == 'label_shuffled':
            rng = np.random.default_rng(seed)
            # Shuffle truth labels within each concept, preserving category sizes.
            labels = np.array([r['label'] for r in records])
            names = np.array([r['concept'] for r in records])
            # Canonical order is essential: hash-randomized set iteration would
            # assign different RNG draws to concepts across Python processes.
            for name in sorted(set(names)):
                ids = np.flatnonzero(names == name)
                labels[ids] = rng.permutation(labels[ids])
            records_b = [dict(r, label=int(label)) for r, label in zip(records, labels)]
        use_sign = method == 'sign_semantic'
        if use_sign and (signs_a is None or signs_b is None):
            raise ValueError("Sign-aware matching requires gate/value sign regimes")
        fa = semantic_fingerprint(a, records, signs_a if use_sign else None)
        fb = semantic_fingerprint(b, records_b, signs_b if use_sign else None)
        return cosine_similarity(fa, fb)
    raise ValueError(f"Unknown method {method}")


def calibration_threshold(a, b, records=None, method='activation', signs_a=None,
                          signs_b=None, split='D2', quantile=.95,
                          permutations=100, seed=1729):
    """95th percentile of null row-maxima, accounting for target search.

    Shuffle corresponding example rows in B; retain labels and A. This is a
    descriptive calibration threshold, not a calibrated neuron-level p-value.
    Dependent prompts require group-level inference in the statistics module.
    """
    _fit_guard(records, split)
    a, b = _matrix(a), _matrix(b)
    if not 0 < quantile < 1 or permutations < 1:
        raise ValueError("Invalid null calibration settings")
    if records is None and method not in ('activation', 'rank'):
        raise ValueError("Semantic calibration requires records")
    rng = np.random.default_rng(seed)
    maxima = []
    for _ in range(permutations):
        order = rng.permutation(len(b))
        sb = None if signs_b is None else np.asarray(signs_b)[order]
        s = similarity_for_method(a, b[order], records, method,
                                  signs_a=signs_a, signs_b=sb, seed=seed)
        maxima.extend(s.max(axis=1).tolist())
    return float(np.quantile(maxima, quantile))


def fit_alignment(a, b, records, method='activation', split='D2', signs_a=None,
                  signs_b=None, seed=1729, mode='hungarian', threshold=None):
    _fit_guard(records, split)
    a, b = _matrix(a), _matrix(b)
    if len(a) != len(b) or len(records) != len(a):
        raise ValueError("Corresponding examples and records required")
    if method == 'random':
        result = random_matching(a.shape[1], b.shape[1], seed)
    else:
        s = similarity_for_method(a, b, records, method, signs_a, signs_b, seed)
        result = match_neurons(s, threshold=threshold, mode=mode)
    return dict(result, method=method, fit_split=split)
