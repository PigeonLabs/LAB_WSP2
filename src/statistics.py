"""Cluster-aware exploratory statistics, with explicit finite-data checks."""
from __future__ import annotations

import numpy as np


def _arrays(values, groups):
    values = np.asarray(values, dtype=float)
    groups = np.asarray(groups, dtype=str)
    if values.ndim != 1 or groups.shape != values.shape or not len(values):
        raise ValueError("Expected nonempty one-dimensional equal-length values/groups")
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite measurements cannot be silently dropped")
    unique = np.unique(groups)
    return values, groups, unique


def cluster_bootstrap(values, groups, n_boot=2000, seed=1729, confidence=.95):
    """Equal-cluster-weighted mean and percentile CI; sample whole template clusters.

    Each cluster is reduced to its mean. The estimand gives templates equal weight,
    not prompts equal weight. With <2 clusters an interval is not identifiable.
    When wrappers are shared by concepts, pass shared wrapper IDs so every concept
    is resampled jointly. Crossing concept and wrapper IDs would pseudoreplicate.
    """
    values, groups, unique = _arrays(values, groups)
    if n_boot < 1 or not 0 < confidence < 1:
        raise ValueError("Invalid bootstrap settings")
    means = np.array([values[groups == g].mean() for g in unique])
    summary = {"mean": float(means.mean()), "median": float(np.median(means)),
               "std": float(means.std(ddof=1)) if len(means) > 1 else None,
               "n_observations": len(values), "n_clusters": len(means),
               "estimand": "equal-cluster-weighted mean", "confidence": confidence}
    if len(means) < 2:
        return {**summary, "ci": None, "status": "INSUFFICIENT_CLUSTERS"}
    rng = np.random.default_rng(seed)
    boot = means[rng.integers(0, len(means), (n_boot, len(means)))].mean(axis=1)
    alpha = (1 - confidence) / 2
    return {**summary, "ci": np.quantile(boot, [alpha, 1-alpha]).tolist(),
            "status": "EXPLORATORY_FEW_CLUSTERS" if len(means) < 20 else "OK"}


def paired_randomization_test(a, b, groups, n_permutations=5000, seed=1729):
    """Two-sided paired sign-flip randomization at template-cluster level.

    Tests exchangeability of method labels per cluster, not neuron independence.
    Uses exact enumeration for <=16 clusters, otherwise Monte Carlo +1 correction.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("Paired measurements must have identical shapes")
    differences, groups, unique = _arrays(a-b, groups)
    cluster = np.array([differences[groups == g].mean() for g in unique])
    observed = float(cluster.mean())
    if len(cluster) < 2:
        return {"effect": observed, "pvalue": None, "n_clusters": len(cluster), "status": "INSUFFICIENT_CLUSTERS"}
    if len(cluster) <= 16:
        bits = (np.arange(2 ** len(cluster))[:, None] >> np.arange(len(cluster))) & 1
        null = ((2 * bits - 1) * cluster).mean(axis=1)
        pvalue = float(np.mean(np.abs(null) >= abs(observed) - 1e-15))
        kind = "exact"
    else:
        if n_permutations < 1:
            raise ValueError("n_permutations must be positive")
        rng = np.random.default_rng(seed)
        null = (rng.choice([-1, 1], (n_permutations, len(cluster))) * cluster).mean(axis=1)
        pvalue = float((1 + (np.abs(null) >= abs(observed) - 1e-15).sum()) / (n_permutations + 1))
        kind = "monte_carlo"
    sd = cluster.std(ddof=1)
    return {"effect": observed, "pvalue": pvalue, "n_clusters": len(cluster), "method": kind,
            "standardized_effect": float(observed / sd) if sd > 0 else None,
            "status": "EXPLORATORY_FEW_CLUSTERS" if len(cluster) < 20 else "OK"}


def fdr_bh(pvalues):
    """Benjamini-Hochberg adjusted p-values in original order (finite values only)."""
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1 or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("p-values must be a finite vector within [0, 1]")
    if not len(p):
        return []
    order = np.argsort(p)
    adjusted = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p)+1))[::-1])[::-1]
    result = np.empty_like(adjusted)
    result[order] = np.minimum(adjusted, 1)
    return result.tolist()


def _rank(values):
    order = np.argsort(values, kind="stable")
    out = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i+1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        out[order[i:j]] = (i+j-1)/2
        i = j
    return out


def safe_correlation(a, b, method="pearson"):
    """Return None for insufficient/constant vectors, never fabricate zero evidence."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 1 or a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Expected paired finite vectors")
    if method not in ("pearson", "spearman"):
        raise ValueError("Unknown correlation method")
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    if method == "spearman":
        a, b = _rank(a), _rank(b)
    return float(np.corrcoef(a, b)[0, 1])
