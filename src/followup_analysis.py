"""Follow-up v2 analyses with frozen D2 mappings and joint wrapper inference.

The primary evaluation standardizes *within task and wrapper* on D3. These
evaluation moments are used only to compute correlations, never to choose a
neuron, map, threshold, or hyperparameter. Seed pairs are descriptive units;
all pairs move together when wrappers are bootstrapped or sign-flipped.
"""
from __future__ import annotations

import hashlib
import json
import numpy as np

from .alignment import _matrix, correlation_matrix, cosine_similarity, match_neurons
from .statistics import cluster_bootstrap, paired_randomization_test, fdr_bh


METHODS = ('activation', 'rank', 'semantic', 'sign_semantic')
MODES = ('hungarian', 'partial', 'one_to_many')


def _metadata(records, n, split):
    if split not in ('D2', 'D3'):
        raise ValueError('Only D2 fitting or D3 evaluation is supported')
    if len(records) != n or not n:
        raise ValueError('Nonempty matching records and activation rows required')
    if any(r.get('split') != split for r in records):
        raise ValueError('Record split mismatch: no held-out fitting permitted')
    for key in ('concept', 'label'):
        if any(key not in r for r in records):
            raise ValueError(f'Missing {key} metadata')
    labels = np.asarray([r['label'] for r in records])
    if not np.isin(labels, (0, 1)).all():
        raise ValueError('Binary positive/negative labels required')
    groups = np.asarray([str(r.get('wrapper_id', r.get('group_id', ''))) for r in records])
    if np.any(groups == ''):
        raise ValueError('Shared wrapper_id or group_id required')
    return (np.asarray([str(r['concept']) for r in records]), labels, groups,
            np.asarray([str(r.get('subtype', r.get('semantic_subtype', 'all'))) for r in records]))


def _seed(seed, key):
    # A stable independent stream for each method/scope; never Python hash().
    digest = hashlib.sha256(f'{int(seed)}:{key}'.encode()).digest()
    return int.from_bytes(digest[:8], 'little')


def expanded_semantic_profile(a, records, signs=None, *, split='D2',
                              min_effect=.2, min_stability=.75, min_wrappers=3):
    """Concept/subtype truth contrasts, equally weighted across wrappers.

    Each contrast is (positive mean-negative mean)/all-example SD within that
    task/subtype and wrapper. This bounded-scale contrast does not explode when
    each truth condition is internally constant. Across-wrapper directional
    consistency weights the mean contrast. Fewer than min_wrappers or weak /
    inconsistent contrasts produce UNKNOWN primary labels. Sign-aware features
    use route-masked product with neutral-zero excluded, like pilot-v1.
    """
    if split != 'D2':
        raise ValueError('Profiles must be estimated on D2 only')
    a = _matrix(a)
    concepts, labels, groups, subtypes = _metadata(records, len(a), split)
    sources, routes = [a], ['all']
    if signs is not None:
        signs = np.asarray(signs)
        if signs.shape != a.shape or not np.isin(signs, range(5)).all():
            raise ValueError('Signs must be 0..4 and match activations')
        if np.any((signs == 4) & (a != 0)):
            raise ValueError('Neutral sign regime requires zero product')
        sources = [np.where(signs == k, a, 0.) for k in range(4)]
        routes = ['++', '+-', '-+', '--']
    descriptors = []
    for concept in sorted(set(concepts)):
        descriptors.append((concept, None))
        available = sorted(set(subtypes[concepts == concept]))
        if available != ['all']:
            descriptors.extend((concept, subtype) for subtype in available)
    effects, stability, counts, names = [], [], [], []
    for route, values in zip(routes, sources):
        for concept, subtype in descriptors:
            mask = concepts == concept
            if subtype is not None:
                mask &= subtypes == subtype
            per_wrapper = []
            for group in sorted(set(groups[mask])):
                ix = mask & (groups == group)
                pos, neg = values[ix & (labels == 1)], values[ix & (labels == 0)]
                if min(len(pos), len(neg)) < 2:
                    continue
                sd = values[ix].std(0)
                contrast = np.divide(pos.mean(0)-neg.mean(0), sd,
                                     out=np.zeros(a.shape[1]), where=sd > 1e-10)
                per_wrapper.append(contrast)
            if per_wrapper:
                per_wrapper = np.asarray(per_wrapper)
                mean = per_wrapper.mean(0)
                stable = np.mean((np.sign(per_wrapper) == np.sign(mean)) &
                                 (np.abs(per_wrapper) > 1e-10), axis=0)
            else:
                mean, stable = np.zeros(a.shape[1]), np.zeros(a.shape[1])
            effects.append(mean)
            stability.append(stable)
            counts.append(len(per_wrapper))
            names.append(f'{concept}/{subtype or "all"}/{route}')
    effects, stability = np.stack(effects, 1), np.stack(stability, 1)
    counts = np.asarray(counts)
    usable = counts >= min_wrappers
    features = effects * stability * usable[None, :]
    eligible = ((np.abs(effects) >= min_effect) & (stability >= min_stability)
                & usable[None, :])
    best = np.argmax(np.where(eligible, np.abs(features), -1.), axis=1)
    known = eligible.any(1)
    primary = [names[k] if good else 'UNKNOWN' for k, good in zip(best, known)]
    secondary = [[names[k] for k in np.flatnonzero(eligible[i]) if k != best[i]]
                 for i in range(len(a.T))]
    return dict(features=features, effects=effects, stability=stability,
                feature_names=names, wrapper_counts=counts, primary=primary,
                secondary=secondary, known=known, fit_split=split,
                unknown_fraction=float((~known).mean()),
                definition='truth contrasts conditional on concept/subtype, wrapper-weighted',
                criteria=dict(min_effect=min_effect, min_stability=min_stability,
                              min_wrappers=min_wrappers))


