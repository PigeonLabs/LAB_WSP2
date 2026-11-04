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


METHODS = ('activation', 'rank', 'semantic', 'sign_semantic', 'label_shuffled')
MODES = ('hungarian', 'partial', 'one_to_many')


def _metadata(records, n, split):
    if split not in ('D2', 'D3', 'D4'):
        raise ValueError('Only D2 fitting or D3/D4 evaluation is supported')
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


def _profile_plan(records):
    concepts, labels, groups, subtypes = _metadata(records, len(records), 'D2')
    descriptors = []
    for concept in sorted(set(concepts)):
        descriptors.append((concept, None))
        available = sorted(set(subtypes[concepts == concept]))
        if available != ['all']:
            descriptors.extend((concept, subtype) for subtype in available)
    positive, negative, total, cell_features = [], [], [], []
    for feature, (concept, subtype) in enumerate(descriptors):
        mask = concepts == concept
        if subtype is not None:
            mask &= subtypes == subtype
        for group in sorted(set(groups[mask])):
            ix = mask & (groups == group)
            pos, neg = ix & (labels == 1), ix & (labels == 0)
            if min(pos.sum(), neg.sum()) < 2:
                continue
            positive.append(pos / pos.sum())
            negative.append(neg / neg.sum())
            total.append(ix / ix.sum())
            cell_features.append(feature)
    shape = (-1, len(records))
    return dict(positive=np.asarray(positive).reshape(shape),
                negative=np.asarray(negative).reshape(shape),
                total=np.asarray(total).reshape(shape), cell_features=np.asarray(cell_features),
                descriptors=descriptors)


def _semantic_arrays(a, plan, signs=None, route_products=None):
    sources, routes = [a], ['all']
    if signs is not None and route_products is not None:
        raise ValueError('Supply categorical signs OR token-aggregated route products')
    if route_products is not None:
        products = np.asarray(route_products, float)
        if products.ndim != 3 or products.shape[:2] != a.shape or products.shape[2] not in (4, 5):
            raise ValueError('Route products must have shape [examples,neurons,4 or 5]')
        if not np.isfinite(products).all() or not np.allclose(products.sum(2), a, rtol=1e-4, atol=1e-6):
            raise ValueError('Route contributions must be finite and sum to the measured product')
        if products.shape[2] == 5 and not np.all(products[:, :, 4] == 0):
            raise ValueError('Neutral route contribution must be zero')
        sources, routes = [products[:, :, k] for k in range(4)], ['++', '+-', '-+', '--']
    elif signs is not None:
        signs = np.asarray(signs)
        if signs.shape != a.shape or not np.isin(signs, range(5)).all():
            raise ValueError('Signs must be 0..4 and match activations')
        if np.any((signs == 4) & (a != 0)):
            raise ValueError('Neutral sign regime requires zero product')
        sources, routes = [np.where(signs == k, a, 0.) for k in range(4)], ['++', '+-', '-+', '--']
    effects, stability, counts, names = [], [], [], []
    for route, values in zip(routes, sources):
        means = plan['total'] @ values
        variance = np.maximum(plan['total'] @ (values*values)-means*means, 0.)
        # Floating cancellation in constant cells must not create false effects.
        nonconstant = variance > np.maximum(1e-20, np.abs(plan['total'] @ (values*values))*1e-12)
        delta = (plan['positive']-plan['negative']) @ values
        contrast = np.divide(delta, np.sqrt(variance), out=np.zeros_like(delta), where=nonconstant)
        for feature, (concept, subtype) in enumerate(plan['descriptors']):
            per_wrapper = contrast[plan['cell_features'] == feature]
            if len(per_wrapper):
                mean = per_wrapper.mean(0)
                stable = np.mean((np.sign(per_wrapper) == np.sign(mean)) &
                                 (np.abs(per_wrapper) > 1e-10), axis=0)
            else:
                mean, stable = np.zeros(a.shape[1]), np.zeros(a.shape[1])
            effects.append(mean)
            stability.append(stable)
            counts.append(len(per_wrapper))
            names.append(f'{concept}/{subtype or "all"}/{route}')
    return np.stack(effects, 1), np.stack(stability, 1), np.asarray(counts), names


def expanded_semantic_profile(a, records, signs=None, *, route_products=None, split='D2',
                              min_effect=.2, min_stability=.75, min_wrappers=3, _plan=None):
    """Concept/subtype truth contrasts, equally weighted across wrappers.

    Contrast=(positive mean-negative mean)/all-example SD within task/subtype
    and wrapper. Directional consistency weights cross-wrapper mean contrast.
    Weak/inconsistent effects get UNKNOWN primary labels. For statement-span
    measurements supply token-averaged signed route contributions through
    route_products[N,K,4 or 5]; never infer routes from the sign of a span mean.
    """
    if split != 'D2':
        raise ValueError('Profiles must be estimated on D2 only')
    a = _matrix(a)
    _metadata(records, len(a), split)
    plan = _profile_plan(records) if _plan is None else _plan
    effects, stability, counts, names = _semantic_arrays(a, plan, signs, route_products)
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


