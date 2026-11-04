"""Followup-v2 controls, grouped interventions, and parameter-transplant probes.

Only within-MLP permutations are function-preserving by construction. Copying
native parameters between independent models assumes compatible residual
coordinates and is an empirical probe, NOT a circuit-preserving merge.
All parameter edits return a detached clone; source/target models are untouched.
"""
from __future__ import annotations

from contextlib import ExitStack
import copy
from dataclasses import asdict

import numpy as np
import torch

from .hooks import SwiGLUHook
from .models import TinyDecoder, model_mlps


INTERPOLATION_GRID = (0.0, 0.25, 0.5, 1.0)
DOSE_GRID = (0.0, 0.5, 1.0, 1.5, 2.0)
TRANSPLANT_LIMITATION = (
    "Native gate/up rows and down columns are copied in existing residual coordinates. "
    "Independent models need not share that basis; functional conservation does not "
    "guarantee transplant or merging compatibility."
)


def _clone(model):
    if any(m._forward_hooks or m._forward_pre_hooks or m._backward_hooks for m in model.modules()):
        raise ValueError("Remove active hooks before cloning parameter controls")
    return copy.deepcopy(model)


def _compatible(source, target):
    if not isinstance(source, TinyDecoder) or not isinstance(target, TinyDecoder):
        raise TypeError("Parameter transplantation/averaging supports TinyDecoder only")
    if asdict(source.config) != asdict(target.config):
        raise ValueError("Source and target must have exactly the same architecture/token vocabulary")


def _mapping(source, target, mapping):
    _compatible(source, target)
    left, right = model_mlps(source), model_mlps(target)
    records, targets = [], set()
    for row in mapping:
        rec = {name: int(row[name]) for name in ("source_layer", "source_neuron", "target_layer", "target_neuron")}
        sl, sn, tl, tn = [rec[name] for name in ("source_layer", "source_neuron", "target_layer", "target_neuron")]
        if not 0 <= sl < len(left) or not 0 <= tl < len(right):
            raise IndexError("Mapping layer is out of bounds")
        if not 0 <= sn < left[sl].down_proj.in_features or not 0 <= tn < right[tl].down_proj.in_features:
            raise IndexError("Mapping neuron is out of bounds")
        if (tl, tn) in targets:
            raise ValueError("Every transplant target must have one donor; duplicate targets are ambiguous")
        targets.add((tl, tn))
        records.append(rec)
    if not records:
        raise ValueError("An explicit nonempty group mapping is required")
    return records


@torch.no_grad()
def permute_swiglu_model(model, seed=1729, layers=None):
    """Return (permuted clone, source-to-target mapping) for exact MLP symmetry.

    New gate/up row j and down column j use old index perm[j]. Therefore an
    original neuron i maps to target index inverse_perm[i]. Residual coordinates,
    attention, embeddings, normalization, and all other parameters stay fixed.
    """
    if not isinstance(model, TinyDecoder):
        raise TypeError("The explicit positive control supports TinyDecoder only")
    result = _clone(model)
    original, changed = model_mlps(model), model_mlps(result)
    chosen = list(range(len(original))) if layers is None else list(map(int, layers))
    if len(chosen) != len(set(chosen)) or any(not 0 <= layer < len(original) for layer in chosen):
        raise ValueError("Permutation layers must be unique and in bounds")
    rng = np.random.default_rng(seed)
    mapping = []
    for layer, (before, after) in enumerate(zip(original, changed)):
        count = before.down_proj.in_features
        order = rng.permutation(count) if layer in chosen else np.arange(count)
        index = torch.as_tensor(order, device=before.gate_proj.weight.device)
        after.gate_proj.weight.copy_(before.gate_proj.weight[index])
        after.up_proj.weight.copy_(before.up_proj.weight[index])
        after.down_proj.weight.copy_(before.down_proj.weight[:, index])
        for projection in ("gate_proj", "up_proj"):
            bias = getattr(before, projection).bias
            if bias is not None:
                getattr(after, projection).bias.copy_(bias[index])
        inverse = np.argsort(order)
        mapping.extend({"source_layer": layer, "source_neuron": neuron,
                        "target_layer": layer, "target_neuron": int(inverse[neuron])}
                       for neuron in range(count))
    return result, mapping


