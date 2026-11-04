## Followup-v3 Gemma map — 실행 기록

기존 pilot/v2 결과와 분리한 새 실행이다. 아래 상태는 단계별 실행 receipt를 따른다. **MEASURED는 해당 단계 산출물의 측정을 뜻하며 가설 지지를 뜻하지 않는다.** RUNNING/BLOCKED는 완료 결과가 아니며, 미측정 값은 0으로 채우지 않는다.

[설계](reports/followup-v3-gemma-map/DESIGN.md) · [설정](configs/followup_v3_gemma_map.json)

| 단계 | 상태 | 내용 |
|---|---|---|
| G0 | MEASURED | Exact GGUF provenance and environment preflight |
| G1 | MEASURED | Independent engine parity and readiness diagnostics |

### G0 · Exact GGUF provenance and environment preflight — MEASURED

참고 지도와 SHA256이 같은 3,106,738,272-byte GGUF를 확보·검증했다. 모델은 instruction-tuned checkpoint의 Q4_K_M이며 추가 LoRA가 없다. 엔진 및 데이터의 유효성은 후속 G1 gate에서 별도 검증한다.

[단계 원본 receipt](results/followup-v3-gemma-map/stages/G0.json)

**해석 범위:** Model-file identity and execution environment only; no new functional or causal inference.

**과학 판정:** DEPENDENCY_ACQUIRED_ENGINE_PENDING

| 측정 항목 | 값 | 단위/범위 | 원자료 |
|---|---:|---|---|
| GGUF bytes | 3106738272 | bytes | [results/followup-v3-gemma-map/model_download.json](results/followup-v3-gemma-map/model_download.json) |
| Download and checksum elapsed | 78.3297 | seconds | [results/followup-v3-gemma-map/model_download.json](results/followup-v3-gemma-map/model_download.json) |
| Prior evidence preserved snapshot | 3919 | files | [results/followup-v3-gemma-map/preservation_before.json](results/followup-v3-gemma-map/preservation_before.json) |

![Verified native MLP coordinates by layer](artifacts/followup-v3-gemma-map/figures/G0_native_widths.svg)

Exact downloaded GGUF tensor shapes; counts are architectural, not a functional result. Zero-based layers.

[PNG](artifacts/followup-v3-gemma-map/figures/G0_native_widths.png) · [정확한 그림 값·출처 SHA256](artifacts/followup-v3-gemma-map/figures/G0_native_widths.source.json)

해석 제한:

- GGUF file identity does not establish original engine equivalence.
- The referenced term base must not be interpreted as pretrained-only: verified artifact is instruction-tuned.
- No readiness/test data have been evaluated.

원자료 및 산출물:

- [results/followup-v3-gemma-map/model_download.json](results/followup-v3-gemma-map/model_download.json)
- [results/followup-v3-gemma-map/environment.json](results/followup-v3-gemma-map/environment.json)
- [results/followup-v3-gemma-map/preservation_before.json](results/followup-v3-gemma-map/preservation_before.json)
- [results/followup-v3-gemma-map/gguf_structure.json](results/followup-v3-gemma-map/gguf_structure.json)

### G1 · Independent engine parity and readiness diagnostics — MEASURED

정확한 GGUF의 FP32 엔진과 별도 reference를 E 8개·R 8개 입력에서 검증했다. GELU lookup 수치 실패는 원본을 보존하고 별도 빌드에서 수정했다. 고정 프롬프트 R1024 정확도는 Gemma 61.72%, Qwen 49.90%이며 공동 능력 적격 축은 없다.

[단계 원본 receipt](results/followup-v3-gemma-map/stages/G1.json)

**해석 범위:** G1 engineering and conditional readiness measurements completed; strict template/generalization gate failed. No G2–G5 confirmatory effects measured.

**과학 판정:** NUMERICAL_CHECKS_PASS; NO_JOINT_CAPABILITY_AXIS; STRICT_TEMPLATE_GATE_FAILED

