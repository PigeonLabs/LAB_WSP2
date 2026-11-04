# F4 과제 능력별 인과 정렬 기술 통계

**기존 D4 평가26개를 모두 완료한 뒤, 저장된 과제별 정렬 점수만 재집계했다.** 정렬을 다시 학습하거나 주 검정군110개를 변경하지 않았다. 이 문서는 새 가설 검정·p값·신뢰구간을 제공하지 않는다.

`all_pairs`는 관측 모델 쌍 전체, `both_passed`는 해당 D4 과제에서 두 모델 모두 기존 능력 기준(정확도≥0.70, Wilson95 하한>0.50)을 통과한 쌍이다. **D4 결과에 조건을 건 부분집합이므로 독립적인 확인적 추론으로 해석할 수 없다.** 공통 모델을 사용하는 쌍들도 독립 반복이 아니다.

표의 각 값은 해당 과제·위치·개입 단위에서 관측한 모델 쌍의 평균 상관계수다. 각 쌍의 점수는 기존 평가에서 wrapper와 개입 유형에 동일 가중을 준 값이며, 여기서는 유한한 쌍 평균들을 동일 가중으로 평균한다. 미정의 값은0으로 채우지 않는다.

셀 형식: **평균 [유효 쌍 수; 유효 wrapper 셀/가능 wrapper 셀]**. `Pairs`는 해당 부분집합의 쌍 수/전체 관측 쌍 수다. 방법별 누락 쌍 수와 완전한 wrapper 지원을 가진 쌍 수, 개별 쌍 점수는 [JSON](../../results/followup-v2/causal_alignment/competence_descriptive.json)에 기록했다.

## 독립 초기화 모델

### single · answer

| Task | Subset | Pairs | Semantic | Causal | Combined | Random |
|---|---|---:|---:|---:|---:|---:|
| arithmetic | all_pairs | 10/10 | -0.0075 [10; 240/240] | 0.0177 [10; 240/240] | 0.0140 [10; 240/240] | 0.0010 [10; 240/240] |
| arithmetic | both_passed | 0/10 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| comparison | all_pairs | 10/10 | 0.0047 [10; 240/240] | 0.0922 [10; 240/240] | 0.0911 [10; 240/240] | 0.0021 [10; 240/240] |
| comparison | both_passed | 10/10 | 0.0047 [10; 240/240] | 0.0922 [10; 240/240] | 0.0911 [10; 240/240] | 0.0021 [10; 240/240] |
| negation | all_pairs | 10/10 | 0.0147 [10; 240/240] | 0.0145 [10; 240/240] | 0.0117 [10; 240/240] | -0.0005 [10; 240/240] |
| negation | both_passed | 6/10 | 0.0137 [6; 144/144] | 0.0112 [6; 144/144] | 0.0175 [6; 144/144] | -0.0003 [6; 144/144] |
| syntax | all_pairs | 10/10 | 0.0013 [10; 240/240] | 0.1117 [10; 240/240] | 0.1312 [10; 240/240] | -0.0041 [10; 240/240] |
| syntax | both_passed | 10/10 | 0.0013 [10; 240/240] | 0.1117 [10; 240/240] | 0.1312 [10; 240/240] | -0.0041 [10; 240/240] |

### single · span

| Task | Subset | Pairs | Semantic | Causal | Combined | Random |
|---|---|---:|---:|---:|---:|---:|
| arithmetic | all_pairs | 10/10 | 0.0076 [10; 240/240] | 0.0015 [10; 240/240] | 0.0084 [10; 240/240] | -0.0015 [10; 240/240] |
| arithmetic | both_passed | 0/10 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| comparison | all_pairs | 10/10 | -0.0110 [10; 240/240] | 0.0220 [10; 240/240] | 0.0099 [10; 240/240] | 0.0027 [10; 240/240] |
| comparison | both_passed | 10/10 | -0.0110 [10; 240/240] | 0.0220 [10; 240/240] | 0.0099 [10; 240/240] | 0.0027 [10; 240/240] |
| negation | all_pairs | 10/10 | -0.0088 [10; 240/240] | 0.0084 [10; 240/240] | -0.0092 [10; 240/240] | -0.0038 [10; 240/240] |
| negation | both_passed | 6/10 | -0.0088 [6; 144/144] | 0.0025 [6; 144/144] | -0.0154 [6; 144/144] | -0.0025 [6; 144/144] |
| syntax | all_pairs | 10/10 | -0.0210 [10; 240/240] | -0.0027 [10; 240/240] | 0.0044 [10; 240/240] | 0.0018 [10; 240/240] |
| syntax | both_passed | 10/10 | -0.0210 [10; 240/240] | -0.0027 [10; 240/240] | 0.0044 [10; 240/240] | 0.0018 [10; 240/240] |

### group · answer