@torch.no_grad()
def transplant_group(source, target, mapping, alpha=1.0):
    """Interpolate a mapped group of native parameters into a target clone.

    Each selected gate/up row and down column becomes
    (1-alpha)*target + alpha*source. A complete row+column is copied together.
    This parameter interpolation is nonlinear in the network's function.
    Many-to-one destinations are rejected; repeated donors to distinct targets
    are allowed and must be described as duplication, not a permutation.
    """
    if not np.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("Interpolation alpha must lie in [0,1]")
    records = _mapping(source, target, mapping)
    result = _clone(target)
    if alpha == 0:
        return result
    left, original, edited = model_mlps(source), model_mlps(target), model_mlps(result)
    for row in records:
        sl, sn, tl, tn = [row[name] for name in ("source_layer", "source_neuron", "target_layer", "target_neuron")]
        for projection in ("gate_proj", "up_proj"):
            src, tgt, dst = getattr(left[sl], projection), getattr(original[tl], projection), getattr(edited[tl], projection)
            donor = src.weight[sn].to(device=dst.weight.device, dtype=dst.weight.dtype)
            dst.weight[tn].copy_(torch.lerp(tgt.weight[tn], donor, alpha))
            if (src.bias is None) != (tgt.bias is None):
                raise ValueError("Projection bias structures differ")
            if src.bias is not None:
                dst.bias[tn].copy_(torch.lerp(tgt.bias[tn], src.bias[sn].to(dst.bias), alpha))
        donor = left[sl].down_proj.weight[:, sn].to(edited[tl].down_proj.weight)
        edited[tl].down_proj.weight[:, tn].copy_(torch.lerp(original[tl].down_proj.weight[:, tn], donor, alpha))
    return result


def random_group_mapping(source, target, mapping, seed=1729):
    """Same target units and source-layer group sizes, uniformly random donors.

    Samples without replacement inside each donor layer. This controls donor
    selection while preserving destination count and target group membership.
    It does not preserve each donor's activation/weight magnitude.
    """
    rows = _mapping(source, target, mapping)
    rng = np.random.default_rng(seed)
    widths = [mlp.down_proj.in_features for mlp in model_mlps(source)]
    result = [dict(row) for row in rows]
    for layer in sorted({row["source_layer"] for row in rows}):
        indices = [i for i, row in enumerate(rows) if row["source_layer"] == layer]
        if len(indices) > widths[layer]:
            raise ValueError("Requested random donor group exceeds layer width")
        donors = rng.choice(widths[layer], size=len(indices), replace=False)
        for i, neuron in zip(indices, donors):
            result[i]["source_neuron"] = int(neuron)
    return result


@torch.no_grad()
def parameter_average(source, target, alpha=0.5):
    """Naive full-parameter average control, explicitly without alignment."""
    _compatible(source, target)
    if not np.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("Interpolation alpha must lie in [0,1]")
    result = _clone(target)
    if alpha == 0:
        return result
    source_parameters = dict(source.named_parameters())
    target_parameters = dict(target.named_parameters())
    with torch.no_grad():
        for name, parameter in result.named_parameters():
            donor = source_parameters[name].to(parameter)
            parameter.copy_(torch.lerp(target_parameters[name], donor, alpha))
    return result


class GroupIntervention:
    """Group edits at a boolean [batch,time] mask or answer positions [batch].

    Uses existing SwiGLUHook to validate/capture the original actual down input,
    then changes only selected coordinates. No graph mutation survives exit.
    replacements_by_layer values may be scalar, [K], [B,K], or [B,T,K]. A
    [B,K] donor span mean broadcasts over recipient span positions explicitly;
    this is span-mean patching, not token-to-token aligned activation patching.
    .records[layer] contains original product and modified_product [B,T,K].
    """
    def __init__(self, model, units_by_layer, positions, mode, replacement_by_layer=None, scale=1.0):
        if mode not in (None, "zero", "mean", "patch", "scale"):
            raise ValueError("Unsupported group intervention")
        if not np.isfinite(scale) or not 0 <= scale <= 2:
            raise ValueError("Dose scale must lie in [0,2]")
        self.model, self.units_by_layer = model, {int(l): list(map(int, ns)) for l, ns in units_by_layer.items()}
        self.positions, self.mode, self.scale = positions, mode, scale
        self.replacements = {} if replacement_by_layer is None else {int(k): v for k, v in replacement_by_layer.items()}
        self.records, self._stack = {}, None
        mlps = model_mlps(model)
        if not self.units_by_layer:
            raise ValueError("A nonempty neuron group is required")
        for layer, neurons in self.units_by_layer.items():
            if not 0 <= layer < len(mlps):
                raise IndexError("Group layer is out of bounds")
            if not neurons or len(neurons) != len(set(neurons)) or any(not 0 <= n < mlps[layer].down_proj.in_features for n in neurons):
                raise ValueError("Group neuron indices must be nonempty, unique and in bounds")
            if mode in ("mean", "patch") and layer not in self.replacements:
                raise ValueError("Every edited layer requires reference replacement values")

    def __enter__(self):
        if self._stack is not None:
            raise RuntimeError("Group hook is already installed")
        self._stack = ExitStack()
        try:
            mlps = model_mlps(self.model)
            for layer, neurons in self.units_by_layer.items():
                observer = self._stack.enter_context(SwiGLUHook(mlps[layer], neurons=neurons,
                            positions=None, capture_contribution=False))
                handle = mlps[layer].down_proj.register_forward_pre_hook(self._edit(layer, neurons, observer))
                self._stack.callback(handle.remove)
        except BaseException:
            self._stack.close()
            self._stack = None
            raise
        return self

    def __exit__(self, *exc):
        stack, self._stack = self._stack, None
        return stack.__exit__(*exc)

    def _mask(self, product):
        b, t, _ = product.shape
        if isinstance(self.positions, int):
            pos = torch.full((b,), self.positions, device=product.device, dtype=torch.long)
        else:
            pos = torch.as_tensor(self.positions, device=product.device)
        if pos.dtype == torch.bool:
            if tuple(pos.shape) != (b, t):
                raise ValueError("Position mask must match [batch,time]")
            mask = pos
        else:
            if pos.ndim != 1 or len(pos) != b or pos.is_floating_point():
                raise ValueError("Answer positions must be integer [batch] or boolean [batch,time]")
            if bool(((pos < -t) | (pos >= t)).any()):
                raise IndexError("Answer position is out of bounds")
            mask = torch.zeros((b, t), dtype=torch.bool, device=product.device)
            mask[torch.arange(b, device=product.device), pos.long() % t] = True
        if not bool(mask.any(dim=1).all()):
            raise ValueError("Every example requires at least one selected position")
        return mask

    def _edit(self, layer, neurons, observer):
        def edit(module, inputs):
            product = inputs[0]
            mask = self._mask(product)
            selected = product[..., neurons]
            modified = selected
            changed = product
            if self.mode is not None:
                if self.mode == "zero":
                    value = torch.zeros_like(selected)
                elif self.mode == "scale":
                    value = selected * self.scale
                else:
                    value = torch.as_tensor(self.replacements[layer], dtype=product.dtype, device=product.device)
                    if value.ndim == 2 and tuple(value.shape) == (product.shape[0], len(neurons)):
                        value = value[:, None, :]
                    value = torch.broadcast_to(value, selected.shape)
                modified = torch.where(mask[..., None], value, selected)
                changed = product.clone()
                changed[..., neurons] = modified
            self.records[layer] = dict(observer.records, mask=mask.detach().cpu(),
                                       modified_product=modified.detach().float().cpu())
            return (changed,) + inputs[1:]
        return edit


