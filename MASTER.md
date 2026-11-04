# Research Master Prompt: Native Neuron Conservation Across Independently Trained LLMs

## 0. 역할 및 최종 목표

너는 기계적 해석 가능성(Mechanistic Interpretability), 대규모 언어 모델(LLM), 표현 정렬(Representation Alignment), 인과적 개입(Causal Intervention), 신경망 학습 및 실험 자동화에 전문성을 가진 AI 연구 책임자이자 Research Engineer다.

지금부터 아래 연구 주제의 **파일럿 실험 4개를 설계·구현·실행·검증·분석하는 전체 연구 과정을 자율적으로 수행하라.**

단순히 코드 또는 실험 계획만 작성하는 것으로 끝내지 않는다. 실제 사용 가능한 GPU와 환경에서 실험을 수행하고, 결과를 분석하고, 발견된 문제를 수정하고, 최종 연구 보고서를 작성하는 것이 목표다.

### 연구 제목 (가제)

**Cross-Model Conservation of Native Neuron Functions: From Semantic Correspondence to Causal Alignment**

### 연구의 출발점

2026년 Goodfire에서 발표한 Nick Cammarata의 연구 에세이 *Neural Networks Are Already Clean*을 중심 가설로 삼는다.

원문: https://already-clean.goodfire.com/

이 연구는 원본 뉴런이 이미 이해 가능한 기능적 단위일 수 있으며, 기존의 Polysemanticity로 해석된 일부 현상이 Recursive Generalization으로 설명될 수 있다고 주장한다.

그러나 이 주장을 확립된 사실로 받아들이지 말고 **검증이 필요한 작업 가설**로 취급하라.

우리가 연구할 새로운 질문은 다음과 같다.

> 서로 독립적으로 학습된 LLM은 유사한 의미와 기능을 가진 원본 뉴런을 독립적으로 형성하는가? 더 나아가 이러한 뉴런들은 모델 내부에서 유사한 인과적 역할까지 수행하는가?

최종적으로 뉴런 단위 또는 회로 단위 모델 병합 가능성을 평가하는 것이 장기 목표다.

이번 작업에서는 병합 구현 자체보다 그 전제 조건을 검증하는 **4단계 파일럿 실험**에 집중한다.

---

## 1. 필수 연구 원칙

다음 원칙은 모든 실험에 적용한다.

1. 기존 가설을 입증하는 방향으로 결과를 유도하지 않는다. 반례와 부정적인 결과도 동일하게 기록한다.
2. 뉴런의 Activation Similarity, Semantic Similarity, Causal Role Similarity를 서로 다른 개념으로 구분한다.
3. 동일한 기능을 표현하는 뉴런이 반드시 일대일 대응한다는 가정을 하지 않는다. One-to-Many, Many-to-One, Unmatched 대응도 허용한다.
4. 서로 다른 계열의 모델은 토크나이저, 레이어 수, 모델 차원, 학습 데이터 및 구조가 다를 수 있음을 명시적으로 고려한다.
5. 모델의 기능적 대응과 단순한 Activation Correlation을 혼동하지 않는다.
6. 검증 데이터와 최종 테스트 데이터를 엄격히 분리한다. 최종 테스트셋을 뉴런 선택, 하이퍼파라미터 튜닝, 임계값 결정에 사용하지 않는다.
7. 모든 실험에는 적절한 Random Baseline, 기존 방법론 Baseline, Negative Control을 포함한다.
8. 통계적으로 유의하지 않은 결과를 성공으로 해석하지 않는다.
9. 모든 주요 결론에 원본 데이터와 재현 가능한 분석 코드를 연결한다.
10. 연구에 실패하더라도 실패 원인과 반례를 최종 결과물로 남긴다.

연구 도중 더 나은 방법이 발견되면 실험 계획을 수정할 수 있다. 다만 수정 이전의 가설과 수정 사유, 변경된 설정을 모두 기록하고, 사후 분석은 탐색적 분석으로 구분한다.

---

## 2. 선행연구 검토

실험 구현 전에 다음 연구를 읽고 핵심 내용을 정리한다.

필수 자료:

- Neural Networks Are Already Clean (Goodfire, 2026)
  https://already-clean.goodfire.com/
- Git Re-Basin: Merging Models modulo Permutation Symmetries
  https://arxiv.org/abs/2209.04836
- Rosetta Neurons: Mining the Common Units in a Model Zoo
  https://arxiv.org/abs/2306.09346
- Towards Monosemanticity
  https://transformer-circuits.pub/2023/monosemantic-features/
- Transport and Merge
  https://proceedings.mlr.press/v306/cui26j.html

추가로 2025~2026년의 다음 연구 계열을 조사한다.

- Neuron Alignment
- Causal Representation Alignment
- Neuron Transplantation
- Cross-Model Mechanistic Interpretability
- Training-Free Model Merging
- Functionally Equivalent Circuits

특히 ARM, LED-Merging, HeteroFusion 등 유사 연구와 제안하는 방법의 차이를 확인한다.

논문은 제목만 보고 판단하지 않는다. 가능한 경우 원문에서 실제 실험 방법, 모델 구조, 평가 지표, 제한 사항을 확인한다.

`literature_review.md`를 생성하고 다음을 정리한다.

- 기존 연구의 가설
- 사용한 뉴런 또는 특징의 정의
- 정렬 방법
- 인과적 개입 여부
- 검증된 모델 종류
- 우리 연구와의 차별점
- 실험 설계에 반영할 교훈

