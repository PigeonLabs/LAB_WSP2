# Followup-v2 research report

## 후속 연구 — followup-v2

갱신: **2026-11-04 12:37 KST**. 이 절은 새 단계별 측정 파일에서 생성되었습니다.

| 단계 | 실험 | 실행 상태 | 가설 판정 |
|---|---|---|---|
| F0 | [새 benchmark와 기존 결과 보존](../../reports/followup-v2/F0_REPORT.md) | MEASURED | SUPPORTED |
| F1 | [5개 독립 초기화 학습과 calibration 전용 형식 선택](../../reports/followup-v2/F1_REPORT.md) | MEASURED | INCONCLUSIVE |
| F2 | [정확한 뉴런 순열의 양성 대조군](../../reports/followup-v2/F2_REPORT.md) | MEASURED | SUPPORTED |
| F3 | [독립 시드·이종 계열의 두 위치 정렬과 학습 궤적](../../reports/followup-v2/F3_REPORT.md) | MEASURED | INCONCLUSIVE |
| F4 | [Single/group causal effects and dose response](../../reports/followup-v2/F4_REPORT.md) | PENDING | INCONCLUSIVE |
| F5 | [Transplantation and selective merging](../../reports/followup-v2/F5_REPORT.md) | PENDING | INCONCLUSIVE |
| F6 | [Global statistics, replay and preservation audit](../../reports/followup-v2/F6_REPORT.md) | PENDING | INCONCLUSIVE |

실행 완료와 가설 지지는 별개입니다. 모델이 해당 과제를 학습했는지 먼저 확인하며, 낮은 능력의 대응 실패를 보존 가설의 반증으로 바꾸지 않습니다. 새 데이터·프로토콜·후보·검정 범위를 기록하고 기존 pilot-v1 결과를 보존합니다. 군집·모델 seed·매칭 seed·다중검정 범위가 다른 수치를 임의로 합치지 않습니다. 인과 효과 일치도 이식이나 병합의 유효성을 자동으로 보장하지 않습니다.

### F0 — 새 benchmark와 기존 결과 보존

**MEASURED · SUPPORTED**. 20,224문항의 정답 oracle·분할 중복·짝별 단서 균형 검증을 통과했다. 이는 명시한 단서의 차단을 확인하며 모든 shortcut의 부재를 뜻하지 않는다. 기존 파일 261개의 SHA256을 보존했다.

![Frozen followup data by split](../../artifacts/followup-v2/figures/f0_f0_dataset.svg)



[그림 데이터](../../artifacts/followup-v2/figures/f0_f0_dataset.json)

[F0 측정값·불확실성·원본](../../reports/followup-v2/F0_REPORT.md)

### F1 — 5개 독립 초기화 학습과 calibration 전용 형식 선택

**MEASURED · INCONCLUSIVE**. 서로 다른 초기 파라미터 해시의 모델 5개 학습과 8개 모델의 calibration 형식 고정을 완료했다. 선택한 형식의 calibration 과제 셀 32개 중 14개가 사전 능력 기준을 충족했다. 이는 형식 선택에 사용한 표본의 진단이며 독립 D3/D4 일반화 결과가 아니다.

![Five independent seeds: training objective](../../artifacts/followup-v2/figures/f1_five_seed_training.svg)

Training loss is not held-out competence. No D3/D4 outcomes are used in this figure.

[그림 데이터](../../artifacts/followup-v2/figures/f1_five_seed_training.json)

![Calibration accuracy under frozen selected formats](../../artifacts/followup-v2/figures/f1_selected_calibration_accuracy.svg)

Selected on calibration itself; this is an in-sample readiness diagnostic, not final test accuracy.

[그림 데이터](../../artifacts/followup-v2/figures/f1_selected_calibration_accuracy.json)

![Calibration format comparison](../../artifacts/followup-v2/figures/f1_calibration_variant_comparison.svg)

Byte-tokenizer models use default only; unevaluated formats are N/A. One format is frozen per model.

[그림 데이터](../../artifacts/followup-v2/figures/f1_calibration_variant_comparison.json)

[F1 측정값·불확실성·원본](../../reports/followup-v2/F1_REPORT.md)

### F2 — 정확한 뉴런 순열의 양성 대조군

**MEASURED · SUPPORTED**. 등록한 모델 내부 순열 대칭 대조군의 정렬·개입 검증을 통과했다. 이는 측정 파이프라인의 해당 회복 성질을 검사하며, 독립적으로 학습된 모델의 의미 보존을 입증하지 않는다.

