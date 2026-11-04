# followup-v2 프롬프트 형식 보정 프로토콜

이 문서는 **새 followup-v2 데이터의 calibration 분할만으로 프롬프트 형식을 선택**하는 사전 규칙이다. 기존 pilot-v1 결과·데이터·판정을 수정하지 않는다. 구현은 `src/followup_calibration.py`이며, 여기의 규칙을 구현했다는 사실과 모델별 실제 보정 실행 완료는 구분한다. 모델별 선택 결과는 실행 시 저장되는 calibration lock과 원시 margin을 확인해야 한다.

## 비교할 형식

| Variant | 입력 변화 | 정답 후보 | 데이터 의존성 |
|---|---|---|---|
| `default` | 원래 prompt 그대로 | ` yes`, ` no` | 없음 |
| `explicit` | 사실로 주어진 전제를 받아들이고 참이면 yes, 거짓이면 no만 답하라는 고정 지시문 추가 | 동일 | 없음 |
| `fourshot` (`4shot` 별칭 허용) | 동일 지시문 + 같은 과제의 TRAIN 예제 네 개 + 원래 target prompt | 동일 | TRAIN의 완전한 matched pair 두 개 |

Four-shot 예제는 true/false 두 개씩, yes/no 두 개씩이다. 첫 matched pair는 yes→no, 두 번째는 no→yes 순서여서 각 pair의 첫 위치가 항상 같은 정답이 되지 않는다. 예제 선택은 pair 내 최대 prompt 길이, 길이 합, pair ID 순으로 정렬하여 가장 짧은 두 pair를 고른다. 이는 **짧은 문항을 이용하는 결과 비의존적 편의 기준**이며, 모델이 잘 푼다는 의미의 난이도 추정은 아니다. 모델 출력이나 calibration 정확도로 예제를 고르지 않는다. 같은 과제의 모든 target은 target label과 무관하게 동일한 네 예제를 사용한다.

TRAIN 이외의 row가 demonstration bank에 섞이거나, pair가 불완전하거나, target과 동일 ID/prompt가 예제에 들어오면 실패한다. Four-shot 형식은 모델 훈련에 쓰지 않는다. ByteTokenizer로 독립 학습하는 E1 모델은 훈련·평가 모두 default 형식을 유지한다.

## 선택과 잠금

1. 각 HF 모델마다 동일한 **새 calibration 문항 전체**에서 각 형식의 full teacher-forced continuation likelihood를 계산한다. 기존 evaluator의 prompt와 answer를 따로 tokenization하는 경계 규칙을 유지한다.
2. `margin = log P(correct | prompt) - log P(foil | prompt)`를 보관한다. `margin > 0`만 정답으로 센다. 정확히 0이면 기권으로 세며 정답 처리하지 않는다.
3. 과제별 정확도, 과제별 yes 응답률, tie 비율, 표본 수, Wilson 95% 구간과 전체 macroaccuracy를 보고한다. yes 응답률은 label 방향을 복원한 `log P(yes)-log P(no) > 0`의 비율이다. 무조건 yes에 가까운 응답은 이 지표에 드러난다.
4. **과제 평균 정확도 최대 → 전체 yes 응답률과 0.5의 차이 최소 → default, explicit, fourshot 순서**로 결정한다. 하나의 모델에는 하나의 형식을 고른다. 과제별 다른 최적 형식이나 D3/D4 성능에 따른 재선택은 허용하지 않는다.
5. `save_lock`으로 형식·기준·모든 형식의 보정 요약·증거 해시를 저장하고, 모델 ID/revision을 함께 묶어 **D1 후보 탐색 전에 고정**한다. 기존 lock에 다른 내용으로 덮어쓰기는 실패한다. 동일 내용의 재시작만 허용한다.
6. D1–D4에 잠긴 변환을 동일하게 적용한다. TRAIN은 default로 둔다. 모델별 변환과 lock을 collection의 `model_info` 및 resume signature에 포함한다. 원시 margin과 토큰 수는 별도 결과 artifact로 보존한다.

`choose_variant`는 `calibration` split만 받는다. 다른 분할을 전달하거나, variant마다 문항 순서/ID/정답이 다르거나, 과제별 true/false 균형이 깨져 있으면 실패한다. 결과가 좋지 않아도 같은 calibration 문항으로 추가 형식을 반복 탐색하지 않는다. 새 설계가 필요하면 버전을 바꾸고 새 calibration/held-out 데이터를 사용한다.