def _layer_mask(layers_a, layers_b, layer_pairs=None):
    la, lb = np.asarray(layers_a), np.asarray(layers_b)
    ua, ub = sorted(set(la.tolist())), sorted(set(lb.tolist()))
    if layer_pairs is None:
        if len(ua) != len(ub):
            raise ValueError('Unequal sampled-depth counts need explicit layer_pairs')
        layer_pairs = list(zip(ua, ub))
    if any(x not in ua or y not in ub for x, y in layer_pairs):
        raise ValueError('layer_pairs references an absent candidate layer')
    mask = np.zeros((len(la), len(lb)), dtype=bool)
    for x, y in layer_pairs:
        mask |= (la[:, None] == x) & (lb[None, :] == y)
    if not mask.any():
        raise ValueError('No eligible layer pairs')
    return mask, [list(p) for p in layer_pairs]


def _shuffle_blocks(rng, concepts, groups):
    """Preserve task/wrapper identity while removing example correspondence."""
    order = np.arange(len(concepts))
    for group in sorted(set(groups)):
        for concept in sorted(set(concepts[groups == group])):
            ix = np.flatnonzero((groups == group) & (concepts == concept))
            order[ix] = rng.permutation(ix)
    return order


def _fit_similarity(a, b, records, method, sa, sb):
    if method in ('activation', 'rank'):
        return correlation_matrix(a, b, rank=method == 'rank')
    pa = expanded_semantic_profile(a, records, sa if method == 'sign_semantic' else None)
    pb = expanded_semantic_profile(b, records, sb if method == 'sign_semantic' else None)
    return cosine_similarity(pa['features'], pb['features'])


