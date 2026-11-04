# V3 R64 데이터 준비 검토 — 2026-11-04

**최신 상태:** 실제 CC0 source record 64개와 canonical fact 112개를 수집하고 원 API snapshot 재생 검산을 통과했다. [합본](Rsourcecatalogv2.json), [검산 결과](SOURCE_BANK_VALIDATION.json). 아래 초기 조사와 후속 확장 결과를 함께 보존한다. Source bank 확보와 독립 template gate 통과는 구분한다.

**판정: 엄격한 R gate는 아직 BLOCKED_DATA_GATE다.** 현재 E는 32 scenario / 512 variant지만 생성 문법 계보는 4개다. 이름·사물·수치만 교체하여 R64를 만들거나 문서 ID만 새로 부여하면 설계의 독립 source/template 요구를 충족하지 않는다. 본 source-bank 작업에서 R 문항·모델 결과 및 T/O를 생성하거나 개봉하지 않았다. 기존 설계·설정·데이터 소스 코드는 수정하지 않았다.

[원 설계](../followup-v3-gemma-map/DESIGN.md), [기존 실행 amendment](../followup-v3-gemma-map/RUN_AMENDMENTS.md), [신규 catalogue 초안](R64_SOURCE_CATALOG_DRAFT.json)을 함께 보아야 한다. 초기 초안에는 **공개 자료 6쪽의 사실 후보, 이 중 CC0 기본 메타데이터 2쪽, 실제 승인 R family 0개, 독립 R lineage 0개**를 기록했다. 64개 recruitment slot은 할당 계획이며 관측값이나 확보된 독립 표본이 아니다.

## 추가 실행 결과: 실제 공개 source bank 64개 확보

후속 요청에 따라 위의 초기 조사에서 멈추지 않고 [Rsourcecatalogv2.json](Rsourcecatalogv2.json)에 **실제 원 기록 64개 / canonical facts 112개 / 네 축 각16개**를 수집했다. 앞의 초기 초안과 미충원 상태는 이 추가 수집 전의 기록으로 보존한다. 새 합본에는 placeholder가 없다.

| 축 | 실제 자료 | 기록 수 | 해석 범위 |
|---|---|---:|---|
| 수 비교 | Met의 별도 accession, Overall 높이·너비, cm | 16 | 기록된 치수 간 비교; frame/glazing 측정 제외 |
| 부정 | Met의 별도 accession에 명시된 objectName·title | 16 | 명시된 exact-label predicate의 긍정/부정; 누락 속성으로 거짓 추론 금지 |
| 소유/지시 | Wikidata P127 assertion, 원 qualifier·rank·reference | 16 | 기록에 따른 역사적 소유 관계; 현재 소유로 일반화하지 않음 |
| 시간 | Wikidata 인물별 P569/P570, day precision·Gregorian | 16 | 기록된 날짜 비교; 출생→사망 event-type shortcut 별도 한계 |

Met 32개는 서로 다른 accession·작가로 선택했다. 전체 64개의 URL/record ID는 서로 다르고, 사용 가능한 Met→Wikidata entity crosswalk에서도 중복이 없다. 이것은 실제 내용 표집 단위의 차이를 뒷받침하지만 통계적 독립성을 증명하지 않는다. **같은 기관이나 공통 질문 wrapper만을 이유로 별도 원 기록을 전부 같은 source lineage로 합치지는 않는다.** 원 문서·사건·참조·import·derivation의 공유를 따로 추적하고 의존성 sensitivity에 사용한다.

라이선스 범위는 Met 기본 메타데이터와 Wikidata 구조화 데이터의 CC0다. 외부 참조 문서의 prose는 복제하지 않았다. EN/KO 짧은 controlled paraphrase, typed facts, URL·revision·출처 hash를 저장했다. 소유 기록은 13 owner ID와 17 reference hash를 포함하고, 11개 레코드에는 외부 reference URL도 있다. 사실 추출과 API 대조는 자동/에이전트 검증이며 사람 검증을 주장하지 않는다.

새 bank 역시 **새 renderer family 4개를 공유**한다. 원 기록 64개 확보를 독립 template 64개 확보로 바꾸어 말하지 않는다. 부정 exact-label 예제의 어휘 단서, 생애 날짜의 고정 순서 단서, 유명 작품/인물 및 유럽 회화의 편의 표집은 후속 구성에서 별도 통제가 필요하다. 데이터 담당자가 새로운 bilingual renderer와 독립 text oracle를 구현·검증해야 하며, 원 사실과 가상 반사실 context를 분명히 구분해야 한다. R 모델 평가·T/O는 이 수집에 포함되지 않는다. 원 strict source/template gate를 자동으로 통과시킨 결과가 아니다.

## 독립성의 단위를 분리해야 하는 이유