| Task | Subset | Pairs | Semantic | Causal | Combined | Random |
|---|---|---:|---:|---:|---:|---:|
| arithmetic | all_pairs | 10/10 | 0.0059 [10; 240/240] | -0.0139 [10; 240/240] | 0.0083 [10; 240/240] | -0.0074 [10; 240/240] |
| arithmetic | both_passed | 0/10 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| comparison | all_pairs | 10/10 | 0.0116 [10; 240/240] | 0.1453 [10; 240/240] | 0.1378 [10; 240/240] | 0.0196 [10; 240/240] |
| comparison | both_passed | 10/10 | 0.0116 [10; 240/240] | 0.1453 [10; 240/240] | 0.1378 [10; 240/240] | 0.0196 [10; 240/240] |
| negation | all_pairs | 10/10 | 0.0094 [10; 240/240] | 0.0352 [10; 240/240] | 0.0290 [10; 240/240] | 0.0225 [10; 240/240] |
| negation | both_passed | 6/10 | -0.0026 [6; 144/144] | 0.0316 [6; 144/144] | 0.0400 [6; 144/144] | 0.0216 [6; 144/144] |
| syntax | all_pairs | 10/10 | 0.0307 [10; 240/240] | 0.1590 [10; 240/240] | 0.1536 [10; 240/240] | 0.0302 [10; 240/240] |
| syntax | both_passed | 10/10 | 0.0307 [10; 240/240] | 0.1590 [10; 240/240] | 0.1536 [10; 240/240] | 0.0302 [10; 240/240] |

### group · span

| Task | Subset | Pairs | Semantic | Causal | Combined | Random |
|---|---|---:|---:|---:|---:|---:|
| arithmetic | all_pairs | 10/10 | -0.0059 [10; 240/240] | 0.0107 [10; 240/240] | -0.0062 [10; 240/240] | -0.0086 [10; 240/240] |
| arithmetic | both_passed | 0/10 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| comparison | all_pairs | 10/10 | -0.0054 [10; 240/240] | 0.0193 [10; 240/240] | 0.0170 [10; 240/240] | 0.0019 [10; 240/240] |
| comparison | both_passed | 10/10 | -0.0054 [10; 240/240] | 0.0193 [10; 240/240] | 0.0170 [10; 240/240] | 0.0019 [10; 240/240] |
| negation | all_pairs | 10/10 | -0.0003 [10; 240/240] | -0.0282 [10; 240/240] | -0.0230 [10; 240/240] | 0.0044 [10; 240/240] |
| negation | both_passed | 6/10 | -0.0187 [6; 144/144] | -0.0490 [6; 144/144] | -0.0339 [6; 144/144] | 0.0017 [6; 144/144] |
| syntax | all_pairs | 10/10 | 0.0047 [10; 240/240] | -0.0078 [10; 240/240] | 0.0117 [10; 240/240] | 0.0080 [10; 240/240] |
| syntax | both_passed | 10/10 | 0.0047 [10; 240/240] | -0.0078 [10; 240/240] | 0.0117 [10; 240/240] | 0.0080 [10; 240/240] |

## 서로 다른 모델 계열

### single · answer

| Task | Subset | Pairs | Semantic | Causal | Combined | Random |
|---|---|---:|---:|---:|---:|---:|
| arithmetic | all_pairs | 3/3 | -0.0243 [3; 72/72] | 0.0299 [3; 72/72] | 0.0299 [3; 72/72] | -0.0122 [3; 72/72] |
| arithmetic | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| comparison | all_pairs | 3/3 | -0.0125 [3; 72/72] | 0.0553 [3; 72/72] | 0.0553 [3; 72/72] | 0.0090 [3; 72/72] |
| comparison | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| negation | all_pairs | 3/3 | -0.0301 [3; 72/72] | 0.0349 [3; 72/72] | 0.0349 [3; 72/72] | 0.0032 [3; 72/72] |
| negation | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| syntax | all_pairs | 3/3 | -0.0389 [3; 72/72] | 0.0541 [3; 72/72] | 0.0541 [3; 72/72] | -0.0019 [3; 72/72] |
| syntax | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |

### single · span

| Task | Subset | Pairs | Semantic | Causal | Combined | Random |
|---|---|---:|---:|---:|---:|---:|
| arithmetic | all_pairs | 3/3 | -0.0288 [3; 72/72] | 0.0206 [3; 72/72] | 0.0206 [3; 72/72] | 0.0056 [3; 72/72] |
| arithmetic | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| comparison | all_pairs | 3/3 | 0.0119 [3; 72/72] | 0.0880 [3; 72/72] | 0.0880 [3; 72/72] | 0.0135 [3; 72/72] |
| comparison | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| negation | all_pairs | 3/3 | -0.0051 [3; 72/72] | 0.1912 [3; 72/72] | 0.1912 [3; 72/72] | -0.0101 [3; 72/72] |
| negation | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| syntax | all_pairs | 3/3 | 0.0129 [3; 72/72] | 0.0523 [3; 72/72] | 0.0523 [3; 72/72] | -0.0126 [3; 72/72] |
| syntax | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |

### group · answer

| Task | Subset | Pairs | Semantic | Causal | Combined | Random |
|---|---|---:|---:|---:|---:|---:|
| arithmetic | all_pairs | 3/3 | -0.0335 [3; 72/72] | 0.0274 [3; 72/72] | 0.0192 [3; 72/72] | -0.0209 [3; 72/72] |
| arithmetic | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| comparison | all_pairs | 3/3 | -0.0445 [3; 72/72] | 0.0306 [3; 72/72] | 0.0607 [3; 72/72] | -0.0271 [3; 72/72] |
| comparison | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| negation | all_pairs | 3/3 | 0.0043 [3; 72/72] | 0.0969 [3; 72/72] | 0.1082 [3; 72/72] | 0.0286 [3; 72/72] |
| negation | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| syntax | all_pairs | 3/3 | -0.0827 [3; 72/72] | 0.0224 [3; 72/72] | 0.0322 [3; 72/72] | -0.0290 [3; 72/72] |
| syntax | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |

### group · span

| Task | Subset | Pairs | Semantic | Causal | Combined | Random |
|---|---|---:|---:|---:|---:|---:|
| arithmetic | all_pairs | 3/3 | -0.0040 [3; 72/72] | 0.0330 [3; 72/72] | 0.0330 [3; 72/72] | -0.0076 [3; 72/72] |
| arithmetic | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| comparison | all_pairs | 3/3 | -0.0158 [3; 72/72] | 0.0352 [3; 72/72] | 0.0352 [3; 72/72] | -0.0108 [3; 72/72] |
| comparison | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| negation | all_pairs | 3/3 | 0.1213 [3; 72/72] | 0.1820 [3; 72/72] | 0.1820 [3; 72/72] | 0.0271 [3; 72/72] |
| negation | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |
| syntax | all_pairs | 3/3 | -0.0902 [3; 72/72] | 0.0957 [3; 72/72] | 0.0957 [3; 72/72] | -0.0095 [3; 72/72] |
| syntax | both_passed | 0/3 | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] | N/A [0; 0/0] |

## 해석 제한과 syntax 구성 타당성

기존 syntax 과제에서 능력 기준을 통과했더라도 계층적 괄호 구조를 학습했다는 뜻은 아니다. [새 hard-stress 평가](HARD_STRESS_REPORT.md)는 인접 괄호 종류 불일치 단서를 제거한 별도 동결 문항을 사용했다. [데이터 설계](../../data/followup-v2-hard-stress/README.md)와 [기존 문항의 사후 단서 분석](STRESS_ANALYSIS.md)을 함께 읽어야 한다. 높은 인과 정렬 상관은 공통 답변 편향이나 제한된 단서 처리로도 설명될 수 있다.

능력 통과 쌍이0개이면 결과는 N/A다. 이를 인과적 기능이 없다는 증거로 해석하지 않는다. 방법별 지원 셀이 다르면 평균 차이에 누락 패턴의 영향이 포함될 수 있다. 이 표를 보고 새로운 정렬 가중치·임계값·주 평가 과제를 선택하지 않는다.

## 출처와 무결성

전체 평가 요약: [summary.json](../../results/followup-v2/causal_alignment/summary.json) · SHA256 `51502e8d174995ca881bda01bfe4d7f18267ea4baa04b9a4e4df3733eecf04e9`

