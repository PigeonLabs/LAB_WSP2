"""F5 CPU unit/integration tests; toy checkpoints never enter research outputs."""
from dataclasses import asdict
import json

import numpy as np
import pytest
import torch

from src.models import ModelConfig, build_model, ByteTokenizer
from src.followup_transfer import (
    choose_target_task, mapped_groups, select_policy, run_transfers,
)
from src.experiment import sequence_margins, capture


def records(split):
    result = []
    for wrapper in range(3):
        for concept in ("arithmetic", "logic"):
            for label in (0, 1):
                text = f"Case {wrapper}: {concept} statement {label}?"
                result.append({"id": f"{split}-{wrapper}-{concept}-{label}", "split": split,
                    "prompt": text, "span": [0, len(text)], "concept": concept, "label": label,
                    "group_id": f"{split}:wrapper{wrapper}", "template_id": f"{split}:wrapper{wrapper}",
                    "correct": " yes" if label else " no", "foil": " no" if label else " yes"})
    return result


def test_task_and_policy_are_d2_only_and_apply_per_task_retention():
    rows = records("D2")
    donor = np.ones(len(rows))
    target = np.array([-1 if row["concept"] == "arithmetic" else 1 for row in rows])
    assert choose_target_task(donor, target, rows)["target_task"] == "arithmetic"
    with pytest.raises(ValueError, match="D2 only"):
        choose_target_task(donor, target, records("D4"))
    baseline = {"arithmetic": .5, "logic": .8}
    candidates = {
        "activation_1": {"method": "activation", "alpha": 1., "accuracy": {"arithmetic": .9, "logic": .7}},
        "activation_half": {"method": "activation", "alpha": .5, "accuracy": {"arithmetic": .75, "logic": .79}},
        "semantic_quarter": {"method": "semantic", "alpha": .25, "accuracy": {"arithmetic": .75, "logic": .79}},
        "random_best": {"method": "random_seed17", "alpha": 1., "accuracy": {"arithmetic": 1., "logic": 1.}},
    }
    policy = select_policy(candidates, baseline, "arithmetic")
    assert policy["selected"] == "semantic_quarter"  # Equal gain/retention -> smaller alpha.
    none = select_policy({"bad": candidates["activation_1"]}, baseline, "arithmetic")
    assert none["selected_none"] and none["selected"] is None


def test_mapping_reverse_and_group_coordinate_identity():
    rows = records("D2")
    labels = np.array([r["label"] for r in rows])
    data = {"product": np.column_stack([labels, labels, labels, labels]).astype(float),
            "layers": np.array([0, 0, 1, 1]), "neuron_ids": np.array([3, 7, 4, 8])}
    target = dict(data, neuron_ids=np.array([9, 10, 11, 12]))
    mapping = {"source": [0, 1, 2, 3], "target": [1, 0, 3, 2], "fit_split": "D2"}
    fitted = {"mappings": {f"{method}__layer__hungarian": mapping for method in ("activation", "semantic")}}
    forward = mapped_groups(fitted, data, target, rows, "arithmetic", group_size=1)
    assert forward["activation"][0]["source_neuron"] == 3
    assert forward["activation"][0]["target_neuron"] == 10
    reverse = mapped_groups(fitted, target, data, rows, "arithmetic", reverse=True, group_size=1)
    assert reverse["activation"][0]["source_neuron"] == 9
    assert reverse["activation"][0]["target_neuron"] == 7
    with pytest.raises(ValueError, match="D2 only"):
        mapped_groups(fitted, data, target, records("D4"), "arithmetic", group_size=1)


def _fixture_run(root):
    torch.set_num_threads(1)
    dataset = {"D2": records("D2"), "D4": records("D4")}
    config = ModelConfig(dim=16, hidden_dim=24, layers=2, heads=2, max_seq_len=64)
    for seed in (101, 211):
        model = build_model(config, seed).eval()
        directory = root/"training"/f"seed_{seed}"
        directory.mkdir(parents=True)
        torch.save({"config": asdict(config), "state_dict": model.state_dict(), "seed": seed}, directory/"final.pt")
        collection = root/"collections"/f"seed{seed}"/"final"/"D2"
        collection.mkdir(parents=True)
        arrays = capture(model, ByteTokenizer(), dataset["D2"], selection={0: [1, 2], 1: [3, 4]}, device="cpu")
        arrays["margins"], _ = sequence_margins(model, ByteTokenizer(), dataset["D2"], device="cpu")
        arrays["row_ids"] = np.array([r["id"] for r in dataset["D2"]])
        np.savez_compressed(collection/"measurements.npz", **arrays)
    fit = root/"alignment"/"seed101_seed211"/"answer"
    fit.mkdir(parents=True)
    fit.joinpath("fit.json").write_text(json.dumps({"mappings": {
        f"{method}__layer__hungarian": {"source": [0, 1, 2, 3], "target": [0, 1, 2, 3], "fit_split": "D2"}
        for method in ("activation", "semantic")}}))
    settings = {"causal": {"group_size": 1}, "transplant": {
        "directed_pairs": [[101, 211]], "interpolation_weights": [0, .5],
        "selection_split": "D2", "test_split": "D4", "batch_size": 6,
        "random_seeds": [17, 31, 47], "retention_tolerance": .02}}
    return dataset, settings


