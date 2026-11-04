"""CPU-only constructed controls, not scientific experiment outcomes."""
import numpy as np
import pytest
import torch

from src.models import ModelConfig, build_model
from src.followup_interventions import (
    permute_swiglu_model, verify_permutation_control, transplant_group,
    random_group_mapping, parameter_average, group_hooks,
)


@pytest.fixture
def models():
    torch.set_num_threads(1)
    config = ModelConfig(dim=16, hidden_dim=24, layers=2, heads=2, max_seq_len=64)
    return build_model(config, 11).eval(), build_model(config, 29).eval()


def snapshot(model):
    return {k: v.detach().clone() for k, v in model.state_dict().items()}


def assert_unchanged(model, before):
    for key, value in model.state_dict().items():
        torch.testing.assert_close(value, before[key], atol=0, rtol=0)


def test_permutation_preserves_logits_and_mapped_group_interventions(models):
    original, _ = models
    before = snapshot(original)
    permuted, mapping = permute_swiglu_model(original, seed=21)
    ids = torch.tensor([[3, 7, 8, 9], [4, 5, 6, 7]])
    mask = torch.tensor([[False, True, True, False], [True, False, False, True]])
    measured = verify_permutation_control(original, permuted, mapping, ids, positions=mask,
                                         atol=1e-6, rtol=1e-5)
    assert measured["passed"]
    assert len(measured["interventions"]) == 8
    assert measured["interventions"]["zero"]["source_max_abs_effect"] > 0
    assert_unchanged(original, before)
    assert not any(m._forward_pre_hooks for m in original.modules())
    assert not any(m._forward_pre_hooks for m in permuted.modules())


def test_permutation_mapping_direction_and_partial_layers(models):
    source, _ = models
    permuted, mapping = permute_swiglu_model(source, seed=55, layers=[0])
    for row in mapping:
        sl, sn, tl, tn = [row[k] for k in ("source_layer", "source_neuron", "target_layer", "target_neuron")]
        torch.testing.assert_close(source.layers[sl].mlp.gate_proj.weight[sn], permuted.layers[tl].mlp.gate_proj.weight[tn], atol=0, rtol=0)
        if sl == 1:
            assert sn == tn


@pytest.mark.parametrize("alpha", [0., .25, .5, 1.])
def test_transplant_exact_parameter_interpolation_only_mapped_group(models, alpha):
    source, target = models
    source_before, target_before = snapshot(source), snapshot(target)
    mapping = [{"source_layer": 0, "source_neuron": 2, "target_layer": 1, "target_neuron": 5},
               {"source_layer": 1, "source_neuron": 3, "target_layer": 1, "target_neuron": 7}]
    result = transplant_group(source, target, mapping, alpha=alpha)
    expected = snapshot(target)
    for row in mapping:
        sl, sn, tl, tn = [row[k] for k in ("source_layer", "source_neuron", "target_layer", "target_neuron")]
        for projection in ("gate_proj", "up_proj"):
            key = f"layers.{tl}.mlp.{projection}.weight"
            expected[key][tn] = torch.lerp(target_before[key][tn], source_before[f"layers.{sl}.mlp.{projection}.weight"][sn], alpha)
        key = f"layers.{tl}.mlp.down_proj.weight"
        expected[key][:, tn] = torch.lerp(target_before[key][:, tn], source_before[f"layers.{sl}.mlp.down_proj.weight"][:, sn], alpha)
    assert_unchanged(result, expected)
    assert_unchanged(source, source_before)
    assert_unchanged(target, target_before)
    assert result.embedding.weight.data_ptr() != target.embedding.weight.data_ptr()


def test_random_control_preserves_destination_and_group_size(models):
    source, target = models
    mapping = [{"source_layer": l, "source_neuron": n, "target_layer": l, "target_neuron": n+5}
               for l in (0, 1) for n in range(4)]
    random = random_group_mapping(source, target, mapping, seed=9)
    assert random == random_group_mapping(source, target, mapping, seed=9)
    assert len(random) == len(mapping)
    assert [(r["target_layer"], r["target_neuron"]) for r in random] == [(r["target_layer"], r["target_neuron"]) for r in mapping]
    assert len({r["source_neuron"] for r in random if r["source_layer"] == 0}) == 4


def test_naive_parameter_average_clones_target(models):
    source, target = models
    before = snapshot(target)
    result = parameter_average(source, target)
    for key, param in result.named_parameters():
        torch.testing.assert_close(param, torch.lerp(dict(target.named_parameters())[key], dict(source.named_parameters())[key], .5), atol=0, rtol=0)
    assert_unchanged(target, before)


@pytest.mark.parametrize("mode", ["zero", "mean", "patch", "scale"])
def test_group_mask_changes_exact_selected_channels_and_positions(models, mode):
    model, _ = models
    ids = torch.tensor([[3, 4, 5, 6], [7, 8, 9, 10]])
    mask = torch.tensor([[False, True, True, False], [True, False, False, True]])
    neurons = [2, 7]
    replacement = torch.tensor([[.1, .2], [.3, .4]])
    actual = []
    with group_hooks(model, {0: neurons}, mask, mode, {0: replacement}, scale=.5) as hooks:
        handle = model.layers[0].mlp.down_proj.register_forward_pre_hook(lambda m, args: actual.append(args[0].detach().clone()))
        model(ids)
        handle.remove()
    record = hooks.records[0]
    original_full = []
    handle = model.layers[0].mlp.down_proj.register_forward_pre_hook(lambda m, args: original_full.append(args[0].detach().clone()))
    model(ids)
    handle.remove()
    expected = original_full[0].clone()
    old = expected[..., neurons]
    new = torch.zeros_like(old) if mode == "zero" else old*.5 if mode == "scale" else replacement[:, None, :].expand_as(old)
    expected[..., neurons] = torch.where(mask[..., None], new, old)
    torch.testing.assert_close(actual[0], expected, atol=0, rtol=0)
    torch.testing.assert_close(record["product"], old, atol=0, rtol=0)
    torch.testing.assert_close(record["modified_product"], expected[..., neurons], atol=0, rtol=0)


def test_group_identity_answer_positions_and_cleanup(models):
    model, _ = models
    ids = torch.tensor([[3, 4, 5], [6, 7, 8]])
    before = model(ids).logits
    with group_hooks(model, {0: [1, 2], 1: [3]}, [1, 2], "scale", scale=1):
        after = model(ids).logits
    torch.testing.assert_close(before, after, atol=0, rtol=0)
    with pytest.raises(ValueError, match="mask must match"):
        with group_hooks(model, {0: [1]}, torch.zeros(2, 2, dtype=torch.bool), "zero"):
            model(ids)
    assert not any(m._forward_pre_hooks for m in model.modules())


def test_transplant_and_group_reject_ambiguous_inputs(models):
    source, target = models
    row = {"source_layer": 0, "source_neuron": 1, "target_layer": 0, "target_neuron": 2}
    with pytest.raises(ValueError, match="duplicate targets"):
        transplant_group(source, target, [row, row])
    with pytest.raises(ValueError, match="unique"):
        group_hooks(source, {0: [1, 1]}, -1, "zero")
    with pytest.raises(ValueError, match="reference"):
        group_hooks(source, {0: [1]}, -1, "mean")
    with pytest.raises(ValueError, match="Remove active hooks"):
        with group_hooks(target, {0: [1]}, -1):
            transplant_group(source, target, [row])
