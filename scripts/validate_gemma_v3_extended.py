"""Root-launched real-model G1 arithmetic checks, with prewritten tolerances.

This checks two formulations and cache schedules in the SAME HF engine. It is
not independent intervention validation or reproduction of the original map.
All error vectors are retained in NPZ; summary JSON records each comparison.
The first four greedy decisions are forced even after EOG for a fixed-length
arithmetic check. Normal generation stopping behavior is outside this check.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import torch

from src.gemma_v3_engine import NativeGeluHook, load_gemma_gguf, sha256_file


def metrics(left, right, criteria):
    """Accumulate in float64; preserve signed raw error vectors separately."""
    a, b = left.detach().float().cpu().numpy(), right.detach().float().cpu().numpy()
    delta = a.astype(np.float64) - b.astype(np.float64)
    finite = bool(np.isfinite(a).all() and np.isfinite(b).all())
    rmse = float(np.sqrt(np.mean(delta * delta))) if finite else None
    maximum = float(np.max(np.abs(delta))) if finite else None
    result = {
        "finite": finite, "rmse": rmse, "max_abs": maximum,
        "passed_numeric": finite and rmse <= criteria["logit_rmse_max"] and maximum <= criteria["logit_max_abs_max"],
    }
    return result, delta.astype(np.float32)


@contextmanager
def raw_delta_hook(down, neuron, target, capture):
    """Apply (target-current) W_down[:,neuron] to raw MLP output only."""
    def change(module, args, output):
        current = args[0][0, -1, neuron]
        delta = (torch.as_tensor(target, dtype=current.dtype, device=current.device) - current) * module.weight[:, neuron]
        changed = output.clone()
        changed[0, -1] += delta
        capture["raw"] = changed[0, -1].detach().clone()
        capture["delta"] = delta.detach().clone()
        capture["current"] = float(current)
        return changed
    handle = down.register_forward_hook(change)
    try:
        yield
    finally:
        handle.remove()


@torch.inference_mode()
def run_fixture(model, input_ids, units, criteria):
    if input_ids.ndim != 2 or input_ids.shape[0] != 1:
        raise ValueError("Validation expects exactly one unpadded token sequence")
    result = {"tokens": input_ids[0].tolist(), "native_delta": [], "cached_full": [], "greedy": []}
    errors = {}
    # Baseline covers all prompt positions, not just the final token.
    full = model(input_ids=input_ids, use_cache=False, logits_to_keep=0).logits[0].float().detach()
    if not torch.isfinite(full).all():
        raise RuntimeError("Nonfinite full-forward baseline")
    baseline_last = full[-1]
    for unit in units:
        layer, neuron = unit["layer_zero_based"], unit["neuron"]
        down = model.model.layers[layer].mlp.down_proj
        with NativeGeluHook(model, layer, [neuron], positions=-1) as capture:
            observed = model(input_ids=input_ids, use_cache=False, logits_to_keep=1).logits[0, -1].float()
        baseline_value = float(capture.records[-1]["product"][0, 0])
        capture_metrics, error = metrics(observed, baseline_last, criteria)
        errors[f"L{layer}_N{neuron}_capture_minus_baseline"] = error
        result.setdefault("capture_checks", []).append({"layer_zero_based": layer, "neuron": neuron, **capture_metrics})
        for mode, target in (("zero", 0.0), ("patch", -0.5 * baseline_value)):
            direct_raw = {}
            def grab_raw(module, args, output):
                direct_raw["raw"] = output[0, -1].detach().clone()
            handle = down.register_forward_hook(grab_raw)
            try:
                with NativeGeluHook(model, layer, [neuron], positions=-1, mode=mode, replacement=target):
                    direct = model(input_ids=input_ids, use_cache=False, logits_to_keep=1).logits[0, -1].float()
            finally:
                handle.remove()
            additive_raw = {}
            with raw_delta_hook(down, neuron, target, additive_raw):
                additive = model(input_ids=input_ids, use_cache=False, logits_to_keep=1).logits[0, -1].float()
            comparison, error = metrics(direct, additive, criteria)
            raw_left, raw_right = direct_raw["raw"], additive_raw["raw"]
            raw_error = (raw_left - raw_right).float().cpu().numpy()
            raw_ok = bool(torch.allclose(raw_left, raw_right, atol=criteria["raw_mlp_atol"], rtol=criteria["raw_mlp_rtol"]))
            label = f"L{layer}_N{neuron}_{mode}"
            errors[label + "_direct_minus_additive_logits"] = error
            errors[label + "_direct_minus_additive_raw_mlp"] = raw_error
            errors[label + "_direct_delta_logits"] = (direct - baseline_last).cpu().numpy()
            errors[label + "_additive_delta_logits"] = (additive - baseline_last).cpu().numpy()
            errors[label + "_explicit_raw_delta"] = additive_raw["delta"].cpu().numpy()
            result["native_delta"].append({
                "layer_zero_based": layer, "neuron": neuron, "mode": mode,
                "baseline_product": baseline_value, "target_product": target,
                "raw_mlp_allclose": raw_ok,
                "raw_mlp_rmse": float(np.sqrt(np.mean(raw_error.astype(np.float64) ** 2))),
                "raw_mlp_max_abs": float(np.abs(raw_error).max()),
                "direct_effect_max_abs": float((direct - baseline_last).abs().max()),
                "additive_effect_max_abs": float((additive - baseline_last).abs().max()),
                **comparison, "passed": raw_ok and comparison["passed_numeric"],
            })
    # One-token prefill, compare EVERY position against the full baseline.
    past = None
    cached_last = None
    cached_errors = []
    for position in range(input_ids.shape[1]):
        output = model(input_ids=input_ids[:, position:position + 1], past_key_values=past, use_cache=True, logits_to_keep=1)
        if output.past_key_values is None:
            raise RuntimeError("Model did not return a cache when requested")
        past = output.past_key_values
        cached_last = output.logits[0, -1].float()
        comparison, error = metrics(cached_last, full[position], criteria)
        top1 = int(cached_last.argmax()) == int(full[position].argmax())
        result["cached_full"].append({"position": position, "top1_exact": top1, **comparison, "passed": comparison["passed_numeric"] and top1})
        cached_errors.append(error)
    errors["cached_minus_full_all_prompt_positions"] = np.stack(cached_errors)
    # Separate context streams prevent forcing identical tokens after divergence.
    full_ids = input_ids.clone()
    full_last = baseline_last
    full_tokens, cached_tokens, greedy_errors = [], [], []
    for step in range(criteria["greedy_steps"]):
        context_equal = full_tokens == cached_tokens
        full_token, cache_token = int(full_last.argmax()), int(cached_last.argmax())
        comparison, error = metrics(cached_last, full_last, criteria)
        full_tokens.append(full_token)
        cached_tokens.append(cache_token)
        passed = context_equal and full_token == cache_token and comparison["passed_numeric"]
        result["greedy"].append({"step": step, "contexts_equal_before_step": context_equal, "full_token": full_token, "cached_token": cache_token, **comparison, "passed": passed})
        greedy_errors.append(error)
        if step + 1 < criteria["greedy_steps"]:
            full_ids = torch.cat((full_ids, torch.tensor([[full_token]], device=input_ids.device)), dim=1)
            full_last = model(input_ids=full_ids, use_cache=False, logits_to_keep=1).logits[0, -1].float()
            output = model(input_ids=torch.tensor([[cache_token]], device=input_ids.device), past_key_values=past, use_cache=True, logits_to_keep=1)
            past, cached_last = output.past_key_values, output.logits[0, -1].float()
    errors["greedy_cached_minus_full"] = np.stack(greedy_errors)
    result["greedy_full_tokens"] = full_tokens
    result["greedy_cached_tokens"] = cached_tokens
    result["passed"] = all(x["passed"] for group in ("native_delta", "cached_full", "greedy") for x in result[group]) and all(x["passed_numeric"] for x in result["capture_checks"])
    return result, errors


def _save_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--criteria", default="configs/gemma_v3_extended_numeric_criteria.json")
    parser.add_argument("--out", default="results/followup-v3-gemma-map/engineering_extended_validation")
    args = parser.parse_args()
    criteria_path = ROOT / args.criteria
    criteria = json.loads(criteria_path.read_text())
    if criteria["status"] != "FROZEN_BEFORE_GPU_EXECUTION":
        raise ValueError("Criteria must be frozen before loading the model")
    fixture_path = ROOT / "results/followup-v3-gemma-map/engineering_engine/fixtures.json"
    validation_path = fixture_path.with_name("validation.json")
    fixtures = json.loads(fixture_path.read_text())
    previous = json.loads(validation_path.read_text())
    for unit in criteria["units"]:
        if not any(row["fixture"] == unit["fixture"] and row["layer"] == unit["layer_zero_based"] and row["neuron"] == unit["neuron"] for row in previous["checks"]):
            raise ValueError("Frozen neuron does not match original engineering selection")
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=False)
    receipt = {
        "status": "STARTED", "scope": criteria["scope"], "criteria": criteria,
        "criteria_sha256": sha256_file(criteria_path), "script_sha256": sha256_file(__file__),
        "fixture_sha256": sha256_file(fixture_path), "original_validation_sha256": sha256_file(validation_path),
    }
    _save_new(out / "start.json", receipt)
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    started = time.monotonic()
    try:
        model, tokenizer, provenance = load_gemma_gguf(ROOT / "cache/gemma-v3/gemma-4-E2B-it-Q4_K_M.gguf", device=args.device, progress=lambda x: print(json.dumps(x), flush=True))
        results = []
        for index in criteria["fixture_indexes"]:
            fixture = fixtures[index]
            ids = tokenizer(fixture["prompt"], return_tensors="pt")["input_ids"].to(args.device)
            if ids[0].tolist() != previous["rows"][index]["tokens"]:
                raise ValueError("Fixture token IDs changed from original validation")
            units = [unit for unit in criteria["units"] if unit["fixture"] == index]
            row, arrays = run_fixture(model, ids, units, criteria)
            row.update({"fixture_index": index, "id": fixture["id"]})
            row["greedy_eog_encountered"] = any(token in tokenizer.eog_token_ids for token in row["greedy_full_tokens"] + row["greedy_cached_tokens"])
            array_path = out / f"fixture_{index}_raw_errors.npz"
            np.savez_compressed(array_path, **arrays)
            row["raw_errors_file"] = array_path.name
            row["raw_errors_sha256"] = sha256_file(array_path)
            _save_new(out / f"fixture_{index}.json", row)
            results.append(row)
            print(json.dumps({"fixture": index, "passed": row["passed"], "seconds": time.monotonic() - started}), flush=True)
        if str(args.device).startswith("cuda"):
            torch.cuda.synchronize()
        status = "PASS_SAME_ENGINE_ONLY" if all(row["passed"] for row in results) else "FAIL"
        _save_new(out / "summary.json", {
            **receipt, "status": status, "provenance": provenance, "rows": results,
            "elapsed_seconds": time.monotonic() - started,
            "limitation": "Not independent cross-engine intervention validation; two short raw E negation prompts, two layers and fixed single neurons. Greedy four-step arithmetic deliberately does not stop at EOG.",
        })
        if status == "FAIL":
            raise SystemExit(1)
    except Exception as exc:
        _save_new(out / "failure.json", {"status": "ERROR", "exception_type": type(exc).__name__, "message": str(exc), "elapsed_seconds": time.monotonic() - started})
        raise


if __name__ == "__main__":
    main()
