# Executive Summary

갱신: 2026-11-04 10:59 KST. 실행 완료와 가설 지지는 다른 판단입니다.

| Experiment | Hypothesis | Main Metric | Baseline | Proposed | Improvement | CI | Verdict |
|---|---|---|---:|---:|---:|---|---|
| E1 | 독립 초기화 모델의 기능 대응 | D3 response agreement | -0.077 | 0.289 | 0.366 | [0.296, 0.443] | INCONCLUSIVE |
| E2 | 이종 Base 모델의 기능 대응 | D3 response agreement | 모델 쌍별 | 모델 쌍별 | 모델 쌍별 | 상세 표 참조 | INCONCLUSIVE |
| E3 | 의미 정렬의 독립 입력 일반화 | D3 response agreement | 미측정 | 미측정 | 미측정 | 미측정 | INCONCLUSIVE |
| E4 | 독립 인과 효과 일치 | D4 causal effect agreement | 미측정 | 미측정 | 미측정 | 미측정 | INCONCLUSIVE |

이 연구는 제한된 합성 참·거짓 과제의 파일럿입니다. 학습·탐색·정렬·독립 반응 평가·독립 인과 평가를 분리했지만 의미 문법은 공유합니다. 여섯 wrapper 군집의 부트스트랩 신뢰구간과 무작위화 검정은 탐색적입니다. 뉴런 개수를 독립 표본 수로 사용하지 않습니다. 모델의 과제 능력이 낮으면 대응 실패를 기능 보존의 기각으로 해석하지 않습니다. 활성값 유사성·의미 설명·인과 효과 일치를 구분하며, 긍정적 결과도 뉴런 복사나 모델 병합의 안전성을 보장하지 않습니다.

- [E1 상세 보고서](E1_report.md)
- [E2 상세 보고서](E2_report.md)
- [E3 상세 보고서](E3_report.md)
- [E4 상세 보고서](E4_report.md)
