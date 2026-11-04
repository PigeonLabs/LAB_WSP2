# Gemma 4 E2B neuron map: source review for WSP2 followup-v3

검토일: 2026-11-04. **외부 연구 검토이며 WSP2의 새 측정 결과가 아니다.** 작성자 Jiho Ryou의 [지도](https://salixkoreensis94-spec.github.io/gemma4-e2b-neuron-map/map/index.html)와 [저장소](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map)를 참고했다. 고정 revision은 `c2dfd9e7a54c745824ffe2472ab15040ffb8048f`이다. 파일별 Git blob ID와 열람 사본 해시는 [참조 manifest](../../artifacts/followup-v3-gemma-map/reference_manifest.json)에 기록했다.

지도 URL의 웹 추출은 실패했고 브라우저 사용도 비활성화되어 있었다. 대신 해당 지도의 저장소 HTML, 데이터 schema, metadata, METHODS, RESULTS 및 공개 코드를 확인했다. 실제 화면의 시각 검수를 수행했다는 주장은 하지 않는다.

## 확인한 사실과 해석 범위

| 자료 | 확인한 내용 | 이번 설계에 반영할 점 |
|---|---|---|
| [Map manifest](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/data/round3/manifest.json) | 35층, 337,920개 native neuron; dev 49,438,284 tokens / 263,910 chunks. 별도 held-out 561,716 tokens | 공개 dev 지도는 후보 탐색 자료다. 우리 최종 시험은 새로운 문서·시나리오로 만든다. chunk 수를 독립 문서 수로 취급하지 않는다. |
| [METHODS](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/METHODS.md) | Native 단위는 `GELU_tanh(gate)×up`, down projection 이전. 정적 렌즈는 정규화한 write column의 pre-softcap 투영. Round 3은 exact-dequantized FP32 경로이며 이전 custom CUDA rounding 경로는 수치 gate에 실패 | 기존 WSP2 SwiGLU hook을 그대로 재사용하지 않는다. 렌즈·관측 활성·실제 개입 효과를 별도 측정한다. |
| [M2 aggregate](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/data/round3/m2.json) | 1,400개 실제 뉴런과 420개 대조 항목. 다수결 판정의 원 가설은 reject; 만장일치 분석은 controls_valid=false, inconclusive | AI 라벨을 기능 정답으로 재사용하지 않는다. unknown·심사 불일치를 보존하고 후보 선택에 의한 범위를 명시한다. |
| [M3 training](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/data/round3/m3_training.json) | 원 CE gate는 L5/L15/L27 모두 FAIL. 사후 KL 수정에서 L5/L27만 통과; L15 dead fraction은 k32에서 27.03%, k64 재시도에서 49.88% | 원 실패와 사후 수정 결과를 합치지 않는다. 새 fidelity 기준을 시험 전에 고정하고 실패층도 기록한다. |
| [M3 exploratory](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/data/round3/m3_exploratory.json) | 단일 개념 다수결 라벨은 feature 207/240=86.25%, neuron 36/80=45.0%. direction 18/36=50.0%. 명시적으로 post hoc | 설명 용이성의 탐색 결과이지 인과 우위나 모델 간 보존의 증명이 아니다. 공간별 random 대조군을 구분한다. |
| [M4 aggregate](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/data/round3/m4.json) | 상태는 gate_failure_no_verdict | 내부 gate를 실패한 수치를 긍정·부정 결론으로 재해석하지 않는다. |
| [F1b schema](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/code/round4/F1b_SCHEMA.md), [RESULTS](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/RESULTS.md) | neuron clamp와 feature additive 개입은 서로 다르다. F1b3는 438 neurons + 440 features, 사후 수정된 강도 선택. 토큰 겹침은 의미 평가가 아니다 | 동일 차분 연산·위치·노름으로 재비교한다. 강제 출력에서 관련 토큰이 나온다는 사실만으로 기능을 확정하지 않는다. |
| [Round 4 metadata](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/docs/map/data/round4/metadata.json) | L5/L27 각 16,384 features. 카드 이웃은 decoder와 native down column의 같은 층 cosine | 같은 색·같은 이웃·같은 ID 번호가 동일 활성 또는 인과 역할을 뜻하지 않는다. |

## 공개 자료의 재현 가능 범위

정적 지도, compact JSON, schema, 시각화 코드와 일부 초기 실험 코드는 공개되어 있다. 그러나 이 revision의 `code/round4/`에는 `F1b_SCHEMA.md`만 있고 실제 F1b 추론 엔진은 없다. Round 3 공개 코드는 주로 지도 구축·표시·검증 코드다. Feature provenance에 있는 체크포인트 해시는 해당 가중치를 다운로드할 수 있다는 뜻이 아니다. [공개 코드 설명](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/code/README.md), [feature provenance](https://github.com/salixkoreensis94-spec/gemma4-e2b-neuron-map/blob/c2dfd9e7a54c745824ffe2472ab15040ffb8048f/docs/map/data/round4/provenance.json).

따라서 다음 작업을 분리한다.

1. **공개 자료 재분석:** 집계 수치·판정·표시 구조를 확인한다. 새 inference 없이 가능하다.
2. **동일 모델의 독립 재현:** 지정 GGUF·tokenizer·수치 경로를 확보하고 검증해야 한다. 현재 설계 단계에서는 확보·동등성을 확인하지 않았다.
3. **새 모델/새 transcoder 실험:** 독자적으로 만든 가중치와 엔진으로 실행할 수 있으나 원 지도의 동일 feature나 원 실험의 정확한 재현이라고 부르지 않는다.

프로젝트 코드 Apache-2.0, 프로젝트 데이터·문서 CC BY 4.0, 제3자 snippet의 개별 라이선스를 구분한다. 이번 설계에서는 원문 snippet이나 비공개 LoRA를 복제하지 않는다. 향후 데이터 수집에는 source revision, document ID, license, split lineage를 함께 보존한다.

## WSP2 기존 결과와 연결

우리 [최종 과학 검토](../../results/followup-v2/scientific_review.json)는 truth-oriented 개입 상관의 제한된 개선만 지지했고, 공개 모델의 공동 과제 능력, semantic proxy의 activation 대비 우위, 유용한 이식은 확립하지 못했다. 따라서 다음 단계의 질문은 **“설명하기 쉬운 단위인가?”를 넘어 “어휘·정답 표현·개입 크기를 통제한 새 문맥에서 기능을 예측하고 선택적으로 바꿀 수 있는가?”**이다.

이 연결은 새 연구 제안이다. 외부 지도의 결과와 우리 v2 결과를 합산하거나 같은 표본으로 통계 검정하지 않는다. 구체적 실행·중단 규칙은 [DESIGN.md](DESIGN.md)에 정리했다.
