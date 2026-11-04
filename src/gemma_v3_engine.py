"""Independent FP32 engine for the hash-locked Gemma-4 E2B IT GGUF.

This is not the unpublished engine used to create the external neuron map.
GGUF weights are dequantized, without retraining or conversion to BF16. The
Transformers Gemma4 implementation preserves PLE, shared KV, GELU-tanh, the
post-MLP norm, layer scaling, and final softcap. Independent forward parity
must be measured separately; a complete tensor audit alone is insufficient.
"""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
import numpy as np
import torch
from torch import nn

GGUF_SHA256 = "740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8"
GGUF_REPO = "unsloth/gemma-4-E2B-it-GGUF"
GGUF_REVISION = "0314792d7f1f7e229411f620751375812bb9faf2"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _field(reader, key):
    if key not in reader.fields:
        raise ValueError(f"Required GGUF metadata missing: {key}")
    return reader.fields[key].contents()


def _text_config(reader):
    from transformers import Gemma4TextConfig

    expected = {
        "general.architecture": "gemma4",
        "gemma4.block_count": 35,
        "gemma4.embedding_length": 1536,
        "gemma4.feed_forward_length": [6144] * 15 + [12288] * 20,
        "gemma4.attention.head_count": 8,
        "gemma4.attention.head_count_kv": 1,
        "gemma4.attention.key_length": 512,
        "gemma4.attention.value_length": 512,
        "gemma4.attention.key_length_swa": 256,
        "gemma4.attention.value_length_swa": 256,
        "gemma4.attention.shared_kv_layers": 20,
        "gemma4.embedding_length_per_layer_input": 256,
        "gemma4.attention.sliding_window": 512,
        "gemma4.attention.sliding_window_pattern": [bool((i + 1) % 5) for i in range(35)],
        "gemma4.rope.freq_base": 1000000.0,
        "gemma4.rope.freq_base_swa": 10000.0,
        "gemma4.final_logit_softcapping": 30.0,
        "tokenizer.ggml.bos_token_id": 2,
        "tokenizer.ggml.eos_token_id": 106,
        "tokenizer.ggml.add_bos_token": True,
        "tokenizer.ggml.add_space_prefix": False,
    }
    for key, wanted in expected.items():
        actual = _field(reader, key)
        if actual != wanted:
            raise ValueError(f"Unsupported GGUF {key}: {actual!r} != {wanted!r}")
    eps = float(_field(reader, "gemma4.attention.layer_norm_rms_epsilon"))
    if not np.isclose(eps, 1e-6, rtol=1e-6):
        raise ValueError(f"Unexpected RMSNorm epsilon: {eps}")
    config = Gemma4TextConfig(
        hidden_size=1536, intermediate_size=6144, num_hidden_layers=35,
        num_attention_heads=8, num_key_value_heads=1, head_dim=256,
        global_head_dim=512, num_kv_shared_layers=20,
        hidden_size_per_layer_input=256, vocab_size=262144,
        vocab_size_per_layer_input=262144, use_double_wide_mlp=True,
        layer_types=["sliding_attention" if (i + 1) % 5 else "full_attention" for i in range(35)],
        sliding_window=512, hidden_activation="gelu_pytorch_tanh",
        rms_norm_eps=eps, final_logit_softcapping=30.0,
        attention_k_eq_v=False, enable_moe_block=False, attention_bias=False,
        attention_dropout=0.0, tie_word_embeddings=True,
        max_position_embeddings=int(_field(reader, "gemma4.context_length")),
        rope_parameters={
            "sliding_attention": {"rope_type": "default", "rope_theta": 10000.0},
            "full_attention": {"rope_type": "proportional", "partial_rotary_factor": 0.25, "rope_theta": 1000000.0},
        },
        bos_token_id=2, pad_token_id=0, eos_token_id=[1, 106, 50],
        use_cache=False,
    )
    config._attn_implementation = "eager"
    return config


def _skeleton(reader):
    from accelerate import init_empty_weights
    from transformers import Gemma4ForCausalLM

    # Keeping buffers real preserves analytically initialized rotary frequencies
    # and embedding scales; to_empty() would leave these uninitialized.
    with init_empty_weights(include_buffers=False):
        model = Gemma4ForCausalLM(_text_config(reader))
    return model


