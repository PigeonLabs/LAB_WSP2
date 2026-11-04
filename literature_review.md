# 원본 뉴런의 모델 간 보존: 선행연구 검토

검토일: 2026-11-04 (Asia/Seoul). 목적은 E1–E4의 설계 근거 확보이며, 아래 논문의 결과를 이번 실험의 측정 결과로 취급하지 않는다. 원문에서 확인한 범위와 우리 연구자의 해석을 구분한다.

## 핵심 판단

뉴런 정렬, 유사 특징 발견, 선택적 이식, 이종 모델 병합 자체에는 선행연구가 있다. 따라서 신규성을 “뉴런의 공통성을 최초로 발견” 또는 “최초의 뉴런 병합”으로 주장할 수 없다. 이 파일럿의 구별되는 질문은 **독립 초기화·이종 계열의 원본 뉴런을 대상으로, 의미적 정렬이 독립 입력의 반응과 독립 개입 효과를 얼마나 예측하는지 비교**하는 것이다. 이 또한 아래 제한된 조사만으로 최초성을 확정할 수 없다.

## 필수 문헌

### 1. Neural Networks Are Already Clean — Nick Cammarata / Goodfire, 2026

[원문](https://already-clean.goodfire.com/)의 도입부, 언어 모델, 부호 구간 및 개입 사례를 확인했다. 저자 자신이 working hypothesis로 제시한 연구 에세이다. 원본 뉴런의 강한 반응과 주변 회로를 함께 보면 일부 다의성은 관련된 반응의 확장으로 설명된다는 가설이다. Qwen3-32B의 MLP 뉴런 및 시각 모델의 채널을 다루며, 뉴런 제거에 따른 출력 변화 사례가 있다. SwiGLU에서는 gate와 value의 부호 조합을 분리해야 한다. 양의 곱만 관찰하면 음수×음수 경로가 섞인다. 이는 독립 모델 간 체계적인 인과 정렬 검증과는 다르다.

**설계 반영:** `SiLU(gate) * up`을 원본 뉴런으로 정의하고 네 부호 구간을 저장한다. 강한 반응뿐 아니라 음의 반응, 비설명 반응, 주변 기여를 기록한다. 주기능을 찾지 못한 뉴런은 `UNKNOWN`으로 남긴다. 작은 합성 모델의 실패가 에세이의 광범위한 주장을 곧바로 반박하지도, 일부 성공이 보편적 단일 의미성을 입증하지도 않는다.

### 2. Git Re-Basin: Merging Models modulo Permutation Symmetries — Ainsworth et al.

[원문 v6, §§3–5 및 부록](https://arxiv.org/html/2209.04836v6). 은닉 유닛 순열 대칭을 제거하면 독립 학습 모델의 가중치 공간을 정렬할 수 있다는 가설이다. 활성값 OLS 기반 할당, 가중치 기반 순열 최적화, straight-through 추정 방식이 제안된다. MLP, VGG, ResNet 및 MNIST/CIFAR/ImageNet 계열에서 손실 장벽과 병합을 평가한다. 모델 내부 유닛의 의미나 개별 뉴런의 독립 인과 효과 일치를 주 지표로 삼지 않는다. 보편적 단일 basin 가설의 반례도 제시한다.

**설계 반영:** E1에 활성 상관·할당 기준선을 둔다. 가중치 기준선을 구현한다면 연결된 모든 축의 순열 일관성을 검사한다. 단일 레이어의 가중치 벡터 cosine만 사용한 경우 전체 Git Re-Basin 구현이라고 부르지 않는다. SwiGLU의 gate/up 행과 down 열은 동일한 순열로 묶여야 한다. 병합 성능과 의미적 보존을 구분한다.

### 3. Rosetta Neurons: Mining the Common Units in a Model Zoo — Dravid et al., 2023

[원문 v2, §§3–5](https://arxiv.org/html/2306.09346v2). 여러 입력에서 양의 상관을 갖는 모델 간 채널을 공통 유닛으로 정의한다. 공간 활성 지도를 비교하고 여러 모델의 대응을 모아 공통 개념을 찾는다. ResNet50, DINO, ViT, MAE, CLIP 및 GAN 계열을 검토한다. 생성 모델을 이용한 inversion·편집을 보이지만, LLM 원본 뉴런의 held-out 인과 효과 정렬과 동일한 실험은 아니다. GAN끼리 동일 입력을 확보하기 어려워 직접 매칭하지 못한다는 제한도 명시한다.

**설계 반영:** 동일한 자극의 대응이 정렬의 전제다. E2에서는 Token ID를 맞추지 않고 원문 문자 span과 답변 직전 위치를 맞춘다. 높은 활성 상관을 기능 보존의 정의로 채택한 뒤 같은 상관으로 가설을 검증하는 순환을 피한다. 층 번호 고정과 일대일 대응을 강제하지 않는다.

### 4. Towards Monosemanticity — Bricken et al., 2023

[공식 원문](https://transformer-circuits.pub/2023/monosemantic-features/). 전체 페이지 직접 열기는 도구의 크기 제한으로 실패했으며, 공식 도메인의 검색 인덱스에서 Problem Setup, Summary of Results, Detailed Investigations 및 Feature Splitting 본문을 확인했다. 512개 ReLU MLP 뉴런의 단일 층 Transformer 활성값을 sparse autoencoder로 분해한다. SAE의 encoder 활성값과 decoder 방향이 분석 특징이며 원본 뉴런과 다르다. 복원 오차와 희소성 목적을 사용하고, 특징 활성화에 따른 아랍어/base64 생성 변화, 모델 간 특징 유사성, 사전 크기에 따른 특징 분할을 조사한다.

**설계 반영:** SAE 특징과 원본 뉴런을 혼동하지 않는다. 설명의 특이도·민감도를 양성/음성 예제로 검증하고, 토크나이저와 불완전한 개념 proxy의 영향을 분리한다. 특징 해상도가 달라지면 다대일 대응이 가능하다. 본 파일럿이 SAE 기준선을 실행하지 않는다면 SAE보다 우월하다는 결론을 내리지 않는다.

### 5. Transport and Merge: Cross-Architecture Merging for Large Language Models — Cui et al., 2026

[ICML/PMLR 출판 기록](https://proceedings.mlr.press/v306/cui26j.html), [원문 arXiv v2, §§3–5·부록](https://arxiv.org/html/2602.05495v2). 선형 서브레이어의 가중치 행/열을 뉴런, 통과하는 값을 activated feature로 구분한다. 입력 자극의 활성 통계로 뉴런 및 층 수준 optimal transport를 추정하고, 입력·출력 운송 행렬로 가중치를 옮겨 혼합한다. Llama 계열 저자원 언어/전문 영역 모델과 Qwen 계열 등의 전이를 평가한다. 병합 뒤 adaptation을 포함하는 조건과 제외하는 조건을 구분한다. 주된 결과는 전이 성능이며 개별 뉴런의 의미·인과 보존 입증과 같지 않다.

**설계 반영:** 서로 다른 차원의 모델에서는 순열보다 부분 또는 연성 대응이 적절할 수 있다. 상대 깊이와 유연한 층 대응을 비교한다. calibration 분포가 대응을 좌우하므로 분포 이동을 보고한다. 이 논문 전체를 “학습 없는 병합”으로 단순화하지 않는다. 출판 PDF는 content-type 오류로 열리지 않았으며 방법 검토는 공개 arXiv v2에 근거한다. 두 판의 완전한 동일성은 검사하지 않았다.

## 2025–2026 인접 연구

| 연구·확인 원문 | 분석 단위·방법 | 개입과 검증 모델 | 이번 연구와의 차이·교훈 |
|---|---|---|---|
| [ARM, 2026, §§3–4](https://arxiv.org/html/2601.07309v1) | 역할별 활성 중요도, merged backbone 선택, 충돌하는 중요 뉴런을 보호한 이식. SwiGLU gate/up 행과 down 열을 묶음 | Qwen3-8B 및 Qwen2.5-7B 기반 SFT 전문가 풀을 각각 병합; 뉴런 가중치 이식 후 agent benchmark 평가 | 공통 사전학습에서 파생된 전문가 병합은 독립 초기화 증거가 아니다. 구조적 호환성과 주변 기능 손상을 별도로 검사해야 한다. |
| [LED-Merging, ACL 2025, §3·§4.4·부록 A](https://aclanthology.org/2025.acl-long.1055.pdf) | gradient attribution으로 중요 파라미터/뉴런 위치 선택, 여러 모델 중요도 결합, 충돌 업데이트 격리; SNIP 방식 비교 | Llama-3-8B, Mistral-7B, Llama2-13B 기반 안전·수학·코드 전문가; 병합 성능과 방법 ablation | 여러 아키텍처에서 방법을 시험했다는 사실을 이종 기반 모델 사이 원본 뉴런 대응의 입증으로 해석하지 않는다. 중요도는 완전한 개입 효과 fingerprint와 다르다. |
| [HeteroFusion, 2026, §§3–4](https://arxiv.org/html/2604.01674v1) | 모듈 역할·구조에 따른 LoRA topology 정렬, 충돌 완화, 학습 가능한 전이 네트워크 | Llama-3.1-8B-Instruct, Qwen2.5-7B-Instruct, Mistral-7B-v0.3; adapter를 동적으로 patch하고 LM loss로 전이 연산자를 학습 | 원본 뉴런 일대일 보존 검증이 아니다. replay 데이터로 최적화하므로 training-free 기준선으로 분류하면 안 된다. |
| [Circuit Tracing, 2025](https://transformer-circuits.pub/2025/attribution-graphs/methods.html) | cross-layer transcoder로 MLP를 근사한 replacement model; 특징·오차·logit 노드의 attribution graph | 18층 LM과 Claude 3.5 Haiku 관련 방법; 원모델 개입을 통한 가설 검사 | 특징 정렬과 원본 뉴런 정렬을 구분한다. 그래프의 직접 기여만으로 전체 개입 효과를 대체하지 않는다. 복원 오차와 고정한 attention/normalization의 제한을 보고한다. |
| [The Non-Linear Representation Dilemma, 2025, §§5–7](https://arxiv.org/html/2507.08802v1) | 신경망–알고리즘 causal abstraction의 선형/비선형 alignment map 비교 | 계층적 동등성·IOI; 무작위 초기화 LM에서도 복잡한 map으로 높은 interchange-intervention accuracy 가능 | 강력한 정렬기가 가설에 필요한 계산을 대신할 위험이 있다. 정렬 복잡도를 제한하고 untrained·low-competence control을 유지한다. |
| [Same Task, Different Circuits, NeurIPS 2025, §§2·4](https://papers.nips.cc/paper_files/paper/2025/file/5fcd540792da599adf1b932624e98f1f-Paper-Conference.pdf) | 위치별 attention head/MLP 뉴런 회로; AP-IG로 후보 발견 후 회로 faithfulness와 부분회로 교환 평가 | 다중 VLM의 대응 시각/텍스트 과제; query·generation과 data 처리 부분을 구분, later-to-earlier patching | 같은 기능이 다른 구조에서 구현될 수 있다. 동일 모델의 모달리티 간 교환이 독립 모델 사이 단일 뉴런의 교환 가능성을 입증하지 않는다. |

## 실험 설계에 반영할 결정

다음은 문헌 내용의 인용이 아니라 본 파일럿의 설계 판단이다.

1. **단위와 범위:** 원본 MLP 뉴런, SAE 특징, LoRA 모듈, 회로를 별도 단위로 명명한다. 뉴런 하나를 비교한 결과를 전체 회로의 동등성으로 확장하지 않는다.
2. **사전 분리:** D1 후보 탐색, D2 정렬·임계값·정규화 설정, D3 독립 반응 평가, D4 독립 인과 평가를 분리한다. D3/D4의 결과를 본 뒤 기존 버전의 후보를 바꾸지 않는다.
3. **기능 학습 여부:** 각 모델의 과제 정확도와 chance를 먼저 측정한다. 학습 실패·낮은 능력 조건의 약한 대응은 보존 가설의 기각 근거가 아니다.
4. **비교 기준:** random, activation correlation, rank/distribution, label permutation, untrained control을 포함한다. 높은 최대 유사도는 후보 수가 많아서 발생할 수 있으므로 동일한 후보 수와 검색 자유도를 통제한다.
5. **인과 검증:** 각 모델 내부에서 zero/mean/patch 개입을 시행한다. 동일 프롬프트의 정답–대비 답변 log probability margin 변화와 부호를 비교한다. mean과 정규화 척도는 calibration에서만 추정한다.
6. **통계 단위:** 동일 템플릿에서 만든 여러 문항을 독립 연구 반복으로 계산하지 않는다. 템플릿/과제 군집 bootstrap과 seed/model-pair variation을 보고한다. 비유의성과 작은 효과를 숨기지 않는다.
7. **해석 제한:** 양의 활성은 출력에 대한 양의 기여와 다르다. 높은 의미 유사도는 높은 인과 일치를 보장하지 않으며, 높은 인과 일치 역시 안전한 가중치 이식을 보장하지 않는다.

## 접근 기록과 남은 문헌 검증

- 필수 다섯 자료의 본문 또는 공식 본문 발췌를 확인했다. Re-Basin/Rosetta/ARM/HeteroFusion/Transport는 위에 링크한 버전을 기준으로 한다.
- Monosemanticity의 전체 HTML 직접 fetch는 약 20 MB 크기 제한으로 실패했다. 공식 도메인의 검색 인덱스 본문을 이용했으며 전체 부록을 읽었다고 주장하지 않는다. 직접 Python 다운로드도 sandbox DNS 오류로 실패했다.
- Transport의 PMLR PDF 직접 fetch는 `application/octet-stream` 미지원 오류였다. arXiv v2 본문으로 대체했다.
- 이 검토는 체계적 전수조사가 아니다. 모델별 라이선스·정확한 revision 확인, 최신 판별 변경점, OT/SAE/회로 단위 기준선의 직접 재현은 별도 작업이다.
- 외부 논문의 보고 수치는 이번 실행의 표·그래프에 혼합하지 않는다. 본 파일의 설계 제안도 구현·실행 상태를 뜻하지 않는다.