def fit_pair(a, b, records, *, layers_a, layers_b, signs_a=None, signs_b=None,
             split='D2', n_random=100, seed=1729, null_permutations=100,
             methods=METHODS, modes=MODES, scopes=('flexible', 'layer'),
             layer_pairs=None, null_quantile=.95):
    """Freeze D2 maps, thresholds, and >=100 random mappings for each scope.

    Layer-restricted means caller-supplied layer pairs or relative sampled-depth
    rank when both models have the same number of sampled layers. Null shuffles
    preserve wrapper/task membership. Thresholds are descriptive calibration,
    not neuron-level significance claims. Random maps use random edge scores
    and exact assignment under the same layer constraints (not uniform draws
    over all feasible constrained assignments).
    """
    if split != 'D2' or n_random < 100 or null_permutations < 1:
        raise ValueError('Require D2, >=100 random controls, >=1 null permutation')
    a, b = _matrix(a), _matrix(b)
    concepts, _, groups, _ = _metadata(records, len(a), split)
    if len(a) != len(b) or len(layers_a) != a.shape[1] or len(layers_b) != b.shape[1]:
        raise ValueError('Activation/record/candidate layer dimensions disagree')
    if not set(methods) <= set(METHODS) or not set(modes) <= set(MODES):
        raise ValueError('Unknown alignment method or mode')
    if not set(scopes) <= {'flexible', 'layer'} or not 0 < null_quantile < 1:
        raise ValueError('Invalid scope or null quantile')
    if 'sign_semantic' in methods and (signs_a is None or signs_b is None):
        raise ValueError('Sign-semantic method needs both sign matrices')
    mask, layer_pairs = _layer_mask(layers_a, layers_b, layer_pairs)
    masks = {'flexible': np.ones_like(mask), 'layer': mask}
    result = dict(fit_split=split, seed=int(seed), mappings={}, random_mappings={},
                  layer_pairs=layer_pairs, null_permutations=null_permutations,
                  null_quantile=null_quantile, candidate_count=[a.shape[1], b.shape[1]])
    for method in methods:
        scores = _fit_similarity(a, b, records, method, signs_a, signs_b)
        rng = np.random.default_rng(_seed(seed, f'null/{method}'))
        null_maxima = {scope: [] for scope in scopes}
        for _ in range(null_permutations):
            order = _shuffle_blocks(rng, concepts, groups)
            sb = None if signs_b is None else np.asarray(signs_b)[order]
            null = _fit_similarity(a, b[order], records, method, signs_a, sb)
            for scope in scopes:
                eligible = masks[scope]
                row_has_target = eligible.any(1)
                null_maxima[scope].extend(np.where(eligible, null, -2.).max(1)[row_has_target])
        for scope in scopes:
            threshold = float(np.quantile(null_maxima[scope], null_quantile))
            restricted = np.where(masks[scope], scores, -2.)
            for mode in modes:
                mapping = match_neurons(restricted, threshold=threshold if mode != 'hungarian' else None,
                                        mode=mode)
                # Remove forbidden edges if unequal layer candidate counts forced
                # an otherwise complete assignment to use a sentinel edge.
                rows, cols = mapping['source'], mapping['target']
                keep = masks[scope][rows, cols]
                mapping['source'], mapping['target'] = rows[keep], cols[keep]
                mapping['similarity'] = scores[rows[keep], cols[keep]]
                mapping['coverage'] = len(set(rows[keep])) / a.shape[1]
                mapping['target_coverage'] = len(set(cols[keep])) / b.shape[1]
                mapping['unmatched_source_fraction'] = 1-mapping['coverage']
                mapping['unmatched_target_fraction'] = 1-mapping['target_coverage']
                mapping.update(method=method, scope=scope, fit_split=split,
                               calibration_threshold=threshold)
                result['mappings'][f'{method}__{scope}__{mode}'] = mapping
    for scope in scopes:
        rng = np.random.default_rng(_seed(seed, f'random/{scope}'))
        result['random_mappings'][scope] = []
        for _ in range(n_random):
            scores = np.where(masks[scope], rng.random(mask.shape), -2.)
            mapping = match_neurons(scores)
            rows, cols = mapping['source'], mapping['target']
            keep = masks[scope][rows, cols]
            result['random_mappings'][scope].append(dict(source=rows[keep], target=cols[keep]))
    result['profiles_a'] = expanded_semantic_profile(a, records)
    result['profiles_b'] = expanded_semantic_profile(b, records)
    return result