| 측정 항목 | 값 | 단위/범위 | 원자료 |
|---|---:|---|---|
| Independent FP32 reference fixtures passed | 8 | of8 | [results/followup-v3-gemma-map/engineering_engine/forward_parity_fp32_gelu.json](results/followup-v3-gemma-map/engineering_engine/forward_parity_fp32_gelu.json) |
| Maximum FP32 logit difference | 8.53539e-05 | logit | [results/followup-v3-gemma-map/engineering_engine/forward_parity_fp32_gelu.json](results/followup-v3-gemma-map/engineering_engine/forward_parity_fp32_gelu.json) |
| Real model native-hook checks passed | 16 | of16 | [results/followup-v3-gemma-map/engineering_engine/validation.json](results/followup-v3-gemma-map/engineering_engine/validation.json) |
| Readiness FP32 reference fixtures passed | 8 | of8 | [results/followup-v3-gemma-map/readiness_engine/forward_parity_fp32_gelu.json](results/followup-v3-gemma-map/readiness_engine/forward_parity_fp32_gelu.json) |
| Readiness maximum logit difference | 0.000213623 | logit | [results/followup-v3-gemma-map/readiness_engine/forward_parity_fp32_gelu.json](results/followup-v3-gemma-map/readiness_engine/forward_parity_fp32_gelu.json) |
| Joint conditional capability cells | 0 | of8 | [results/followup-v3-gemma-map/readiness_summary.json](results/followup-v3-gemma-map/readiness_summary.json) |
| Same-engine arithmetic comparisons passed | 111 | checks, not independent samples | [results/followup-v3-gemma-map/engineering_extended_validation/independent_audit.json](results/followup-v3-gemma-map/engineering_extended_validation/independent_audit.json) |

**조건부 readiness: 정확도·분모·cluster 민감도**

| 모델 | 개념 | 언어 | 정확도 | 변형 수 | source clusters | source 95% CI | shared-reference clusters | 민감도 95% CI | 조건부 기준 | 민감도 기준 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemma | negation | en | 64.06% | 128 | 16 | [60.16%, 67.97%] | 16 | [60.16%, 67.97%] | False | False |
| gemma | negation | ko | 54.69% | 128 | 16 | [51.56%, 57.81%] | 16 | [51.56%, 57.81%] | False | False |
| gemma | ownership_coreference | en | 82.81% | 128 | 16 | [79.69%, 85.94%] | 14 | [80.00%, 85.71%] | True | True |
| gemma | ownership_coreference | ko | 67.97% | 128 | 16 | [63.28%, 71.88%] | 14 | [64.29%, 71.43%] | False | False |
| gemma | temporal_order | en | 63.28% | 128 | 16 | [62.50%, 64.84%] | 4 | [62.50%, 63.44%] | False | False |
| gemma | temporal_order | ko | 50.00% | 128 | 16 | [47.66%, 52.34%] | 4 | [49.06%, 59.38%] | False | False |
| gemma | numeric_comparison | en | 59.38% | 128 | 16 | [56.25%, 62.50%] | 16 | [56.25%, 62.50%] | False | False |
| gemma | numeric_comparison | ko | 51.56% | 128 | 16 | [50.00%, 53.91%] | 16 | [50.00%, 53.91%] | False | False |
| qwen | negation | en | 50.00% | 128 | 16 | [50.00%, 50.00%] | 16 | [50.00%, 50.00%] | False | False |
| qwen | negation | ko | 50.00% | 128 | 16 | [50.00%, 50.00%] | 16 | [50.00%, 50.00%] | False | False |
| qwen | ownership_coreference | en | 50.00% | 128 | 16 | [50.00%, 50.00%] | 14 | [50.00%, 50.00%] | False | False |
| qwen | ownership_coreference | ko | 50.00% | 128 | 16 | [50.00%, 50.00%] | 14 | [50.00%, 50.00%] | False | False |
| qwen | temporal_order | en | 50.00% | 128 | 16 | [50.00%, 50.00%] | 4 | [50.00%, 50.00%] | False | False |
| qwen | temporal_order | ko | 50.00% | 128 | 16 | [50.00%, 50.00%] | 4 | [50.00%, 50.00%] | False | False |
| qwen | numeric_comparison | en | 50.00% | 128 | 16 | [47.66%, 52.34%] | 16 | [47.66%, 52.34%] | False | False |
| qwen | numeric_comparison | ko | 49.22% | 128 | 16 | [47.66%, 50.00%] | 16 | [47.66%, 50.00%] | False | False |