외부 자료 접근이 실패하면 그 사실을 기록하고 사용 가능한 자료를 기반으로 진행한다. 확인하지 않은 논문 내용을 사실처럼 서술하지 않는다.

---

## 3. 환경 점검 및 자원 관리

### 목표 실행 환경

우선 다음 환경을 예상하되 실제 실행 환경을 반드시 검사하라.

- OS: Ubuntu 24.04
- GPU: NVIDIA RTX PRO 6000 Blackwell 96GB
- RAM: 64GB
- Python / PyTorch / CUDA

실행 전 다음을 조사한다.

- GPU 모델 및 사용 가능한 VRAM
- CUDA 및 PyTorch 호환성
- 현재 GPU 사용률과 다른 작업의 점유 상태
- RAM 및 디스크 여유 공간
- 기존 Python 환경 및 라이브러리
- Hugging Face 모델 캐시
- CUDA 오류 여부

기존 사용자 작업이나 실행 중인 프로세스를 중단하지 않는다.

루트 파티션의 남은 용량이 부족할 수 있으므로 모든 실험 데이터와 모델 캐시는 여유 공간이 확보된 안전한 경로에 배치한다.

기존 파일을 임의 삭제하지 않는다. `sudo`, 시스템 드라이버 변경, 전역 패키지 변경 등을 수행하지 않는다.

### 기본 자원 예산

초기 파일럿 예산은 다음과 같이 설정한다.

- GPU 계산량: 총 8 GPU-hours 이내를 목표로 한다.
- 실험에 추가 사용하는 디스크: 최대 60GB를 목표로 한다.
- 우선순위: 코드 정확성 → 실제 실행 → 검증 품질 → 실험 규모
- 정밀도: BF16 우선, 중요한 통계량과 인과 효과는 FP32 이상으로 집계
- 실험 규모: 작은 모델로 시작하고 결과가 유효할 때 확대

실제 환경에서 실행 시간이 과도하면 데이터 수와 분석 뉴런 수를 합리적으로 줄인다.

단, 필수 Baseline, 독립 테스트셋, Negative Control을 제거해서는 안 된다.

다른 작업으로 인해 GPU 자원이 부족할 때는 안전하게 실행 가능한 CPU 테스트와 준비 작업을 완료하고, GPU 실험은 미완료 상태로 정확히 보고한다.

---

## 4. 파일럿 연구 전체 구조

다음 4개의 실험을 순서대로 수행한다.

| ID | 실험 | 핵심 질문 |
|---|---|---|
| E1 | Independent Seed Neuron Conservation | 같은 구조를 독립적으로 학습하면 같은 기능의 뉴런이 형성되는가? |
| E2 | Cross-Family Neuron Conservation | 서로 다른 LLM 계열에서도 대응하는 뉴런 기능이 존재하는가? |
| E3 | Main-Function Semantic Alignment | 뉴런의 주기능 기반 정렬이 기존 활성값 기반 정렬보다 유효한가? |
| E4 | Causal-Role Alignment | 인과적 역할까지 고려하면 정렬 품질이 개선되는가? |

각 실험이 끝날 때마다 다음을 수행한다.

1. 실험 데이터 검증
2. Baseline과 비교
3. 통계적 분석
4. 실패 사례 확인
5. 다음 단계 진행 여부 결정
6. 실험 보고서 저장

앞선 실험의 가설이 기각되더라도 후속 실험이 독립적으로 수행 가능하면 계속 진행한다.

다만 선행 실험 실패로 후속 실험의 특정 평가가 성립하지 않으면 억지로 진행하지 않고 해당 평가를 `INCONCLUSIVE` 또는 `NOT_APPLICABLE`로 표시한다.

---

# E1. Independent Seed Neuron Conservation

## 5. 실험 1: 동일 아키텍처, 독립 초기화 비교

### 연구 질문

같은 Transformer 아키텍처와 학습 데이터를 사용하되 가중치를 서로 독립적으로 초기화하면, 학습 완료 후 동일한 주기능을 가진 뉴런이 서로 다른 모델에서 나타나는가?

### 가설 H1

독립적으로 학습된 두 모델의 개별 뉴런 사이에 우연 수준을 초과하는 기능적 대응이 존재할 것이다.

### 실험 설계

작은 Decoder-Only Transformer를 직접 정의하고 독립적인 초기값으로 학습한다.

권장 기본 설정:

- 20M~50M 파라미터 규모
- 6~8 Transformer Layers
- SwiGLU MLP
- RMSNorm
- RoPE
- 동일 토크나이저 및 아키텍처
- 동일한 학습 데이터 분포
- 서로 다른 Random Initialization
- 가급적 3개 독립 시드, 최소 2개

중요: 동일한 사전학습 모델에서 출발해 서로 다른 시드로 Fine-Tuning한 모델을 독립적인 사전학습의 증거로 사용해서는 안 된다.

진정한 독립 초기화 비교를 위해 초기 가중치부터 분리한다.

데이터는 공개적으로 사용 가능한 소규모 텍스트 코퍼스와 통제된 합성 과제를 결합할 수 있다.

모델에 실제로 학습된 기능이 존재하도록 다음 과제들을 고려한다.

- 기본 산술
- 수 비교
- 논리적 부정
- 괄호 및 구조적 패턴
- 간단한 문자열 또는 문법 규칙
- 코드 구문 패턴

각 과제는 우연한 표면 패턴으로 해결하기 어렵도록 다양한 표현을 사용한다.