def within_task_correlation_matrices(a, b, records, *, split='D3'):
    """Wrapper->concept->correlation matrix after task-specific centering/scaling.

    Constants and <3-example task/wrapper cells are NaN, not invented zero
    evidence. Correlation is already invariant to positive per-task scaling.
    Unequal task counts do not change task weights when maps are evaluated.
    """
    if split != 'D3':
        raise ValueError('Primary evaluation requires independent D3')
    a, b = _matrix(a), _matrix(b)
    concepts, _, groups, _ = _metadata(records, len(a), split)
    if len(a) != len(b):
        raise ValueError('Corresponding example counts differ')
    output = {}
    for group in sorted(set(groups)):
        output[group] = {}
        for concept in sorted(set(concepts[groups == group])):
            ix = (groups == group) & (concepts == concept)
            aa, bb = a[ix], b[ix]
            matrix = np.full((a.shape[1], b.shape[1]), np.nan)
            if ix.sum() >= 3:
                valid = (aa.std(0)[:, None] > 1e-10) & (bb.std(0)[None, :] > 1e-10)
                values = correlation_matrix(aa, bb)
                matrix[valid] = values[valid]
            output[group][concept] = matrix
    return output


def _mapped_score(matrices, mapping):
    rows, cols = np.asarray(mapping['source'], int), np.asarray(mapping['target'], int)
    if not len(rows):
        return None
    task_scores = []
    for matrix in matrices.values():
        values = matrix[rows, cols]
        # One-to-many: first average over targets per source, then over sources.
        neuron_scores = [values[(rows == row) & np.isfinite(values)].mean()
                         for row in np.unique(rows)
                         if np.any((rows == row) & np.isfinite(values))]
        if neuron_scores:
            task_scores.append(float(np.mean(neuron_scores)))
    return float(np.mean(task_scores)) if task_scores else None


def evaluate_pair(a, b, records, fitted, *, split='D3'):
    if fitted.get('fit_split') != 'D2':
        raise ValueError('Evaluation requires a previously frozen D2 fit')
    matrices = within_task_correlation_matrices(a, b, records, split=split)
    scores = {name: {group: _mapped_score(cells, mapping) for group, cells in matrices.items()}
              for name, mapping in fitted['mappings'].items()}
    random_controls = {}
    for scope, mappings in fitted['random_mappings'].items():
        if len(mappings) < 100:
            raise ValueError('At least 100 repeated random controls required')
        draws = [{group: _mapped_score(cells, mapping) for group, cells in matrices.items()}
                 for mapping in mappings]
        means = []
        for draw in draws:
            vals = [v for v in draw.values() if v is not None]
            means.append(float(np.mean(vals)) if vals else None)
        random_controls[scope] = dict(wrapper_scores=draws, means=means, n_draws=len(draws))
        scores[f'random__{scope}'] = {}
        for group in matrices:
            vals = [draw[group] for draw in draws if draw[group] is not None]
            scores[f'random__{scope}'][group] = float(np.mean(vals)) if vals else None
    descriptives = {}
    for name, values in scores.items():
        finite = [x for x in values.values() if x is not None]
        descriptives[name] = dict(mean=float(np.mean(finite)) if finite else None,
                                  n_valid_wrappers=len(finite), n_wrappers=len(values))
    return dict(evaluation_split=split, fit_split='D2', wrapper_scores=scores,
                descriptive=descriptives, random_controls=random_controls,
                metric='within-task wrapper-equal native-neuron Pearson correlation',
                limitations=['Pair estimates are descriptive; shared model seeds are dependent.',
                             'One-to-many averages targets within each source neuron.',
                             'Invalid constant-neuron correlations are excluded and coverage must be reported.'])


