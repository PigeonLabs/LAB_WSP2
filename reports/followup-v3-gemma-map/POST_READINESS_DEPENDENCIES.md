# Post-readiness G2–G5 dependencies

검토일: 2026-11-04. 범위: 동결된 원 설계와 기존 실행 receipt의 CPU/read-only 감사. GPU 추론, 새 모델·자료 검색, D/F/T/O 생성, 원 결과 변경을 수행하지 않았다. 이 문서는 단계 완료 receipt를 대신하지 않는다.

**현재 수행할 수 있는 유용한 작업은 E/R의 수치·측정 진단과 저장 결과 재검산이다. 원 설계의 G2–G5 과학 실험을 완결할 독립 D/F/T·feature/corpus·생성 평가 자산은 아직 없다.** R64 조건부 진단 파일은 양 모델 모두 측정 완료이며, Qwen은 모든 concept×language 정확도에서 .75 미만이다. 공동 적격 축이 없으므로 H1/H2는 `NOT_APPLICABLE`이다. 엄격 source/template gate 실패는 이와 별개의 차단 사유다. H3/H4는 필요한 데이터·표현/평가 자산 부재로 `NOT_EVALUABLE`이다. 이는 효과0 또는 가설 반증을 측정했다는 뜻이 아니다.

## 확인된 근거와 범위

- [원 설계](DESIGN.md) G1은 양측 각 축·언어 R accuracy≥.75 및 cluster-aware bootstrap 하한>.50을 요구한다. [조건부 amendment](../../results/followup-v3-gemma-map/readiness_conditional_amendment.json)는 R source-record 진단을 허용하지만 원 독립-template gate나 H1–H4 eligibility를 대체하지 않는다고 명시한다.
- [R manifest](../../data/followup-v3-gemma-map/readiness_manifest.json)는 64 family/1024 variant/64 관측 source component/4 renderer와 `FAIL_SHARED_RENDERERS`, T/O 미개봉을 기록한다. Source component는 통계적 독립성의 증명이 아니다. 파일의 `MATERIALIZED_NOT_SCORED`는 당시 생성 receipt이며, 이후 별도 score 파일이 측정을 기록한다.
- [Gemma R score](../../results/followup-v3-gemma-map/readiness_scores/gemma.json), [Qwen R score](../../results/followup-v3-gemma-map/readiness_scores/qwen.json)는 모두 `MEASURED_CONDITIONAL_DIAGNOSTIC`이다. 아래 정확도는 저장된 `correct`를 CPU로 단순 평균했다. CI를 새로 선택하거나 cutoff를 바꾸지 않았다. Qwen이 accuracy 조건에서 실패하므로 CI에 관계없이 공동 pass는 없다.
- 현재 `data/followup-v3-gemma-map`에는 E와 조건부 R의 jsonl/manifest만 확인된다. 승인 D96, F96의64/32배정, T320, O96 및 별도2M-token discovery corpus receipt는 없다. 미확보를 시스템 전체의 부재로 확대하지 않는다.
- [공개 reference manifest](../../artifacts/followup-v3-gemma-map/reference_manifest.json)와 동결 config는 원 feature/transcoder weights가 검토한 공개 tree에서 확인되지 않았음을 기록한다. Exact Gemma GGUF와 native hook 확보는 transcoder weights 확보와 다르다.

| 모델 | 축 | 언어 | 저장 R 정확도 | variant 수 |
|---|---|---|---:|---:|
| gemma | negation | en | 0.640625 | 128 |
| gemma | negation | ko | 0.546875 | 128 |
| gemma | numeric_comparison | en | 0.593750 | 128 |
| gemma | numeric_comparison | ko | 0.515625 | 128 |
| gemma | ownership_coreference | en | 0.828125 | 128 |
| gemma | ownership_coreference | ko | 0.679688 | 128 |
| gemma | temporal_order | en | 0.632812 | 128 |
| gemma | temporal_order | ko | 0.500000 | 128 |
| qwen | negation | en | 0.500000 | 128 |
| qwen | negation | ko | 0.500000 | 128 |
| qwen | numeric_comparison | en | 0.500000 | 128 |
| qwen | numeric_comparison | ko | 0.492188 | 128 |
| qwen | ownership_coreference | en | 0.500000 | 128 |
| qwen | ownership_coreference | ko | 0.500000 | 128 |
| qwen | temporal_order | en | 0.500000 | 128 |
| qwen | temporal_order | ko | 0.500000 | 128 |

각 cell은16 source family의8변형이다. 128개 variant를 독립 family로 세지 않는다. Gemma ownership EN의 .828125도 그 자체로 원 strict gate 통과가 아니며, 다른 조건·자유생성으로 전이되는 능력 증거가 아니다.