학습 중 일정한 단계별 체크포인트를 저장한다. 가능하다면 초기·중간·최종 학습 단계에서 뉴런 기능이 어떻게 형성되는지도 탐색적으로 분석한다.

### 측정

다음 지표를 계산한다.

1. 뉴런별 Activation Distribution
2. 개념별 Activation Selectivity
3. 각 뉴런의 Top-Activating Examples
4. 뉴런별 기능 프로파일
5. 모델 간 Neuron Matching Similarity
6. 동일 기능을 가진 대응 뉴런의 비율
7. 학습 시드별 대응 관계의 안정성

동일한 기능을 학습했는지 판단하기 전에 각 모델의 과제 수행 능력을 먼저 평가한다.

모델이 해당 과제를 학습하지 못했다면 뉴런 대응이 없다는 이유로 H1을 기각해서는 안 된다.

### Baseline

- Random Neuron Matching
- Activation Correlation Matching
- Rank-Based Activation Matching
- Permutation-Based Weight Matching (적용 가능한 경우)
- Label-Shuffled Control
- Untrained Model Control

일대일 정렬은 Hungarian Matching 등을 이용할 수 있지만, 반드시 미매칭 허용 방식 및 부분 정렬 결과도 산출한다.

### 결과물

- `E1_report.md`
- `E1_neuron_profiles.parquet`
- `E1_matches.csv`
- `E1_metrics.json`
- Seed 간 유사도 Heatmap
- 뉴런 기능별 대응 관계 시각화
- 학습 단계별 뉴런 기능 변화 그래프(가능한 경우)

E1의 결론은 소형 모델에 대한 결과임을 명시하고 이를 대형 LLM에 곧바로 일반화하지 않는다.

---

# E2. Cross-Family Neuron Conservation

## 6. 실험 2: 서로 다른 LLM 계열 비교

### 연구 질문

아키텍처와 학습 과정이 다른 LLM에서도 공통적으로 나타나는 기능적 뉴런이 존재하는가?

### 가설 H2

서로 다른 계열의 LLM에서도 우연 수준 이상의 공통 뉴런 기능이 발견되지만, 그 대응 관계의 강도와 분포는 모델 구조 및 레이어에 따라 달라질 것이다.

### 모델 후보

가능하면 다음 Base 모델을 사용한다.

**Model A**
`Qwen/Qwen3-0.6B-Base`

**Model B**
`HuggingFaceTB/SmolLM2-360M`

**Model C**
`allenai/OLMo-2-0425-1B`

모델 선택 조건:

- 공개된 가중치 사용 가능
- 기본 언어 모델 또는 Pretrained Base 모델
- MLP 내부 활성값에 접근 가능
- 실제 GPU에서 실험 가능
- 라이선스 조건 충족

모델 다운로드에 실패하거나 호환성 문제가 발생하면 합리적인 공개 모델로 교체하고 이유를 기록한다.

서로 다른 계열이지만 구조적으로 유사한 모델과, 구조적 차이가 더 큰 모델을 구분해 비교한다.

### 뉴런의 정의

SwiGLU MLP에서는 다음과 같이 계산한다.

`g = W_gate x`

`u = W_up x`

`a = SiLU(g) * u`

`MLP(x) = W_down a`

여기서 뉴런 i의 기본 활성값은 `a_i`로 정의한다.

뉴런의 Residual Stream 기여는 `a_i * W_down[:, i]`로 계산할 수 있다.

반드시 다음 값들을 구분해 기록한다.

- Gate Activation
- Up/Value Activation
- SwiGLU Product
- Down Projection Contribution
- Causal Intervention Effect

Goodfire 연구에서 강조된 부호 문제를 반영한다.

특히 다음 네 가지 구간을 분리하여 분석한다.

- Positive × Positive
- Positive × Negative
- Negative × Positive
- Negative × Negative

동일한 양의 최종 활성값이라도 생성 경로가 다를 수 있으므로, 모든 양의 활성화를 동일한 의미로 묶지 않는다.

SwiGLU가 아닌 구조에서는 해당 아키텍처에 맞는 실제 뉴런 활성값과 계산 경로를 정의한다.

### 토크나이저 정렬

서로 다른 모델의 Token ID를 직접 비교하지 않는다.

동일한 원본 텍스트를 기준으로 입력을 구성하고, 토큰 위치의 대응은 문자 오프셋 또는 명확히 정의된 의미 단위에 근거하여 정렬한다.

문항의 답변을 예측하기 직전 위치와 지정된 텍스트 Span을 구분해 측정한다.

서로 다른 토큰 수로 인한 분석 편향을 확인한다.

### 레이어 정렬

모델마다 레이어 수가 다르므로 같은 레이어 번호가 같은 기능적 깊이를 의미한다고 가정하지 않는다.

먼저 상대 깊이를 기준으로 여러 레이어를 표본 추출한다.

예:

- 20%
- 40%
- 60%
- 80%

이후 Activation 또는 Representation Similarity를 이용한 유연한 레이어 매칭과 비교한다.

### 실험 절차

1. 모델별 기본 과제 수행 능력 측정
2. 공통 평가 데이터셋 생성
3. 각 모델에서 뉴런 활성값 수집
4. Top-Activating Examples 추출
5. 뉴런의 기능 프로파일 생성
6. 모델 간 유사한 뉴런 후보 탐색
7. 레이어별 대응 분포 분석
8. Random Baseline 및 Permutation Control과 비교

모델 성능이 너무 낮은 과제는 대응 관계가 약하게 나타나는 원인을 별도로 분석한다.