def group_hooks(model, units_by_layer, positions, mode=None, replacement_by_layer=None, scale=1.0):
    return GroupIntervention(model, units_by_layer, positions, mode, replacement_by_layer, scale)


@torch.inference_mode()
def verify_permutation_control(model, permuted, mapping, input_ids, units_by_layer=None,
                               positions=-1, atol=1e-5, rtol=1e-4):
    """Measure output equivalence and mapped zero/mean/patch/dose interventions.

    This verifies a constructed symmetry; it is not independent-model evidence.
    Reference mean/patch values here are control inputs, not research D1 means.
    """
    rows = _mapping(model, permuted, mapping)
    lookup = {(r["source_layer"], r["source_neuron"]): (r["target_layer"], r["target_neuron"]) for r in rows}
    if len(lookup) != len(rows):
        raise ValueError("Permutation control requires unique source units")
    if units_by_layer is None:
        units_by_layer = {layer: list(range(min(4, mlp.down_proj.in_features))) for layer, mlp in enumerate(model_mlps(model))}
    targets = {}
    for layer, neurons in units_by_layer.items():
        for neuron in neurons:
            target_layer, target_neuron = lookup[(layer, neuron)]
            if target_layer != layer:
                raise ValueError("Constructed within-layer permutation must preserve layer identity")
            targets.setdefault(layer, []).append(target_neuron)
    before_mode, after_mode = model.training, permuted.training
    model.eval(); permuted.eval()
    try:
        original = model(input_ids).logits
        copied = permuted(input_ids).logits
        baseline_ok = bool(torch.allclose(original, copied, atol=atol, rtol=rtol))
        details = {"baseline_max_abs_logit_difference": float((original-copied).abs().max()),
                   "baseline_equal": baseline_ok, "atol": atol, "rtol": rtol,
                   "interpretation": "Constructed permutation symmetry positive control only", "interventions": {}}
        with group_hooks(model, units_by_layer, positions) as observed:
            model(input_ids)
        mean, patch = {}, {}
        for layer, record in observed.records.items():
            values, mask = record["product"], record["mask"]
            mean[layer] = values[mask].mean(0)
            per_example = (values * mask[..., None]).sum(1) / mask.sum(1)[:, None]
            patch[layer] = per_example.roll(1, dims=0)
        conditions = [("zero", "zero", None, 1.), ("mean", "mean", mean, 1.), ("patch", "patch", patch, 1.)]
        conditions.extend((f"scale_{dose:g}", "scale", None, dose) for dose in DOSE_GRID)
        for name, mode, replacement, dose in conditions:
            with group_hooks(model, units_by_layer, positions, mode, replacement, dose):
                left = model(input_ids).logits
            with group_hooks(permuted, targets, positions, mode, replacement, dose):
                right = permuted(input_ids).logits
            details["interventions"][name] = {"equal": bool(torch.allclose(left, right, atol=atol, rtol=rtol)),
                "max_abs_logit_difference": float((left-right).abs().max()),
                "source_max_abs_effect": float((original-left).abs().max()),
                "effect_difference_max_abs": float(((original-left)-(copied-right)).abs().max())}
        details["passed"] = baseline_ok and all(r["equal"] for r in details["interventions"].values())
        return details
    finally:
        model.train(before_mode); permuted.train(after_mode)
