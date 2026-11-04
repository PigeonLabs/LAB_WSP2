"""CPU G3 endpoint for followup-v3; no model calls and no v2 mutations.

Inference is conditional on frozen models, selected units, maps and readiness
strata. It concerns new source-lineage clusters under the sampled source process,
not new models/neurons or the 16 within-family variants as independent samples.
Null-centered cluster-bootstrap tests are asymptotic, not exact randomization.
"""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import numpy as np

from .alignment import match_neurons


CLAIMS = (
    'H1_semantic_minus_activation_causal_agreement',
    'H2_combined_minus_activation_causal_agreement',
    'H3_feature_minus_native_causal_prediction_skill',
    'H4_joint_utility_and_semantic_fluency_retention',
)
CELLS = tuple(itertools.product((0, 1), (0, 1), ('en', 'ko')))


class NumericalFailure(ValueError):
    """Malformed/nonfinite/missing observations block a claim; never score zero."""


@dataclass(frozen=True)
class EffectPanel:
    values: np.ndarray  # family, (truth,answer_code,language), unit, proposition
    family_ids: tuple
    lineage_ids: tuple
    concepts: tuple
    cells: tuple
    unit_ids: tuple
    proposition_ids: tuple
    model_id: str
    split: str
    fit_partition: str | None


def _finite(x, name):
    x = np.asarray(x, dtype=np.float64)
    if not np.isfinite(x).all():
        raise NumericalFailure(f'{name}: NaN/Inf blocks claim completion')
    return x


def _state(row):
    return row.get('semantic_truth_state', row.get('semantic_state'))


def build_effect_panel(effects, records, expected_records, *, unit_ids, model_id,
                       row_ids=None, cells=CELLS):
    """Validate against the frozen collection manifest, center K, average lexical.

    effects must be full-continuation logP(do)-logP(baseline), [row,unit,K].
    expected_records is mandatory: without it an entirely uncollected family
    cannot be detected. Canonical proposition IDs must already align alternatives
    across answer codes, languages, and model tokenizers. No truth-sign multiply.
    """
    x = _finite(effects, 'effect tensor')
    if x.ndim != 3 or len(records) != x.shape[0] or x.shape[1] != len(unit_ids) or x.shape[2] < 2:
        raise NumericalFailure('Expected [rows,units,K>=2] effects and matching metadata')
    if len(set(unit_ids)) != len(unit_ids) or not len(unit_ids):
        raise NumericalFailure('Unit IDs must be unique and nonempty')
    if not isinstance(model_id,str) or not model_id:
        raise NumericalFailure('Verified model/revision identity is required')
    if not records or not expected_records:
        raise NumericalFailure('Empty observations/expected manifest')
    actual_ids = [r['id'] for r in records]
    expected = {r['id']:r for r in expected_records}
    if (len(set(actual_ids)) != len(actual_ids) or len(expected) != len(expected_records)
        or set(actual_ids) != set(expected)):
        raise NumericalFailure('Missing, duplicate, or unexpected measured row')
    if row_ids is not None and list(row_ids) != actual_ids:
        raise NumericalFailure('Tensor row IDs disagree with record order')
    keys = ('family_id','lineage_id','concept','answer_code','language','lexical','split','fit_partition',
            'canonical_proposition_ids')
    for row in records:
        frozen = expected[row['id']]
        if any(row.get(k) != frozen.get(k) for k in keys) or _state(row) != _state(frozen):
            raise NumericalFailure('Observation metadata differs from frozen manifest')
        if _state(row) not in (0,1) or row['answer_code'] not in (0,1):
            raise NumericalFailure('Binary truth and answer-code factors required')
    splits = {r['split'] for r in records}
    partitions = {r.get('fit_partition') for r in records}
    if len(splits) != 1 or len(partitions) != 1:
        raise NumericalFailure('Mixed split or F partition in one effect panel')
    alternatives = tuple(records[0]['canonical_proposition_ids'])
    if len(alternatives) != x.shape[-1] or len(set(alternatives)) != len(alternatives):
        raise NumericalFailure('Canonical alternative axis is malformed')
    if any(tuple(r['canonical_proposition_ids']) != alternatives for r in records):
        raise NumericalFailure('Canonical proposition order differs across rows')
    cells = tuple(tuple(c) for c in cells)
    if len(set(cells)) != len(cells):
        raise NumericalFailure('Duplicate planned stratum cell')
    families = sorted({r['family_id'] for r in records})
    centered = x - x.mean(axis=-1, keepdims=True)
    values, lineages, concepts = [], [], []
    for family in families:
        indices = [i for i,r in enumerate(records) if r['family_id'] == family]
        items = [records[i] for i in indices]
        if len({(r['lineage_id'],r['concept']) for r in items}) != 1:
            raise NumericalFailure('Family changes concept or source lineage across variants')
        lineages.append(items[0]['lineage_id']);concepts.append(items[0]['concept'])
        observed = {(_state(r),r['answer_code'],r['language']) for r in items}
        if observed != set(cells):
            raise NumericalFailure('Missing/unexpected family stratum cell')
        out = []
        for cell in cells:
            take = [i for i in indices if (_state(records[i]),records[i]['answer_code'],records[i]['language']) == cell]
            if len({records[i]['lexical'] for i in take}) != len(take):
                raise NumericalFailure('Duplicate lexical variant inside family cell')
            out.append(centered[take].mean(0))
        values.append(out)
    values = _finite(values,'family-averaged centered effects')
    values.setflags(write=False)
    return EffectPanel(values,tuple(families),tuple(lineages),tuple(concepts),cells,
                       tuple(unit_ids),alternatives,model_id,next(iter(splits)),next(iter(partitions)))


