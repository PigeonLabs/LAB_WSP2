# Native Neuron Conservation Pilot

독립적으로 학습된 모델에서 원본 뉴런의 **활성 반응·의미 proxy·인과 역할**이 보존되는지를 검증합니다. [MASTER.md](MASTER.md)에 따른 연구이며, 결과는 각 단계의 실제 측정 파일에서 자동 생성됩니다.

갱신: **2026-11-04 10:59 KST**. 정렬 평가 결과가 있는 단계: **E1, E2**.

## 실험 결과

| Experiment | Hypothesis | Main Metric | Baseline | Proposed | Improvement | CI | Verdict |
|---|---|---|---:|---:|---:|---|---|
| E1 | 독립 초기화 모델의 기능 대응 | D3 response agreement | -0.077 | 0.289 | 0.366 | [0.296, 0.443] | INCONCLUSIVE |
| E2 | 이종 Base 모델의 기능 대응 | D3 response agreement | 모델 쌍별 | 모델 쌍별 | 모델 쌍별 | 상세 표 참조 | INCONCLUSIVE |
| E3 | 의미 정렬의 독립 입력 일반화 | D3 response agreement | 미측정 | 미측정 | 미측정 | 미측정 | INCONCLUSIVE |
| E4 | 독립 인과 효과 일치 | D4 causal effect agreement | 미측정 | 미측정 | 미측정 | 미측정 | INCONCLUSIVE |

이 연구는 제한된 합성 참·거짓 과제의 파일럿입니다. 학습·탐색·정렬·독립 반응 평가·독립 인과 평가를 분리했지만 의미 문법은 공유합니다. 여섯 wrapper 군집의 부트스트랩 신뢰구간과 무작위화 검정은 탐색적입니다. 뉴런 개수를 독립 표본 수로 사용하지 않습니다. 모델의 과제 능력이 낮으면 대응 실패를 기능 보존의 기각으로 해석하지 않습니다. 활성값 유사성·의미 설명·인과 효과 일치를 구분하며, 긍정적 결과도 뉴런 복사나 모델 병합의 안전성을 보장하지 않습니다.

![Held-out competence](artifacts/figures/competence.svg)

정답과 대비 답변의 전체 continuation likelihood를 비교한 D3 정확도입니다. 우연 수준은 50%입니다.

### E1 — Independent Seed Neuron Conservation

- **seed11_seed29**: activation_minus_random Δ=0.366, Δ 95% CI [0.296, 0.443], q=0.0521. 양의 차이가 관찰됨; BH 보정 후 유의 기준 q<0.05 미충족.
- **untrained11_untrained29**: activation_minus_random Δ=0.135, Δ 95% CI [0.104, 0.173], q=0.0391. 양의 차이가 관찰됨; BH 보정 후 유의 기준 q<0.05 충족.
학습 전 대조군에서도 대응이 나타나면 공유된 아키텍처·표면 패턴만으로 상관이 생길 수 있습니다. 학습 모델의 산술·부정 과제 능력이 약한 조건도 있으므로 H1의 일반적 기능 보존 주장은 판단을 보류합니다.

![E1 method comparison](artifacts/figures/e1_methods.svg)

![E1 method comparison](artifacts/figures/e1_seed_heatmap.svg)

[E1 방법·원본 데이터·통계](reports/E1_report.md)

### E2 — Cross-Family Neuron Conservation

- **qwen_olmo**: activation_minus_random Δ=0.118, Δ 95% CI [0.062, 0.172], q=0.0781. 양의 차이가 관찰됨; BH 보정 후 유의 기준 q<0.05 미충족.
- **qwen_smol**: activation_minus_random Δ=0.196, Δ 95% CI [0.143, 0.272], q=0.0312. 양의 차이가 관찰됨; BH 보정 후 유의 기준 q<0.05 충족.
- **smol_olmo**: activation_minus_random Δ=0.059, Δ 95% CI [0.010, 0.108], q=0.2344. 양의 차이가 관찰됨; BH 보정 후 유의 기준 q<0.05 미충족.
모델 쌍별 능력 차이와 같은 yes/no 답변 공간의 영향을 분리해야 합니다. 반응 상관만으로 이종 모델의 동일 의미 기능을 확정하지 않습니다.

![E2 method comparison](artifacts/figures/e2_methods.svg)

![E2 method comparison](artifacts/figures/e2_layers.svg)

[E2 방법·원본 데이터·통계](reports/E2_report.md)

## 독립 초기화 모델 학습

![E1 training](artifacts/figures/e1_training.svg)

- Seed 11: 20,718,080 parameters, 1,200 steps, 32.1 s; 초기 SHA256 `1f145274bd40588b758ecf438de08824cb31b05060e919d843cdb1b8989d64c5`.
- Seed 29: 20,718,080 parameters, 1,200 steps, 24.9 s; 초기 SHA256 `0a284644080f81bc07f6965bbaa3016716092bf1b763e62d1665a0f22b9b4a5a`.

학습 손실 감소는 과제 일반화나 뉴런 보존의 증거를 대신하지 않습니다.

## 재현과 자료

```bash
make smoke
make e1
make e2
make e3
make e4
make pilot
make report
```

- [최종 연구 보고서](reports/FINAL_RESEARCH_REPORT.md)
- [Executive summary](reports/EXECUTIVE_SUMMARY.md)
- [비판적 검토](reports/RESEARCH_CRITIQUE.md)
- [다음 실험](reports/NEXT_EXPERIMENTS.md)
- [문헌 검토](literature_review.md)
- [데이터 설계 한계](reports/DATA_DESIGN_LIMITATIONS.md)
- [실험 코드](src/experiment.py) · [보고서 생성 코드](src/reporting.py)

각 그림 옆 JSON은 실제 그림 값과 원본 파일 경로를 보존합니다. 모델 가중치와 캐시는 저장소에 업로드하지 않고, 정확한 revision과 데이터·체크포인트 해시로 추적합니다. 유료 외부 API는 사용하지 않습니다.
