# Native Neuron Conservation Pilot

MASTER.md 기반 E1–E4 실험 진행 중입니다.

- E1: 독립 초기화 모델의 뉴런 대응
- E2: 이종 Base 모델 간 대응
- E3: 의미 기반 정렬 비교
- E4: 독립 테스트에서 인과 효과 비교

## 환경 점검 — 2026-11-04 KST

실제 측정: NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition, VRAM 97,887 MiB, PyTorch 2.14.1+cu130 / CUDA 13.0. CUDA 접근 확인. 시작 시 GPU 사용률 0%, 기존 데스크톱 프로세스 VRAM 약 3.6 GiB. 외장 작업 디스크 여유 약 427 GiB.

샌드박스에서는 GPU가 보이지 않아 실패했으나, 승인된 실행 환경에서 정상 접근을 확인했습니다. 실험은 준비 중이며 아직 가설에 대한 결과는 없습니다.

```mermaid
flowchart LR
    A[환경·문헌·사전 설계] --> B[E1 독립 시드]
    B --> C[E2 이종 모델]
    C --> D[E3 의미 정렬]
    D --> E[E4 인과 정렬]
    E --> F[검증·최종 보고서]
```

각 단계의 실제 결과·통계·시각자료를 완료 시 자동 커밋합니다. 미측정 값은 성공으로 간주하지 않습니다.