def fit_epsilon(panel, *, sd_fraction=.05, nats_floor=1e-6):
    """Frozen model/unit epsilon from F-fit only; never recomputed by bootstrap."""
    if panel.split != 'fit' or panel.fit_partition != 'train':
        raise ValueError('Epsilon must be frozen from fit/train, never validation/test')
    if sd_fraction != .05 or nats_floor != 1e-6:
        raise ValueError('G3 frozen epsilon settings are .05 SD and 1e-6 nats floor')
    sd = panel.values.transpose(0,1,3,2).reshape(-1,len(panel.unit_ids)).std(0,ddof=0)
    epsilon = np.maximum(sd_fraction*sd,nats_floor)
    return dict(unit_ids=list(panel.unit_ids),epsilon=epsilon.tolist(),effect_sd=sd.tolist(),
                model_id=panel.model_id,fit_family_ids=list(panel.family_ids),
                fit_split='fit',fit_partition='train',sd_fraction=sd_fraction,nats_floor=nats_floor,
                definition='Population SD over F-fit family/cell/canonical-alternative effects after K centering and lexical mean')


def partial_match(similarity, threshold):
    """Exact partial assignment with dummy unmatched targets; F fitting only."""
    s = _finite(similarity,'matching similarity')
    if s.ndim != 2 or not np.isfinite(threshold):
        raise NumericalFailure('Invalid matching matrix or threshold')
    result = match_neurons(s,threshold=float(threshold),mode='partial')
    return {k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in result.items()}


def choose_validation_map(candidates, validation_losses, *, split='fit', partition='validation'):
    """Select predeclared maps by externally computed F-validation prediction loss.

    Exact loss ties prefer fewer matched pairs, then stable candidate name. This
    helper does not invent a response-prediction model or consult test effects.
    """
    if split != 'fit' or partition != 'validation' or set(candidates) != set(validation_losses):
        raise ValueError('Require corresponding F-validation candidates/losses')
    losses = {k:float(v) for k,v in validation_losses.items()}
    if not losses or not np.isfinite(list(losses.values())).all():
        raise NumericalFailure('Nonfinite/missing validation loss')
    chosen = min(losses,key=lambda k:(losses[k],len(candidates[k]['source']),str(k)))
    return dict(selected=chosen,mapping=candidates[chosen],validation_losses=losses,
                selection_split='fit/validation',tie_policy='fewer matched pairs then candidate name')


