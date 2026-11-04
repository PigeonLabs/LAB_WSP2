"""CPU correctness tests only; these tiny models are never research evidence."""
import json
import pytest
import torch
from src.models import ModelConfig, build_model
from src.training import train_independent, load_trained, parameter_hash
from src.models import ByteTokenizer
from src.experiment import capture, sequence_margins, causal_subset, collect_model, collect_causal
from src.data import generate_dataset
from src.hooks import SwiGLUHook
import numpy as np


def smoke_train_config():
    return {"model": {"dim": 16, "hidden_dim": 24, "layers": 1, "heads": 2,
                      "max_seq_len": 64},
            "seeds": [31, 37], "steps": 2, "batch_size": 2,
            "lr": 1e-3, "max_seconds_per_seed": 30}


def test_training_cpu_smoke_independent_and_resume(tmp_path):
    torch.set_num_threads(1)
    records = [{"split": "train", "prompt": "One plus one equals two?", "correct": " yes"},
               {"split": "train", "prompt": "One plus one equals three?", "correct": " no"}]
    manifests = train_independent(smoke_train_config(), records, tmp_path, device="cpu")
    assert len({m["initial_hash"] for m in manifests}) == 2
    for m in manifests:
        assert m["steps"] == 2
        assert m["initial_hash"] != m["final_hash"]
        model, tokenizer = load_trained(m["checkpoint"])
        assert parameter_hash(model) == m["final_hash"]
        assert tokenizer.decode(tokenizer.encode("Unicode: 한")) == "Unicode: 한"
    mtimes = [(tmp_path / f"seed_{s}" / "final.pt").stat().st_mtime_ns for s in [31, 37]]
    resumed = train_independent(smoke_train_config(), records, tmp_path, device="cpu")
    assert [m["final_hash"] for m in resumed] == [m["final_hash"] for m in manifests]
    assert mtimes == [(tmp_path / f"seed_{s}" / "final.pt").stat().st_mtime_ns for s in [31, 37]]


def test_training_rejects_heldout_before_checkpoint(tmp_path):
    with pytest.raises(ValueError, match="train records only"):
        train_independent(smoke_train_config(), [{"split": "D3", "prompt": "x", "correct": " y"}], tmp_path, device="cpu")
    assert not list(tmp_path.rglob("*.pt"))


def test_training_rejects_changed_config_on_resume(tmp_path):
    config = smoke_train_config()
    config["seeds"] = [31]
    records = [{"split": "train", "prompt": "Truth?", "correct": " yes"}]
    train_independent(config, records, tmp_path, device="cpu")
    with pytest.raises(ValueError, match="different config or data"):
        train_independent(dict(config, lr=2e-3), records, tmp_path, device="cpu")


def test_sequence_scores_full_multitoken_answers_and_padding():
    model = build_model(ModelConfig(dim=16, hidden_dim=24, layers=2, heads=2, max_seq_len=64), 7).eval()
    tok = ByteTokenizer()
    rows = [{"prompt": "Is two even?", "correct": " yes", "foil": " no"},
            {"prompt": "Three even?", "correct": " no", "foil": " yes"}]
    expected = []
    with torch.no_grad():
        for r in rows:
            prompt = tok.encode(r["prompt"])
            scores = []
            for answer in [r["correct"], r["foil"]]:
                continuation = tok.encode(answer)
                sequence = prompt + continuation
                logits = model(torch.tensor([sequence])).logits[0]
                score = sum(float(logits[len(prompt) - 1 + i].log_softmax(-1)[token]) for i, token in enumerate(continuation))
                scores.append(score)
            expected.append(scores[0] - scores[1])
    observed, counts = sequence_margins(model, tok, rows, device="cpu", batch_size=2)
    np.testing.assert_allclose(observed, expected, atol=3e-6, rtol=1e-6)
    assert counts.tolist() == [[4, 3], [3, 4]]
    separate, _ = sequence_margins(model, tok, rows, device="cpu", batch_size=1)
    np.testing.assert_allclose(observed, separate, atol=3e-6, rtol=1e-6)