def _mapping(reader, model):
    import gguf

    name_map = gguf.get_tensor_name_map(gguf.MODEL_ARCH.GEMMA4, 35)
    tensors = {tensor.name: tensor for tensor in reader.tensors}
    mapping = {}
    for hf_name, value in model.state_dict().items():
        if hf_name == "lm_head.weight" and "output.weight" not in tensors:
            # Explicit tied-head identity, not a missing-weight fallback.
            gguf_name = "token_embd.weight"
        else:
            lookup = hf_name + ".weight" if hf_name.endswith(".layer_scalar") else hf_name
            gguf_name = name_map.get_name(lookup, try_suffixes=(".weight", ".bias"))
        if gguf_name not in tensors:
            raise ValueError(f"Unmapped HF tensor: {hf_name} -> {gguf_name}")
        shape = tuple(int(v) for v in tensors[gguf_name].shape[::-1])
        if tuple(value.shape) != shape and not (value.numel() == 1 and shape == (1,)):
            raise ValueError(f"Shape mismatch {hf_name}: HF {tuple(value.shape)}, GGUF {shape}")
        mapping[hf_name] = gguf_name
    # Conversion retained K/V parameters in the 20 shared-KV layers. Both
    # HF and llama.cpp's Gemma4 graph skip those projections (sources 13/14).
    # Audit this exact whitelist and every shape rather than silently dropping.
    unused_kv = set()
    for layer in range(15, 35):
        width = 512 if (layer + 1) % 5 == 0 else 256
        for suffix, shape in (("attn_k.weight", (width, 1536)), ("attn_v.weight", (width, 1536)), ("attn_k_norm.weight", (width,))):
            name = f"blk.{layer}.{suffix}"
            if name not in tensors or tuple(int(v) for v in tensors[name].shape[::-1]) != shape:
                raise ValueError(f"Shared-KV unused tensor missing or malformed: {name}")
            unused_kv.add(name)
    extras = set(tensors) - set(mapping.values())
    if extras != {"rope_freqs.weight"} | unused_kv:
        raise ValueError(f"Unconsumed GGUF tensors: {sorted(extras)}")
    rope = gguf.dequantize(tensors["rope_freqs.weight"].data, tensors["rope_freqs.weight"].tensor_type)
    expected_rope = np.array([1.0] * 64 + [1e30] * 192, dtype=np.float32)
    if not np.array_equal(rope, expected_rope):
        raise ValueError("GGUF proportional RoPE factors do not match HF configuration")
    return mapping


def _open_verified(path):
    import gguf

    actual = sha256_file(path)
    if actual != GGUF_SHA256:
        raise ValueError(f"Wrong GGUF identity: {actual}; required {GGUF_SHA256}")
    return gguf.GGUFReader(str(path))


def inspect_gguf(path):
    """CPU-only, no full-weight allocation: validate all names, shapes and metadata."""
    reader = _open_verified(path)
    model = _skeleton(reader)
    mapping = _mapping(reader, model)
    return {
        "sha256": GGUF_SHA256, "repo": GGUF_REPO, "revision": GGUF_REVISION,
        "identity": "instruction-tuned checkpoint without LoRA",
        "gguf_tensors": len(reader.tensors), "hf_state_entries": len(mapping),
        "explicit_derived_tensor": "rope_freqs.weight",
        "unused_shared_kv_tensor_count": 60,
        "tied_output": mapping["lm_head.weight"] == "token_embd.weight",
        "native_widths": [layer.mlp.down_proj.in_features for layer in model.model.layers],
        "native_unit_count": sum(layer.mlp.down_proj.in_features for layer in model.model.layers),
        "config": model.config.to_dict(), "mapping": mapping,
        "forward_parity": "NOT_EVALUATED",
    }


def embedded_tokenizer(reader):
    """Build from the file's actual vocabulary, merges and token types only."""
    from tokenizers.processors import TemplateProcessing
    from transformers import PreTrainedTokenizerFast
    from transformers.integrations.gguf.gguf_tokenizer_mapping import convert_gguf_tokenizer

    names = {"model": "tokenizer_type", "tokens": "tokens", "scores": "scores", "token_type": "token_type", "merges": "merges"}
    data = {destination: _field(reader, f"tokenizer.ggml.{name}") for name, destination in names.items() if f"tokenizer.ggml.{name}" in reader.fields}
    tokens = data["tokens"]
    if len(tokens) != 262144:
        raise ValueError("Embedded vocabulary has unexpected length")
    backend, _ = convert_gguf_tokenizer("gemma4", data)
    backend.post_processor = TemplateProcessing(
        single=f"{tokens[2]} $A", pair=f"{tokens[2]} $A $B", special_tokens=[(tokens[2], 2)],
    )
    tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=backend, bos_token=tokens[2], eos_token=tokens[106],
        pad_token=tokens[0], unk_token=tokens[3], mask_token=tokens[4],
        model_max_length=131072, clean_up_tokenization_spaces=False,
        chat_template=_field(reader, "tokenizer.chat_template"), padding_side="right",
    )
    vocab = tokenizer.get_vocab()
    if len(vocab) != len(tokens) or any(vocab.get(token) != i for i, token in enumerate(tokens)):
        raise ValueError("Embedded-tokenizer reconstruction changed vocabulary IDs")
    tokenizer.eog_token_ids = [1, 106, 50]
    return tokenizer