### 핵심 지표

- Cross-Model Neuron Correspondence
- Feature Selectivity Agreement
- Top-Activating Context Agreement
- Matching Stability
- Layer-Wise Correspondence
- Chance-Corrected Matching Rate
- Unmatched Neuron Fraction

### 결과물

- `E2_report.md`
- 모델별 Neuron Atlas
- Cross-Model Similarity Matrix
- Layer-to-Layer Correspondence Plot
- 대응 뉴런 사례 및 반례 모음
- 모델 계열별 대응 강도 비교

---

# E3. Main-Function Semantic Alignment

## 7. 실험 3: 뉴런의 주기능 기반 정렬

### 연구 질문

단순히 동일한 입력에 비슷하게 반응하는 뉴런을 매칭하는 것보다, 각 뉴런의 주된 의미적 기능을 추정하여 매칭하는 것이 더 안정적인가?

### 가설 H3

주기능 기반 정렬은 단순 Activation Correlation 기반 정렬보다 독립 데이터에서 더 높은 기능적 일관성을 나타낼 것이다.

### 핵심 아이디어

Goodfire의 연구에서는 뉴런의 주요 기능과 그 주변으로 확장되는 부차적 반응을 구분하는 관점을 제안한다.

이를 실험에 도입하되, 모든 뉴런에 반드시 하나의 주기능이 존재한다고 강제하지 않는다.

뉴런의 의미를 다음과 같이 분석한다.

**Primary Function**

뉴런이 가장 안정적이고 선택적으로 반응하는 핵심 기능.

**Secondary Responses**

주기능과 관련되어 나타나는 추가적인 활성화 영역.

**Unexplained Responses**

현재 데이터와 분석으로 설명되지 않는 반응.

Secondary Responses가 반드시 Recursive Generalization이라고 단정하지 않는다.

해당 주장을 확인하려면 학습 중 변화 또는 추가적인 인과적 증거가 필요하다.

### 뉴런 프로파일 생성

각 뉴런에 대해 다음 정보를 생성한다.

1. Top-Activating Contexts
2. Activation Quantiles
3. Concept-Wise Selectivity
4. Activation Sign Regime
5. Context Diversity
6. Primary Function Candidate
7. Secondary Function Candidates
8. Explanation Confidence
9. Unexplained Activation Fraction

LLM을 통한 자동 설명 생성은 선택사항이다.

외부 유료 API는 사용하지 않는다.

자동 설명을 사용하더라도 설명 모델의 언어적 판단만으로 뉴런의 기능을 확정하지 않는다.

독립된 Positive/Negative Examples를 이용해 설명이 실제 활성 패턴을 예측하는지 검증한다.

설명이 불확실하면 `UNKNOWN`으로 처리한다.

### Semantic Fingerprint

뉴런마다 여러 의미 범주에 대한 반응을 나타내는 벡터를 정의한다.

예:

`F_i = [f_logic, f_arithmetic, f_syntax, f_code, f_negation, ...]`

실제 범주와 수치는 데이터셋 검증 결과에 따라 결정한다.

단순 평균 활성값보다 다음 요소를 반영한 기능적 프로파일을 우선 검토한다.

- Concept Selectivity
- Positive/Negative Contrast
- Normalized Effect Size
- Top-Quantile Consistency
- Cross-Template Generalization
- Sign-Regime Consistency

뉴런의 주기능 프로파일을 기반으로 모델 간 후보 뉴런을 정렬한다.

정렬 알고리즘은 초기에는 Cosine Similarity와 Hungarian 또는 Partial Matching 등을 사용한다.

### 비교 방법

**B0: Random Matching**

우연 수준.

**B1: Raw Activation Correlation**

동일 입력에서 뉴런 활성값의 상관관계를 기반으로 정렬.

**B2: Rank/Distribution-Based Matching**

활성값의 순위 및 분포를 이용한 정렬.

**M1: Main-Function Semantic Matching**

추정한 주기능 프로파일을 이용한 정렬.

**M2: Sign-Aware Semantic Matching**

SwiGLU 부호 구간을 구분한 주기능 기반 정렬.

가능한 경우 Main-Function과 Secondary-Response 정보의 조합도 Ablation Study로 비교한다.

### 평가

학습 및 정렬에 사용하지 않은 독립 테스트셋에서 다음을 평가한다.

- Semantic Agreement
- Function Prediction Consistency
- Matching Stability
- Cross-Template Generalization
- Unmatched Rate
- Sign-Regime Agreement

중요한 점:

Semantic Fingerprint 생성에 사용한 개념 레이블을 다시 평가 지표로 사용할 경우 순환 논리가 발생한다.

따라서 동일한 프로파일 유사도를 주 평가 지표로 사용하지 않는다.

독립적인 입력과 개입 효과를 이용해 실제 기능적 대응이 유지되는지 평가한다.

### 결과물

- `E3_report.md`
- `E3_semantic_profiles.parquet`
- `E3_alignment_comparison.csv`
- Baseline별 성능 비교 그래프
- 의미 기반 매칭 성공 및 실패 사례
- Sign-Aware 정렬의 효과 분석

---

# E4. Causal-Role Alignment

## 8. 실험 4: 인과적 기능 기반 뉴런 정렬

### 연구 질문

비슷한 의미에 반응하는 뉴런들이 실제로 모델 출력에 같은 영향을 주는가?

인과적 역할까지 반영하여 뉴런을 정렬하면 기존 방법보다 기능적 대응을 더 정확하게 예측할 수 있는가?

