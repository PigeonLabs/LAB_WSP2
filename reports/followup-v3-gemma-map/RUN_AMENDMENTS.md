# V3 execution amendments and preflight decisions

Decisions A0–A2 precede readiness inference. A3 documents an engineering repair after observing a numerical failure; A4 was frozen before readiness scores. The original DESIGN.md and design JSON remain unchanged. No v2 measurement is revised.

## A0 — exact model identity (2026-11-04)

The public GGUF specified by the reference map was downloaded at pinned revision `0314792d7f1f7e229411f620751375812bb9faf2`; its actual 3,106,738,272 bytes hash to the required SHA256. Its upstream identity is Gemma-4-E2B-IT. In this study, "base" in the external project must be understood as without its optional LoRA, not as pretrained-only. The Gemma↔Qwen comparison therefore includes an instruction-tuning confound, in addition to architecture/tokenizer/training differences. It cannot isolate independent-pretraining conservation.

## A1 — independent engine validation

The published map's full inference engine is unavailable. We implement an independent Transformers FP32 engine from the exact quantized GGUF values, with explicit metadata, tensor mapping, proportional RoPE and embedded-tokenizer checks. An official pinned llama.cpp CPU implementation supplies an independent reference. Model identity, tensor equality, forward parity, and intervention correctness are separate gates. No original-map bitwise reproduction is claimed.

The original 12GB incremental disk figure was a planning target. If a temporary FP32 GGUF reference is required to separate weight identity from quantized activation arithmetic, its additional disk is recorded explicitly; the MASTER total 60GB target still applies. No user file is deleted to make space.

## A2 — engineering data are not independent test families

The first controlled engineering set has 32 scenarios / 512 variants but only four generating grammar lineages. It is used solely for numerical and prompt diagnostics. Readiness, discovery and test independence are not established by this set; no confidence interval over 32 names will be described as independent-template evidence. R/T/O are not opened by this engineering preparation. A separate source/lineage audit is required before advancing.

## A3 — failed reference retained; analytic FP32 GELU repair

The original CPU reference passed token and top-1 equality but failed the frozen logit tolerances on the eight engineering inputs. The CPU implementation used a FP16 GELU lookup table even with F32 weights/activations. Its analytic GELU path was enabled in a separate build, with the one-line source patch and both raw runs retained. The tolerance was not changed. The new forward comparison passed all eight E inputs (maximum absolute error 0.000085354, limit 0.01). This is independent forward-graph evidence, with a shared GGUF dequantizer; it is not original-map reproduction or an independent intervention-effect validation. See [patch receipt](../../results/followup-v3-gemma-map/reference_gelu_patch.json) and [original failure](../../results/followup-v3-gemma-map/engineering_engine/forward_parity.json).

## A4 — pre-readiness conditional diagnostic; strict gate unchanged

After E-only comparison of raw and common four-shot prompts, raw was frozen by the predeclared max-min two-model accuracy rule. No R scores were used in that choice. The source bank contains 64 actual public source records, with API snapshots and fact replay. Four shared bilingual renderer lineages generate 1,024 balanced variants. The 64 source components and 50 shared-reference sensitivity components are distinct from template independence. Both truth states are explicitly fictional records.

The [pre-readiness amendment](../../results/followup-v3-gemma-map/readiness_conditional_amendment.json) permits only a fixed-prompt conditional capability diagnostic. Accuracy ≥0.75 and source-cluster bootstrap lower bound >0.50 remain the diagnostic thresholds; the intervals are descriptive for this convenience sample. Passing them cannot override the failed strict independent-template gate. No confirmatory T/O data are opened and no H1–H4 claim is licensed by this amendment. R findings cannot be used to retune the current prompt. Any repair requiring new discovery/fit/test data requires a separately frozen revision and leaves this run intact.