def test_cpu_end_to_end_policy_precedes_test_all_conditions_saved_and_resume(tmp_path, monkeypatch):
    dataset, config = _fixture_run(tmp_path)
    import src.followup_transfer as module
    actual = module.sequence_margins
    seen_d4 = []
    def monitored(*args, **kwargs):
        rows = args[2]
        if rows[0]["split"] == "D4":
            policy = tmp_path/"transfers"/"seed101_to_seed211"/"policy.json"
            assert policy.exists()
            assert json.loads(policy.read_text())["frozen_before_D4_scoring"]
            seen_d4.append(True)
        return actual(*args, **kwargs)
    monkeypatch.setattr(module, "sequence_margins", monitored)
    result = run_transfers(dataset, tmp_path, config, device="cpu")
    pair = result["pairs"]["seed101_to_seed211"]
    assert pair["conditions_evaluated"] == 12  # 2 aligned + 3 random + naive, each alpha 0/.5.
    assert len(seen_d4) == 7  # Baseline + six nonzero conditions; alpha 0 reuses baseline.
    hashes = pair["original_parameter_hashes"]
    assert hashes["donor_before"] == hashes["donor_after"]
    assert hashes["target_before"] == hashes["target_after"]
    margins = np.load(tmp_path/"transfers"/"seed101_to_seed211"/"D4_margins.npz")
    assert margins["row_ids"].tolist() == [r["id"] for r in dataset["D4"]]
    assert len(pair["selected_minus_baseline"]["wrapper_effects"]) == 3
    monkeypatch.setattr(module, "sequence_margins", lambda *a, **k: pytest.fail("Complete resume must not score again"))
    assert run_transfers(dataset, tmp_path, config, device="cpu") == result
    changed = dict(config, transplant=dict(config["transplant"], retention_tolerance=.03))
    with pytest.raises(ValueError, match="signatures changed"):
        run_transfers(dataset, tmp_path, changed, device="cpu")


def test_evaluation_data_cannot_change_d2_selected_policy(tmp_path, monkeypatch):
    dataset, config = _fixture_run(tmp_path)
    import src.followup_transfer as module
    calls = []
    actual = module.sequence_margins
    def force_d4_failure(*args, **kwargs):
        if args[2][0]["split"] == "D4":
            calls.append("D4")
            raise RuntimeError("Test scoring intentionally unavailable")
        return actual(*args, **kwargs)
    monkeypatch.setattr(module, "sequence_margins", force_d4_failure)
    with pytest.raises(RuntimeError, match="intentionally"):
        run_transfers(dataset, tmp_path, config, device="cpu")
    policy_file = tmp_path/"transfers"/"seed101_to_seed211"/"policy.json"
    assert policy_file.exists() and calls == ["D4"]
    policy = json.loads(policy_file.read_text())
    assert policy["policy"]["selection_scope"].startswith("all D2")
    assert not (policy_file.parent/"summary.json").exists()


def test_cli_applies_collection_default_metadata_without_changing_config(tmp_path, monkeypatch):
    import src.followup_transfer as module
    import src.followup_data as data_module
    dataset = {"train": records("train"), "D2": records("D2"), "D4": records("D4")}
    config = {"transplant": {"directed_pairs": [[101, 211]]}}
    config_path = tmp_path/"config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(data_module, "load_dataset", lambda path: dataset)
    called = []
    def check_run(formatted, run_dir, passed, device):
        assert passed == config  # Implicit default batch-size must not change resume signature.
        assert device == "cpu"
        for split in ("D2", "D4"):
            assert all(r["prompt_variant"] == "default" and r["demonstration_ids"] == [] and r["format_protocol"] for r in formatted[split])
            assert [r["prompt"] for r in formatted[split]] == [r["prompt"] for r in dataset[split]]
        called.append(True)
        return {"status": "COMPLETED", "pairs": {}, "aggregate_selected_minus_baseline": {}}
    monkeypatch.setattr(module, "run_transfers", check_run)
    module.main(["--device", "cpu", "--config", str(config_path), "--run-dir", str(tmp_path)])
    assert called == [True]
    result = module.main(["--device", "cpu", "--config", str(config_path), "--check-only"])
    assert result["status"] == "PREFLIGHT_ONLY_NO_MODEL_INFERENCE"
    assert called == [True]


def test_cli_cuda_unavailable_fails_before_dataset_or_model_loading(monkeypatch):
    import src.followup_transfer as module
    monkeypatch.setattr(module.torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="CUDA is unavailable"):
        module.main(["--device", "cuda"])
