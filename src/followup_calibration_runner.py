"""Sequential, resumable followup-v2 format calibration; no held-out evaluation.

Run only after the resource scheduler authorizes GPU work. Example:
  python -m src.followup_calibration_runner --models seed101 qwen --resume
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np
import torch

from .followup_calibration import (
    PROTOCOL_VERSION, VARIANTS, calibration_summary, choose_variant, save_lock,
    transform_records, validate_context,
)
from .training import load_trained

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results" / "followup-v2"
DATA = ROOT / "data" / "followup-v2"
TINY_NAMES = tuple(f"seed{s}" for s in (101, 211, 307, 401, 503))
HF_NAMES = ("qwen", "smol", "olmo")
MODEL_NAMES = TINY_NAMES + HF_NAMES


def _sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _relative(path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _model_descriptor(name, checkpoint="final", run_dir=None):
    """Describe immutable model identity without allocating CPU/GPU weights."""
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown followup model {name!r}; expected {MODEL_NAMES}")
    if checkpoint not in ("initial", "middle", "final"):
        raise ValueError("Checkpoint must be initial, middle, or final")
    root = Path(run_dir) if run_dir is not None else RUN
    if name in TINY_NAMES:
        seed = int(name[4:])
        path = root / "training" / f"seed_{seed}" / f"{checkpoint}.pt"
        if not path.is_file():
            raise FileNotFoundError(f"Required trained checkpoint is absent: {path}")
        digest = _sha_file(path)
        return {"id": name, "family": "independent_tiny", "seed": seed,
                "checkpoint_kind": checkpoint, "checkpoint": _relative(path),
                "sha256": digest, "checkpoint_sha256": digest,
                "source_run": _relative(root)}
    if checkpoint != "final":
        raise ValueError("Public pretrained models have only the pinned final revision")
    entries = json.loads((ROOT / "configs" / "models.json").read_text())["models"]
    model_id = {"qwen": "Qwen/Qwen3-0.6B-Base", "smol": "HuggingFaceTB/SmolLM2-360M",
                "olmo": "allenai/OLMo-2-0425-1B"}[name]
    item = next(m for m in entries if m["model_id"] == model_id)
    return {"id": name, "family": "public_pretrained", "model_id": item["model_id"],
            "revision": item["revision"], "license": item["license"],
            "model_type": item["model_type"],
            "cached_file_manifest_sha256": _hash_json(item["files"])}


def load_followup_model(name, checkpoint="final", device="cuda", run_dir=None):
    """Load a reproducibly identified tiny checkpoint or pinned cached HF model.

    GPU HF loading follows the existing ``src.runner.load`` path. CPU loading
    uses those same cached assets without briefly allocating a GPU. This helper
    does not apply prompt locks; callers include both returned model info and
    the final lock in their own measurement signatures.
    """
    info = _model_descriptor(name, checkpoint, run_dir)
    if name in TINY_NAMES:
        path = Path(info["checkpoint"])
        if not path.is_absolute():
            path = ROOT / path
        model, tokenizer = load_trained(path, device)
    elif str(device).startswith("cuda"):
        from .runner import load
        model, tokenizer, original = load(name)
        if any(original[k] != info[k] for k in ("id", "model_id", "revision", "license")):
            raise RuntimeError("Public model loader returned unexpected pinned identity")
        model = model.to(device)
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        entries = json.loads((ROOT / "configs" / "models.json").read_text())["models"]
        item = next(m for m in entries if m["model_id"] == info["model_id"])
        tokenizer = AutoTokenizer.from_pretrained(item["local_path"], local_files_only=True,
                                                  trust_remote_code=False)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(item["local_path"], local_files_only=True,
                                                    trust_remote_code=False, dtype=torch.float32).to(device)
    return model.eval(), tokenizer, info


def transform_for_model(rows, name, train_rows, run_dir=None):
    """Apply a persisted final calibration lock, also to earlier tiny checkpoints.

    Never changes a format based on the supplied rows' outcome or split.
    Training rows remain default; calibration/evaluation uses the locked format.
    """
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown followup model {name!r}")
    root = Path(run_dir) if run_dir is not None else RUN
    folder = root / "calibration" / name
    summary = json.loads((folder / "summary.json").read_text())
    if _sha_file(folder / "lock.json") != summary["artifact_sha256"]["lock.json"]:
        raise ValueError("Calibration lock changed after publication")
    lock = json.loads((folder / "lock.json").read_text())
    if lock.get("calibration_signature") != summary["signature"]:
        raise ValueError("Calibration lock and summary signatures disagree")
    if lock.get("protocol_version") != PROTOCOL_VERSION or lock.get("model_info", {}).get("id") != name:
        raise ValueError("Calibration lock protocol/model identity mismatch")
    if lock.get("training_records_sha256") != _hash_json(train_rows):
        raise ValueError("TRAIN demonstration bank changed after calibration lock")
    rows = list(rows)
    if any(r["split"] == "train" for r in rows):
        if not all(r["split"] == "train" for r in rows):
            raise ValueError("Do not mix TRAIN and evaluation records")
        variant = "default"
    else:
        variant = lock["variant"]
    return transform_records(rows, variant, train_rows)


def _read_calibration_data(directory):
    """Read and hash only TRAIN and calibration, never D1-D4 JSONL files."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    dataset, file_hashes = {}, {}
    for split in ("train", "calibration"):
        name = f"{split}.jsonl"
        payload = (directory / name).read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != manifest["file_sha256"][name]:
            raise ValueError(f"Frozen calibration input hash mismatch: {name}")
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
        if not rows or any(r["split"] != split for r in rows):
            raise ValueError(f"Wrong split inside {name}")
        dataset[split] = rows
        file_hashes[name] = actual
    return dataset, file_hashes