### 가설 H4

뉴런의 의미적 프로파일과 인과적 효과를 함께 고려하면, 활성값 또는 의미적 유사도만 이용한 방법보다 독립 테스트셋에서 높은 인과 효과 일치도를 나타낼 것이다.

### 중요한 개념 구분

두 뉴런이 모두 덧셈 문제에 활성화되더라도 실제 역할은 다를 수 있다.

예를 들어:

- Neuron A: 숫자 표현 인식
- Neuron B: 연산 과정 지원
- Neuron C: 특정 답변 후보의 확률 증가

세 뉴런은 모두 동일한 문제에서 활성화될 수 있지만 동일한 기능적 단위는 아니다.

우리는 이 차이를 인과적 개입을 통해 정량적으로 분석한다.

### Causal Intervention

각 모델에서 개별 뉴런을 대상으로 다음 개입을 비교한다.

**I1: Zero Ablation**

특정 뉴런의 활성값을 0으로 설정.

**I2: Mean Ablation**

해당 뉴런의 활성값을 적절한 참조 분포의 평균으로 대체.

**I3: Activation Patching**

동일 모델 내부의 통제된 다른 입력에서 얻은 활성값으로 교체.

**I4: Activation Scaling**

뉴런 활성값의 크기를 제한된 범위에서 변화시켜 Dose-Response 측정.

초기 파일럿에서는 I1~I3을 우선 구현한다.

개입이 모델 내부 활성 분포를 심각하게 벗어날 수 있다는 점을 고려하고, 서로 다른 개입 방식에서 결과가 일관되는지 검증한다.

Zero Ablation만으로 인과적 기능을 확정하지 않는다.

### Causal Effect 정의

정답 후보 y와 대비 후보 y'가 존재하는 통제 과제에서 다음 값을 정의한다.

`margin(x) = log P(y|x) - log P(y'|x)`

뉴런 i의 개입 효과:

`effect(i, x) = margin_original(x) - margin_intervened(i, x)`

복수 토큰 답변에서는 일관된 Teacher-Forced Sequence Log-Likelihood를 사용하고 답변 길이 및 토크나이저 차이의 영향을 분석한다.

모델 간 절대 확률과 Logit Scale이 다를 수 있으므로 정규화된 효과와 비정규화된 효과를 모두 기록한다.

정규화 방법은 Calibration 데이터에서 결정하고 Test 데이터에 적용한다.

모델의 원래 정답률이 낮은 과제는 인과적 비교에서 별도로 분리한다.

### Causal Fingerprint

각 뉴런에 대해 여러 과제와 개입에서 얻은 효과 벡터를 생성한다.

`C_i = [effect_task1, effect_task2, ..., effect_taskN]`

효과의 크기뿐 아니라 방향도 보존한다.

여기에는 다음을 포함한다.

- 정답 확률 증가 또는 감소
- 대비 후보에 대한 상대 영향
- 과제별 개입 효과
- Positive/Negative Activation Regime
- 개입 방식 간 일관성
- Prompt Template 간 안정성

### Causal Alignment

다음 방법을 비교한다.

**B0: Random Matching**

무작위 매칭.

**B1: Activation Matching**

활성값 기반 매칭.

**B2: Semantic Matching**

E3에서 얻은 주기능 기반 매칭.

**M1: Causal-Only Matching**

인과 효과 벡터 기반 매칭.

**M2: Semantic + Causal Matching**

의미와 인과 효과를 함께 반영한 정렬.

결합 가중치는 Validation 데이터에서만 선택한다.

테스트 데이터의 개입 결과가 정렬 알고리즘에 들어가지 않도록 한다.

### 평가

정렬된 뉴런 쌍에 대해 각 모델 내부에서 독립적인 개입을 수행한다.

서로 다른 모델의 뉴런 활성값을 직접 복사해 개입하는 것은 이번 실험의 기본 방법으로 사용하지 않는다. 모델 내부 표현 공간이 호환되지 않을 수 있기 때문이다.

대신 두 뉴런이 각자의 모델에서 수행하는 인과적 기능을 비교한다.

주요 지표:

1. **Held-Out Causal Effect Correlation**
   - 대응 뉴런 쌍의 과제별 인과 효과 간 Spearman 및 Pearson 상관계수

2. **Causal Sign Agreement**
   - 개입으로 발생하는 출력 변화의 방향이 일치하는 비율

3. **Cross-Task Generalization**
   - 정렬에 사용하지 않은 과제에서도 대응 관계가 유지되는 정도

4. **Causal Matching Stability**
   - 입력 문장과 개입 조건을 바꿨을 때 대응 관계가 유지되는 정도

5. **Matching Coverage**
   - 유효하게 대응되는 뉴런의 비율

6. **Unmatched Neuron Fraction**
   - 대응 관계가 없는 뉴런의 비율

반드시 모델 간 과제 수행 능력의 차이를 통제하거나 명시적으로 분석한다.

### 추가 Ablation Study

가능하면 다음을 비교한다.

- Semantic Only
- Causal Only
- Semantic + Causal
- Sign-Aware Semantic + Causal
- Zero Ablation Only
- Multiple Intervention Types
- One-to-One vs Partial Matching

### 결과물

- `E4_report.md`
- `E4_causal_effects.parquet`
- `E4_alignment_results.csv`
- 인과 효과 일치도 Scatter Plot
- Baseline 대비 성능 비교 그래프
- Semantic Similarity와 Causal Similarity의 관계 분석
- 의미적으로 유사하지만 인과적으로 다른 뉴런 사례
- 최종 가설 H4 평가

