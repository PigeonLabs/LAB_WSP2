# V3 execution amendments and preflight decisions

All entries below precede readiness and confirmatory inference. The original DESIGN.md and design JSON remain unchanged. No v2 measurement is revised.

## A0 — exact model identity (2026-11-04)

The public GGUF specified by the reference map was downloaded at pinned revision `0314792d7f1f7e229411f620751375812bb9faf2`; its actual 3,106,738,272 bytes hash to the required SHA256. Its upstream identity is Gemma-4-E2B-IT. In this study, "base" in the external project must be understood as without its optional LoRA, not as pretrained-only. The Gemma↔Qwen comparison therefore includes an instruction-tuning confound, in addition to architecture/tokenizer/training differences. It cannot isolate independent-pretraining conservation.

## A1 — independent engine validation

The published map's full inference engine is unavailable. We implement an independent Transformers FP32 engine from the exact quantized GGUF values, with explicit metadata, tensor mapping, proportional RoPE and embedded-tokenizer checks. An official pinned llama.cpp CPU implementation supplies an independent reference. Model identity, tensor equality, forward parity, and intervention correctness are separate gates. No original-map bitwise reproduction is claimed.

The original 12GB incremental disk figure was a planning target. If a temporary FP32 GGUF reference is required to separate weight identity from quantized activation arithmetic, its additional disk is recorded explicitly; the MASTER total 60GB target still applies. No user file is deleted to make space.

## A2 — engineering data are not independent test families

The first controlled engineering set has 32 scenarios / 512 variants but only four generating grammar lineages. It is used solely for numerical and prompt diagnostics. Readiness, discovery and test independence are not established by this set; no confidence interval over 32 names will be described as independent-template evidence. R/T/O are not opened by this engineering preparation. A separate source/lineage audit is required before advancing.
