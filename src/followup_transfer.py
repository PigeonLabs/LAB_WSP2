"""F5: D2-selected native-parameter transfer probes, evaluated once on D4.

Mapping/target-task/group/alpha selection uses D2 only and is in-sample fitting.
The selected policy is persisted before any D4 model scoring. All D4 conditions
are descriptive; only the selected-minus-target contrast receives inference.
Native transplantation does not establish residual-basis or circuit compatibility.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

from .experiment import sequence_margins
from .followup_interventions import (
    transplant_group, random_group_mapping, parameter_average, TRANSPLANT_LIMITATION,
)
from .models import ByteTokenizer
from .statistics import cluster_bootstrap, paired_randomization_test
from .training import load_trained, parameter_hash


VERSION = "followup-v2-native-transfer-v1"


def _hash_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _write(path, value):
    path = Path(path)
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError(f"Refusing to overwrite different transfer artifact: {path}")
        return
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text)
    temp.replace(path)


def _save(path, **arrays):
    path = Path(path)
    if path.exists():
        old = np.load(path)
        if set(old.files) != set(arrays) or any(not np.array_equal(old[k], v) for k, v in arrays.items()):
            raise ValueError("Refusing to overwrite different transfer measurements")
        return
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    temp.replace(path)


def _seed_name(seed):
    return f"seed{int(str(seed).replace('seed_', '').replace('seed', ''))}"


def _collection_path(run_dir, name, split):
    root = Path(run_dir) / "collections" / name / "final"
    options = [root/split/"measurements.npz", root/f"{split}.npz"]
    found = [p for p in options if p.exists()]
    if len(found) != 1:
        raise ValueError(f"Need exactly one {name}/{split} measurement artifact; found {found}")
    return found[0]


def _load_collection(path, records):
    manifest_path = Path(path).parent/"manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        recorded = manifest.get("plan", {}).get("records_sha256")
        if recorded is not None and recorded != _digest(records):
            raise ValueError("D2 record contents differ from collection manifest")
        recorded_file = manifest.get("measurements_sha256")
        if recorded_file is not None and recorded_file != _hash_file(path):
            raise ValueError("D2 collection checksum differs from manifest")
    with np.load(path) as loaded:
        arrays = {k: loaded[k] for k in loaded.files}
    required = ("layers", "neuron_ids", "row_ids", "margins")
    if any(k not in arrays for k in required):
        raise ValueError("Collection lacks candidate coordinates or margins")
    product = arrays.get("answer_product", arrays.get("product"))
    if product is None or product.shape != (len(records), len(arrays["layers"])) or len(arrays["neuron_ids"]) != len(arrays["layers"]):
        raise ValueError("Answer-boundary activation dimensions disagree")
    if not np.array_equal(arrays["row_ids"], [r["id"] for r in records]):
        raise ValueError("D2 measurement row order differs from supplied dataset")
    if not np.isfinite(product).all() or not np.isfinite(arrays["margins"]).all():
        raise ValueError("Nonfinite collection values")
    arrays["product"] = product
    return arrays


def _accuracy(margins, records):
    concepts = np.asarray([r["concept"] for r in records])
    return {concept: float(np.mean(np.asarray(margins)[concepts == concept] > 0))
            for concept in sorted(set(concepts))}


def choose_target_task(donor_margins, target_margins, records):
    """Largest D2-only donor-minus-target competence gap; deterministic ties."""
    if any(r.get("split") != "D2" for r in records):
        raise ValueError("Task selection accepts D2 only")
    donor, target = _accuracy(donor_margins, records), _accuracy(target_margins, records)
    if len(donor) < 2:
        raise ValueError("Retention control requires at least two tasks")
    gaps = {task: donor[task]-target[task] for task in donor}
    chosen = sorted(gaps, key=lambda task: (-gaps[task], task))[0]
    return {"target_task": chosen, "donor_accuracy": donor, "target_accuracy": target,
            "competence_gap": gaps, "positive_donor_gap": gaps[chosen] > 0,
            "selection_split": "D2"}


def _truth_scores(product, records, task):
    labels = np.asarray([r["label"] for r in records])
    concepts = np.asarray([r["concept"] for r in records])
    groups = np.asarray([r["group_id"] for r in records])
    contrasts = []
    for group in sorted(set(groups[concepts == task])):
        use = (concepts == task) & (groups == group)
        pos, neg = product[use & (labels == 1)], product[use & (labels == 0)]
        if not len(pos) or not len(neg):
            raise ValueError("D2 truth contrast requires both labels within every wrapper")
        scale = product[use].std(0)
        contrast = np.divide(pos.mean(0)-neg.mean(0), scale,
                             out=np.zeros(product.shape[1]), where=scale > 1e-10)
        contrasts.append(contrast)
    return np.abs(np.mean(contrasts, axis=0))


def _fit_path(run_dir, donor, target):
    number = lambda name: int(name.replace("seed", ""))
    a, b = sorted([donor, target], key=number)
    path = Path(run_dir)/"alignment"/f"{a}_{b}"/"answer"/"fit.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return path, donor != a


def mapped_groups(fitted, donor_collection, target_collection, records, task, *,
                  reverse=False, group_size=4):
    """Use frozen layerwise maps; rank donor units by D2 task truth contrast."""
    if any(r.get("split") != "D2" for r in records):
        raise ValueError("Group selection accepts D2 only")
    if group_size < 1:
        raise ValueError("Positive group size required")
    mappings = fitted.get("mappings", fitted.get("maps"))
    if mappings is None:
        raise ValueError("Frozen fit must contain mappings/maps")
    scores = _truth_scores(donor_collection["product"], records, task)
    result = {}
    for method in ("activation", "semantic"):
        fit = mappings[f"{method}__layer__hungarian"]
        if fit.get("fit_split", "D2") != "D2":
            raise ValueError("Frozen mapping must be fit on D2")
        source = np.asarray(fit["target" if reverse else "source"], dtype=int)
        target = np.asarray(fit["source" if reverse else "target"], dtype=int)
        if source.ndim != 1 or source.shape != target.shape or len(set(source)) != len(source) or len(set(target)) != len(target):
            raise ValueError("Transplant requires an unambiguous one-to-one mapping")
        if any(source < 0) or any(source >= len(donor_collection["layers"])) or any(target < 0) or any(target >= len(target_collection["layers"])):
            raise IndexError("Mapping candidate index out of bounds")
        selected = []
        for layer in sorted(set(donor_collection["layers"].tolist())):
            eligible = [i for i, col in enumerate(source) if donor_collection["layers"][col] == layer]
            if len(eligible) < group_size:
                raise ValueError("Frozen map has fewer candidates than the declared per-layer group")
            chosen = sorted(eligible, key=lambda i: (-scores[source[i]], int(source[i])))[:group_size]
            for i in chosen:
                a, b = int(source[i]), int(target[i])
                if donor_collection["layers"][a] != target_collection["layers"][b]:
                    raise ValueError("F5 same-architecture layerwise map crossed layers")
                selected.append({"source_layer": int(donor_collection["layers"][a]),
                    "source_neuron": int(donor_collection["neuron_ids"][a]),
                    "target_layer": int(target_collection["layers"][b]),
                    "target_neuron": int(target_collection["neuron_ids"][b]),
                    "source_column": a, "target_column": b, "d2_truth_contrast_abs": float(scores[a])})
        result[method] = selected
    return result


def select_policy(d2_results, baseline, target_task, retention_tolerance=.02):
    """Choose aligned transfer only; random/naive controls are never proposed."""
    eligible = []
    considered = []
    for condition, result in sorted(d2_results.items()):
        if result["method"] not in ("activation", "semantic"):
            continue
        gain = result["accuracy"][target_task] - baseline[target_task]
        changes = {task: result["accuracy"][task]-value for task, value in baseline.items() if task != target_task}
        retains = all(value >= -retention_tolerance-1e-12 for value in changes.values())
        considered.append({"condition": condition, "target_gain": gain, "other_task_changes": changes,
                           "retention_satisfied": retains})
        if result["alpha"] > 0 and gain > 0 and retains:
            eligible.append((gain, min(changes.values()), -result["alpha"], condition))
    best = sorted(eligible, key=lambda x: (-x[0], -x[1], -x[2], x[3]))[0][-1] if eligible else None
    return {"selected": best, "selected_none": best is None,
            "reason": "positive D2 target gain with per-task retention" if best else "no aligned transfer has positive D2 gain and required retention",
            "target_task": target_task, "retention_tolerance": retention_tolerance,
            "eligible_methods": ["activation", "semantic"], "considered": considered,
            "selection_scope": "all D2, in-sample fitting; no additional independent validation fold"}


def _condition_key(method, alpha):
    return f"{method}__alpha_{alpha:g}"


def _candidate(source, target, condition, mappings):
    if condition["method"] == "naive_average":
        return parameter_average(source, target, condition["alpha"])
    return transplant_group(source, target, mappings[condition["method"]], condition["alpha"])


def _same_vocabulary(source, target, tok_a, tok_b):
    if not isinstance(tok_a, ByteTokenizer) or not isinstance(tok_b, ByteTokenizer):
        raise TypeError("F5 currently requires the same fixed ByteTokenizer for both tiny models")
    if source.config.vocab_size != target.config.vocab_size or source.config.vocab_size != tok_a.vocab_size:
        raise ValueError("Model vocabulary and fixed tokenizer are incompatible")
    probe = "ASCII 0123 yes no 한🙂"
    if tok_a.encode(probe) != tok_b.encode(probe):
        raise ValueError("Token IDs differ despite matching vocabulary sizes")


def run_transfers(dataset, run_dir, config, device="cuda"):
    """Run frozen directed-pair F5 policies; return JSON-ready aggregate summary.

    Existing immutable per-pair results resume only under identical input hashes.
    Each new pair freezes D2 policy.json before any D4 calls. All original model
    parameter hashes are checked after candidate evaluation.
    """
    run_dir = Path(run_dir)
    settings = config["transplant"]
    if settings.get("selection_split", "D2") != "D2" or settings.get("test_split", "D4") != "D4":
        raise ValueError("F5 requires D2 selection and D4 evaluation")
    for split in ("D2", "D4"):
        if not dataset[split] or any(r.get("split") != split for r in dataset[split]):
            raise ValueError("Dataset split contents disagree")
        if len({r["id"] for r in dataset[split]}) != len(dataset[split]):
            raise ValueError("Duplicate evaluation row IDs")
    if {r["id"] for r in dataset["D2"]} & {r["id"] for r in dataset["D4"]}:
        raise ValueError("D2/D4 ID leakage")
    if {r["concept"] for r in dataset["D2"]} != {r["concept"] for r in dataset["D4"]}:
        raise ValueError("D2 and D4 must cover the same transfer/retention tasks")
    if not settings.get("directed_pairs"):
        raise ValueError("At least one frozen directed pair is required")
    weights = list(map(float, settings.get("interpolation_weights", [0, .25, .5, 1])))
    if not weights or len(set(weights)) != len(weights) or 0 not in weights or any(not 0 <= a <= 1 for a in weights):
        raise ValueError("Unique interpolation weights in [0,1], including zero, required")
    random_seeds = list(map(int, settings.get("random_seeds", [17, 31, 47])))
    if len(set(random_seeds)) < 3 or len(set(random_seeds)) != len(random_seeds):
        raise ValueError("At least three independent random-donor seeds are required")
    group_size = int(settings.get("group_size", config.get("causal", {}).get("group_size", 4)))
    batch_size = int(settings.get("batch_size", 16))
    output = run_dir/"transfers"
    output.mkdir(parents=True, exist_ok=True)
    pair_results, wrapper_vectors = {}, {}
    checkpoint_hashes = {}
    for donor_seed, target_seed in settings["directed_pairs"]:
        donor_name, target_name = _seed_name(donor_seed), _seed_name(target_seed)
        if donor_name == target_name:
            raise ValueError("F5 directed pairs must use independent seeds")
        pair_name = f"{donor_name}_to_{target_name}"
        pair_dir = output/pair_name
        pair_dir.mkdir(exist_ok=True)
        source_path = run_dir/"training"/f"seed_{int(donor_name[4:])}"/"final.pt"
        target_path = run_dir/"training"/f"seed_{int(target_name[4:])}"/"final.pt"
        donor_file, target_file = (_collection_path(run_dir, name, "D2") for name in (donor_name, target_name))
        fit_file, reverse = _fit_path(run_dir, donor_name, target_name)
        for path in (source_path, target_path):
            if str(path) not in checkpoint_hashes:
                checkpoint_hashes[str(path)] = _hash_file(path)
        plan = {"version": VERSION, "donor": donor_name, "target": target_name,
            "settings": settings, "group_size": group_size, "random_seeds": random_seeds,
            "d2_sha256": _digest(dataset["D2"]), "d4_sha256": _digest(dataset["D4"]),
            "source_checkpoint_sha256": checkpoint_hashes[str(source_path)],
            "target_checkpoint_sha256": checkpoint_hashes[str(target_path)],
            "donor_collection_sha256": _hash_file(donor_file), "target_collection_sha256": _hash_file(target_file),
            "fit_sha256": _hash_file(fit_file), "fit_inverted": reverse}
        signature = _digest(plan)
        final_path = pair_dir/"summary.json"
        if final_path.exists():
            previous = json.loads(final_path.read_text())
            if previous["signature"] != signature:
                raise ValueError("Completed F5 input signatures changed; choose a new run")
            pair_results[pair_name] = previous
            wrapper_vectors[pair_name] = previous["selected_minus_baseline"]["wrapper_effects"]
            continue
        started = time.monotonic()
        donor_data = _load_collection(donor_file, dataset["D2"])
        target_data = _load_collection(target_file, dataset["D2"])
        task_choice = choose_target_task(donor_data["margins"], target_data["margins"], dataset["D2"])
        target_task = task_choice["target_task"]
        mappings = mapped_groups(json.loads(fit_file.read_text()), donor_data, target_data, dataset["D2"],
                                 target_task, reverse=reverse, group_size=group_size)
        source, tok_source = load_trained(source_path, device=device)
        target, tok_target = load_trained(target_path, device=device)
        _same_vocabulary(source, target, tok_source, tok_target)
        before_source, before_target = parameter_hash(source), parameter_hash(target)
        for seed in random_seeds:
            mappings[f"random_seed{seed}"] = random_group_mapping(source, target, mappings["activation"], seed)
        conditions = [{"method": method, "alpha": alpha} for method in list(mappings)+["naive_average"] for alpha in weights]
        d2_baseline = target_data["margins"]
        d2_arrays = {"baseline": d2_baseline, "row_ids": np.asarray([r["id"] for r in dataset["D2"]])}
        d2_results = {}
        for condition in conditions:
            key = _condition_key(**condition)
            if condition["alpha"] == 0:
                margins = d2_baseline.copy()
            else:
                candidate = _candidate(source, target, condition, mappings).eval()
                margins, _ = sequence_margins(candidate, tok_target, dataset["D2"], device=device, batch_size=batch_size)
                del candidate
            d2_arrays[key] = margins
            d2_results[key] = {**condition, "accuracy": _accuracy(margins, dataset["D2"])}
        policy = select_policy(d2_results, task_choice["target_accuracy"], target_task,
                               float(settings.get("retention_tolerance", .02)))
        policy_artifact = {"signature": signature, "plan": plan, "task_choice": task_choice,
            "mappings": mappings, "conditions": conditions, "d2_results": d2_results, "policy": policy,
            "frozen_before_D4_scoring": True, "limitations": [TRANSPLANT_LIMITATION,
                "All D2 examples fit mappings, group choice, target task, and alpha; D2 gains are in-sample.",
                "Random donors preserve target units/group size but not donor activation magnitude."]}
        _save(pair_dir/"D2_margins.npz", **d2_arrays)
        _write(pair_dir/"policy.json", policy_artifact)
        # No model scoring on D4 occurs above this persisted policy boundary.
        baseline, counts = sequence_margins(target, tok_target, dataset["D4"], device=device, batch_size=batch_size)
        d4_arrays = {"baseline": baseline, "answer_token_counts": counts,
            "row_ids": np.asarray([r["id"] for r in dataset["D4"]]),
            "groups": np.asarray([r["group_id"] for r in dataset["D4"]]),
            "concepts": np.asarray([r["concept"] for r in dataset["D4"]])}
        d4_results = {}
        for condition in conditions:
            key = _condition_key(**condition)
            if condition["alpha"] == 0:
                margins = baseline.copy()
            else:
                candidate = _candidate(source, target, condition, mappings).eval()
                margins, _ = sequence_margins(candidate, tok_target, dataset["D4"], device=device, batch_size=batch_size)
                del candidate
            d4_arrays[key] = margins
            d4_results[key] = {**condition, "accuracy": _accuracy(margins, dataset["D4"]),
                               "status": "DESCRIPTIVE_ONLY_NO_D4_SELECTION"}
        selected = d4_arrays[policy["selected"]] if policy["selected"] else baseline
        use = d4_arrays["concepts"] == target_task
        selected_correct = (selected[use] > 0).astype(float)
        base_correct = (baseline[use] > 0).astype(float)
        groups = d4_arrays["groups"][use]
        difference = selected_correct-base_correct
        wrapper_effects = {str(group): float(difference[groups == group].mean()) for group in sorted(set(groups))}
        test = paired_randomization_test(selected_correct, base_correct, groups)
        effect = {**test, "bootstrap": cluster_bootstrap(difference, groups), "wrapper_effects": wrapper_effects,
            "hypothesis": "D2-selected aligned transplant improves D4 target-task accuracy versus untouched target",
            "global_bh_pending": True, "selected_none": policy["selected_none"],
            "selection_is_positive_control": False}
        after_source, after_target = parameter_hash(source), parameter_hash(target)
        if before_source != after_source or before_target != after_target:
            raise AssertionError("Original model parameters were mutated by transfer evaluation")
        result = {"signature": signature, "pair": pair_name, "target_task": target_task,
            "policy": policy, "task_choice": task_choice, "d4_baseline_accuracy": _accuracy(baseline, dataset["D4"]),
            "d4_conditions": d4_results, "selected_minus_baseline": effect,
            "original_parameter_hashes": {"donor_before": before_source, "donor_after": after_source,
                "target_before": before_target, "target_after": after_target},
            "elapsed_seconds": time.monotonic()-started, "conditions_evaluated": len(conditions),
            "limitations": policy_artifact["limitations"] + [
                "Five directed pairs reuse models; they are not independent seed replicates.",
                "D4 results for unselected methods and weights are descriptive and cannot change the policy.",
                "Native parameter transfer is not evidence of circuit-preserving model merging."]}
        _save(pair_dir/"D4_margins.npz", **d4_arrays)
        _write(final_path, result)
        pair_results[pair_name] = result
        wrapper_vectors[pair_name] = wrapper_effects
        del source, target
        if str(device).startswith("cuda"):
            torch.cuda.empty_cache()
    wrappers = sorted(next(iter(wrapper_vectors.values())))
    if any(sorted(v) != wrappers for v in wrapper_vectors.values()):
        raise ValueError("All directed pairs must retain the same D4 wrapper support")
    joint = np.mean([[v[w] for w in wrappers] for v in wrapper_vectors.values()], axis=0)
    aggregate = {**paired_randomization_test(joint, np.zeros_like(joint), wrappers),
        "bootstrap": cluster_bootstrap(joint, wrappers), "n_pairs": len(wrapper_vectors),
        "wrapper_effects": dict(zip(wrappers, joint.tolist())),
        "inference_scope": "fixed observed models; pairs averaged inside shared wrappers, not treated as independent observations",
        "global_bh_pending": True}
    summary = {"version": VERSION, "pairs": pair_results, "aggregate_selected_minus_baseline": aggregate,
        "primary_test": "aggregate selected-minus-baseline target-task accuracy; global BH pending",
        "pair_tests": "descriptive unless explicitly included in the predeclared global family",
        "status": "COMPLETED", "selection_split": "D2", "evaluation_split": "D4"}
    _write(output/"summary.json", summary)
    return summary


def main(argv=None):
    """Public CLI reproduces the same default-format metadata as collection."""
    import argparse
    from .followup_data import load_dataset
    from .followup_calibration import transform_records

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default="results/followup-v2", help="Existing F1/F3 run with training, collections and alignment")
    parser.add_argument("--dataset-dir", default="data/followup-v2", help="Frozen version-two dataset directory")
    parser.add_argument("--config", default="configs/followup_v2.json", help="Frozen experiment JSON configuration")
    parser.add_argument("--device", default="cuda", help="cuda, cuda:N, or cpu")
    parser.add_argument("--threads", type=int, default=8, help="PyTorch CPU thread count (default: 8)")
    parser.add_argument("--batch-size", type=int, default=None, help="Explicit scoring batch override; config value or 16 otherwise")
    parser.add_argument("--check-only", action="store_true", help="Validate device, configuration and dataset formatting without model inference")
    args = parser.parse_args(argv)
    if args.threads < 1 or (args.batch_size is not None and args.batch_size < 1):
        parser.error("threads and batch-size must be positive")
    device = torch.device(args.device)
    if device.type not in ("cpu", "cuda"):
        parser.error("Only CPU and CUDA are supported")
    if device.type == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; use a GPU-capable execution environment or explicitly pass --device cpu")
        if device.index is not None and device.index >= torch.cuda.device_count():
            raise RuntimeError("Requested CUDA device index is unavailable")
    torch.set_num_threads(args.threads)
    config = json.loads(Path(args.config).read_text())
    if args.batch_size is not None:
        config["transplant"]["batch_size"] = args.batch_size
    dataset = load_dataset(args.dataset_dir)
    # Default formatting leaves prompt text unchanged but adds the calibration
    # provenance fields hashed by followup_engine.collect; raw rows are different.
    formatted = {split: transform_records(dataset[split], "default", dataset["train"])
                 for split in ("D2", "D4")}
    if args.check_only:
        result = {"status": "PREFLIGHT_ONLY_NO_MODEL_INFERENCE", "device": str(device),
                  "run_dir": str(Path(args.run_dir)), "threads": args.threads,
                  "batch_size": config["transplant"].get("batch_size", 16),
                  "prompt_variant": "default", "splits": {s: len(r) for s, r in formatted.items()},
                  "formatted_dataset_hashes": {s: _digest(r) for s, r in formatted.items()}}
    else:
        measured = run_transfers(formatted, args.run_dir, config, device=str(device))
        result = {"status": measured["status"], "pairs": len(measured["pairs"]),
                  "summary": str(Path(args.run_dir)/"transfers"/"summary.json"),
                  "aggregate_selected_minus_baseline": measured["aggregate_selected_minus_baseline"]}
    print(json.dumps(result, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    main()