## 단계별 정확한 판정과 재개 요건

| 단계/주장 | 현재 상태 | 빠진 선행조건 | 구체적인 재개 작업 |
|---|---|---|---|
| G2 새 functional profile | `BLOCKED_DATA_GATE` | 승인 D96, 새로운 문맥/lineage, D-only 후보64/layer 선택 및 lexical controls, 독립 F 설명 예측 검증 | 원 출처·template split을 만족하는 D/F를 수집·감사; L5/L27의 random32+firing-quartile32를 D에서 동결; F에서 설명 실패를 UNKNOWN으로 유지 |
| G3 / H1·H2 | `NOT_APPLICABLE` (공동 능력 적격축0), 추가 `BLOCKED_DATA_GATE` | 양측 적격 축, D-selected source8/target16 panel, F-fit/validation map·dose·eps 및 donor controls, 독립 T | 모델/공통 prompt/과제 변경을 새 protocol 버전으로 선언한 경우 새 E와 미개봉 R에서 재검증; 기존 R 결과로 조정한 prompt를 같은 R에 다시 평가해 사전 gate로 쓰지 않음. 적격 축이 확보되면 독립 D/F/T 구축 후 재개 |
| G4 / H3 | `NOT_EVALUABLE` | 검증 feature weights 또는 새 transcoder, 허가된 discovery corpus, D activity statistics, F fidelity/common-support/회귀 선택, T prediction data | 원 weights를 확보·검증하거나 별도 discovery corpus와 D로 새 skip-TopK를 3seed 학습; 새 feature ID로 명명. E에서 수치·gate 규칙 확인, F에서 fidelity 및 층당≥32 matched pairs 확인, T 이전 동결 |
| G5 / H4 | `NOT_EVALUABLE` | F-selected intervention policy, E에서 동결된 register/semantic parser 및 반례 검증, T 한국어 재진술 family, 실제5-arm generation | 사실 슬롯·한국어 register parser를 E의 반례로 검증; D 후보와 F dose {0,.25,.5,1} 정책을 실제 선택; T에서 prompt-only와 선택 정책을 포함한5arm을 평가. 사람 검증이 없으면 통제 fact-slot 범위로 한정 |

H3와 H4는 Gemma 단일 모델 실험이므로 **Qwen의 능력 실패만으로 자동 금지되는 것은 아니다.** 각각 자체 D/F/T·fidelity·생성 측정 gate가 없는 것이 현재 직접 차단 원인이다. 따라서 Qwen만 교체하면 G4/G5가 곧 실행 가능하다는 설명도 잘못이다.

G4의 원 기준을 유지한다: training 2M tokens/seed 목표·3seed는 비용 gate에 조건부; F-validation KL recovery≥.90, denominator≥1e-4, FVU≤.20, dead fraction≤.10, 정확도 하락≤2%p; 공통 support는 각층≥32쌍이다. 데이터나 corpus가 없을 때 E/R를 복제해2M tokens를 채워 이 기준을 충족했다고 하지 않는다. Reference 지도 JSON, static decoder lens 또는 native down-projection을 실제 trained transcoder로 대체하지 않는다.

G5의 **zero fallback은 F에서 후보 정책들을 실제 평가했으나 보존 조건을 만족한 정책이 없을 때의 선택 규칙**이다. F 자체가 없거나 정책 탐색을 하지 않은 지금은 fallback을 발동할 수 없다. Prompt-only를 두 번 복사해 joint gain0을 기록하거나, 무개입 identity 검사를 H4 대조 실험으로 발표하지 않는다. H4는 gain≥5%p 및 semantic/fluency 비열등성2%p를 실제 T generation으로 평가해야 한다.

## 독립적으로 실행할 수 있는 유용한 작업

**실행 완료 — 저장 R 점수의 factor sensitivity 재검산.** 추가 GPU/D/F/T/corpus 없이, semantic-state 쌍과 answer-code 쌍을 각각512개 묶어 비교했다. Canonical completion index0/1은 truth proposition에 고정되고 answer_code는 A/B 표기만 바꾸므로, 코드 변경 시 같은 index가 나와야 proposition 선택이 일관적이다. 의미 상태를 뒤집으면 올바른 proposition은 반대로 바뀐다. 이 진단은 결과를 본 뒤 계산한 **post-hoc descriptive measurement audit**이며 후보·prompt·hypothesis를 재선택하거나 primary p family에 넣지 않는다.

| 모델 | 전체 정확도 | 의미 상태 변경 시 prediction 전환율 | 코드 변경 시 canonical prediction 일치율 |
|---|---:|---:|---:|
| gemma | 0.617188 | 0.238281 | 0.406250 |
| qwen | 0.499023 | 0.005859 | 0.529297 |