고정 renderer·편의표집 source에 조건부인 진단이다. Source cluster 95% bootstrap CI는 독립 template 모집단 CI가 아니다. 같은 source의 변형을 함께 재표집하며, 공유 reference로 묶은 민감도 CI도 별도로 공개한다. 표의 조건부 기준(.75 정확도 및 CI 하한>.50)은 원래 strict renderer gate 또는 H1–H4의 적격성 통과를 뜻하지 않는다.

[results/followup-v3-gemma-map/readiness_summary.json](results/followup-v3-gemma-map/readiness_summary.json) · [results/followup-v3-gemma-map/readiness_replay_audit.json](results/followup-v3-gemma-map/readiness_replay_audit.json) · [results/followup-v3-gemma-map/readiness_conditional_amendment.json](results/followup-v3-gemma-map/readiness_conditional_amendment.json) · [results/followup-v3-gemma-map/readiness_scores/gemma.json](results/followup-v3-gemma-map/readiness_scores/gemma.json) · [results/followup-v3-gemma-map/readiness_scores/qwen.json](results/followup-v3-gemma-map/readiness_scores/qwen.json)

![Independent reference error before and after FP32 GELU](artifacts/followup-v3-gemma-map/figures/G1_reference_parity.svg)

Maximum across8 engineering fixtures and262144 vocabulary logits; frozen limit .01. Original failure and patched independent graph are both retained.

[PNG](artifacts/followup-v3-gemma-map/figures/G1_reference_parity.png) · [정확한 그림 값·출처 SHA256](artifacts/followup-v3-gemma-map/figures/G1_reference_parity.source.json)

![Engineering diagnostic accuracy under common raw prompt](artifacts/followup-v3-gemma-map/figures/G1_engineering_accuracy.svg)

64 variants per model/concept/language cell,8 scenarios,1 shared renderer lineage. E-only: neither independent readiness nor final test.

[PNG](artifacts/followup-v3-gemma-map/figures/G1_engineering_accuracy.png) · [정확한 그림 값·출처 SHA256](artifacts/followup-v3-gemma-map/figures/G1_engineering_accuracy.source.json)

![Conditional readiness accuracy — source-cluster bootstrap 95% CI](artifacts/followup-v3-gemma-map/figures/G1_readiness_conditional_accuracy.svg)

16 model/concept/language cells; dashed line: accuracy threshold .75 only. The separate lower-CI criterion is >.50. 고정 renderer·편의표집 source에 조건부인 진단이다. Source cluster 95% bootstrap CI는 독립 template 모집단 CI가 아니다. 같은 source의 변형을 함께 재표집하며, 공유 reference로 묶은 민감도 CI도 별도로 공개한다. 표의 조건부 기준(.75 정확도 및 CI 하한>.50)은 원래 strict renderer gate 또는 H1–H4의 적격성 통과를 뜻하지 않는다.

[PNG](artifacts/followup-v3-gemma-map/figures/G1_readiness_conditional_accuracy.png) · [정확한 그림 값·출처 SHA256](artifacts/followup-v3-gemma-map/figures/G1_readiness_conditional_accuracy.source.json)

해석 제한:

