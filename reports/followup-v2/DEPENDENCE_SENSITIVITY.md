# followup-v2: 의존성에 대한 다중검정 민감도 분석

이 분석은 **사후 보충 민감도 분석**이다. 사전 정의된 110개 가설·원래 p-value·주 분석 BH 결과를 변경하지 않았다. 모델 실행, 정렬 재학습, 추가 가설 검정은 하지 않았다.

원래 110개 가설 중 유효한 p-value는 110개, 정의되지 않은 p-value는 0개다. 정의되지 않은 항목은 다중검정 계산 안에서만 p=1 자리로 유지하고 공개 p/q는 `null`로 남겼다.

| 보정 | q < 0.05 기각 수 | 역할 |
|---|---:|---|
| BH | 58 | 기존 주 분석의 독립 재계산 |
| BY | 43 | 임의 의존성에 대한 사후 민감도 |

SciPy로 재계산한 BH는 원래 값과 일치했다(최대 절대 차이 1.11e-16). BY는 같은 110개 p-value에 조화합 계수 5.28223460를 적용한다.

## 기각된 가설 ID

### BH와 BY 모두에서 기각

- `F3/qwen_smol/answer/semantic_minus_activation`
- `F3/seed101_seed211/answer/activation_minus_random`
- `F3/seed101_seed211/span/activation_minus_random`
- `F3/seed101_seed211/span/semantic_minus_activation`
- `F3/seed101_seed307/answer/activation_minus_random`
- `F3/seed101_seed307/span/activation_minus_random`
- `F3/seed101_seed307/span/semantic_minus_activation`
- `F3/seed101_seed401/answer/activation_minus_random`
- `F3/seed101_seed401/span/activation_minus_random`
- `F3/seed101_seed503/answer/activation_minus_random`
- `F3/seed101_seed503/span/activation_minus_random`
- `F3/seed211_seed307/answer/activation_minus_random`
- `F3/seed211_seed307/span/activation_minus_random`
- `F3/seed211_seed401/answer/activation_minus_random`
- `F3/seed211_seed401/span/activation_minus_random`
- `F3/seed211_seed503/answer/activation_minus_random`
- `F3/seed211_seed503/span/activation_minus_random`
- `F3/seed307_seed401/answer/activation_minus_random`
- `F3/seed307_seed401/span/activation_minus_random`
- `F3/seed307_seed503/answer/activation_minus_random`
- `F3/seed307_seed503/span/activation_minus_random`
- `F3/seed307_seed503/span/semantic_minus_activation`
- `F3/seed401_seed503/answer/activation_minus_random`
- `F3/seed401_seed503/span/activation_minus_random`
- `F3/smol_olmo/span/activation_minus_random`
- `F3/smol_olmo/span/semantic_minus_activation`
- `F4/qwen_olmo/span/single/combined_minus_semantic`
- `F4/qwen_smol/span/group/combined_minus_semantic`
- `F4/qwen_smol/span/single/combined_minus_semantic`
- `F4/seed101_seed211/answer/group/combined_minus_semantic`
- `F4/seed101_seed211/answer/single/combined_minus_semantic`
- `F4/seed101_seed307/answer/group/combined_minus_semantic`
- `F4/seed101_seed307/answer/single/combined_minus_semantic`
- `F4/seed101_seed503/answer/single/combined_minus_semantic`
- `F4/seed211_seed307/answer/single/combined_minus_semantic`
- `F4/seed211_seed401/answer/group/combined_minus_semantic`
- `F4/seed211_seed503/answer/single/combined_minus_semantic`
- `F4/seed307_seed401/answer/group/combined_minus_semantic`
- `F4/seed307_seed401/answer/single/combined_minus_semantic`
- `F4/seed307_seed503/answer/single/combined_minus_semantic`
- `F4/smol_olmo/answer/group/combined_minus_semantic`
- `F4/smol_olmo/span/group/combined_minus_semantic`
- `F4/smol_olmo/span/single/combined_minus_semantic`

### BH에서만 기각

- `F3/qwen_olmo/answer/semantic_minus_activation`
- `F3/qwen_olmo/span/activation_minus_random`
- `F3/qwen_smol/answer/activation_minus_random`
- `F3/seed101_seed211/answer/semantic_minus_activation`
- `F3/seed211_seed401/span/semantic_minus_activation`
- `F3/seed211_seed503/span/semantic_minus_activation`
- `F3/seed307_seed401/answer/semantic_minus_activation`
- `F3/seed307_seed401/span/semantic_minus_activation`
- `F4/qwen_olmo/answer/single/combined_minus_semantic`
- `F4/qwen_olmo/span/group/combined_minus_semantic`
- `F4/qwen_smol/answer/single/combined_minus_semantic`
- `F4/seed101_seed401/answer/single/combined_minus_semantic`
- `F4/seed101_seed401/span/single/combined_minus_semantic`
- `F4/seed401_seed503/span/single/combined_minus_semantic`
- `F4/smol_olmo/answer/single/combined_minus_semantic`

## 해석의 제한

공유 모델과 출력 때문에 검정들이 서로 의존한다. BH는 독립성 또는 적절한 양의 의존성이 필요하며, BY는 유효한 p-value 사이의 임의 의존성을 허용하는 더 보수적인 보정이다. [SciPy 공식 문서](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html)

그러나 개별 p-value의 타당성과 wrapper sign-flip의 교환가능성·대칭성 가정은 여전히 필요하다. BY는 잘못된 p-value, 유사 반복의 독립 표본 처리, 적은 학습 seed 수, 낮은 과제 능력, 측정 개념의 부적절성이나 결과를 본 뒤의 설계 변경을 고치지 않는다. 두 보정에서 기각되더라도 인과적·의미적 보존의 모든 전제 조건이 충족된다는 뜻은 아니다.

## 추적 정보

- [원래 110개 검정](../../results/followup-v2/statistics/global_tests.json)
- [전체 BH/BY 값과 가설 ID](../../results/followup-v2/statistics/dependence_sensitivity.json)
- 원본 SHA256: `3a2ecbacb6752c74f15faf7019f25e37d2dc1045480d8bb350fc71c434fb1009`
- SciPy 버전: `1.18.1`