각 비율은512 pair의 단순 비율이며 독립 표본 기반 CI가 아니다. 낮은 Qwen state sensitivity는 이 조건에서 문맥 변화에 둔감한 점수라는 직접 관측이다. 기능 부재·보편적 언어 무능력·특정 neuron의 원인으로 확대하지 않는다. Gemma의 code sensitivity 역시 새 prompt 탐색이나 유리한 answer_code 선택의 근거로 사용하지 않는다.

다음도 현재 자산만으로 가능하지만 새 G2–G5 과학 주장과 분리해야 한다.

1. 저장된 E/R logits와 독립 reference의 parity, batch/single scorer 일치, source/parser/해시 replay를 끝까지 검증한다. 이미 측정된 검사를 다시 실행하는 것은 새 실험 표본이 아니다.
2. E 전용으로 최소 register parser의 반례 fixture·정규식/문법 검사, null·paired-cluster resampling 코드의 수학적 simulation을 구현할 수 있다. 이는 측정 소프트웨어 준비이며 새 F/T 또는 실제 생성 기반 H4를 대체하지 않는다. R 이후 선택된 parser 변경은 별도 버전·미개봉 검증 자료가 필요하다.
3. 이미 공개된 지도 JSON을 원 출처 attribution과 함께 재집계할 수 있다. 외부 discovery 재분석으로 표시하며 새 문맥 functional validity·새 causal intervention·독립 T 성공으로 세지 않는다.
4. E-only native no-op/zero/patch의 추가 수치 검사는 하드웨어·hook engineering으로 실행 가능하지만, 이 감사는 GPU를 실행하지 않았다. 현재16 native-hook check receipt와 중복되지 않는 구체적 unresolved numerical concern이 있을 때만 추가할 가치가 있다.

현 상태에서 **데이터·자산 의존성 없이 독립적으로 완성할 수 있는 미실행 G2/G3/G4/G5 confirmatory 실험은 확인되지 않았다.** 먼저 engineering 진단과 보고를 완료하고, 위 repair 목록은 후속 독립 데이터 준비 단계로 정확히 남기는 것이 원 설계의 실행이다. 자료가 없는 단계를 가짜 측정 결과로 채우는 것은 실행 완료가 아니다.

## 통계·공개 표기

원 설계의4-claim Holm family를 유지할 때 gate 미충족 claim의 p=1은 **검정 family 크기를 보존하는 bookkeeping placeholder**다. 효과값·표준오차·CI를0으로 생성하지 않는다. 표에는 effect/CI=`not measured`, scientific verdict=`NOT_APPLICABLE`(H1/H2) 또는 `NOT_EVALUABLE`(H3/H4), reason을 따로 표시한다. 유의하지 않음·효과 없음·가설 반증으로 해석하지 않는다. G2–G5 stage status는 measured로 만들지 않는다.

## 읽은 receipt 해시

아래는 이 감사 시점의 파일 식별자다. 후속 stage aggregator가 갱신되어도 읽은 근거를 구별할 수 있도록 원 score/data/config 해시를 남긴다.

| 파일 | SHA256 |
|---|---|
| `reports/followup-v3-gemma-map/DESIGN.md` | `67600c301d80e6bde94e0005303dca541cdf3f841f5fee2132bdab18f7835d6b` |
| `configs/followup_v3_gemma_map.json` | `6f738338dcb64cd623968c71d85c15c38ba8848ba9904b18ba1d64ce14948464` |
| `configs/gemma_v3_prompt_lock.json` | `f26cee1e30467fd076ce396fe2db722993661d2e6668bb30486238075508af89` |
| `results/followup-v3-gemma-map/readiness_conditional_amendment.json` | `dac09dc28941af6a8382d4400dc31b55fb719f2a4218b40bd51ef1ca17cb1251` |
| `data/followup-v3-gemma-map/readiness_manifest.json` | `a670a63a3d609f9e487c7347accc80fd51db00e61e32c7f565d8e3033d00568b` |
| `results/followup-v3-gemma-map/readiness_scores/gemma.json` | `549dadf9076736f05c71cb1c39e1a31298e6384dbc8bfbfaa1b2c9aa6a7d99d4` |
| `results/followup-v3-gemma-map/readiness_scores/qwen.json` | `77b5a399925c07866a0ae836ef3f4e732e384d6a443cdd808331214debf974bc` |
| `artifacts/followup-v3-gemma-map/reference_manifest.json` | `db976e987e6f9dc3af4b570d3ac55c50779d649b03300b4736d43a0bfcc88b08` |