## 문자 span과 context 제한

변환은 record의 ID, split, pair, group, 정답, label, 의미 metadata를 보존한다. 원문 statement의 span에는 prefix의 문자 길이를 더한다. 따라서 hook이 예제의 statement를 잘못 관찰하지 않도록 target span을 명시적으로 유지한다. 예제는 공통 prefix이므로 관측 간 의존성을 추가하며, 이를 독립적인 실험 반복으로 세지 않는다.

`validate_context(rows, tokenizer, model.config, variant)`를 **모델 실행 전** 호출한다. 실제 tokenizer로 원문 prompt와 두 answer를 각각 인코딩하여 가장 긴 continuation까지 포함한 길이를 측정한다. finite model/tokenizer 제한 중 작은 값을 적용하며, 총 길이는 해당 제한보다 엄격히 작아야 한다. 초과 시 잘라내지 않고 실패한다. 실제 네이티브 모델 설정에서 확인한 제한은 다음과 같다.

| 모델 | 고정 revision | max_position_embeddings |
|---|---|---:|
| Qwen/Qwen3-0.6B-Base | `da87bfb608c14b7cf20ba1ce41287e8de496c0cd` | 32768 |
| HuggingFaceTB/SmolLM2-360M | `f8027fd0eaeea54caa13c31d31b9fdc459c38b49` | 8192 |
| allenai/OLMo-2-0425-1B | `a1847dff35000b4271fa70afc5db10fd29fedbdf` | 4096 |

근거는 `configs/models.json`의 local_path가 가리키는 cached `config.json`이다. 각 모델의 tokenizer 제한이 더 작으면 그 값을 따른다. ByteTokenizer 모델은 `max_seq_len`을 사용하며 nondefault 형식을 거부한다. 기존 모델 파일은 변경하지 않았다.

## 능력 확인과 결과 해석

D3의 **각 과제별로 두 대응 모델 모두** 다음을 만족할 때 그 과제를 능력 확인 조건으로 보고한다.

- 정확도 ≥ 0.70
- two-sided Wilson 95% 구간의 하한 > 0.50

`paired_competence_gate`는 같은 순서의 문항에서 측정된 두 모델만 비교하고 과제별 통과 여부를 돌려준다. 이 규칙은 D3 결과를 본 뒤 정렬이나 뉴런 후보를 다시 학습하는 허가가 아니다. 전체 과제의 결과와 이 사전 정의 하위집합의 결과를 함께 보고하며, 미통과 과제는 low-competence 조건으로 분리한다. 통과 과제가 없는 경우 기능 보존 가설의 기각으로 바꾸지 않는다.

**D4의 능력 확인은 D3와 별도로 계산·보고**한다. D4 결과로 D3 형식이나 대응 관계를 변경하지 않는다. D3/D4의 서로 다른 데이터나 모델을 혼합한 능력 확인을 금지한다.

Wilson 구간은 prompt 결과를 이항 관측으로 계산하므로 matched-pair·template 의존성을 완전히 반영하지 못한다. 여기서는 사전 정의된 운영상 능력 기준이며, 연구 효과의 최종 불확실성은 별도의 cluster-aware bootstrap/randomization 분석으로 평가해야 한다. 이 기준 통과만으로 과제 자체가 충분히 대표적이라고 주장하지 않는다.

## Margin 보정의 범위

이번 구현은 **프롬프트 형식 선택만 수행**한다. content-free prior offset 또는 학습된 yes/no 결정 threshold는 사용하지 않는다. 기본 threshold는 0이고 uncorrected sequence log-likelihood margin을 그대로 보고한다. 인과 효과는 원래 margin과 개입 후 margin의 차이며, 능력 보정용 threshold를 끼워 넣지 않는다. 이후 content-free 보정을 추가하려면 calibration에서만 offset을 추정하고, raw/보정 예측을 함께 보존하며, 별도 버전으로 명시해야 한다.

## 통합 API와 검증