| Evaluation | SHA256 |
|---|---|
| [seed101_seed211/single](../../results/followup-v2/causal_alignment/seed101_seed211/single/eval.json) | `66cbb243a559bcbb869207d0f06e94966621168c9622d3a076d5f95f01ba9555` |
| [seed101_seed211/group](../../results/followup-v2/causal_alignment/seed101_seed211/group/eval.json) | `c50dfe23fef58c5443e08789a5b10976324de93dd22349869e65acd46c65195e` |
| [seed101_seed307/single](../../results/followup-v2/causal_alignment/seed101_seed307/single/eval.json) | `6a760bba659f8e3ea8d1af7c7cb927ce0cd08367b6c7a168a13694e9b25a5712` |
| [seed101_seed307/group](../../results/followup-v2/causal_alignment/seed101_seed307/group/eval.json) | `bed3fc41191712ba4cfd83abf936722f5b9bcf5218689f58d671a910e4154907` |
| [seed101_seed401/single](../../results/followup-v2/causal_alignment/seed101_seed401/single/eval.json) | `1c5c9cf2d05ea89b35a9fac9e369144c1d07406cea5dac16060a1dc120b54e64` |
| [seed101_seed401/group](../../results/followup-v2/causal_alignment/seed101_seed401/group/eval.json) | `a6080edfc917595d76b962f610f5e9f2b70c63ad30105e8a47f38b8308a3ecaf` |
| [seed101_seed503/single](../../results/followup-v2/causal_alignment/seed101_seed503/single/eval.json) | `799fcc6d87c310bb0e791ee468614b337a983b857ed8675f388fbf43934ca48c` |
| [seed101_seed503/group](../../results/followup-v2/causal_alignment/seed101_seed503/group/eval.json) | `f312458b0abe11e961a3c03cc944a367d7b3e19a9d50d1375f94bf8f9c0673b6` |
| [seed211_seed307/single](../../results/followup-v2/causal_alignment/seed211_seed307/single/eval.json) | `c06bb8a724d932109705915409b86288fec02465c4a1466b99e13141016758c1` |
| [seed211_seed307/group](../../results/followup-v2/causal_alignment/seed211_seed307/group/eval.json) | `a1ab25e233a6f477e1c9248d2cc58e59633b5ac8625cba93c11bea63b01573e4` |
| [seed211_seed401/single](../../results/followup-v2/causal_alignment/seed211_seed401/single/eval.json) | `a4c76f7a98f739e1885e68365acac04c1d58e88e9f70a41c3a7bf8c43befed0f` |
| [seed211_seed401/group](../../results/followup-v2/causal_alignment/seed211_seed401/group/eval.json) | `182b994bfdf1079785907bf92e631a8594241cf3e387c6f9db9a510cece0fad2` |
| [seed211_seed503/single](../../results/followup-v2/causal_alignment/seed211_seed503/single/eval.json) | `3e6a7ac857cdeb62ef3747f52ce95d301e3d4a9ed5ab003ff9ed4abb72df4ba3` |
| [seed211_seed503/group](../../results/followup-v2/causal_alignment/seed211_seed503/group/eval.json) | `cec1f1850fd813cc90bbab5a7dde35dea7552892ae5fcdc40ea3e28ebeea5025` |
| [seed307_seed401/single](../../results/followup-v2/causal_alignment/seed307_seed401/single/eval.json) | `fb0e5c016daf80ae773227e7d39e429da81c805aaf9141bdc1b2ca9ec07d8b66` |
| [seed307_seed401/group](../../results/followup-v2/causal_alignment/seed307_seed401/group/eval.json) | `4854de4b3ff60009bbf493eeaf7e3c30bc11851bfac6a2d7ba34424951b2bf5f` |
| [seed307_seed503/single](../../results/followup-v2/causal_alignment/seed307_seed503/single/eval.json) | `63bf17f5ba0d6868377d5782eb50b81ac2dabd4a66d8891bd3ce54c32c9066c6` |
| [seed307_seed503/group](../../results/followup-v2/causal_alignment/seed307_seed503/group/eval.json) | `9e011f1da8540b410b6e215ab81718fbccba1a836577831f0a38c7ec8bfb85ec` |
| [seed401_seed503/single](../../results/followup-v2/causal_alignment/seed401_seed503/single/eval.json) | `5602ebda4ea4175e4992057ae5ac86e5225ba4502b4d123648b4ff1a3eeed8bb` |
| [seed401_seed503/group](../../results/followup-v2/causal_alignment/seed401_seed503/group/eval.json) | `f59e078e31991c5320868d0f43079bccf2733f531f2cc2249d83790e431d93f6` |
| [qwen_smol/single](../../results/followup-v2/causal_alignment/qwen_smol/single/eval.json) | `6e0a0de21bcfd793d172d734ecc93df5c35a62b99ee9d361404a1b513fcbeff5` |
| [qwen_smol/group](../../results/followup-v2/causal_alignment/qwen_smol/group/eval.json) | `ec0caf239d4bdd3cb1ca50039257daa6e2781970d79b4128d69235c3e5c1df41` |
| [qwen_olmo/single](../../results/followup-v2/causal_alignment/qwen_olmo/single/eval.json) | `53db434d1d97ae89631ae84f5ba911641ec5a018cb8025ea94f12792ec92df06` |
| [qwen_olmo/group](../../results/followup-v2/causal_alignment/qwen_olmo/group/eval.json) | `1a64cf53c05e76e3268a98905899f9de5a8b6c974d1a0d90eeb9f3095be52201` |
| [smol_olmo/single](../../results/followup-v2/causal_alignment/smol_olmo/single/eval.json) | `82784fd68f9cd2bcc0e5130f965b33d36a48da4a788ced44a559ad29b540a144` |
| [smol_olmo/group](../../results/followup-v2/causal_alignment/smol_olmo/group/eval.json) | `4d1f92320e21f7c6cd416dd6ccb3d92519d7eb2e49fd9d7ccb11a276f78fd04a` |
