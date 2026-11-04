"""Leakage-resistant prompt-format calibration for followup-v2.

Pure CPU utilities. This module never loads models or reads evaluation files.
The caller evaluates formats only on ``calibration``, persists the selected
lock, and supplies the locked transformed records to the existing evaluator.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

VARIANTS = ("default", "explicit", "fourshot")
INSTRUCTION = (
    "Decide whether the statement is true. Treat any facts stated in the "
    "question as given. Answer with exactly yes if it is true, or no if it "
    "is false.\n\n"
)
PROTOCOL_VERSION = "followup-v2-format-calibration-v1"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _variant(value):
    value = "fourshot" if value == "4shot" else value
    if value not in VARIANTS:
        raise ValueError(f"Unknown prompt variant {value!r}; expected {VARIANTS}")
    return value


def _validate_record(row):
    required = ("id", "split", "concept", "label", "prompt", "correct", "foil", "span")
    if any(k not in row for k in required):
        raise ValueError(f"Missing required record fields: {required}")
    if row["label"] not in (0, 1):
        raise ValueError("Truth label must be 0 or 1")
    expected = (" yes", " no") if row["label"] else (" no", " yes")
    if (row["correct"], row["foil"]) != expected:
        raise ValueError("Truth labels must agree with fixed yes/no candidate strings")
    start, end = row["span"]
    if not (isinstance(start, int) and isinstance(end, int)
            and 0 <= start < end <= len(row["prompt"])):
        raise ValueError("Invalid statement character span")


def _demonstrations(train_records, concept):
    """Two complete train-only pairs, shortest prompts first, then stable IDs.

    'Easy' is an outcome-blind short-text heuristic, not model success. No
    calibration or evaluation example is eligible as a demonstration.
    """
    pairs = {}
    ids = set()
    for row in train_records:
        _validate_record(row)
        if row["split"] != "train":
            raise ValueError("Demonstration bank must contain TRAIN records only")
        if row["id"] in ids:
            raise ValueError("Duplicate demonstration record ID")
        ids.add(row["id"])
        if row["concept"] == concept:
            if "pair_id" not in row:
                raise ValueError("Four-shot demonstrations require matched pair_id")
            pairs.setdefault(row["pair_id"], []).append(row)
    for pair in pairs.values():
        if len(pair) != 2 or sorted(r["label"] for r in pair) != [0, 1]:
            raise ValueError("Every demonstration pair must have one true and one false row")
    if len(pairs) < 2:
        raise ValueError(f"Need two complete TRAIN pairs for concept {concept!r}")
    ranked = sorted(pairs.items(), key=lambda item: (
        max(len(r["prompt"]) for r in item[1]),
        sum(len(r["prompt"]) for r in item[1]), str(item[0])))
    selected = []
    # Each concept uses one yes-first pair and one no-first pair, so truth
    # label is not confounded with the first position within a matched pair.
    for pair_index, (_, pair) in enumerate(ranked[:2]):
        ordered = sorted(pair, key=lambda r: r["label"], reverse=pair_index == 0)
        selected.extend(ordered)
    return selected


def transform_records(records, variant, train_records=()):
    """Return copies with a fixed prompt format and corrected character spans.

    IDs, group and pair membership, answers, labels and semantic metadata are
    preserved. Demonstrations use two matched TRAIN pairs from the same task,
    regardless of the target label. Four-shot formatting is not for training.
    """
    variant = _variant(variant)
    records = list(records)
    train_records = list(train_records)
    demos = {}
    output = []
    for row in records:
        _validate_record(row)
        if row.get("prompt_variant") not in (None, "default"):
            raise ValueError("Refusing to prefix already-transformed prompts")
        if variant == "fourshot" and row["split"] == "train":
            raise ValueError("Four-shot formatting is calibration/evaluation only; train uses default")
        prefix, demo_ids = "", []
        if variant != "default":
            prefix = INSTRUCTION
        if variant == "fourshot":
            if row["concept"] not in demos:
                demos[row["concept"]] = _demonstrations(train_records, row["concept"])
            chosen = demos[row["concept"]]
            if any(d["id"] == row["id"] or d["prompt"] == row["prompt"] for d in chosen):
                raise ValueError("Target overlaps a TRAIN demonstration")
            demo_ids = [d["id"] for d in chosen]
            prefix += "".join(f"Example {i + 1}:\n{d['prompt']}{d['correct']}\n\n"
                              for i, d in enumerate(chosen))
            prefix += "Now answer the next question:\n"
        changed = deepcopy(row)
        changed["prompt"] = prefix + row["prompt"]
        changed["span"] = [v + len(prefix) for v in row["span"]]
        changed["prompt_variant"] = variant
        changed["demonstration_ids"] = demo_ids
        changed["format_protocol"] = PROTOCOL_VERSION
        output.append(changed)
    return output


def validate_context(records, tokenizer, model_config, variant="default"):
    """Fail before inference if full prompt+candidate reaches a context limit.

    Uses the evaluator's separate prompt/continuation tokenization convention.
    Does not truncate: truncation could remove the target or shift hook spans.
    ByteTokenizer models use default format only, including their training data.
    """
    variant = _variant(variant)
    from .models import ByteTokenizer
    if isinstance(tokenizer, ByteTokenizer) and variant != "default":
        raise ValueError("ByteTokenizer models use default format only")
    limits = []
    for owner, key in ((model_config, "max_position_embeddings"),
                       (model_config, "max_seq_len"), (tokenizer, "model_max_length")):
        value = owner.get(key) if isinstance(owner, dict) else getattr(owner, key, None)
        # HF tokenizers sometimes use enormous sentinel values for 'unknown'.
        if isinstance(value, (int, np.integer)) and 1 < value < 10**9:
            limits.append(int(value))
    if not limits:
        raise ValueError("No finite model/tokenizer context limit found")
    limit = min(limits)
    lengths = []
    for row in records:
        _validate_record(row)
        if row.get("prompt_variant", variant) != variant:
            raise ValueError("Record format does not match the locked variant")
        prompt_length = len(tokenizer.encode(row["prompt"], add_special_tokens=False))
        answers = [len(tokenizer.encode(row[k], add_special_tokens=False)) for k in ("correct", "foil")]
        if not prompt_length or not min(answers):
            raise ValueError("Empty encoded prompt or continuation")
        n = prompt_length + max(answers)
        if n >= limit:
            raise ValueError(f"Record {row['id']} uses {n} tokens; must be strictly below context limit {limit}")
        lengths.append(n)
    return {"variant": variant, "context_limit": limit, "max_tokens": max(lengths, default=0),
            "min_tokens": min(lengths, default=0), "n": len(lengths), "truncated": False}


def wilson_interval(successes, n, z=1.959963984540054):
    """Two-sided Wilson 95% binomial interval; an operational capability gate."""
    if not isinstance(n, (int, np.integer)) or n <= 0 or not 0 <= successes <= n:
        raise ValueError("Wilson interval requires 0 <= successes <= n and n > 0")
    proportion = successes / n
    denominator = 1 + z * z / n
    midpoint = (proportion + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, midpoint - radius), min(1.0, midpoint + radius)]


def summarize_margins(margins, records, expected_split=None):
    """Uncorrected full-sequence correct-minus-foil LL margin diagnostics.

    A zero margin is an abstention, counted incorrect; it is not silently a yes
    or no prediction. yes_rate is the fraction of all rows with a strict yes
    preference. No learned threshold is applied to predictions or causal effects.
    """
    records = list(records)
    margins = np.asarray(margins, dtype=np.float64)
    if margins.shape != (len(records),) or not records or not np.isfinite(margins).all():
        raise ValueError("Need one finite margin per nonempty record list")
    for row in records:
        _validate_record(row)
    splits = {r["split"] for r in records}
    if len(splits) != 1 or (expected_split is not None and splits != {expected_split}):
        raise ValueError(f"Expected one {expected_split or 'consistent'} split, got {splits}")
    ids = [r["id"] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Repeated record IDs would inflate competence counts")
    labels = np.array([r["label"] for r in records])
    yes_margins = margins * (2 * labels - 1)
    per_task = {}
    for concept in sorted({r["concept"] for r in records}):
        mask = np.array([r["concept"] == concept for r in records])
        n = int(mask.sum())
        successes = int((margins[mask] > 0).sum())
        low, high = wilson_interval(successes, n)
        per_task[concept] = {"n": n, "correct": successes, "accuracy": successes / n,
                             "yes_rate": float(np.mean(yes_margins[mask] > 0)),
                             "tie_rate": float(np.mean(margins[mask] == 0)),
                             "true_label_rate": float(labels[mask].mean()),
                             "wilson95": [low, high],
                             "competent": bool(successes / n >= .70 and low > .5)}
    return {"split": next(iter(splits)), "n": len(records), "per_task": per_task,
            "macro_accuracy": float(np.mean([x["accuracy"] for x in per_task.values()])),
            "accuracy": float(np.mean(margins > 0)), "yes_rate": float(np.mean(yes_margins > 0)),
            "tie_rate": float(np.mean(margins == 0)), "margin_type": "uncorrected_sequence_log_likelihood",
            "prediction_threshold": 0.0, "row_ids_sha256": _digest(ids),
            "records_sha256": _digest(records)}


def calibration_summary(margins, records):
    return summarize_margins(margins, records, expected_split="calibration")


def choose_variant(results):
    """Select one format using the same calibration records for every variant.

    ``results`` is ``{variant: {'margins': array, 'rows': calibration_rows}}``.
    At least default must be present. Format choice is per model, not per task.
    The returned deterministic lock must be saved before D1-D4 are evaluated.
    """
    if not results:
        raise ValueError("No calibration results")
    summaries, evidences = {}, {}
    common_rows = None
    for name, values in results.items():
        name = _variant(name)
        if name in summaries:
            raise ValueError("Duplicate aliases for a prompt variant")
        rows = list(values["rows"])
        for row in rows:
            if row.get("prompt_variant", name) != name:
                raise ValueError("Variant key disagrees with transformed records")
        summary = calibration_summary(values["margins"], rows)
        identity = [(r["id"], r["concept"], r["label"], r["correct"], r["foil"]) for r in rows]
        if common_rows is None:
            common_rows = identity
        elif identity != common_rows:
            raise ValueError("Every variant must evaluate the same ordered calibration records")
        if any(x["true_label_rate"] != .5 for x in summary["per_task"].values()):
            raise ValueError("Calibration must be true/false balanced within each task")
        summaries[name] = summary
        evidences[name] = {"summary": summary, "margins": np.asarray(values["margins"]).tolist()}
    if "default" not in summaries:
        raise ValueError("Default is a required calibration baseline")
    selected = min(summaries, key=lambda name: (-summaries[name]["macro_accuracy"],
                                              abs(summaries[name]["yes_rate"] - .5),
                                              VARIANTS.index(name)))
    return {"protocol_version": PROTOCOL_VERSION, "variant": selected,
            "source_split": "calibration", "variants_evaluated": list(sorted(summaries, key=VARIANTS.index)),
            "selection_rule": "max macro_accuracy; then min abs(yes_rate-0.5); then default, explicit, fourshot",
            "selected_metrics": summaries[selected], "metrics": summaries,
            "evidence_sha256": _digest(evidences), "locked_before": ["D1", "D2", "D3", "D4"],
            "correction": "none; raw sequence margins preserved for competence and causal effects",
            "competence_gate": {"accuracy_min": .70, "wilson95_lower_strictly_above": .5,
                                "both_models_required": True, "D4_reported_separately": True}}


def save_lock(path, lock):
    """Write-once deterministic calibration lock; identical resume is allowed."""
    path = Path(path)
    text = json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as out:
            out.write(text)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != text:
            raise ValueError("Refusing to overwrite an existing calibration lock")
    return path


def paired_competence_gate(summary_a, summary_b, split="D3"):
    """Report predeclared per-task eligibility; never select/retrain mappings.

    D4 is reported separately and cannot retroactively alter D3 eligibility.
    Supplying different example sets or mixing splits is an error.
    """
    if split not in ("D3", "D4"):
        raise ValueError("Paired competence reporting is for D3 or D4 only")
    if summary_a["split"] != split or summary_b["split"] != split:
        raise ValueError("Do not mix calibration, D3, and D4 competence")
    if summary_a["row_ids_sha256"] != summary_b["row_ids_sha256"]:
        raise ValueError("Paired competence must evaluate the same ordered records")
    if set(summary_a["per_task"]) != set(summary_b["per_task"]):
        raise ValueError("Paired models must have the same tasks")
    tasks = {}
    for task in sorted(summary_a["per_task"]):
        a, b = summary_a["per_task"][task], summary_b["per_task"][task]
        eligible = all(x["accuracy"] >= .70 and x["wilson95"][0] > .5 for x in (a, b))
        tasks[task] = {"eligible": bool(eligible), "model_a": a, "model_b": b}
    return {"split": split, "per_task": tasks, "eligible_tasks": [k for k, v in tasks.items() if v["eligible"]],
            "all_tasks_eligible": all(v["eligible"] for v in tasks.values()),
            "rule": "Both models: task accuracy >=0.70 and two-sided Wilson95 lower >0.5",
            "role": "predeclared reporting strata; never tune formats, candidate neurons, thresholds, or maps on these results",
            "interval_limitation": "Wilson treats prompt outcomes as binomial; matched-pair/template dependence means this is an operational gate, not the main cluster-aware research CI"}
