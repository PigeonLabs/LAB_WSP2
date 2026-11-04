import pytest
torch = pytest.importorskip("torch")
from src.models import ModelConfig, build_model, SwiGLU, ByteTokenizer, token_span_indices, model_mlps, sample_layers
from src.hooks import SwiGLUHook, sign_regime


def tiny(seed=0):
    return build_model(ModelConfig(dim=16, hidden_dim=24, layers=2, heads=2, max_seq_len=64), seed).eval()


def test_observation_preserves_output_and_repeatability():
    model = tiny()
    ids = torch.tensor([[3, 8, 9, 10]])
    baseline = model(ids).logits
    with SwiGLUHook(model.layers[0].mlp, neurons=[1, 3], positions=-1) as hook:
        observed = model(ids).logits
        assert torch.equal(baseline, observed)
        assert torch.equal(observed, model(ids).logits)
        assert hook.records["product"].shape == (1, 1, 2)


def test_zero_removes_exact_down_contribution_only_at_selected_position():
    torch.manual_seed(7)
    mlp = SwiGLU(8, 12)
    x = torch.randn(2, 4, 8)
    before = mlp(x)
    product = torch.nn.functional.silu(mlp.gate_proj(x)) * mlp.up_proj(x)
    actual = []
    with SwiGLUHook(mlp, neurons=[3], positions=-1, mode="zero"):
        # Registered after intervention: captures actual modified down input.
        handle = mlp.down_proj.register_forward_pre_hook(lambda m, inputs: actual.append(inputs[0].detach().clone()))
        after = mlp(x)
        handle.remove()
    expected_product = product.clone()
    expected_product[:, -1, 3] = 0
    assert torch.equal(actual[0], expected_product)
    expected_delta = torch.zeros_like(before)
    expected_delta[:, -1] = product[:, -1, 3, None] * mlp.down_proj.weight[:, 3]
    torch.testing.assert_close(before - after, expected_delta, atol=1e-7, rtol=1e-5)


@pytest.mark.parametrize("mode", ["mean", "patch", "scale"])
def test_interventions(mode):
    mlp = SwiGLU(8, 12)
    x = torch.randn(2, 4, 8)
    with SwiGLUHook(mlp, neurons=[1, 2], positions=[1, 3], mode=mode, replacement=torch.tensor([[0.1, 0.2], [0.3, 0.4]]), scale=1.5) as hook:
        mlp(x)
        expected = hook.records["product"] * 1.5 if mode == "scale" else torch.tensor([[[0.1, 0.2]], [[0.3, 0.4]]])
        torch.testing.assert_close(hook.records["modified_product"], expected)


def test_sign_quadrants_and_zero_bin():
    assert sign_regime(torch.tensor([1., 1., -1., -1., 0.]), torch.tensor([1., -1., 1., -1., 1.])).tolist() == [0, 1, 2, 3, 4]


def test_independent_seeds_and_next_token_backward():
    a, b, c = tiny(3), tiny(4), tiny(3)
    assert not torch.equal(a.embedding.weight, b.embedding.weight)
    assert torch.equal(a.embedding.weight, c.embedding.weight)
    ids = torch.tensor([[3, 4, 5, 6]])
    result = a(ids, labels=ids)
    result.loss.backward()
    assert torch.isfinite(result.loss)
    assert a.layers[0].mlp.gate_proj.weight.grad is not None


def test_causal_attention_does_not_see_future():
    model = tiny()
    x = torch.tensor([[3, 4, 5, 6]])
    y = x.clone()
    y[:, -1] = 30
    torch.testing.assert_close(model(x).logits[:, :-1], model(y).logits[:, :-1], rtol=0, atol=0)


def test_tokenizer_unicode_offsets_and_span():
    tok = ByteTokenizer()
    text = "a한b"
    result = tok(text, return_offsets_mapping=True)
    assert tok.decode(result["input_ids"]) == text
    assert result["offset_mapping"] == [(0, 1), (1, 2), (1, 2), (1, 2), (2, 3)]
    assert token_span_indices(result["offset_mapping"], 1, 2) == [1, 2, 3]


def test_adapters_validate_and_reject_unknown():
    model = tiny()
    assert len(model_mlps(model)) == 2
    assert sample_layers(model) == [0, 1]
    with pytest.raises(TypeError):
        model_mlps(torch.nn.Linear(2, 2))
    model.layers[0].mlp.act_fn = torch.relu
    with pytest.raises(TypeError, match="not SwiGLU"):
        model_mlps(model)


def test_hook_cleanup_after_failure():
    mlp = SwiGLU(8, 12)
    with pytest.raises(ValueError):
        with SwiGLUHook(mlp, neurons=[12], mode="zero"):
            mlp(torch.randn(1, 2, 8))
    assert not mlp.down_proj._forward_pre_hooks


def test_contribution_norm_without_large_contribution_tensor():
    mlp = SwiGLU(8, 12)
    with SwiGLUHook(mlp, neurons=[1, 4], positions=-1, capture_contribution=False) as hook:
        mlp(torch.randn(2, 4, 8))
        assert "contribution" not in hook.records
        expected = hook.records["product"].abs() * mlp.down_proj.weight[:, [1, 4]].detach().norm(dim=0)
        torch.testing.assert_close(hook.records["contribution_norm"], expected)


@pytest.mark.parametrize("family", ["llama", "qwen3", "olmo2"])
def test_huggingface_model_families(family):
    transformers = pytest.importorskip("transformers")
    names = {"llama": ("LlamaConfig", "LlamaForCausalLM"),
             "qwen3": ("Qwen3Config", "Qwen3ForCausalLM"),
             "olmo2": ("Olmo2Config", "Olmo2ForCausalLM")}
    config_name, model_name = names[family]
    cfg_cls, model_cls = getattr(transformers, config_name), getattr(transformers, model_name)
    cfg = cfg_cls(vocab_size=32, hidden_size=16, intermediate_size=32,
                  num_hidden_layers=2, num_attention_heads=2,
                  num_key_value_heads=2, head_dim=8, max_position_embeddings=64)
    model = model_cls(cfg).eval()
    ids = torch.tensor([[2, 3, 4, 5]])
    with torch.no_grad():
        original = model(ids).logits
        with SwiGLUHook(model_mlps(model)[0], neurons=[1, 2], positions=-1) as hook:
            observed = model(ids).logits
            torch.testing.assert_close(original, observed, rtol=0, atol=0)
            assert hook.records["product"].shape == (1, 1, 2)
