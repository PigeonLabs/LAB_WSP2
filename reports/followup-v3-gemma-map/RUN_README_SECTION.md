## Followup-v3 Gemma map — 실행 기록

기존 pilot/v2 결과와 분리한 새 실행이다. 아래 상태는 단계별 실행 receipt를 따른다. **MEASURED는 해당 단계 산출물의 측정을 뜻하며 가설 지지를 뜻하지 않는다.** RUNNING/BLOCKED는 완료 결과가 아니며, 미측정 값은 0으로 채우지 않는다.

[설계](reports/followup-v3-gemma-map/DESIGN.md) · [설정](configs/followup_v3_gemma_map.json)

| 단계 | 상태 | 내용 |
|---|---|---|
| G0 | MEASURED | Exact GGUF provenance and environment preflight |

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