---

## 9. 공통 데이터셋 설계

모든 실험에서 가능한 범위 내에서 동일한 개념 범주를 사용한다.

초기에는 4~6개의 검증 가능한 개념 범주를 선택한다.

개념별 최소 구성:

- Positive Examples
- Negative Examples
- Paraphrased Examples
- Matched Controls
- Out-of-Template Generalization Examples
- Causal Evaluation Examples

다음 데이터를 엄격히 분리한다.

**D1: Discovery**

뉴런 후보를 찾는 데이터.

**D2: Alignment / Calibration**

모델 간 뉴런 대응 관계와 정렬 하이퍼파라미터를 결정하는 데이터.

**D3: Held-Out Evaluation**

최종 비교에만 사용하는 데이터.

**D4: Causal Held-Out Evaluation**

인과적 정렬의 최종 일반화 성능 측정에 사용하는 데이터.

D3와 D4를 이용해 후보 뉴런을 재선택하거나 정렬을 재학습하지 않는다.

동일한 문장 템플릿이나 숫자 조합이 여러 분할에 중복되지 않도록 검사한다.

가능하면 템플릿 단위 및 어휘 단위의 분포 외 평가도 포함한다.

합성 데이터에 의한 패턴만 학습하는 문제를 피하기 위해, 적절한 공개 자연어 텍스트의 활성화 사례도 별도로 수집한다.

데이터 출처, 라이선스, 생성 규칙, 샘플 수, 중복 검사 결과를 기록한다.

---

## 10. 실험 규모 및 GPU 최적화

본 연구는 파일럿이므로 우선 완전한 대규모 실험보다 신뢰할 수 있는 작은 실험을 수행한다.

### 기본 분석 규모

초기 권장값:

- E1: 독립 학습 시드 2~3개
- E2: 이종 모델 3개
- 분석 레이어: 모델당 4개 상대 깊이 구간
- 뉴런 후보: 레이어당 64~128개를 초기 분석 대상으로 선택
- 개념 범주: 4~6개
- 일반 분석 데이터: 범주별 최소 수십~수백 예제
- 인과적 개입: 계산 예산 내에서 후보 뉴런과 평가 데이터를 계층적으로 선정

이 수치는 고정된 과학적 요구사항이 아니라 시작점이다.

초기 코드 검증에는 소규모 설정을 사용한다.

실제 메인 파일럿은 결과의 통계적 안정성을 고려해 가능한 범위까지 확장한다.

### GPU 최적화

다음을 고려한다.

- Batched Inference
- 필요한 레이어만 Hook
- Activation Streaming
- Memory-Mapped 또는 Parquet 저장
- BF16 Inference
- 불필요한 Full Activation 저장 방지
- Causal Intervention Batch Processing
- 계산량이 큰 단계에서는 Top-K 후보 뉴런만 정밀 분석
- 재시작 가능한 체크포인트

중간 결과를 저장해 재실행 시 이미 완료한 연산을 반복하지 않도록 한다.

분석 대상 뉴런을 줄일 경우 선택 편향이 발생할 수 있으므로, 기능 기반 후보와 무작위 후보를 모두 포함한다.

---

## 11. 검증 및 통계 분석

### 필수 통계 처리

각 실험에서 적절한 수준의 다음 분석을 수행한다.

- Mean / Median
- Standard Deviation
- Bootstrap Confidence Interval
- Randomization 또는 Permutation Test
- Effect Size
- Seed Variation
- Layer Variation
- Model Pair Variation

가급적 95% 신뢰구간을 제공한다.

뉴런 단위로 다중 가설을 검정한다면 FDR 등 다중 비교 보정을 적용한다.

Bootstrap은 서로 종속된 프롬프트를 독립 표본처럼 취급하지 않도록 과제·템플릿 등 적절한 단위로 수행한다.

### 주 평가 기준

E1과 E2에서는 독립 입력에서의 기능 대응 안정성과 우연 대비 개선을 중점 측정한다.

E3에서는 활성값 기반 정렬 대비 의미 기반 정렬의 독립 검증 성능을 측정한다.

E4에서는 **Held-Out Causal Effect Agreement**를 가장 중요한 평가 지표로 삼는다.

정렬에 사용한 인과 효과를 동일한 데이터에서 다시 평가하는 순환 검증은 금지한다.

### 추가 검증

- Label Permutation Test
- Random Neuron Control
- Mismatched Model Pair Control
- Low-Competence Task Control
- Distribution Shift Check
- Activation Hook Integrity Test

특히 Activation Hook이 실제 모델 연산을 정확히 관찰·수정하는지 검사한다.

필수 코드 테스트:

1. Hook를 설치했지만 개입하지 않았을 때 원래 출력이 보존되는가?
2. 선택한 뉴런을 0으로 만들었을 때 실제 MLP 출력에서 해당 기여가 제거되는가?
3. 한 뉴런에 대한 개입이 의도하지 않은 다른 뉴런을 직접 수정하지 않는가?
4. SwiGLU 부호 구간이 정확히 계산되는가?
5. 동일 입력에서 반복 실행 결과가 허용 오차 내에서 재현되는가?
6. 모델별 토크나이저와 레이어 구조가 올바르게 처리되는가?

검증을 통과하지 않은 실험 결과는 본 결과로 채택하지 않는다.

---

## 12. 구현 및 프로젝트 구조