| 필드 | 의미 | 독립 표본 수에 대한 해석 |
|---|---|---|
| source_document_id / original_reference | 실제 저작 문서·원 기록과 원 출처 | URL이 다르더라도 같은 원문 재게시·DB import·동일 사건 요약이면 같은 계보일 수 있음 |
| semantic_graph_id / derivation_parent | 사실·사건·상태전이 그래프 및 파생 관계 | 다른 이름을 넣은 동일 그래프는 독립 구조가 아님. 번역·반사실·어휘 변형은 같은 family |
| rendering_grammar_id / template_parent | 내용을 문장으로 만드는 구조·문법 | 여러 사실 그래프에 같은 renderer를 적용하면 내용 다양성은 생기지만 새 template 일반화 근거는 생기지 않음 |
| measurement_wrapper_id | 공통 지시문·답 코드·채점 wrapper | 동일한 측정 절차 자체를 모든 독립 문서의 공통 저작 계보로 간주할 필요는 없음. 하지만 wrapper가 이야기 구조까지 생성한다면 renderer 역할도 별도 기록 |
| family_id / split | 같은 underlying scenario의 16변형과 배정 | KO/EN, true/false, lexical, answer-code는 family 내부 반복이며 16개의 독립 관측이 아님 |

현재 `gemma_v3_data.validate_records`는 같은 `grammar_id`에 여러 독립 `lineage_id`를 주는 것을 거부한다. `build_readiness`는 E prompt freeze와 E/R의 source·lineage·grammar·prompt·content disjointness를 요구한다. 따라서 이 초안을 기존 함수에 넣어 gate를 통과시키는 우회는 없다. 다른 실제 문서를 가져오더라도 기존 4개 렌더링 문법을 재사용하려면 추론 범위와 validation 규칙에 대한 **명시적인 새 조건부 arm**이 먼저 필요하다.

## 지금 실제 확보한 작은 공개 evidence bank

