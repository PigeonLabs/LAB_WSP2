#!/usr/bin/env python3
"""Fetch pinned public base models and a separate public-domain prose reference.

No GPU allocation, remote code, credentials, optimizer states or duplicate weights.
Re-running reuses verified hub cache files and preserves the immutable source hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
HF_HOME = ROOT / "cache" / "huggingface"
os.environ["HF_HOME"] = str(HF_HOME)
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
MODELS = [
    ("Qwen/Qwen3-0.6B-Base", "da87bfb608c14b7cf20ba1ce41287e8de496c0cd"),
    ("HuggingFaceTB/SmolLM2-360M", "f8027fd0eaeea54caa13c31d31b9fdc459c38b49"),
    ("allenai/OLMo-2-0425-1B", "a1847dff35000b4271fa70afc5db10fd29fedbdf"),
]
ALLOW = ["config.json", "generation_config.json", "tokenizer*", "special_tokens_map.json",
         "added_tokens.json", "vocab.json", "vocab.txt", "merges.txt", "*.model",
         "model*.safetensors", "model.safetensors.index.json", "README.md", "LICENSE*", "NOTICE*"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def prepare_models() -> None:
    from huggingface_hub import snapshot_download
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "cache_dir": str(HF_HOME / "hub"), "allow_patterns": ALLOW,
                "trust_remote_code": False, "models": []}
    for repo, revision in MODELS:
        print(f"Downloading {repo}@{revision}", flush=True)
        path = Path(snapshot_download(repo_id=repo, revision=revision, token=False,
                    cache_dir=str(HF_HOME / "hub"), allow_patterns=ALLOW, max_workers=2))
        config = json.loads((path / "config.json").read_text())
        card = (path / "README.md").read_text()
        license_match = re.search(r"(?m)^license:\s*([^\n]+)", card)
        if not license_match:
            raise ValueError(f"Missing license in model card: {repo}")
        entry = {"model_id": repo, "revision": revision, "local_path": str(path),
                 "model_type": config.get("model_type"), "architectures": config.get("architectures"),
                 "hidden_size": config.get("hidden_size"), "intermediate_size": config.get("intermediate_size"),
                 "num_hidden_layers": config.get("num_hidden_layers"), "hidden_act": config.get("hidden_act"),
                 "license": license_match.group(1).strip(),
                 "model_card_url": f"https://huggingface.co/{repo}/blob/{revision}/README.md",
                 "status": "DOWNLOADED", "files": []}
        for file in sorted(path.rglob("*")):
            if file.is_file():
                entry["files"].append({"path": str(file.relative_to(path)), "bytes": file.stat().st_size,
                                       "sha256": sha256(file)})
        if not any(x["path"].endswith(".safetensors") for x in entry["files"]):
            raise RuntimeError(f"No safe tensor weights found for {repo}")
        manifest["models"].append(entry)
        save_json(ROOT / "configs" / "models.json", manifest)
        print(f"Verified {repo}: {entry['model_type']}; license {entry['license']}", flush=True)


def prepare_natural() -> None:
    url = "https://www.gutenberg.org/ebooks/1661.txt.utf-8"
    target = ROOT / "cache" / "corpora" / "pg1661.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "NeuronConservationPilot/1.0 (research)"})
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read()
        target.write_bytes(raw)
    raw = target.read_bytes()
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    start = re.search(r"\*\*\* START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*", text)
    end = re.search(r"\*\*\* END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*", text)
    if not start or not end:
        raise ValueError("Cannot isolate original public-domain body from Gutenberg header/footer")
    body = text[start.end():end.start()]
    first_chapter = re.search(r"(?m)^I\. A SCANDAL IN BOHEMIA\s*$", body)
    if not first_chapter:
        raise ValueError("Cannot remove title and table of contents deterministically")
    body = body[first_chapter.end():]
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", body)]
    paragraphs = [p for p in paragraphs if 200 <= len(p) <= 800]
    if len(paragraphs) < 30:
        raise ValueError("Not enough eligible natural-language paragraphs")
    indices = [i * (len(paragraphs) - 1) // 29 for i in range(30)]
    rows = [{"id": f"natural_pg1661_{i:03d}", "text": paragraphs[j],
             "eligible_paragraph_index": j,
             "sha256": hashlib.sha256(paragraphs[j].encode()).hexdigest(),
             "split": "NATURAL_REFERENCE_ONLY", "concept": None,
             "use": "Qualitative activation atlas only; excluded from D1-D4 and model training"}
            for i, j in enumerate(indices)]
    artifact = {"dataset_version": "pg1661-natural-reference-v1", "source_url": url,
                "catalog_url": "https://www.gutenberg.org/ebooks/1661",
                "title": "The Adventures of Sherlock Holmes", "author": "Arthur Conan Doyle",
                "original_publication_year": 1892,
                "license": "Original literary text: public domain in the USA (Gutenberg catalog).",
                "license_url": "https://www.gutenberg.org/policy/license.html",
                "source_notice": text[:start.start()].strip(),
                "source_license_footer": text[end.end():].strip(),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "source_bytes": len(raw), "source_cache_path": str(target),
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "selection_rule": "After title/contents removal: 30 equally spaced eligible full paragraphs, 200-800 normalized characters; no content ranking",
                "sample_count": len(rows), "examples": rows}
    out = ROOT / "data" / "natural_reference.json"
    if out.exists():
        previous = json.loads(out.read_text())
        if previous["source_sha256"] != artifact["source_sha256"]:
            raise RuntimeError("Source changed: create a new corpus version instead of overwriting")
        artifact["retrieved_at_utc"] = previous["retrieved_at_utc"]
    save_json(out, artifact)
    print(f"Saved {len(rows)} natural examples, source SHA256 {artifact['source_sha256']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["models", "natural", "all"], default="all")
    args = parser.parse_args()
    if args.only in ["models", "all"]:
        prepare_models()
    if args.only in ["natural", "all"]:
        prepare_natural()