- Engineering32 scenarios are only4 generating grammar lineages; no independent-template inference.
- GGUF identity and numeric parity do not establish original map engine reproduction.
- Readiness-source diagnostic uses64 real records but four shared new renderers; cannot replace strict template-generalization gate.
- Native hook16checks cover2fixtures ×2layers ×4modes; eight-fixture parity is a separate check.
- 고정 renderer·편의표집 source에 조건부인 진단이다. Source cluster 95% bootstrap CI는 독립 template 모집단 CI가 아니다. 같은 source의 변형을 함께 재표집하며, 공유 reference로 묶은 민감도 CI도 별도로 공개한다. 표의 조건부 기준(.75 정확도 및 CI 하한>.50)은 원래 strict renderer gate 또는 H1–H4의 적격성 통과를 뜻하지 않는다.
- Same-engine native-delta equivalence, cached/full and four-step greedy checks cover two short E negation inputs only; independent cross-engine intervention effects remain unvalidated.
- Qwen intervals such as [50%,50%] reflect repeated .5 family scores under the fixed renderer; they do not establish zero population uncertainty.
- Both greedy paths reached EOG on decision2; decisions3–4 were forced arithmetic checks, not normal output generation.

원자료 및 산출물:

- [results/followup-v3-gemma-map/engineering_engine/validation.json](results/followup-v3-gemma-map/engineering_engine/validation.json)
- [results/followup-v3-gemma-map/engineering_engine/forward_parity.json](results/followup-v3-gemma-map/engineering_engine/forward_parity.json)
- [results/followup-v3-gemma-map/engineering_engine/forward_parity_fp32_gelu.json](results/followup-v3-gemma-map/engineering_engine/forward_parity_fp32_gelu.json)
- [results/followup-v3-gemma-map/reference_gelu_patch.json](results/followup-v3-gemma-map/reference_gelu_patch.json)
- [results/followup-v3-gemma-map/prompt_calibration.json](results/followup-v3-gemma-map/prompt_calibration.json)
- [configs/gemma_v3_prompt_lock.json](configs/gemma_v3_prompt_lock.json)
- [data/followup-v3-gemma-map/engineering_manifest.json](data/followup-v3-gemma-map/engineering_manifest.json)
- [results/followup-v3-gemma-map/engineering_scores/gemma.json](results/followup-v3-gemma-map/engineering_scores/gemma.json)
- [results/followup-v3-gemma-map/engineering_scores/qwen.json](results/followup-v3-gemma-map/engineering_scores/qwen.json)
- [results/followup-v3-gemma-map/readiness_summary.json](results/followup-v3-gemma-map/readiness_summary.json)
- [results/followup-v3-gemma-map/readiness_replay_audit.json](results/followup-v3-gemma-map/readiness_replay_audit.json)
- [results/followup-v3-gemma-map/readiness_conditional_amendment.json](results/followup-v3-gemma-map/readiness_conditional_amendment.json)
- [results/followup-v3-gemma-map/readiness_scores/gemma.json](results/followup-v3-gemma-map/readiness_scores/gemma.json)
- [results/followup-v3-gemma-map/readiness_scores/qwen.json](results/followup-v3-gemma-map/readiness_scores/qwen.json)
- [results/followup-v3-gemma-map/readiness_engine/forward_parity_fp32_gelu.json](results/followup-v3-gemma-map/readiness_engine/forward_parity_fp32_gelu.json)
- [results/followup-v3-gemma-map/engineering_extended_validation/summary.json](results/followup-v3-gemma-map/engineering_extended_validation/summary.json)
- [reports/followup-v3-gemma-map/RUN_AMENDMENTS.md](reports/followup-v3-gemma-map/RUN_AMENDMENTS.md)
- [results/followup-v3-gemma-map/engineering_extended_validation/independent_audit.json](results/followup-v3-gemma-map/engineering_extended_validation/independent_audit.json)