def _check_pair(a,b,eps_a,eps_b):
    for field in ('family_ids','lineage_ids','concepts','cells','proposition_ids','split','fit_partition'):
        if getattr(a,field) != getattr(b,field):
            raise NumericalFailure(f'Cross-model panel mismatch: {field}')
    for panel,eps in ((a,eps_a),(b,eps_b)):
        if (tuple(eps.get('unit_ids',())) != panel.unit_ids or eps.get('fit_split')!='fit'
            or eps.get('fit_partition')!='train' or eps.get('model_id')!=panel.model_id):
            raise NumericalFailure('Epsilon provenance/unit identities do not match')
        values = _finite(eps['epsilon'],'frozen epsilon')
        if values.shape != (len(panel.unit_ids),) or np.any(values < 1e-6):
            raise NumericalFailure('Invalid frozen epsilon vector')
        _finite(panel.values,'panel effects')


def _mapping_targets(mapping,n_source,n_target,max_targets):
    targets = [[] for _ in range(n_source)]
    if isinstance(mapping,dict):
        rows,cols = mapping['source'],mapping['target']
    else:
        if len(mapping) != n_source:
            raise NumericalFailure('Mapping vector must include every source denominator slot')
        rows,cols = zip(*[(i,j) for i,j in enumerate(mapping) if j != -1]) if any(j != -1 for j in mapping) else ([],[])
    if len(rows) != len(cols):
        raise NumericalFailure('Mapping source/target length mismatch')
    for i,j in zip(rows,cols):
        if not np.isfinite([i,j]).all() or int(i)!=i or int(j)!=j or not 0 <= i < n_source or not 0 <= j < n_target:
            raise NumericalFailure('Invalid mapping index')
        if int(j) in targets[int(i)]:
            raise NumericalFailure('Duplicate mapping edge')
        targets[int(i)].append(int(j))
    if max_targets not in (1,4) or any(len(t)>max_targets for t in targets):
        raise NumericalFailure('Primary maps allow one target; secondary one-to-many cap is four')
    return targets


def score_maps(a,b,maps,eps_a,eps_b,*,eligible_strata,source_layers,
               family_weights=None,max_targets=1):
    """Exact G3 score with fixed h/k/source/layer weights and unmatched zero.

    eligible_strata is frozen (concept,truth,answer_code,language). Within each
    h/k, correlation is across families, never across truth/code/language cells.
    Layers are weighted equally, then sources within layer equally. Selected
    targets of a one-to-many source share total weight one.
    """
    _check_pair(a,b,eps_a,eps_b)
    n,u,k = len(a.family_ids),len(a.unit_ids),len(a.proposition_ids)
    if len(source_layers)!=u or not u:
        raise NumericalFailure('Missing source layer denominator')
    weights = np.ones(n) if family_weights is None else _finite(family_weights,'family resampling weights')
    if weights.shape!=(n,) or np.any(weights<0):
        raise NumericalFailure('Invalid family resampling weights')
    strata = [tuple(h) for h in eligible_strata]
    if not strata or len(set(strata))!=len(strata):
        raise NumericalFailure('Empty/duplicate frozen eligible strata')
    layers = np.asarray(source_layers)
    unique_layers = sorted(set(layers.tolist()))
    unit_weights = np.array([1/len(unique_layers)/np.sum(layers==layer) for layer in layers])
    ea,eb = np.asarray(eps_a['epsilon']),np.asarray(eps_b['epsilon'])
    targets = {name:_mapping_targets(m,u,len(b.unit_ids),max_targets) for name,m in maps.items()}
    totals = {name:0. for name in maps}
    constant_counts=0
    for concept,truth,code,lang in strata:
        cell=(truth,code,lang)
        if cell not in a.cells:
            raise NumericalFailure('Eligible stratum absent from collection plan')
        index=a.cells.index(cell)
        take=np.array([c==concept for c in a.concepts])
        w=weights[take]
        if not take.any() or w.sum()<=0:
            raise NumericalFailure('No observed/resampled families in an eligible stratum')
        x,y=a.values[take,index],b.values[take,index]
        # A singleton bootstrap support yields zero variance and therefore zero.
        xc=x-np.einsum('f,fuk->uk',w,x)[None]/w.sum()
        yc=y-np.einsum('f,fvk->vk',w,y)[None]/w.sum()
        vx=np.einsum('f,fuk,fuk->uk',w,xc,xc)/w.sum()
        vy=np.einsum('f,fvk,fvk->vk',w,yc,yc)/w.sum()
        cov=np.einsum('f,fuk,fvk->uvk',w,xc,yc)/w.sum()
        denominator=np.sqrt((vx[:,None,:]+ea[:,None,None]**2)*(vy[None,:,:]+eb[None,:,None]**2))
        corr=cov/denominator
        # Exact constants remain zero, including roundoff after weighted means.
        cx=np.ptp(x[w>0],axis=0)==0;cy=np.ptp(y[w>0],axis=0)==0
        corr=np.where(cx[:,None,:]|cy[None,:,:],0.,corr)
        _finite(corr,'within-stratum regularized correlation')
        constant_counts+=int(cx.sum())
        for name,matched in targets.items():
            source_score=np.array([float(corr[i,js].mean()) if js else 0. for i,js in enumerate(matched)])
            totals[name]+=float(unit_weights@source_score)/len(strata)
    return dict(scores=totals,coverage={name:float(sum(bool(t) for t in ts)/u) for name,ts in targets.items()},
                source_denominator=u,layer_denominator=len(unique_layers),stratum_denominator=len(strata),
                canonical_alternatives=k,constant_source_hk_cells=constant_counts,
                effect_energy_a=float(np.mean(a.values**2)),effect_energy_b=float(np.mean(b.values**2)),
                fixed_weighting='equal eligible h/k; equal layers; equal sources within layer; source total weight one',
                missing_or_nonfinite_policy='FAIL_CLAIM',unmatched_and_constant_score=0.)


