"""Small independent-initialization decoder and explicit SwiGLU model adapters."""
from dataclasses import dataclass
from types import SimpleNamespace
import math

import torch
from torch import nn
from torch.nn import functional as F


@dataclass
class ModelConfig:
    vocab_size: int = 258
    dim: int = 384
    hidden_dim: int = 1024
    layers: int = 6
    heads: int = 6
    max_seq_len: int = 512

    def __post_init__(self):
        if self.dim % self.heads or (self.dim // self.heads) % 2:
            raise ValueError("RoPE requires an even head dimension and dim divisible by heads")


class RMSNorm(nn.Module):
    def __init__(self, dim, eps=1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x):
        norm = x.float() * torch.rsqrt(x.float().square().mean(-1, keepdim=True) + self.eps)
        return norm.to(x.dtype) * self.weight


class CausalAttention(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.heads = config.heads
        self.head_dim = config.dim // config.heads
        self.qkv = nn.Linear(config.dim, 3 * config.dim, bias=False)
        self.out = nn.Linear(config.dim, config.dim, bias=False)
        self.register_buffer("inv_freq", 10000.0 ** (-torch.arange(0, self.head_dim, 2).float() / self.head_dim), persistent=False)

    def rope(self, x):
        angles = torch.outer(torch.arange(x.shape[-2], device=x.device).float(), self.inv_freq.float())
        c, s = angles.cos().to(x.dtype), angles.sin().to(x.dtype)
        a, b = x[..., 0::2], x[..., 1::2]
        return torch.stack((a * c - b * s, a * s + b * c), -1).flatten(-2)

    def forward(self, x):
        b, t, d = x.shape
        q, k, v = self.qkv(x).reshape(b, t, 3, self.heads, self.head_dim).permute(2, 0, 3, 1, 4).unbind(0)
        a = F.scaled_dot_product_attention(self.rope(q), self.rope(k), v, is_causal=True)
        return self.out(a.transpose(1, 2).contiguous().view(b, t, d))


class SwiGLU(nn.Module):
    def __init__(self, dim, hidden_dim):
        super().__init__()
        self.gate_proj = nn.Linear(dim, hidden_dim, bias=False)
        self.up_proj = nn.Linear(dim, hidden_dim, bias=False)
        self.down_proj = nn.Linear(hidden_dim, dim, bias=False)
        self.act_fn = F.silu

    def forward(self, x):
        return self.down_proj(self.act_fn(self.gate_proj(x)) * self.up_proj(x))


class DecoderLayer(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.attention_norm = RMSNorm(config.dim)
        self.attention = CausalAttention(config)
        self.mlp_norm = RMSNorm(config.dim)
        self.mlp = SwiGLU(config.dim, config.hidden_dim)

    def forward(self, x):
        x = x + self.attention(self.attention_norm(x))
        return x + self.mlp(self.mlp_norm(x))


class TinyDecoder(nn.Module):
    def __init__(self, config=None):
        super().__init__()
        self.config = config or ModelConfig()
        self.embedding = nn.Embedding(self.config.vocab_size, self.config.dim)
        self.layers = nn.ModuleList([DecoderLayer(self.config) for _ in range(self.config.layers)])
        self.norm = RMSNorm(self.config.dim)
        self.lm_head = nn.Linear(self.config.dim, self.config.vocab_size, bias=False)
        self.apply(self._init)

    @staticmethod
    def _init(module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, std=0.02)

    def forward(self, input_ids, labels=None, attention_mask=None):
        if input_ids.ndim != 2 or input_ids.shape[1] > self.config.max_seq_len:
            raise ValueError("Expected [batch, time] input within max_seq_len")
        if attention_mask is not None and not bool(torch.all(attention_mask)):
            raise ValueError("TinyDecoder requires unpadded inputs (batch by equal length)")
        x = self.embedding(input_ids)
        for layer in self.layers:
            x = layer(x)
        logits = self.lm_head(self.norm(x))
        loss = None
        if labels is not None:
            loss = F.cross_entropy(logits[:, :-1].float().reshape(-1, logits.shape[-1]), labels[:, 1:].reshape(-1), ignore_index=-100)
        return SimpleNamespace(logits=logits, loss=loss)


def build_model(config=None, seed=0):
    """Independent seed without changing the caller's CPU RNG state."""
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        return TinyDecoder(config)


class ByteTokenizer:
    """UTF-8 tokenizer; offsets refer to Unicode character positions, not bytes."""
    pad_token_id = 0
    eos_token_id = 1
    vocab_size = 258

    def encode(self, text, add_special_tokens=False):
        ids = [b + 2 for b in text.encode("utf-8")]
        return ids + [self.eos_token_id] if add_special_tokens else ids

    def decode(self, ids):
        return bytes([i - 2 for i in ids if i >= 2]).decode("utf-8", errors="replace")

    def __call__(self, text, return_offsets_mapping=False, return_tensors=None, add_special_tokens=False):
        if not isinstance(text, str):
            raise TypeError("ByteTokenizer accepts one string; explicitly batch equal-length examples")
        ids = self.encode(text, add_special_tokens)
        out = {"input_ids": ids, "attention_mask": [1] * len(ids)}
        if return_offsets_mapping:
            offsets = [(i, i + 1) for i, ch in enumerate(text) for _ in ch.encode("utf-8")]
            out["offset_mapping"] = offsets + ([(0, 0)] if add_special_tokens else [])
        if return_tensors is not None:
            if return_tensors != "pt":
                raise ValueError("Only return_tensors='pt' is supported")
            out = {k: torch.tensor([v], dtype=torch.long) for k, v in out.items()}
        return out


def model_mlps(model):
    """Accept only verified explicit gate/up/down layouts; reject fused/other MLPs."""
    if isinstance(model, TinyDecoder):
        layers = model.layers
    elif hasattr(model, "model") and hasattr(model.model, "layers"):
        layers = model.model.layers
    else:
        raise TypeError(f"Unsupported decoder layout: {type(model).__name__}")
    mlps = []
    for i, layer in enumerate(layers):
        mlp = getattr(layer, "mlp", None)
        if mlp is None or not all(isinstance(getattr(mlp, name, None), nn.Linear) for name in ("gate_proj", "up_proj", "down_proj")):
            raise TypeError(f"Layer {i} lacks supported separate gate/up/down projections")
        if mlp.gate_proj.out_features != mlp.up_proj.out_features or mlp.down_proj.in_features != mlp.gate_proj.out_features:
            raise ValueError(f"Layer {i} has inconsistent MLP dimensions")
        act = getattr(mlp, "act_fn", None)
        if act is None:
            raise TypeError(f"Layer {i} does not expose activation function")
        probe = torch.tensor([-2., -0.5, 0., 1., 3.])
        if not torch.allclose(act(probe), F.silu(probe), atol=1e-6, rtol=1e-5):
            raise TypeError(f"Layer {i} is not SwiGLU; provide a distinct neuron definition")
        mlps.append(mlp)
    return mlps


def sample_layers(model, depths=(0.2, 0.4, 0.6, 0.8)):
    n = len(model_mlps(model))
    return sorted(set(max(0, min(n - 1, math.ceil(d * n) - 1)) for d in depths))


def token_span_indices(offsets, start, end):
    """Select tokens overlapping a half-open character span, skipping specials."""
    if start < 0 or end <= start:
        raise ValueError("Expected a nonempty nonnegative character span")
    return [i for i, (a, b) in enumerate(offsets) if b > a and a < end and b > start]
