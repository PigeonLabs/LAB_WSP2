"""Exploratory span and natural-context diagnostics on already frozen neurons.

No outputs from this module may feed candidate selection or H1-H4 fitting.
Token coordinates are model-local; character offsets identify source content.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import torch

from .experiment import _shared_answer_prefix
from .hooks import SwiGLUHook
from .models import TinyDecoder, model_mlps, token_span_indices


VERSION = "fixed-neuron-span-natural-v1"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _tokenize(tokenizer, text):
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    ids = list(encoded["input_ids"])
    offsets = [tuple(map(int, pair)) for pair in encoded["offset_mapping"]]
    if ids != tokenizer.encode(text, add_special_tokens=False):
        raise ValueError("Offset tokenizer and measurement tokenizer disagree")
    if not ids or len(ids) != len(offsets):
        raise ValueError("Expected nonempty tokens with one character offset per token")
    if any(not 0 <= a <= b <= len(text) for a, b in offsets):
        raise ValueError("Invalid Unicode character offsets")
    return ids, offsets


def _context_limit(model):
    if isinstance(model, TinyDecoder):
        return model.config.max_seq_len
    limit = getattr(model.config, "max_position_embeddings", None)
    return int(limit) if limit is not None else None


def _natural_text(model, tokenizer, text):
    """Only Tiny may truncate, retaining a whole Unicode-character prefix."""
    ids, offsets = _tokenize(tokenizer, text)
    limit = _context_limit(model)
    if limit is None or len(ids) <= limit:
        return text, ids, offsets, False
    if not isinstance(model, TinyDecoder):
        raise ValueError("Natural paragraph exceeds pretrained model context; do not silently truncate")
    end = offsets[limit - 1][1]
    used = text[:end]
    ids, offsets = _tokenize(tokenizer, used)
    while len(ids) > limit:
        used = used[:-1]
        ids, offsets = _tokenize(tokenizer, used)
    return used, ids, offsets, True


def _d1_pairs(rows):
    pairs = {}
    for row in rows:
        if row.get("split") != "D1":
            raise ValueError("Diagnostics must select controlled examples from D1 only")
        pairs.setdefault((row["concept"], row["group_id"]), {}).setdefault(row["pair_id"], []).append(row)
    result = []
    for _, group_pairs in sorted(pairs.items()):
        pair = group_pairs[sorted(group_pairs)[0]]
        if len(pair) != 2 or {r["label"] for r in pair} != {0, 1}:
            raise ValueError("Expected one complete positive/negative matched pair per group")
        result.extend(sorted(pair, key=lambda r: r["label"]))
    return result


@torch.inference_mode()
def _all_tokens(model, ids, selection, device):
    mlps = model_mlps(model)
    inputs = torch.tensor([ids], dtype=torch.long, device=device)
    kwargs = {"input_ids": inputs}
    if not isinstance(model, TinyDecoder):
        kwargs.update(attention_mask=torch.ones_like(inputs), use_cache=False)
    with ExitStack() as stack:
        hooks = [stack.enter_context(SwiGLUHook(mlps[layer], neurons=neurons,
                    positions=None, capture_contribution=False)) for layer, neurons in selection.items()]
        model(**kwargs)
        return {key: np.concatenate([hook.records[key][0].numpy() for hook in hooks], axis=1)
                for key in ("product", "gate", "up", "sign_regime", "contribution_norm")}


def _correlation(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def collect_diagnostics(model, tokenizer, dataset, collection_dir, out_dir, natural_path, device="cuda"):
    """Measure fixed D1 neurons on statement spans and a separate natural corpus.

    Uses the first complete pair per D1 concept/wrapper and all reference
    paragraphs. Exact selection is recorded. Main model fitting is untouched.
    """
    started = time.monotonic()
    collection_dir, out_dir, natural_path = map(Path, (collection_dir, out_dir, natural_path))
    selection_payload = json.loads((collection_dir / "selection.json").read_text())
    selection = {int(k): [int(n) for n in v] for k, v in selection_payload["selection"].items()}
    selection = dict(sorted(selection.items()))
    if not selection or any(not neurons for neurons in selection.values()):
        raise ValueError("Frozen nonempty neuron selection is required")
    natural = json.loads(natural_path.read_text())
    examples = natural["examples"]
    rows = _d1_pairs(dataset["D1"])
    provenance = {
        "version": VERSION, "selection": selection, "d1_rows_hash": _digest(rows),
        "natural_sha256": hashlib.sha256(natural_path.read_bytes()).hexdigest(),
        "collection_manifest_sha256": hashlib.sha256((collection_dir / "manifest.json").read_bytes()).hexdigest(),
        "model_dtype": str(next(model.parameters()).dtype), "selection_rule": "first complete pair per D1 concept/wrapper group",
    }
    signature = _digest(provenance)
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        if old.get("signature") != signature:
            raise ValueError("Diagnostics data/model/settings changed; use a new output directory")
        return old
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = ("span_boundary_comparison.parquet", "span_boundary_summary.json", "natural_top_activations.parquet",
               "natural_top_activations.json", "natural_activations.npz")
    if any((out_dir / name).exists() for name in outputs):
        raise ValueError("Partial diagnostic results exist; preserve them and choose a new output directory")
    model.eval()
    layers = np.array([layer for layer, neurons in selection.items() for _ in neurons])
    neurons = np.array([neuron for values in selection.values() for neuron in values])
    span_records, source_rows = [], []
    for row in rows:
        ids, offsets = _tokenize(tokenizer, row["prompt"])
        prefix = _shared_answer_prefix(tokenizer, row)
        context = ids + prefix
        limit = _context_limit(model)
        if limit is not None and len(context) > limit:
            raise ValueError("D1 prompt exceeds model context; span diagnostics must not truncate")
        indices = token_span_indices(offsets, *row["span"])
        if not indices:
            raise ValueError("Annotated statement span has no overlapping tokens")
        measured = _all_tokens(model, context, selection, device)
        mean = measured["product"][indices].mean(axis=0)
        boundary = measured["product"][-1]
        source_rows.append({"id": row["id"], "prompt": row["prompt"], "span": row["span"],
                            "statement": row["prompt"][row["span"][0]:row["span"][1]],
                            "span_tokens": len(indices), "prompt_tokens": len(ids),
                            "shared_prefix_tokens": len(prefix)})
        for j, (layer, neuron) in enumerate(zip(layers, neurons)):
            span_records.append({"row_id": row["id"], "concept": row["concept"], "label": row["label"],
                "template_id": row["template_id"], "layer": int(layer), "neuron": int(neuron),
                "span_start": row["span"][0], "span_end": row["span"][1], "span_token_count": len(indices),
                "prompt_token_count": len(ids), "boundary_token_index": len(context)-1,
                "span_mean_product": float(mean[j]), "boundary_product": float(boundary[j]),
                "span_mean_contribution_norm": float(measured["contribution_norm"][indices, j].mean()),
                "boundary_contribution_norm": float(measured["contribution_norm"][-1, j])})
    span_frame = pd.DataFrame(span_records)
    span_summary = []
    for (layer, neuron), group in span_frame.groupby(["layer", "neuron"]):
        span_summary.append({"layer": int(layer), "neuron": int(neuron), "n": len(group),
            "span_boundary_correlation": _correlation(group.span_mean_product, group.boundary_product),
            "mean_absolute_difference": float(np.mean(np.abs(group.span_mean_product-group.boundary_product))),
            "mean_span_token_count": float(group.span_token_count.mean())})

    # Keep a bounded top-five list per neuron/category while streaming paragraphs.
    top = {(int(l), int(n), category): [] for l, n in zip(layers, neurons)
           for category in ("absolute", "positive", "negative")}
    saved = {"layers": layers, "neuron_ids": neurons}
    natural_sources = []
    for i, example in enumerate(examples):
        raw = example["text"]
        text, ids, offsets, truncated = _natural_text(model, tokenizer, raw)
        measured = _all_tokens(model, ids, selection, device)
        prefix = f"paragraph_{i:03d}"
        for key, values in measured.items():
            saved[f"{prefix}_{key}"] = values
        saved[f"{prefix}_offsets"] = np.asarray(offsets, dtype=np.int32)
        natural_sources.append({"id": example["id"], "corpus_id": natural["dataset_version"],
            "source_url": natural["source_url"], "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "used_text": text, "original_characters": len(raw), "used_characters": len(text),
            "token_count": len(ids), "truncated": truncated, "npz_key_prefix": prefix})
        valid = np.array([b > a for a, b in offsets])
        for j, (layer, neuron) in enumerate(zip(layers, neurons)):
            values = measured["product"][:, j]
            for category in ("absolute", "positive", "negative"):
                eligible = np.flatnonzero(valid & ((values > 0) if category == "positive" else (values < 0) if category == "negative" else True))
                chosen = eligible[np.argsort(np.abs(values[eligible]))[-5:]]
                key = (int(layer), int(neuron), category)
                for token in chosen:
                    a, b = offsets[token]
                    top[key].append({"corpus_id": natural["dataset_version"], "source_url": natural["source_url"],
                        "source_id": example["id"], "layer": int(layer), "neuron": int(neuron), "category": category,
                        "token_index": int(token), "char_start": a, "char_end": b,
                        "token_text": text[a:b], "context": text[max(0,a-80):min(len(text),b+80)],
                        "context_char_start": max(0,a-80), "context_char_end": min(len(text),b+80),
                        "product": float(values[token]), "gate": float(measured["gate"][token,j]),
                        "up": float(measured["up"][token,j]), "sign_regime": int(measured["sign_regime"][token,j]),
                        "contribution_norm": float(measured["contribution_norm"][token,j])})
                top[key] = sorted(top[key], key=lambda r: (-abs(r["product"]), r["source_id"], r["token_index"]))[:5]
    atlas = []
    for records in top.values():
        atlas.extend(dict(record, rank=i+1) for i, record in enumerate(records))
    span_frame.to_parquet(out_dir / "span_boundary_comparison.parquet", index=False)
    _write_json(out_dir / "span_boundary_summary.json", {"neurons": span_summary, "source_rows": source_rows,
        "interpretation": "Exploratory within-model span mean versus answer-boundary activation; no semantic or causal identity claim."})
    pd.DataFrame(atlas).to_parquet(out_dir / "natural_top_activations.parquet", index=False)
    _write_json(out_dir / "natural_top_activations.json", {"sources": natural_sources, "top_contexts": atlas,
        "corpus": {k: natural[k] for k in ("dataset_version", "title", "author", "source_url", "license", "license_url") if k in natural},
        "interpretation": "Qualitative atlas of previously selected synthetic-task neurons; not a natural-text discovery or monosemanticity test."})
    np.savez_compressed(out_dir / "natural_activations.npz", **saved)
    manifest = {"signature": signature, "provenance": provenance, "status": "MEASURED_EXPLORATORY",
        "d1_examples": len(rows), "natural_paragraphs": len(examples), "neurons": len(neurons),
        "layers": list(selection), "natural_tokens": sum(r["token_count"] for r in natural_sources),
        "truncated_paragraphs": sum(r["truncated"] for r in natural_sources), "top_context_rows": len(atlas),
        "device": str(device), "elapsed_seconds": time.monotonic()-started,
        "limitations": ["D1-only descriptive diagnostics; no independent hypothesis test.",
            "Natural reference is a single author/book, not a representative language sample.",
            "Per-model token spans overlap the same character annotation; token counts and weights can differ.",
            "Frozen candidates were selected on synthetic tasks; natural top contexts do not remove selection bias."]}
    _write_json(manifest_path, manifest)
    return manifest