def null_centered_bootstrap_test(observed,bootstrap_statistics,*,null=0.,alternative='greater'):
    """Asymptotic bootstrap error distribution centered at a boundary null.

    This is not sign-flip randomization, an exact test, or a simultaneous CI.
    Validity requires exchangeable independent sampled lineages within strata,
    sufficient clusters, stable nondegenerate moments, and a frozen analysis.
    """
    boot=_finite(bootstrap_statistics,'bootstrap statistics')
    if boot.ndim!=1 or not len(boot) or not np.isfinite([observed,null]).all():
        raise NumericalFailure('Invalid bootstrap test inputs')
    error=boot-observed;distance=observed-null
    if alternative=='greater':exceed=error>=distance
    elif alternative=='less':exceed=error<=distance
    elif alternative=='two-sided':exceed=np.abs(error)>=abs(distance)
    else:raise ValueError('Unknown alternative')
    return dict(p_value=float((1+exceed.sum())/(len(boot)+1)),alternative=alternative,
                null=float(null),method='null-centered cluster bootstrap, asymptotic',
                confidence_interval=np.quantile(boot,[.025,.975]).tolist(),
                interval_scope='ordinary pointwise percentile 95%; not simultaneous')


def bootstrap_maps(a,b,maps,eps_a,eps_b,*,eligible_strata,source_layers,comparisons,
                   n_boot=10000,seed=20261104,max_targets=1,minimum_lineages=40):
    """Concept-stratified upper-lineage resampling, shared jointly by ALL arms.

    Multiple scenarios from one lineage travel together. A lineage crossing
    concept strata is rejected rather than split into pseudo-independent units.
    E engineering data with one lineage/concept cannot yield inferential CIs.
    """
    if n_boot<2:raise ValueError('At least two bootstrap replicates required')
    base=score_maps(a,b,maps,eps_a,eps_b,eligible_strata=eligible_strata,
                    source_layers=source_layers,max_targets=max_targets)
    lineage_concepts={}
    for lineage,concept in zip(a.lineage_ids,a.concepts):
        lineage_concepts.setdefault(lineage,set()).add(concept)
    if any(len(v)!=1 for v in lineage_concepts.values()):
        raise NumericalFailure('Upper lineage spans concept strata; a joint cross-stratum resampling design is required')
    concepts=sorted({h[0] for h in eligible_strata})
    blocks={c:sorted({l for l,cc in zip(a.lineage_ids,a.concepts) if cc==c}) for c in concepts}
    counts={c:len(v) for c,v in blocks.items()}
    if any(n<2 for n in counts.values()):
        return dict(status='NOT_EVALUABLE_INSUFFICIENT_INDEPENDENT_LINEAGES',observed=base,
                    lineage_counts=counts,comparisons={},bootstrap_scores=None,measured_endpoint=True,
                    measured_inferential_p=False,scope='Engineering scenarios sharing one template are not independent families')
    for name,comparison in comparisons.items():
        if comparison['arm'] not in maps or comparison['baseline'] not in maps:
            raise ValueError(f'Unknown map in comparison {name}')
    rng=np.random.default_rng(seed)
    names=list(maps);draws=np.empty((n_boot,len(names)))
    family_lineages=np.array(a.lineage_ids)
    for replicate in range(n_boot):
        weights=np.zeros(len(a.family_ids))
        for concept,lineages in blocks.items():
            chosen=rng.choice(lineages,size=len(lineages),replace=True)
            for lineage in lineages:
                weights[family_lineages==lineage]=int(np.sum(chosen==lineage))
        scores=score_maps(a,b,maps,eps_a,eps_b,eligible_strata=eligible_strata,
                          source_layers=source_layers,family_weights=weights,max_targets=max_targets)['scores']
        draws[replicate]=[scores[name] for name in names]
    tests={}
    eligible=all(n>=minimum_lineages for n in counts.values())
    for name,comparison in comparisons.items():
        left,right=comparison['arm'],comparison['baseline']
        observed=base['scores'][left]-base['scores'][right]
        distribution=draws[:,names.index(left)]-draws[:,names.index(right)]
        tests[name]=dict(effect=observed,**null_centered_bootstrap_test(observed,distribution,
                         alternative=comparison.get('alternative','greater'),null=comparison.get('null',0.)),
                         claim_eligible_lineage_count=eligible)
    return dict(status='MEASURED_CONDITIONAL' if eligible else 'EXPLORATORY_FEW_LINEAGES',
                observed=base,comparisons=tests,bootstrap_scores=draws,arm_order=names,
                lineage_counts=counts,n_boot=n_boot,seed=seed,all_arms_resampled_jointly=True,
                recompute='Within-family lexical/K centering cached (exact under whole-family resampling); stratum means/covariances/correlations recomputed; F epsilon/maps fixed',
                scope='Fixed observed models and selected units; exchangeable new source-lineage population only')