def test_capture_and_causal_identity_are_batch_invariant():
    model = build_model(ModelConfig(dim=16, hidden_dim=24, layers=2, heads=2, max_seq_len=64), 7).eval()
    tok = ByteTokenizer()
    rows = [{"prompt": "Short?", "correct": " yes", "foil": " no"},
            {"prompt": "A longer prompt?", "correct": " no", "foil": " yes"}]
    batched = capture(model, tok, rows, selection={0: [1, 2], 1: [3, 4]}, device="cpu", batch_size=2)
    separate = capture(model, tok, rows, selection={0: [1, 2], 1: [3, 4]}, device="cpu", batch_size=1)
    for key in ("gate", "up", "product", "contribution_norm"):
        np.testing.assert_allclose(batched[key], separate[key], atol=1e-7, rtol=1e-5)
    expected = torch.nn.functional.silu(torch.tensor(batched["gate"])) * torch.tensor(batched["up"])
    np.testing.assert_allclose(batched["product"], expected.numpy(), atol=1e-7)
    baseline, _ = sequence_margins(model, tok, rows, device="cpu")
    identity, _ = sequence_margins(model, tok, rows, device="cpu", intervention={"layer": 0, "neuron": 1, "mode": "scale", "scale": 1.0})
    np.testing.assert_array_equal(baseline, identity)
    assert not model.layers[0].mlp.down_proj._forward_pre_hooks


def test_causal_subset_keeps_complete_pairs_and_balances_templates():
    dataset = generate_dataset(per_concept=24)
    rows = causal_subset(dataset["D4"], per_concept=12)
    assert len(rows) == 48
    for r in rows:
        donors = [other for other in rows if other["pair_id"] == r["pair_id"] and other["label"] != r["label"]]
        assert len(donors) == 1
    assert len({r["template_id"] for r in rows}) == 24


def test_tiny_collection_and_causal_storage_cpu_smoke(tmp_path):
    """Untrained toy weights test the pipeline, never H1-H4 evidence."""
    dataset = generate_dataset(per_concept=12)
    model = build_model(ModelConfig(dim=16, hidden_dim=24, layers=1, heads=2, max_seq_len=256), 17).eval()
    tok = ByteTokenizer()
    collection = tmp_path / "collection"
    manifest = collect_model(model, tok, dataset, collection,
                             {"model_id": "CPU_TEST_ONLY", "seed": 17},
                             per_layer=2, batch_size=8, device="cpu")
    assert manifest["num_candidates"] == 2
    saved = np.load(collection / "D3.npz")
    assert saved["row_ids"].tolist() == [r["id"] for r in dataset["D3"]]
    causal = tmp_path / "causal"
    result = collect_causal(model, tok, dataset, collection, causal,
                            per_layer=2, per_concept=12, batch_size=8, device="cpu")
    assert result["interventions"] == ["zero", "mean", "patch"]
    effects = np.load(causal / "D4_causal.npz")
    assert effects["effects"].shape == (48, 2, 3)
    assert np.isfinite(effects["effects"]).all()
    assert set(effects["row_ids"]) <= {r["id"] for r in dataset["D4"]}
    with pytest.raises(ValueError, match="changed in existing collection"):
        collect_model(model, tok, dataset, collection, {"model_id": "CPU_TEST_ONLY", "seed": 17},
                      per_layer=4, batch_size=8, device="cpu")
    with pytest.raises(ValueError, match="config changed"):
        collect_causal(model, tok, dataset, collection, causal,
                       per_layer=2, per_concept=6, batch_size=8, device="cpu")


def test_shared_continuation_prefix_moves_capture_and_intervention_boundary():
    """A common space must not make final-layer byte-model effects cancel."""
    torch.set_num_threads(1)
    model = build_model(ModelConfig(dim=16, hidden_dim=24, layers=1, heads=2, max_seq_len=64), 7).eval()
    tok = ByteTokenizer()
    row = {"prompt": "Is two even?", "correct": " yes", "foil": " no"}
    context = tok.encode(row["prompt"] + " ")
    observed = capture(model, tok, [row], selection={0: [1]}, device="cpu")
    with torch.no_grad(), SwiGLUHook(model.layers[0].mlp, neurons=[1], positions=-1) as hook:
        model(torch.tensor([context]))
        np.testing.assert_allclose(observed["product"], hook.records["product"][:, 0].numpy(), atol=1e-8)
    baseline, _ = sequence_margins(model, tok, [row], device="cpu")
    changed, _ = sequence_margins(model, tok, [row], device="cpu",
                                 intervention={"layer": 0, "neuron": 1, "mode": "zero"})
    assert abs(float(baseline[0] - changed[0])) > 1e-6
    assert observed["token_lengths"].tolist() == [len(context)]
