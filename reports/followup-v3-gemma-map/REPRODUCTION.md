# V3 measured run: reproduction and evidence

This run measures engineering validity and conditional readiness. It does not measure H1–H4 confirmatory effects. Preserve the frozen design, failed original reference, and all prior pilot/v2 results. Model inference scripts refuse to overwrite their result files; use a fresh checkout/output directory for reruns.

## Evidence without model inference

The `results/followup-v3-gemma-map/raw_archives/manifest.json` manifest gives SHA256 hashes and exact member paths. Extract each corresponding `.tar.gz` at the repository root. These archives contain full 262,144-vocabulary logits for every E/R parity fixture and the public Met/Wikidata API snapshots; they contain no model weights. Extended-check `.npz` files retain complete signed error vectors and intervention logit changes.

The pinned source data and both model continuation scores are published in `data/followup-v3-gemma-map` and `results/followup-v3-gemma-map/{engineering_scores,readiness_scores}`. The four-shot candidate is E-only; the prompt lock precedes R scores. R is a fixed-renderer convenience sample and is not the confirmatory test split.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest -q tests/test_gemma_v3_data.py tests/test_gemma_v3_statistics.py tests/test_gemma_v3_readiness.py tests/test_gemma_v3_readiness_analysis.py
.venv/bin/python scripts/analyze_gemma_v3_readiness.py --replay-only
.venv/bin/python scripts/compare_gemma_v3_readiness_reference.py
MPLCONFIGDIR=artifacts/mplconfig .venv/bin/python scripts/build_gemma_v3_report.py --max-stage G6
```

Analysis CLI defaults and replay mode are documented by `--help`. Read the independent numerical audits for per-array hashes and exact replayed checks. The plot renderer reads stage receipts rather than deciding scientific eligibility itself.

## Exact models and arithmetic

Versions are recorded in `results/followup-v3-gemma-map/environment.json`. CUDA inference used FP32, eager attention and disabled TF32 on one RTX PRO6000. No LoRA or private corpus is used. Gemma is instruction tuned; Qwen is a pretrained base checkpoint, so the comparison cannot isolate pretraining conservation.

- Gemma: `unsloth/gemma-4-E2B-it-GGUF`, revision `0314792d7f1f7e229411f620751375812bb9faf2`, file `gemma-4-E2B-it-Q4_K_M.gguf`, SHA256 `740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8`. Place at `cache/gemma-v3/`.
- Qwen: `Qwen/Qwen3-0.6B-Base`, revision `da87bfb608c14b7cf20ba1ce41287e8de496c0cd`. Set its local cache location in a separate local copy of `configs/models.json` for a rerun.
- Independent forward graph: official llama.cpp commit `bee23322f1baa3d2dd16b8339bed6aff4a8eb663`; the recorded patch disables the CPU FP16 GELU lookup. Preserve an unmodified build for the original failed comparison and a separate `build-fp32-gelu` build for the repaired reference.

The loader reads exact GGUF quantized values and explicitly constructs the 35-layer Gemma architecture. Do not substitute a default Hugging Face GGUF configuration. `src/gemma_v3_reference_weights.py --output cache/gemma-v3/reference-f32.gguf` exports the same dequantized values for CPU reference, checks every tensor and retained metadata, and requires roughly18GB additional disk. This shares the dequantizer; it is not an independent dequantization test.

Build llama.cpp CPU with `GGML_CUDA=OFF`, `LLAMA_CURL=OFF`, and `LLAMA_BUILD_TESTS=OFF`. Compile `scripts/gemma_v3_reference.cpp` with the pinned tree's `include`, `ggml/include`, and `vendor` headers, link `llama`, `ggml`, `ggml-base`, `ggml-cpu` from the selected build's `bin`, and set that directory as runtime rpath. CMake and binary hashes in the numerical audits identify the actual builds.

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python scripts/run_gemma_v3_engineering.py --help
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python scripts/run_gemma_v3_readiness.py --model gemma --data data/followup-v3-gemma-map/readiness.jsonl
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python scripts/run_gemma_v3_readiness.py --model qwen --data data/followup-v3-gemma-map/readiness.jsonl
cache/gemma-v3/reference-fp32-gelu cache/gemma-v3/reference-f32.gguf results/followup-v3-gemma-map/readiness_engine/fixtures.json results/followup-v3-gemma-map/readiness_engine/llama_reference_fp32_gelu
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python scripts/validate_gemma_v3_extended.py --device cuda
```

Run model commands serially and only in a clean rerun directory. The readiness command is a reproduction of frozen R, not fresh evidence for prompt tuning. Extended greedy checks force four arithmetic decisions even after EOG; they do not test normal stopping, naturalness or factual generation quality.

## Publication and storage

The active session uses the connected GitHub Git Data API. `scripts/gemma_v3_publish_manifest.py --stage G1` (or G6) creates an explicit public-evidence allowlist and hashes. The publishing agent uploads blobs, builds on the current remote tree, and advances main only with the expected parent SHA. It verifies the remote tree against local hashes. The script alone does not start a background uploader and contains no credentials.

Execution artifacts are additive under the existing v3 directory. The run index binds this layout to the frozen prompt hash; files are not moved or overwritten merely to match a directory convention. Historical receipts describe their own observation time (for example `MATERIALIZED_NOT_SCORED` before scoring); subsequent measurements are separate receipts.

G2–G5 requirements and resumption conditions are in [POST_READINESS_DEPENDENCIES.md](POST_READINESS_DEPENDENCIES.md). No T/O was opened. H1/H2 are inapplicable for this pair/task protocol; H3/H4 are unevaluable with the currently frozen assets. Bookkeeping p=1 values, if present, are not measured p-values or evidence of no effect.