def _fixed_default_lock(summary):
    return {"protocol_version": PROTOCOL_VERSION, "variant": "default", "source_split": "calibration",
            "variants_evaluated": ["default"], "selection_mode": "fixed_default_no_format_selection",
            "selection_rule": "E1 byte models use default at every checkpoint; calibration measures competence only",
            "selected_metrics": summary, "metrics": {"default": summary},
            "locked_before": ["D1", "D2", "D3", "D4"],
            "correction": "none; raw sequence margins preserved for competence and causal effects",
            "competence_gate": {"accuracy_min": .70, "wilson95_lower_strictly_above": .5,
                                "both_models_required": True, "D4_reported_separately": True}}


def _source_hashes():
    return {name: _sha_file(Path(__file__).with_name(name)) for name in
            ("followup_calibration_runner.py", "followup_calibration.py", "experiment.py", "models.py", "hooks.py")}


def calibrate_model(name, dataset, dataset_hashes, run_dir=None, device="cuda", batch_size=8, resume=False):
    """Measure one final model, then atomically publish immutable artifacts."""
    if set(dataset) != {"train", "calibration"}:
        raise ValueError("Calibration runner accepts TRAIN and calibration only, never final evaluations")
    if not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    root = Path(run_dir) if run_dir is not None else RUN
    out = root / "calibration" / name
    model_info = _model_descriptor(name, "final", root)
    variants = ("default",) if name in TINY_NAMES else VARIANTS
    specification = {"model_info": model_info, "data_file_sha256": dataset_hashes,
                     "training_records_sha256": _hash_json(dataset["train"]),
                     "calibration_records_sha256": _hash_json(dataset["calibration"]),
                     "variants": list(variants), "protocol": PROTOCOL_VERSION, "source_sha256": _source_hashes(),
                     "precision": "float32", "batch_size": batch_size, "device": str(device),
                     "answer_boundary": "separate_prompt_and_full_continuation_tokens; no_truncation"}
    signature = _hash_json(specification)
    if out.exists():
        if not resume:
            raise FileExistsError(f"Calibration exists; use --resume: {out}")
        summary_path = out / "summary.json"
        if not summary_path.is_file():
            raise ValueError("Incomplete calibration folder exists; preserve it and use a new run directory")
        previous = json.loads(summary_path.read_text())
        if previous["signature"] != signature:
            raise ValueError("Calibration model/data/code/settings changed; refusing incompatible resume")
        for filename, digest in previous["artifact_sha256"].items():
            if _sha_file(out / filename) != digest:
                raise ValueError(f"Calibration artifact was changed: {filename}")
        print(json.dumps({"model": name, "status": "REUSED", "variant": previous["variant"]}), flush=True)
        return previous

    from .experiment import sequence_margins
    is_cuda = str(device).startswith("cuda")
    if is_cuda and not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; no silent CPU substitution")
    started = time.monotonic()
    model, tokenizer, loaded_info = load_followup_model(name, "final", device, root)
    if loaded_info != model_info:
        raise RuntimeError("Model identity changed between preparation and loading")
    if is_cuda:
        torch.cuda.reset_peak_memory_stats(device)
    evidence, results, contexts, timings = {}, {}, {}, {}
    try:
        for variant in variants:
            rows = transform_records(dataset["calibration"], variant, dataset["train"])
            contexts[variant] = validate_context(rows, tokenizer, model.config, variant)
            variant_started = time.monotonic()
            margins, token_counts = sequence_margins(model, tokenizer, rows, device=device, batch_size=batch_size)
            if is_cuda:
                torch.cuda.synchronize(device)
            timings[variant] = time.monotonic() - variant_started
            results[variant] = {"rows": rows, "margins": margins}
            evidence[f"margins_{variant}"] = np.asarray(margins, dtype=np.float64)
            evidence[f"answer_token_counts_{variant}"] = np.asarray(token_counts, dtype=np.int64)
            evidence[f"prompts_{variant}"] = np.asarray([r["prompt"] for r in rows])
            print(json.dumps({"model": name, "variant": variant, "status": "CALIBRATION_MEASURED",
                              "metrics": calibration_summary(margins, rows)}), flush=True)
        if name in TINY_NAMES:
            lock = _fixed_default_lock(calibration_summary(results["default"]["margins"], results["default"]["rows"]))
        else:
            lock = choose_variant(results)
            lock["selection_mode"] = "calibration_only_format_selection"
        evidence["row_ids"] = np.asarray([r["id"] for r in dataset["calibration"]])
        evidence["labels"] = np.asarray([r["label"] for r in dataset["calibration"]], dtype=np.int64)
        evidence["concepts"] = np.asarray([r["concept"] for r in dataset["calibration"]])
        evidence["groups"] = np.asarray([r["group_id"] for r in dataset["calibration"]])
        lock["model_info"] = model_info
        lock["training_records_sha256"] = specification["training_records_sha256"]
        lock["calibration_signature"] = signature
        lock["fixed_for_all_checkpoints"] = name in TINY_NAMES
        lock["held_out_status"] = {"D3": "PENDING_UNTIL_F3_MAPS_FROZEN", "D4": "PENDING_UNTIL_F4_MAPS_FROZEN"}
        summary = {"status": "CALIBRATED", "model": name, "model_info": model_info,
                   "signature": signature, "specification": specification, "variant": lock["variant"],
                   "selection_mode": lock["selection_mode"], "calibration_metrics": lock["metrics"],
                   "contexts": contexts, "variant_seconds": timings, "elapsed_seconds": time.monotonic() - started,
                   "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)) if is_cuda else None,
                   "device": str(device), "precision": "float32", "held_out_status": lock["held_out_status"],
                   "hypothesis_verdict": "NOT_EVALUATED_CALIBRATION_ONLY"}
        parent = out.parent
        parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{name}-calibration-", dir=parent))
        try:
            np.savez_compressed(temporary / "evidence.npz", **evidence)
            lock["evidence_file_sha256"] = _sha_file(temporary / "evidence.npz")
            save_lock(temporary / "lock.json", lock)
            summary["artifact_sha256"] = {f: _sha_file(temporary / f) for f in ("lock.json", "evidence.npz")}
            (temporary / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
            if out.exists():
                raise FileExistsError("Another worker created calibration output concurrently")
            os.rename(temporary, out)
        except BaseException:
            # This directory holds only this invocation's unpublished artifacts.
            shutil.rmtree(temporary)
            raise
        print(json.dumps({"model": name, "status": "LOCKED", "variant": lock["variant"],
                          "path": str(out), "seconds": summary["elapsed_seconds"]}), flush=True)
        return summary
    finally:
        del model, tokenizer
        gc.collect()
        if is_cuda:
            torch.cuda.empty_cache()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", choices=MODEL_NAMES, default=list(MODEL_NAMES))
    parser.add_argument("--run-dir", type=Path, default=RUN)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    torch.set_num_threads(8)
    dataset, hashes = _read_calibration_data(args.data_dir)
    # No background jobs: exactly one model is loaded and measured at a time.
    for name in args.models:
        calibrate_model(name, dataset, hashes, args.run_dir, args.device, args.batch_size, args.resume)


if __name__ == "__main__":
    main()