```python
from src.followup_calibration import (
    VARIANTS, transform_records, validate_context, choose_variant, save_lock,
    summarize_margins, paired_competence_gate,
)

results = {}
for variant in VARIANTS:
    rows = transform_records(dataset["calibration"], variant, dataset["train"])
    context = validate_context(rows, tokenizer, model.config, variant)
    margins, answer_token_counts = sequence_margins(model, tokenizer, rows, device, batch_size)
    results[variant] = {"rows": rows, "margins": margins}
lock = choose_variant(results)
lock["model_id"] = model_id
lock["model_revision"] = revision
save_lock(calibration_lock_path, lock)  # D1-D4의 어떤 결과보다 먼저 저장

evaluation = {s: transform_records(dataset[s], lock["variant"], dataset["train"])
              for s in ("D1", "D2", "D3", "D4")}
# 각 split의 validate_context를 완료한 뒤 기존 collection/effect evaluator에 전달
```

단위 검증은 span·identity 보존, train-only 완전한 예제 pair, label 균형, 순서 불변성, calibration-only 선택, 동일한 비교 문항, tie와 yes 방향, 비유한 margin 거부, full-continuation 길이 제한, ByteTokenizer 제한, 두 모델 능력 기준, D3/D4 분리, lock 덮어쓰기 방지를 포함한다. 이 검증은 CPU에서 수행하며 모델의 실제 과제 능력 결과를 대신하지 않는다.

CPU 검증 기록: `tests/test_followup_calibration.py`의 9개 테스트 통과. 실제 고정된 `data/followup-v2`의 calibration 768개 문항과 cached tokenizer를 사용한 context 검사는 다음과 같다. 표의 값은 prompt와 더 긴 answer의 토큰 수 합계 최댓값이다. 전부 truncation 없이 제한을 만족했다. 이 검사는 모델 inference나 형식 선택을 수행하지 않았다.

| 모델 | default | explicit | fourshot | context 제한 |
|---|---:|---:|---:|---:|
| Qwen3-0.6B-Base | 39 | 73 | 215 | 32768 |
| SmolLM2-360M | 43 | 79 | 242 | 8192 |
| OLMo-2-0425-1B | 39 | 73 | 215 | 4096 |

## 순차 실행기

`src/followup_calibration_runner.py`는 final checkpoint의 `seed101`, `seed211`, `seed307`, `seed401`, `seed503`와 고정된 `qwen`, `smol`, `olmo`를 순서대로 처리한다. Tiny 모델에는 default만 실행하고 형식을 선택하지 않는다. 초기·중간 checkpoint의 후속 분석도 이 final default lock을 그대로 재사용한다. HF 모델은 세 형식을 비교한다.

```bash
.venv/bin/python -m src.followup_calibration_runner --resume --batch-size 8
```

GPU 실행은 훈련 작업이 끝나고 자원 스케줄러가 허용한 뒤 호출한다. 단위 테스트나 `--help` 호출은 GPU 작업을 시작하지 않는다. 실행기는 `train.jsonl`, `calibration.jsonl`만 읽고 frozen manifest의 파일 해시를 검증한다. D1–D4 JSONL을 열지 않는다.

모델별 결과는 `results/followup-v2/calibration/{name}/` 아래에 저장한다.

- `evidence.npz`: 모든 형식의 raw margin, answer token count, 실제 변환 prompt, 문항 ID/label/concept/group
- `lock.json`: 고정 형식, 모델 ID·revision 또는 checkpoint byte SHA256, TRAIN 해시, 선택 근거, evidence 파일 해시
- `summary.json`: 형식별 과제 능력, context 길이, 실행 시간, peak VRAM, 재시작 signature, lock/evidence 해시

세 파일은 임시 디렉터리에 완성한 뒤 모델별 폴더로 함께 게시한다. `--resume`은 모델·데이터·코드·설정 signature와 artifact 해시가 일치할 때만 재사용한다. 잠긴 내용을 바꾸거나 불완전한 결과에 덮어쓰지 않는다. summary의 D3/D4 상태는 각각 `PENDING_UNTIL_F3_MAPS_FROZEN`, `PENDING_UNTIL_F4_MAPS_FROZEN`으로 남긴다.

다른 실행기는 `load_followup_model(name, checkpoint='final', device='cuda')`로 동일 모델과 안정적인 provenance를 얻고, `transform_for_model(rows, name, train_rows, run_dir)`로 이미 저장된 lock을 적용한다. 후자는 lock/summary 해시 일치와 TRAIN 불변성을 검사한다. 원본 파일의 byte SHA256은 상태값의 parameter hash와 구분하여 기록한다.