def apply_global_bh(tests):
    """Apply one BH family to ALL supplied confirmatory tests, no per-pair FDR.

    Supply the full preregistered family across datasets/positions/methods.
    Undefined p-values stay undefined and remain listed in family metadata.
    """
    names = sorted(tests)
    valid = [name for name in names if tests[name].get('pvalue') is not None]
    adjusted = fdr_bh([tests[name]['pvalue'] for name in valid])
    result = {name: dict(tests[name], qvalue=None) for name in names}
    for name, q in zip(valid, adjusted):
        result[name]['qvalue'] = q
    return dict(tests=result, correction='Benjamini-Hochberg, single supplied family',
                family_size=len(names), finite_pvalue_count=len(valid),
                family=list(names), limitation='BH control assumes independence or suitable positive dependence.')


def aggregate_pairs(evaluations, comparisons, *, seed=1729, n_boot=5000,
                    n_permutations=20000, correct=True):
    """Average pair effects WITHIN each wrapper; resample those wrappers only.

    evaluations maps pair IDs to evaluate_pair outputs. comparisons maps unique
    preregistered contrast IDs to (method, baseline). Five model seeds may yield
    ten pairs, but n_clusters remains wrapper count, never pairs x wrappers.
    Inference is conditional on this fixed model collection; it is NOT a CI for
    unseen training seeds. Use correct=False when assembling a larger global
    family; call apply_global_bh once after all positions/cohorts are combined.
    """
    if not evaluations:
        raise ValueError('At least one pair evaluation required')
    tests, pair_descriptives = {}, {}
    for name, (method, baseline) in comparisons.items():
        pair_vectors, wrapper_order = [], None
        pair_descriptives[name] = {}
        incomplete = []
        for pair in sorted(evaluations):
            scores = evaluations[pair]['wrapper_scores']
            if method not in scores or baseline not in scores:
                raise ValueError(f'Missing preregistered method for {pair}')
            left, right = scores[method], scores[baseline]
            if set(left) != set(right):
                raise ValueError('Methods must have the same wrapper support')
            wrappers = sorted(left)
            if wrapper_order is not None and wrappers != wrapper_order:
                raise ValueError('All pairs must share wrapper IDs; do not silently intersect')
            wrapper_order = wrappers
            if any(left[w] is None or right[w] is None for w in wrappers):
                incomplete.append(pair)
                continue
            difference = np.array([left[w]-right[w] for w in wrappers])
            pair_vectors.append(difference)
            pair_descriptives[name][pair] = dict(mean=float(difference.mean()),
                                                n_wrappers=len(wrappers))
        if incomplete:
            tests[name] = dict(effect=None, pvalue=None, bootstrap=None,
                               status='INCONCLUSIVE_MISSING_WRAPPER_SCORES',
                               incomplete_pairs=incomplete, n_pairs=len(evaluations))
            continue
        jointly_averaged = np.mean(pair_vectors, axis=0)
        test = paired_randomization_test(jointly_averaged, np.zeros_like(jointly_averaged),
                                         wrapper_order, n_permutations=n_permutations,
                                         seed=_seed(seed, name))
        test['bootstrap'] = cluster_bootstrap(jointly_averaged, wrapper_order,
                                             n_boot=n_boot, seed=_seed(seed, name+'/bootstrap'))
        test.update(n_pairs=len(pair_vectors), wrapper_effects=dict(zip(wrapper_order, jointly_averaged)),
                    inference_scope='fixed observed models; shared-wrapper uncertainty only')
        tests[name] = test
    result = apply_global_bh(tests) if correct else dict(tests=tests, correction='PENDING_GLOBAL_FAMILY')
    result.update(pair_descriptives=pair_descriptives, n_pairs=len(evaluations),
                  resampling_unit='shared wrapper; all pairs and concepts retained together',
                  inference_scope='Conditional on observed models; no independent-seed replication claim.')
    return result


def json_ready(value):
    """Convert numeric analysis objects to strict JSON-compatible structures."""
    if isinstance(value, np.ndarray):
        return json_ready(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_ready(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value