def _fit_similarity(a, b, records, method, sa, sb, *, pa=None, plan=None,
                    ra=None, rb=None, seed=1729):
    if method in ('activation', 'rank'):
        return correlation_matrix(a, b, rank=method == 'rank')
    sign = method == 'sign_semantic'
    if plan is None:
        plan = _profile_plan(records)
    if pa is None:
        pa = expanded_semantic_profile(a, records, sa if sign else None,
                                      route_products=ra if sign else None, _plan=plan)['features']
    if method == 'label_shuffled':
        concepts, labels, groups, _ = _metadata(records, len(records), 'D2')
        rng = np.random.default_rng(_seed(seed, 'labels'))
        order = _shuffle_blocks(rng, concepts, groups)
        shuffled = [dict(r, label=int(label)) for r, label in zip(records, labels[order])]
        plan = _profile_plan(shuffled)
    effect, stability, counts, _ = _semantic_arrays(b, plan, sb if sign else None,
                                                   rb if sign else None)
    fb = effect * stability * (counts >= 3)[None, :]
    return cosine_similarity(pa, fb)


def fit_pair(a, b, records, *, layers_a, layers_b, signs_a=None, signs_b=None,
             route_products_a=None, route_products_b=None,
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
    if 'sign_semantic' in methods and ((signs_a is None and route_products_a is None)
                                      or (signs_b is None and route_products_b is None)):
        raise ValueError('Sign-semantic method needs categorical signs or route contributions for both models')
    mask, layer_pairs = _layer_mask(layers_a, layers_b, layer_pairs)
    masks = {'flexible': np.ones_like(mask), 'layer': mask}
    result = dict(fit_split=split, seed=int(seed), mappings={}, random_mappings={},
                  layer_pairs=layer_pairs, null_permutations=null_permutations,
                  null_quantile=null_quantile, candidate_count=[a.shape[1], b.shape[1]])
    plan = _profile_plan(records)
    ordinary_a = expanded_semantic_profile(a, records, _plan=plan)
    ordinary_b = expanded_semantic_profile(b, records, _plan=plan)
    signed_a = (expanded_semantic_profile(a, records, signs_a, route_products=route_products_a,
                                         _plan=plan)['features']
                if 'sign_semantic' in methods else None)
    for method in methods:
        pa = signed_a if method == 'sign_semantic' else ordinary_a['features']
        common = dict(pa=pa, plan=plan, ra=route_products_a, seed=seed)
        scores = _fit_similarity(a, b, records, method, signs_a, signs_b,
                                 rb=route_products_b, **common)
        rng = np.random.default_rng(_seed(seed, f'null/{method}'))
        null_maxima = {scope: [] for scope in scopes}
        for _ in range(null_permutations):
            order = _shuffle_blocks(rng, concepts, groups)
            sb = None if signs_b is None else np.asarray(signs_b)[order]
            rb = None if route_products_b is None else np.asarray(route_products_b)[order]
            null = _fit_similarity(a, b[order], records, method, signs_a, sb, rb=rb, **common)
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
    result['profiles_a'], result['profiles_b'] = ordinary_a, ordinary_b
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
    # Keep the full preregistered family size even for unavailable comparisons.
    # Their p=1 placeholder is used only for multiplicity, never as a measurement.
    adjusted = fdr_bh([tests[name]['pvalue'] if name in valid else 1. for name in names])
    result = {name: dict(tests[name], qvalue=None) for name in names}
    for name, q in zip(names, adjusted):
        if name in valid:
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
        return json_ready(value.item())
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_ready(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _effect_array(effects):
    a = np.asarray(effects, float)
    if a.ndim == 3:
        a = a[:, :, None, :]
    if a.ndim != 4 or not np.isfinite(a).all() or min(a.shape) == 0:
        raise ValueError('Effects require finite [examples,units,locations,modes] arrays')
    return a


def _effect_cells(a, b, records, split):
    concepts, _, groups, _ = _metadata(records, len(a), split)
    cells = {}
    for group in sorted(set(groups)):
        cells[group] = {}
        for concept in sorted(set(concepts[groups == group])):
            ix = (groups == group) & (concepts == concept)
            for mode in range(a.shape[2]):
                aa, bb = a[ix, :, mode], b[ix, :, mode]
                matrix = np.full((a.shape[1], b.shape[1]), np.nan)
                if len(aa) >= 3:
                    valid = (aa.std(0)[:, None] > 1e-10) & (bb.std(0)[None, :] > 1e-10)
                    corr = correlation_matrix(aa, bb)
                    matrix[valid] = corr[valid]
                cells[group][f'{concept}/mode{mode}'] = matrix
    return cells


def _causal_location_evaluation(a, b, records, fit, split):
    # Arrays here are [N,unit,mode]. Each concept/mode receives equal weight.
    cells = _effect_cells(a, b, records, split)
    scores = {name: {g: _mapped_score(c, mapping) for g, c in cells.items()}
              for name, mapping in fit['mappings'].items()}
    random = [{g: _mapped_score(c, mapping) for g, c in cells.items()}
              for mapping in fit['random_mappings']]
    scores['random'] = {}
    for group in cells:
        values = [x[group] for x in random if x[group] is not None]
        scores['random'][group] = float(np.mean(values)) if values else None
    sign_agreement = {}
    for name, mapping in fit['mappings'].items():
        rows, cols = np.asarray(mapping['source'], int), np.asarray(mapping['target'], int)
        left, right = a[:, rows], b[:, cols]
        valid = (np.abs(left) > 1e-8) & (np.abs(right) > 1e-8)
        sign_agreement[name] = dict(value=float((np.sign(left[valid]) == np.sign(right[valid])).mean())
                                           if valid.any() else None,
                                   n_nonzero_paired_effects=int(valid.sum()),
                                   descriptive_only=True, zero_tolerance=1e-8)
    descriptive = {}
    for name, values in scores.items():
        valid = [x for x in values.values() if x is not None]
        descriptive[name] = dict(mean=float(np.mean(valid)) if valid else None,
                                 n_valid_wrappers=len(valid), n_wrappers=len(values))
    return dict(wrapper_scores=scores, descriptive=descriptive,
                random_controls=dict(n_draws=len(random), wrapper_scores=random),
                sign_agreement=sign_agreement,
                metric='within-task, wrapper-and-intervention-equal causal Pearson correlation',
                evaluation_split=split, fit_split='D2')


def fit_causal_alignment(effects_a, effects_b, records, semantic_similarities, *,
                         split='D2', weights=(0., .25, .5, .75, 1.),
                         n_random=100, seed=1729, location_names=None, mode_names=None):
    """D2 half-wrapper causal fit, other-half lambda selection; no D4 access.

    Inputs are [N,unit,location,mode] (3D means one location). The caller must
    subset single units and grouped units separately. semantic_similarities is
    [unitA,unitB] or [location,unitA,unitB], estimated on D2 activation evidence.
    lambda weights causal similarity; ties choose the smallest lambda. Causal
    effect RMS normalization is fit on the first half only and retained for
    provenance. Test comparisons use within-task correlations with frozen maps.
    """
    if split != 'D2' or n_random < 100:
        raise ValueError('Causal fitting requires D2 and >=100 random controls')
    a, b = _effect_array(effects_a), _effect_array(effects_b)
    if a.shape[0] != b.shape[0] or a.shape[2:] != b.shape[2:]:
        raise ValueError('Models need shared examples, locations, and intervention modes')
    _, _, groups, _ = _metadata(records, len(a), split)
    unique = sorted(set(groups))
    if len(unique) < 4 or len(unique) % 2:
        raise ValueError('Require an even number >=4 shared wrappers for causal train/validation')
    half = len(unique)//2
    train_groups, validation_groups = unique[:half], unique[half:]
    train, validation = np.isin(groups, train_groups), np.isin(groups, validation_groups)
    val_records = [r for r, keep in zip(records, validation) if keep]
    weights = sorted(set(float(w) for w in weights))
    if not weights or any(not 0 <= w <= 1 for w in weights):
        raise ValueError('Mixture weights must lie in [0,1]')
    semantic = np.asarray(semantic_similarities, float)
    if semantic.ndim == 2:
        semantic = np.repeat(semantic[None], a.shape[2], axis=0)
    if semantic.shape != (a.shape[2], a.shape[1], b.shape[1]) or not np.isfinite(semantic).all():
        raise ValueError('Semantic similarities have invalid location/unit dimensions')
    locations = list(location_names) if location_names is not None else [f'location{i}' for i in range(a.shape[2])]
    modes = list(mode_names) if mode_names is not None else [f'mode{i}' for i in range(a.shape[3])]
    if len(locations) != a.shape[2] or len(set(locations)) != len(locations) or len(modes) != a.shape[3]:
        raise ValueError('Location/mode names disagree with array shape')
    output = dict(fit_split='D2', train_wrappers=train_groups,
                  validation_wrappers=validation_groups, locations={}, modes=modes,
                  location_order=locations,
                  weights=weights, seed=seed, normalization='unit-by-mode RMS from D2 fit-half only')
    for location, name in enumerate(locations):
        aa, bb = a[:, :, location], b[:, :, location]
        scale_a = np.maximum(np.sqrt((aa[train]**2).mean(0)), 1e-10)
        scale_b = np.maximum(np.sqrt((bb[train]**2).mean(0)), 1e-10)
        flat_a = (aa[train]/scale_a).transpose(0, 2, 1).reshape(-1, a.shape[1])
        flat_b = (bb[train]/scale_b).transpose(0, 2, 1).reshape(-1, b.shape[1])
        causal = correlation_matrix(flat_a, flat_b)
        validation_cells = _effect_cells(aa[validation], bb[validation], val_records, 'D2')
        candidates, selection = {}, []
        for weight in weights:
            mapping = match_neurons((1-weight)*semantic[location]+weight*causal)
            candidates[weight] = mapping
            scores = [_mapped_score(cell, mapping) for cell in validation_cells.values()]
            available = [score for score in scores if score is not None]
            mean = float(np.mean(available)) if len(available) == len(scores) else None
            selection.append(dict(causal_weight=weight, validation_mean=mean,
                                  n_valid_wrappers=len(available), wrapper_scores=dict(zip(validation_cells, scores))))
        eligible = [x for x in selection if x['validation_mean'] is not None]
        selected = max(eligible, key=lambda x: (x['validation_mean'], -x['causal_weight'])) if eligible else None
        mappings = dict(semantic=match_neurons(semantic[location]), causal=match_neurons(causal))
        if selected is not None:
            mappings['combined'] = candidates[selected['causal_weight']]
        else:
            # Preserve an explicit absent result instead of choosing using D4.
            mappings['combined'] = dict(source=np.array([],int),target=np.array([],int))
        rng = np.random.default_rng(_seed(seed, f'causal-random/{name}'))
        random = [match_neurons(rng.random(causal.shape)) for _ in range(n_random)]
        output['locations'][name] = dict(mappings=mappings, random_mappings=random,
                                         normalization_a=scale_a, normalization_b=scale_b,
                                         causal_similarity=causal, semantic_similarity=semantic[location],
                                         selected_causal_weight=selected['causal_weight'] if selected else None,
                                         selection=selection, selection_split='D2 validation half')
    return output


def evaluate_causal_alignment(effects_a, effects_b, records, fitted, *, split='D4'):
    if split != 'D4' or fitted.get('fit_split') != 'D2':
        raise ValueError('Causal test requires D4 and previously frozen D2 maps')
    a, b = _effect_array(effects_a), _effect_array(effects_b)
    _metadata(records, len(a), split)
    if (a.shape[0] != b.shape[0] or a.shape[2:] != b.shape[2:]
        or a.shape[2] != len(fitted['locations']) or a.shape[3] != len(fitted['modes'])):
        raise ValueError('Effect arrays disagree with each other or frozen locations')
    output = {}
    for i, name in enumerate(fitted.get('location_order', list(fitted['locations']))):
        fit = fitted['locations'][name]
        if len(fit['random_mappings']) < 100:
            raise ValueError('Missing repeated random controls')
        output[name] = _causal_location_evaluation(a[:, :, i],b[:, :, i],records,fit,split)
        output[name]['selected_causal_weight'] = fit['selected_causal_weight']
        output[name]['per_mode'] = {}
        for j, mode in enumerate(fitted['modes']):
            output[name]['per_mode'][mode] = _causal_location_evaluation(
                a[:, :, i, j:j+1],b[:, :, i,j:j+1],records,fit,split)
    return dict(locations=output, evaluation_split='D4', fit_split='D2',
                limitations=['Conditional on fixed units and observed models.',
                             'Exact-zero or constant effect modes are not evidence of agreement.',
                             'A matching effect does not establish raw weight-transfer compatibility.'])


def dose_response_diagnostics(effects, mode_names):
    """Supplementary raw magnitudes only; duplicate/identity modes are not primary evidence."""
    effects = _effect_array(effects)
    modes = list(mode_names)
    if len(modes) != effects.shape[-1] or len(set(modes)) != len(modes):
        raise ValueError('Mode names disagree with effect array')
    result = dict(mode_names=modes, mean_effect=effects.mean(0),
                  mean_absolute_effect=np.abs(effects).mean(0),
                  rms_effect=np.sqrt(np.square(effects).mean(0)),
                  max_absolute_effect=np.abs(effects).max(0),
                  axes=['unit','location','mode'],descriptive_only=True,
                  primary_modes=['zero','mean','patch'])
    if 'scale_1' in modes:
        result['identity_scale_1_max_absolute_effect'] = float(np.abs(effects[...,modes.index('scale_1')]).max())
    if 'zero' in modes and 'scale_0' in modes:
        result['zero_vs_scale_0_max_absolute_difference'] = float(np.abs(
            effects[...,modes.index('zero')]-effects[...,modes.index('scale_0')]).max())
    return result
