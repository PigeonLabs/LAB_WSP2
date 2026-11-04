from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from src.data import generate_dataset
from src.models import ByteTokenizer
from src.followup_calibration import (
    VARIANTS, calibration_summary, choose_variant, paired_competence_gate,
    save_lock, summarize_margins, transform_records, validate_context,
    wilson_interval,
)


@pytest.fixture
def records():
    data = generate_dataset(per_concept=16)
    calibration = deepcopy(data["D2"])
    for row in calibration:
        row["split"] = "calibration"
    data["calibration"] = calibration
    return data


def test_prefix_preserves_identity_and_statement_span(records):
    original = deepcopy(records)
    for variant in VARIANTS:
        changed = transform_records(records["D3"], variant, records["train"])
        for before, after in zip(records["D3"], changed):
            for key in ("id", "split", "concept", "pair_id", "group_id", "label", "correct", "foil"):
                assert before[key] == after[key]
            assert before["prompt"][slice(*before["span"])] == after["prompt"][slice(*after["span"])]
            assert after["prompt"].endswith(before["prompt"])
    assert records == original


def test_fourshot_train_only_balanced_and_label_blind(records):
    result = transform_records(records["calibration"], "4shot", records["train"])
    train = {r["id"]: r for r in records["train"]}
    per_task = {}
    for row in result:
        demo_ids = row["demonstration_ids"]
        assert len(demo_ids) == len(set(demo_ids)) == 4
        demos = [train[i] for i in demo_ids]
        assert sorted(r["label"] for r in demos) == [0, 0, 1, 1]
        assert len({r["pair_id"] for r in demos}) == 2
        assert {r["concept"] for r in demos} == {row["concept"]}
        assert demo_ids == per_task.setdefault(row["concept"], demo_ids)
    # Order of the training bank must not change which demonstrations are used.
    assert result == transform_records(records["calibration"], "fourshot", list(reversed(records["train"])))
    with pytest.raises(ValueError, match="TRAIN"):
        transform_records(records["D3"], "fourshot", records["D4"])
    with pytest.raises(ValueError, match="train uses default"):
        transform_records(records["train"], "fourshot", records["train"])


def test_refuses_incomplete_demonstration_pairs_and_double_prefix(records):
    with pytest.raises(ValueError, match="Every demonstration pair"):
        transform_records(records["calibration"], "fourshot", records["train"][1:])
    prefixed = transform_records(records["D3"], "explicit")
    with pytest.raises(ValueError, match="already-transformed"):
        transform_records(prefixed, "fourshot", records["train"])


def test_choose_format_calibration_only_and_deterministic_ties(records):
    rows = records["calibration"]
    results = {v: {"rows": transform_records(rows, v, records["train"]),
                   "margins": np.ones(len(rows))} for v in reversed(VARIANTS)}
    lock = choose_variant(results)
    assert lock["variant"] == "default"
    assert lock["selected_metrics"]["macro_accuracy"] == 1
    assert lock["selected_metrics"]["yes_rate"] == .5
    results["default"]["margins"][0] = -1
    assert choose_variant(results)["variant"] == "explicit"
    for bad_split in ("train", "D1", "D2", "D3", "D4"):
        bad = deepcopy(results)
        for entry in bad.values():
            for row in entry["rows"]:
                row["split"] = bad_split
        with pytest.raises(ValueError, match="calibration"):
            choose_variant(bad)


def test_summary_yes_rate_uses_truth_orientation_and_counts_ties(records):
    rows = records["calibration"]
    # Always favor yes: margin correct-minus-foil positive only for true rows.
    margin = np.array([1 if r["label"] else -1 for r in rows], dtype=float)
    summary = calibration_summary(margin, rows)
    assert summary["yes_rate"] == 1
    assert summary["macro_accuracy"] == .5
    margin[:] = 0
    summary = calibration_summary(margin, rows)
    assert summary["tie_rate"] == 1
    assert summary["accuracy"] == summary["yes_rate"] == 0


def test_choice_rejects_mismatched_examples_unbalanced_labels_and_nonfinite(records):
    rows = records["calibration"]
    with pytest.raises(ValueError, match="same ordered"):
        choose_variant({"default": {"rows": rows, "margins": np.ones(len(rows))},
                        "explicit": {"rows": rows[::-1], "margins": np.ones(len(rows))}})
    positives = [r for r in rows if r["label"]]
    with pytest.raises(ValueError, match="balanced"):
        choose_variant({"default": {"rows": positives, "margins": np.ones(len(positives))}})
    with pytest.raises(ValueError, match="finite margin"):
        calibration_summary(np.full(len(rows), np.nan), rows)


def test_context_checks_full_continuation_limit_and_byte_restriction(records):
    rows = records["D3"][:2]
    tok = ByteTokenizer()
    max_len = max(len(tok.encode(r["prompt"])) + max(len(tok.encode(r[k])) for k in ("correct", "foil")) for r in rows)
    report = validate_context(rows, tok, SimpleNamespace(max_seq_len=max_len + 1))
    assert report["max_tokens"] == max_len and not report["truncated"]
    with pytest.raises(ValueError, match="strictly below"):
        validate_context(rows, tok, SimpleNamespace(max_seq_len=max_len))
    with pytest.raises(ValueError, match="default format only"):
        validate_context(transform_records(rows, "explicit"), tok, SimpleNamespace(max_seq_len=2000), "explicit")
    with pytest.raises(ValueError, match="No finite"):
        validate_context(rows, tok, SimpleNamespace())


def test_wilson_gate_requires_both_models_and_split_separation(records):
    low, high = wilson_interval(70, 100)
    assert .603 < low < .605 and .780 < high < .782
    a = summarize_margins(np.ones(len(records["D3"])), records["D3"])
    b = summarize_margins(np.ones(len(records["D3"])), records["D3"])
    assert paired_competence_gate(a, b)["all_tasks_eligible"]
    weak = np.array([1 if r["label"] else -1 for r in records["D3"]])
    b = summarize_margins(weak, records["D3"])
    assert paired_competence_gate(a, b)["eligible_tasks"] == []
    d4 = summarize_margins(np.ones(len(records["D4"])), records["D4"])
    with pytest.raises(ValueError, match="Do not mix"):
        paired_competence_gate(a, d4)
    assert paired_competence_gate(d4, d4, split="D4")["all_tasks_eligible"]


def test_calibration_lock_write_once(records, tmp_path):
    rows = records["calibration"]
    lock = choose_variant({"default": {"rows": rows, "margins": np.ones(len(rows))}})
    path = save_lock(tmp_path / "lock.json", lock)
    assert save_lock(path, lock) == path
    lock["variant"] = "explicit"
    with pytest.raises(ValueError, match="overwrite"):
        save_lock(path, lock)