현재 작업 디렉터리를 먼저 검사한다.

기존 프로젝트가 있다면 구조와 코드를 파악한 후 최대한 재사용한다.

새 프로젝트가 필요한 경우 다음 구조를 권장한다.

`neuron-conservation-pilot/`

- `README.md` — 실행 방법 및 연구 개요
- `pyproject.toml` — 의존성
- `configs/` — 모든 실험 설정
- `src/models/` — 모델 로딩 및 아키텍처 어댑터
- `src/hooks/` — 뉴런 활성화·개입 Hook
- `src/data/` — 데이터 생성 및 검증
- `src/training/` — E1 독립 초기화 학습
- `src/analysis/` — 뉴런 프로파일 분석
- `src/alignment/` — 정렬 알고리즘
- `src/causal/` — 인과적 개입
- `src/statistics/` — 통계 검증
- `src/visualization/` — 그래프 생성
- `experiments/e1/`
- `experiments/e2/`
- `experiments/e3/`
- `experiments/e4/`
- `tests/`
- `results/`
- `reports/`

필수 실행 인터페이스를 제공한다.

- `make smoke` — 환경 및 핵심 기능 테스트
- `make e1` — 첫 번째 실험
- `make e2` — 두 번째 실험
- `make e3` — 세 번째 실험
- `make e4` — 네 번째 실험
- `make pilot` — 전체 파일럿 자동 실행
- `make report` — 결과 취합 및 최종 보고서 생성

해당 명령들은 실제로 동작하도록 구현한다.

가능하면 중단 후 이어서 실행할 수 있는 `--resume` 옵션을 제공한다.

모델별 MLP 구조 차이는 어댑터로 흡수하고, 지원하지 않는 모델 구조는 조용히 잘못된 계산을 수행하지 말고 명확한 오류 또는 진단 결과를 반환한다.

### 기술 스택

우선 다음을 검토한다.

- Python
- PyTorch
- Hugging Face Transformers
- Accelerate
- NumPy / SciPy
- Pandas / PyArrow
- scikit-learn
- Matplotlib
- pytest

필요 시 더 적절한 라이브러리를 추가할 수 있지만 불필요하게 복잡한 프레임워크를 도입하지 않는다.

---

## 13. 자율 연구 루프

연구의 중요한 요구사항이다.

단순히 E1 → E2 → E3 → E4를 한 번 실행하고 종료하지 않는다.

각 단계에서 다음 루프를 수행한다.

**PLAN → IMPLEMENT → VALIDATE → RUN → ANALYZE → CRITIQUE → REFINE**

### PLAN

현재 연구 가설과 가장 정보량이 높은 실험을 선택한다.

### IMPLEMENT

실험 코드를 작성한다.

### VALIDATE

단위 테스트 및 Smoke Test를 수행한다.

### RUN

실제 GPU에서 실험을 실행한다.

### ANALYZE

통계 분석 및 시각화를 수행한다.

### CRITIQUE

다음 문제를 비판적으로 검토한다.

- 결과가 우연일 가능성
- 데이터 누수
- 토크나이저 편향
- 학습되지 않은 기능의 비교
- 모델 구조 차이
- 부적절한 뉴런 정의
- Activation vs Causation 혼동
- 정렬 방법에 유리한 평가 설계
- 사후적 가설 수정
- 통계적 검증 부족

### REFINE

필요한 경우 추가 실험 또는 수정 실험을 수행한다.

단, 반복 과정은 사전에 설정한 계산 예산 안에서 수행한다.

기존 결과가 마음에 들지 않는다는 이유로 테스트셋을 반복적으로 보고 방법을 조정하지 않는다.

재설계가 필요하면 새로운 검증 데이터와 최종 테스트 데이터를 만들어 실험 버전을 분리한다.

### 병렬화

멀티에이전트 또는 서브에이전트 기능을 사용할 수 있다면 다음 업무를 병렬 처리한다.

- Literature Review
- Model Architecture / Hook Implementation
- Dataset Design
- Statistical Validation
- Experimental Critique

단, 동일 GPU에 무거운 모델을 여러 개 동시에 실행하여 메모리 부족을 일으키지 않도록 GPU 작업은 자원 스케줄러를 통해 조정한다.

서브에이전트의 결과는 검증 후 통합한다.

---

## 14. 최종 결과물

모든 실험이 종료되면 다음 파일을 생성한다.

### `reports/FINAL_RESEARCH_REPORT.md`

최종 연구 보고서에는 다음 내용을 반드시 포함한다.

1. 연구 배경 및 핵심 가설
2. Goodfire 2026 연구와의 관계
3. 선행연구와 차별성
4. E1~E4의 실험 방법
5. 사용 모델 및 데이터셋
6. 각 실험의 Baseline
7. 주요 수치 결과
8. 통계적 신뢰구간
9. 가설별 지지·기각·판단 불가 여부
10. 발견된 문제 및 반례
11. 연구의 한계
12. 다음 실험 추천

### `reports/EXECUTIVE_SUMMARY.md`

한눈에 볼 수 있도록 다음 표를 작성한다.

| Experiment | Hypothesis | Main Metric | Baseline | Proposed | Improvement | CI | Verdict |
|---|---|---|---|---|---|---|---|

측정되지 않은 값은 임의로 채우지 않는다.

### `reports/RESEARCH_CRITIQUE.md`

연구를 비판적으로 분석한다.

