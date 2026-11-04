from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from src.data import generate_dataset
from src.models import ModelConfig, build_model
from src import followup_calibration_runner as runner


@pytest.fixture
def dataset():
    original = generate_dataset(per_concept=8)
    rows = deepcopy(original["D2"])
    for r in rows:
        r["split"] = "calibration"
    return {"train": original["train"], "calibration": rows}


@pytest.fixture
def tiny_run(tmp_path):
    config = ModelConfig(dim=16, hidden_dim=32, layers=1, heads=2, max_seq_len=256)
    model = build_model(config, 101)
    directory = tmp_path / "training" / "seed_101"
    directory.mkdir(parents=True)
    for kind in ("initial", "middle", "final"):
        torch.save({"config": asdict(config), "seed": 101, "state_dict": model.state_dict()}, directory / f"{kind}.pt")
    return tmp_path


def test_load_tiny_checkpoint_identity_is_byte_hash(tiny_run):
    for checkpoint in ("initial", "middle", "final"):
        model, tok, info = runner.load_followup_model("seed101", checkpoint, "cpu", tiny_run)
        path = tiny_run / "training" / "seed_101" / f"{checkpoint}.pt"
        assert info["checkpoint_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert info["checkpoint_kind"] == checkpoint
        assert model.embedding.weight.device.type == "cpu"
        assert tok.encode(" yes")
    with pytest.raises(ValueError, match="Unknown"):
        runner.load_followup_model("seed11", device="cpu", run_dir=tiny_run)


def test_reader_never_needs_evaluation_files(tmp_path, dataset):
    manifest = {"file_sha256": {}}
    for split, rows in dataset.items():
        payload = "".join(json.dumps(r) + "\n" for r in rows).encode()
        (tmp_path / f"{split}.jsonl").write_bytes(payload)
        manifest["file_sha256"][f"{split}.jsonl"] = hashlib.sha256(payload).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    read, hashes = runner._read_calibration_data(tmp_path)
    assert read == dataset and set(hashes) == {"train.jsonl", "calibration.jsonl"}
    # No D1-D4 files exist; the reader must not attempt to open them.
    (tmp_path / "calibration.jsonl").write_text("tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        runner._read_calibration_data(tmp_path)


def test_tiny_fixed_format_artifacts_and_hash_checked_resume(monkeypatch, tiny_run, dataset):
    import src.experiment
    calls = []
    def fake_margins(model, tokenizer, rows, **kwargs):
        assert {r["split"] for r in rows} == {"calibration"}
        calls.append(rows)
        return np.ones(len(rows)), np.ones((len(rows), 2), dtype=int)
    monkeypatch.setattr(src.experiment, "sequence_margins", fake_margins)
    summary = runner.calibrate_model("seed101", dataset, {}, tiny_run, device="cpu")
    assert summary["selection_mode"] == "fixed_default_no_format_selection"
    assert summary["variant"] == "default" and len(calls) == 1
    out = tiny_run / "calibration" / "seed101"
    lock = json.loads((out / "lock.json").read_text())
    assert lock["fixed_for_all_checkpoints"] is True
    assert lock["held_out_status"]["D3"].startswith("PENDING")
    with np.load(out / "evidence.npz", allow_pickle=False) as raw:
        assert np.array_equal(raw["margins_default"], np.ones(len(dataset["calibration"])))
        assert len(raw["row_ids"]) == len(dataset["calibration"])
    assert runner.calibrate_model("seed101", dataset, {}, tiny_run, device="cpu", resume=True) == summary
    assert len(calls) == 1
    transformed = runner.transform_for_model(dataset["calibration"], "seed101", dataset["train"], tiny_run)
    assert all(r["prompt_variant"] == "default" for r in transformed)
    with pytest.raises(ValueError, match="bank changed"):
        runner.transform_for_model(dataset["calibration"], "seed101", dataset["train"][:-1], tiny_run)
    (out / "lock.json").write_text("{}")
    with pytest.raises(ValueError, match="artifact was changed"):
        runner.calibrate_model("seed101", dataset, {}, tiny_run, device="cpu", resume=True)


def test_hf_three_variants_choose_only_calibration_without_gpu(monkeypatch, tmp_path, dataset):
    import src.experiment
    class Tokenizer:
        def encode(self, text, add_special_tokens=False):
            return list(text.encode())
    descriptor = {"id": "qwen", "model_id": "mock-cpu-test", "revision": "immutable-test"}
    monkeypatch.setattr(runner, "_model_descriptor", lambda *args, **kwargs: descriptor)
    monkeypatch.setattr(runner, "load_followup_model", lambda *args, **kwargs:
                        (SimpleNamespace(config=SimpleNamespace(max_position_embeddings=4096)), Tokenizer(), descriptor))
    variants = []
    def fake_margins(model, tokenizer, rows, **kwargs):
        assert {r["split"] for r in rows} == {"calibration"}
        variant = rows[0]["prompt_variant"]
        variants.append(variant)
        margin = np.ones(len(rows))
        if variant != "explicit":
            margin[::2] = -1
        return margin, np.ones((len(rows), 2), dtype=int)
    monkeypatch.setattr(src.experiment, "sequence_margins", fake_margins)
    summary = runner.calibrate_model("qwen", dataset, {}, tmp_path, device="cpu")
    assert variants == ["default", "explicit", "fourshot"]
    assert summary["variant"] == "explicit"
    lock = json.loads((tmp_path / "calibration" / "qwen" / "lock.json").read_text())
    assert lock["fixed_for_all_checkpoints"] is False
    transformed = runner.transform_for_model(dataset["calibration"], "qwen", dataset["train"], tmp_path)
    assert transformed[0]["prompt_variant"] == "explicit"
    with pytest.raises(ValueError, match="never final"):
        runner.calibrate_model("qwen", {**dataset, "D3": []}, {}, tmp_path, device="cpu")