- Met의 작품 기본 메타데이터는 CC0다. `Wheat Field with Cypresses`의 73.2×93.4 cm, `Sunflowers`의 43.2×61 cm는 단위가 맞는 수 비교 후보다. 두 작품 모두 같은 작가·박물관 자료이므로 독립 source 2개라고 승인하지 않았다. 작품 설명 에세이는 CC0 메타데이터와 구분하며 복제하지 않는다. [공식 Open Access 정책](https://www.metmuseum.org/hubs/open-access), [첫 작품](https://www.metmuseum.org/art/collection/search/436535), [둘째 작품](https://www.metmuseum.org/art/collection/search/436524).
- Voyager 1/2의 발사 날짜와 일부 flyby 날짜는 시간 순서 후보로 확인했다. 두 페이지는 NASA/JPL의 같은 프로그램 자료이므로 우선 하나의 상위 출처 그룹으로 둔다. Voyager 2의 Saturn 날짜는 표와 본문이 달라 후보 사실에서 제외했다. [Voyager 1](https://science.nasa.gov/mission/voyager/voyager-1/), [Voyager 2](https://science.nasa.gov/mission/voyager/voyager-2/).
- Hope Diamond 자료는 1949년 매입과 1958년 기증을 명시한다. 그러나 개인 Harry Winston과 회사 Harry Winston, Inc.를 자동 동일시해서는 안 된다. 전시·대여·보관은 소유권 이전이 아니다. 사실 후보만 기록했고, 페이지 전체의 자유이용 또는 완성된 소유/지시 oracle은 승인하지 않았다. [Smithsonian 원 자료](https://naturalhistory.si.edu/explore/collections/hope-diamond).
- Apollo 13 페이지는 mission type에 Lunar Landing을 표시하면서 본문에서는 계획했던 달 착륙을 설명한다. 이 메타데이터만으로 실제 착륙 여부를 결정하면 오류가 난다. 부정 과제 후보는 **미승인**이다. 출처의 명시적 사건 결과와 시제·부정 scope 검토가 필요하다. [NASA 원 자료](https://www.nasa.gov/mission/apollo-13/).

Wikidata의 구조화 데이터는 CC0지만 QID를 64개 뽑았다는 사실은 독립 저작·독립 template 64개를 증명하지 않는다. 원 citation, imported-from, 같은 문서·사건 및 데이터 생성 계보를 연결해야 한다. 텍스트 namespace까지 CC0라고 확대하지 않는다. [Wikidata Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing). NASA/Smithsonian 공개 페이지 역시 모든 사진·서술문이 동일한 자유 라이선스라고 가정하지 않는다. 본 초안은 최소한의 사실만 추출했고, 허가가 확인되지 않은 prose의 데이터셋 재배포를 보류했다.

## R64를 실제로 채우는 방법과 완료 기준

1. 네 concept마다 16개 source/scenario slot을 모집한다. 문서·원 인용·제작자·라이선스·retrieval date·본문 또는 사실 추출 해시를 보존한다. 같은 사건/문서에서 파생한 슬롯들은 상위 cluster로 묶고, 독립 수가 부족하면 그만큼 부족하다고 기록한다. 단순 64개 페이지 수집을 완료 기준으로 사용하지 않는다.
2. 실제 내용 관계를 먼저 그래프로 옮긴다. negation은 명시적인 부정 사건/속성, ownership은 타입이 명확한 소유권 상태전이와 대명사 antecedent, temporal은 구별되는 사건 간 partial order, numeric은 동일 dimension의 정확한 수치·단위를 요구한다. 새로운 그래프라는 주장도 생성·저작 계보 검토 없이 승인하지 않는다.
3. source graph를 EN/KO의 두 lexical realization으로 표현한다. 공통 질문 wrapper는 E에서 동결한 그대로 사용하되 이야기 renderer와 분리한다. 번역·paraphrase·counterfactual 모두 같은 family에 둔다. 원문과 다른 사실 상태는 명시적인 hypothetical context로 표현하고 실제 역사 기록인 것처럼 쓰지 않는다.
4. 아래 oracle 검사와 수작업 출처 대조를 통과한 family만 승인한다. 자동 생성기가 자신의 latent label을 읽어 정답을 확인하는 순환 검증은 금지한다. 검토자 종류를 기록하고, 에이전트 검토를 사람 검증으로 표기하지 않는다.
5. 데이터 관리자가 E와 source/template/내용 triple 중복을 검사한다. R64 및 상위 lineage 수를 concept별로 명시하고, 라이선스·oracle·해시를 동결한다. **root의 E prompt freeze receipt 이후에만 R prompt materialization 및 모델 채점을 시작**한다. 현재 초안에는 readiness prompt나 모델 점수가 없다.

이 작업은 공개 사실자료만으로 진행 가능하다. 다만 이번 짧은 조사에서 엄격 기준을 충족한 64개 독립 source/template를 확보하지는 못했다. 특히 부정과 소유/지시 과제는 단순 메타데이터 숫자 수집보다 evidence/oracle 검토가 더 필요하다. 현재 자료를 64회 이름 치환하여 채우는 것은 허용되는 해결책이 아니다.

## EN/KO evidence oracle 승인 조건

| 축 | 정답의 근거 | 실패·제외 기준 |
|---|---|---|
| 부정 | 표시된 context의 명시적 긍정/부정 predicate, 시제·양화·scope | 자료에 없다는 이유로 false 판정, 계획/의도와 실제 사건 혼동, 두 겹 부정 해석 미검증 |
| 소유/지시 | 시점별 typed transfer와 유일한 antecedent, person/company 식별 | 보관·전시·기증금 제공을 소유로 치환, 모호한 대명사, 기록 공백을 transfer로 가정 |
| 시간 | 사건 ID와 확정 순서 또는 충돌 없는 날짜 precision | 같은 날짜로 순서 불명, 날짜 범위 겹침, 요약/본문 충돌, 타임존 임의 보완 |
| 수 비교 | 정확한 단위·dimension 정규화 및 Decimal 비교 | 근삿값 경계의 강제 이진화, 질량과 길이 혼합, 변경된 물체의 전후 치수 혼동 |

독립 parser가 실제 표시 EN/KO context를 읽어 canonical graph를 복원하고 그래프 evaluator가 정답을 계산해야 한다. 두 언어·두 lexical형의 그래프가 같아야 하며 answer-code swap은 graph truth를 바꾸지 않아야 한다. 반대 상태 쌍은 계획한 최소 사실만 바꾸어야 한다. source→graph의 사실성 감사와 rendered-text→graph의 논리성 검증은 서로 별도다. 현재 기존 oracle은 네 controlled grammar만 지원하므로 새 source prose를 그대로 넣어 안전하다고 할 수 없다. 새 문법은 oracle extension과 adversarial ambiguity 검사가 필요하다.

## 실행 가능한 사전 amendment 제안 — 아직 적용하지 않음

원 설계의 엄격 template/source split은 유지한다. 동시에 E 이후, R 미개봉 상태에서 다음 **별도 조건부 진단 arm**을 명시적으로 승인·해시 동결할 수 있다.

> R-capability-conditional은 64개의 새로운 내용 family를 목표로 하되, 고정된 검증 renderer 아래의 bilingual statement-truth 수행만 기술한다. 실제 source 및 renderer cluster 수를 모두 보고한다. 0.75 및 0.50 기준은 변경하지 않지만 family 독립성이 확보되지 않으면 원 설계의 family-bootstrap gate 통과로 주장하지 않는다. 정확도와 cluster별 분포는 descriptive 결과로 남긴다. 이 결과는 T의 독립 template 일반화 gate를 열지 않는다.

이 arm의 결과를 본 후 prompt를 재선택하거나 같은 R를 새 gate 검증으로 재사용해서는 안 된다. 독립 source/template가 없는 상태에서는 **G1 numerical/prompt diagnostics 완료**와 **G1 independent capability gate 통과**를 분리해 보고한다. 조건부 진단이 높아도 H1/H2 confirmatory 진행 자격으로 자동 승격하지 않는다. T/O는 계속 봉인한다. 엄격 R 기준 자체를 대체하려면 사용자에게 추론 범위 변경을 명시한 별도 결정이 필요하며, 본 검토는 그 결정을 대신하지 않는다.

실무 권고는 E 엔진·공통 prompt 동결까지 계속 진행하면서 이 catalogue를 확장하는 것이다. 엄격 R64가 준비되기 전에는 검증 가능한 engineering 결과를 공개하고, 미실행 단계를 성공으로 표시하지 않는다. 이 문서와 초안은 결과 관찰 전의 준비성 검토이며 원 설계의 조용한 완화가 아니다.