![Known-permutation correspondence recovery](../../artifacts/followup-v2/figures/f2_permutation_recovery.svg)



[그림 데이터](../../artifacts/followup-v2/figures/f2_permutation_recovery.json)

![Known-permutation correlation and repeated random mean](../../artifacts/followup-v2/figures/f2_permutation_vs_random.svg)

Random baseline has 100 realizations; its SD is reported separately and is not labeled a confidence interval.

[그림 데이터](../../artifacts/followup-v2/figures/f2_permutation_vs_random.json)

[F2 측정값·불확실성·원본](../../reports/followup-v2/F2_REPORT.md)

### F3 — 독립 시드·이종 계열의 두 위치 정렬과 학습 궤적

**MEASURED · INCONCLUSIVE**. 등록한 최종 모델 비교26개와 초기·중간 체크포인트 비교40개를 완료했다. 두 위치의 최종 모델쌍×과제 셀 중 52개에서 양쪽 모델의 능력 조건을 충족했다. 전체 과제 결과와 능력 조건을 구분하며, 학습 전 대응과 반복 무작위 매칭을 함께 공개한다. 확인 검정의 전역 BH는 F6에서 적용한다. 이종 계열은 calibration으로 고정한 서로 다른 프롬프트 접두 맥락을 사용하므로 동일 전체 입력의 비교가 아니며, 낮은 과제 능력에서 기능 보존의 부재를 결론내릴 수 없다. 사후 괄호 스트레스 분석에서 독립 학습 모델의 정확도는 인접 종류 불일치가 있는 pair 집합에서 93.4%–100.0%(n=166), 없는 집합에서 50.0%–61.5%(n=26)였다. 작은 사후 부분집합과 내용 차이를 포함한 연관성이므로 인과적 shortcut 사용 증거는 아니지만, 전체 정확도 능력 gate만으로 재귀적·구조적 이해를 입증할 수 없음을 보여 준다. 수 비교·부정 과제의 측정과는 구분한다.

![D3 final-model alignment: answer position](../../artifacts/followup-v2/figures/f3_final_answer.svg)

All task rows retained; competence-qualified strata are reported in the source. Random baseline averages100 frozen maps.

[그림 데이터](../../artifacts/followup-v2/figures/f3_final_answer.json)

![D3 final-model alignment: span position](../../artifacts/followup-v2/figures/f3_final_span.svg)

All task rows retained; competence-qualified strata are reported in the source. Random baseline averages100 frozen maps.

[그림 데이터](../../artifacts/followup-v2/figures/f3_final_span.json)

![Joint-wrapper activation_minus_random](../../artifacts/followup-v2/figures/f3_activation_minus_random.svg)

All observed pairs remain together inside each resampled wrapper; these intervals are conditional on the fixed model collection, not unseen model seeds.

[그림 데이터](../../artifacts/followup-v2/figures/f3_activation_minus_random.json)

![Joint-wrapper semantic_minus_activation](../../artifacts/followup-v2/figures/f3_semantic_minus_activation.svg)

All observed pairs remain together inside each resampled wrapper; these intervals are conditional on the fixed model collection, not unseen model seeds.

[그림 데이터](../../artifacts/followup-v2/figures/f3_semantic_minus_activation.json)

![Independent-seed response correspondence across training](../../artifacts/followup-v2/figures/f3_independent_seed_trajectory.svg)

The same final-D1 neurons and final-D2 maps are reused at all checkpoints. This is descriptive tracking, not checkpoint-specific feature discovery.

[그림 데이터](../../artifacts/followup-v2/figures/f3_independent_seed_trajectory.json)

![D3 task competence across models and checkpoints](../../artifacts/followup-v2/figures/f3_trajectory_competence.svg)

D3 was collected only after the registered D2 maps were frozen. Initial/middle/final are not independent model replications.

[그림 데이터](../../artifacts/followup-v2/figures/f3_trajectory_competence.json)

![Posthoc D3 syntax accuracy by local-cue stratum](../../artifacts/followup-v2/figures/f3_posthoc_syntax_local_cue.svg)

Exploratory cuts chosen after D3; both true/false pair members retained. N counts rows. Unequal content and small n=26 stratum confound differences; no causal cue-use claim or confirmatory test.

[그림 데이터](../../artifacts/followup-v2/figures/f3_posthoc_syntax_local_cue.json)

[F3 측정값·불확실성·원본](../../reports/followup-v2/F3_REPORT.md)

[연구 해석 한계와 비판](../../reports/followup-v2/RESEARCH_CRITIQUE.md)