def _dequant_to_device(tensor, shape, device, chunk_rows=1024):
    import gguf

    shape = tuple(shape)
    if len(shape) < 2:
        array = np.array(gguf.dequantize(tensor.data, tensor.tensor_type), dtype=np.float32, copy=True)
        return torch.from_numpy(array).reshape(shape).to(device)
    # Quantization blocks lie along the last dimension; complete row chunks
    # avoid a temporary ~9.4 GB FP32 copy of the PLE embedding table.
    output = torch.empty(shape, dtype=torch.float32, device=device)
    for start in range(0, shape[0], chunk_rows):
        stop = min(start + chunk_rows, shape[0])
        array = np.array(gguf.dequantize(tensor.data[start:stop], tensor.tensor_type), dtype=np.float32, copy=True)
        output[start:stop].copy_(torch.from_numpy(array).reshape(stop - start, *shape[1:]))
    return output


def load_gemma_gguf(path, device="cuda", progress=None):
    """Return `(model, embedded_tokenizer, provenance)`; root owns GPU execution."""
    import gguf
    import transformers
    from transformers.models.gemma4 import modeling_gemma4

    reader = _open_verified(path)
    model = _skeleton(reader)
    mapping = _mapping(reader, model)
    tensors = {tensor.name: tensor for tensor in reader.tensors}
    state = model.state_dict()
    loaded = {}
    for index, (hf_name, gguf_name) in enumerate(mapping.items()):
        if gguf_name not in loaded:
            loaded[gguf_name] = _dequant_to_device(tensors[gguf_name], state[hf_name].shape, device)
        value = loaded[gguf_name]
        parent_name, attribute = hf_name.rsplit(".", 1)
        module = model.get_submodule(parent_name)
        if attribute in module._parameters:
            module._parameters[attribute] = nn.Parameter(value, requires_grad=False)
        elif attribute in module._buffers:
            module._buffers[attribute] = value
        else:
            raise ValueError(f"No parameter or persistent buffer at {hf_name}")
        if progress is not None and index % 25 == 0:
            progress({"loaded": index + 1, "total": len(mapping), "tensor": hf_name})
    model.lm_head.weight = model.model.embed_tokens.weight
    if any(value.is_meta for value in list(model.parameters()) + list(model.buffers())):
        raise RuntimeError("Unmaterialized model tensor remains")
    model = model.to(device=device, dtype=torch.float32).eval()
    tokenizer = embedded_tokenizer(reader)
    source = Path(inspect.getfile(modeling_gemma4))
    provenance = {
        "gguf_sha256": GGUF_SHA256, "repo": GGUF_REPO, "revision": GGUF_REVISION,
        "engine": "independent_transformers_gemma4_fp32_dequantized_gguf",
        "engine_sha256": sha256_file(__file__), "transformers_version": transformers.__version__,
        "transformers_model_source_sha256": sha256_file(source),
        "gguf_version": getattr(gguf, "__version__", "see_environment_lock"),
        "torch_version": torch.__version__, "dtype": "float32", "device": str(device),
        "attention": "eager", "gguf_tensor_count": len(tensors),
        "loaded_state_entries": len(mapping), "unmapped_tensors": [],
        "explicit_unused_shared_kv_tensors": [f"blk.{i}.{s}" for i in range(15,35) for s in ("attn_k.weight", "attn_v.weight", "attn_k_norm.weight")],
        "analytically_equivalent_tensor": "rope_freqs.weight",
        "tokenizer": "embedded_GGUF_vocabulary_merges_types; explicit_BOS",
        "tokenizer_backend_sha256": hashlib.sha256(tokenizer.backend_tokenizer.to_str().encode()).hexdigest(),
        "bos_token_id": 2, "eos_token_id": 106, "eog_token_ids": [1, 106, 50],
        "native_widths": [layer.mlp.down_proj.in_features for layer in model.model.layers],
        "forward_parity": "NOT_EVALUATED",
        "limitation": "Not the unavailable original map engine; independent forward validation required.",
    }
    return model, tokenizer, provenance