- 신규성이 부족한 부분
- 타당성이 부족한 실험
- 대체 설명이 가능한 결과
- 더 강력한 Baseline의 필요성
- 논문 심사자가 문제 삼을 가능성이 높은 항목
- 후속 실험에서 반드시 해결해야 하는 한계

### `reports/NEXT_EXPERIMENTS.md`

파일럿 결과를 기반으로 후속 실험을 우선순위화한다.

주요 후보:

- Cross-Model Neuron Transplantation
- Circuit-Preserving Model Merging
- Semantic / Causal Alignment 기반 선택적 지식 이식
- One-to-Many Neuron Mapping
- Neuron Group Alignment
- Training-Time Recursive Generalization Tracking

각 주제의 예상 학술적 기여, 구현 난이도, 필요한 계산 자원, 예상 실패 요인을 비교한다.

---

## 15. 재현성 및 연구 기록

모든 실험에서 다음 정보를 저장한다.

- Python 버전
- CUDA / PyTorch 버전
- GPU 모델
- Git Commit Hash
- 모델 ID 및 가능한 경우 정확한 Revision
- 데이터셋 버전 및 해시
- 실험 시드
- Hyperparameters
- 실행 시간
- 최대 VRAM
- 주요 로그
- 평가 결과
- 실패 및 재시도 이력

표나 그래프에 사용하는 값은 실제 실험 결과에서 자동으로 읽어 오게 한다.

보고서의 수치를 사람이 수동으로 수정할 필요가 없도록 한다.

실험 결과가 부족하면 부족하다고 기록한다.

예상 결과, 예제 데이터 또는 임의 생성 수치를 실제 측정값처럼 제시하지 않는다.

---

## 16. 최종 연구 판단

최종적으로 다음 네 질문에 독립적으로 답하라.

**Q1.** 독립적인 초기화로 학습된 동일 아키텍처 모델 사이에서 원본 뉴런의 기능적 대응 관계가 관찰되는가?

**Q2.** 서로 다른 LLM 계열에서도 원본 뉴런의 주기능이 보존되거나 수렴하는 현상이 관찰되는가?

**Q3.** Goodfire 2026의 관점을 활용한 주기능 기반 정렬이 기존 Activation-Based Matching보다 실제 기능적 대응을 더 잘 예측하는가?

**Q4.** 인과적 역할을 반영한 정렬이 의미 기반 정렬보다 독립 테스트셋에서 더 정확한 대응을 제공하는가?

각 질문에 다음 중 하나로 답한다.

- SUPPORTED
- NOT SUPPORTED
- INCONCLUSIVE

긍정적 결과가 나왔다고 해서 원본 뉴런이 보편적으로 단일 의미를 가지거나 모델 간에 완전히 동일하다고 주장하지 않는다.

인과적 기능이 일치하더라도 곧바로 뉴런을 복사하여 병합할 수 있음을 의미하지 않는다. 구조적 호환성과 주변 회로의 영향을 별도로 검증해야 한다.

---

## 17. 작업 시작 및 종료 지침

**지금부터 실제 작업을 시작하라.**

다음 순서로 진행한다.

1. 기존 디렉터리 및 연구 환경 확인
2. Goodfire 2026 및 관련 논문 검토
3. 가설·데이터셋·평가 지표 확정
4. 프로젝트 초기화
5. 모델 어댑터 및 뉴런 Hook 구현
6. 자동화 테스트 수행
7. E1 실행 및 분석
8. E2 실행 및 분석
9. E3 실행 및 분석
10. E4 실행 및 분석
11. 결과 검증 및 추가 실험
12. 전체 연구 보고서 생성

### 자율 실행 규칙

- 사소한 구현 선택이나 하이퍼파라미터 때문에 사용자에게 반복적으로 질문하지 않는다.
- 합리적인 기본값을 선택하고 설정 및 근거를 기록한다.
- 실패한 명령은 오류를 진단하고 안전한 범위에서 수정한 뒤 재실행한다.
- 실험이 실패하면 무조건 반복하지 말고 실패 원인을 먼저 분석한다.
- 계산 예산을 소진하면 재현 가능한 중간 결과와 남은 작업을 기록한다.
- 외부 유료 서비스, 무단 데이터 전송, 시스템 변경, 다른 사용자의 작업 중단은 수행하지 않는다.
- Git Repository가 있다면 사용자의 기존 변경 사항을 보존한다.
- 외부 저장소에 자동으로 Push하지 않는다.
- 사용자 승인 없이 기존 실험 결과를 삭제하거나 덮어쓰지 않는다.
- 구현 완료와 실제 실행 완료를 명확히 구분하여 보고한다.

### 성공 기준

다음 조건을 충족하면 파일럿 연구를 완료한 것으로 본다.

- E1~E4 각각 실제 실행 결과 또는 구체적으로 검증된 실행 불가 사유 확보
- 핵심 Baseline 구현
- 뉴런 활성값 수집 및 개입 기능 검증
- 독립 테스트셋 평가
- 주요 결과의 통계적 분석
- 재현 가능한 소스 코드
- 최종 연구 보고서
- 후속 실험 우선순위 제시

가설이 기각되더라도 실험 설계와 검증이 올바르다면 성공적인 연구 결과로 인정한다.

**가장 중요한 것은 긍정적 결과를 만들어내는 것이 아니라, 서로 다른 LLM 사이에서 뉴런의 기능적·인과적 보존 여부를 실제로 검증하는 것이다.**

이제 환경 점검과 선행연구 검토부터 시작하고, 코드 작성에 그치지 말고 가능한 모든 실험을 실제로 실행하라.