def holm_four(claims,alpha=.05):
    """Exactly four claims; unavailable=placeholder1, NOT measured null evidence."""
    if set(claims)-set(CLAIMS):raise ValueError('Unknown confirmatory claim')
    if alpha != .05:raise ValueError('Frozen Holm family alpha is .05')
    inputs=[];output={}
    for name in CLAIMS:
        claim=dict(claims.get(name,{}));measured=claim.get('measured',False)
        if measured:
            p=claim.get('p_value')
            if p is None or not np.isfinite(p) or not 0<=p<=1:raise NumericalFailure('Invalid measured claim p-value')
        else:p=1.
        inputs.append(p)
        output[name]=dict(claim,p_value=float(p) if measured else None,
                          measured=measured,holm_input_p=float(p),
                          multiplicity_placeholder=not measured,
                          scientific_status=claim.get('scientific_status','MEASURED' if measured else 'NOT_EVALUABLE'))
    order=np.argsort(inputs,kind='stable');adjusted=np.zeros(4);running=0.
    for rank,index in enumerate(order):
        running=max(running,(4-rank)*inputs[index]);adjusted[index]=min(1.,running)
    for index,name in enumerate(CLAIMS):
        measured=output[name]['measured']
        output[name].update(holm_adjusted_p=float(adjusted[index]) if measured else None,
                            multiplicity_calculation_adjusted_p=float(adjusted[index]),
                            reject_null=bool(measured and adjusted[index]<=alpha))
    return dict(family_size=4,alpha=alpha,method='Holm FWER',claims=output,
                placeholder_policy='Unmeasured blocked claims enter multiplicity as1 but are never displayed as measured p=1')


def h4_composite_p(gain_p,semantic_noninferiority_p,fluency_noninferiority_p):
    values=_finite([gain_p,semantic_noninferiority_p,fluency_noninferiority_p],'H4 component p-values')
    if np.any((values<0)|(values>1)):raise NumericalFailure('Invalid H4 component p-value')
    return float(values.max())