class NativeGeluHook:
    """Capture/change native GELU(gate)*up coordinates before the down projection.

    `positions` is None (all), an integer, one integer per batch item, or a
    boolean [B,T] mask. Records are selected positions by selected neurons.
    Patch/mean replacements broadcast to that shape. No output patch is made
    after the post-FFN norm: the original decoder continues unmodified.
    """

    def __init__(self, model, layer, neurons, positions=None, mode=None, replacement=None, scale=1.0):
        if getattr(model.config, "hidden_activation", None) != "gelu_pytorch_tanh":
            raise ValueError("NativeGeluHook requires actual GELU-tanh Gemma4 MLP")
        self.mlp = model.model.layers[int(layer)].mlp
        if not all(hasattr(self.mlp, name) for name in ("gate_proj", "up_proj", "down_proj", "act_fn")):
            raise ValueError("Unsupported native MLP layout")
        self.neurons = [int(n) for n in neurons]
        if not self.neurons or len(set(self.neurons)) != len(self.neurons) or min(self.neurons) < 0 or max(self.neurons) >= self.mlp.down_proj.in_features:
            raise ValueError("Invalid or duplicate native neuron index")
        if mode not in (None, "zero", "mean", "patch", "scale"):
            raise ValueError(f"Unsupported intervention mode {mode}")
        if mode in ("mean", "patch") and replacement is None:
            raise ValueError("Mean/patch requires an explicitly fitted replacement")
        if not np.isfinite(float(scale)):
            raise ValueError("Scale must be finite")
        self.positions, self.mode, self.replacement, self.scale = positions, mode, replacement, float(scale)
        self.records = []
        self._handles = []
        self._gate = self._up = None

    def _mask(self, product):
        batch, length, _ = product.shape
        if self.positions is None:
            return torch.ones((batch, length), dtype=torch.bool, device=product.device)
        positions = torch.as_tensor(self.positions, device=product.device)
        if positions.dtype == torch.bool:
            if tuple(positions.shape) != (batch, length):
                raise ValueError("Position mask must have exact [batch,sequence] shape")
            return positions
        if positions.dtype not in (torch.int8, torch.int16, torch.int32, torch.int64, torch.uint8):
            raise ValueError("Position indices must be integers, not fractional values")
        if positions.ndim == 0:
            positions = positions.expand(batch)
        if tuple(positions.shape) != (batch,) or torch.any(positions < -length) or torch.any(positions >= length):
            raise ValueError("Positions must have one valid index per batch item")
        mask = torch.zeros((batch, length), dtype=torch.bool, device=product.device)
        mask[torch.arange(batch, device=product.device), positions.long()] = True
        return mask

    def _projection(self, name):
        def capture(module, args, output):
            setattr(self, name, output[..., self.neurons])
        return capture

    def _before_down(self, module, args):
        product = args[0]
        mask = self._mask(product)
        selected = product[mask][:, self.neurons]
        gate, up = self._gate[mask], self._up[mask]
        computed = self.mlp.act_fn(gate) * up
        if not torch.allclose(selected, computed, rtol=2e-6, atol=1e-6):
            raise RuntimeError("Native down input is not the observed GELU-tanh(gate)*up product")
        if not torch.isfinite(selected).all():
            raise RuntimeError("Nonfinite native product")
        self.records.append({"product": selected.detach().cpu(), "gate": gate.detach().cpu(), "up": up.detach().cpu(), "positions": mask.nonzero().detach().cpu()})
        if self.mode is None:
            return None
        if self.mode == "zero":
            new = torch.zeros_like(selected)
        elif self.mode == "scale":
            new = selected * self.scale
        else:
            new = torch.as_tensor(self.replacement, device=product.device, dtype=product.dtype)
            new = torch.broadcast_to(new, selected.shape)
        if not torch.isfinite(new).all():
            raise ValueError("Nonfinite intervention replacement")
        changed = product.clone()
        rows = changed[mask].clone()
        rows[:, self.neurons] = new
        changed[mask] = rows
        return (changed, *args[1:])

    def __enter__(self):
        if self._handles:
            raise RuntimeError("Hook context is already active")
        self._handles = [
            self.mlp.gate_proj.register_forward_hook(self._projection("_gate")),
            self.mlp.up_proj.register_forward_hook(self._projection("_up")),
            self.mlp.down_proj.register_forward_pre_hook(self._before_down),
        ]
        return self

    def __exit__(self, *exc):
        for handle in self._handles:
            handle.remove()
        self._handles.clear()
        self._gate = self._up = None


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description="CPU-only exact GGUF structural audit; never loads full weights")
    parser.add_argument("--gguf", default="cache/gemma-v3/gemma-4-E2B-it-Q4_K_M.gguf")
    parser.add_argument("--output")
    args = parser.parse_args()
    torch.set_num_threads(2)
    result = inspect_gguf(args.gguf)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
