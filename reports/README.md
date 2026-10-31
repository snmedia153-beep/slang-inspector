# 모델 비교 측정 자료

2026-10-29의 연구·대조 실험을 보존합니다. 실행 환경과 당시 제약은 [모델 비교 기록](../docs/history/MODEL_COMPARISON_README.md)에 있습니다.

| 파일 | 내용 |
|---|---|
| `model-comparison-gpu-control.json` | Qwen 4B CPU/GPU 생성 대조 실험 회차 |
| `model-comparison-control-runs.csv` | 같은 회차의 CSV |
| `model-comparison-statistics.json` | 중앙값·부트스트랩·공개 자료 출처 |
| `model-comparison-public-metrics.csv` | 논문·모델 카드의 과제별 공개 수치 |
| `model-comparison-previous-app.json` | 당시 앱의 제한된 문맥 비교 측정 |

공개 과제별 수치를 하나의 한국어 슬랭 탐지 순위로 합산하지 않습니다. 4개 연구 후보의 직접 GPU 경합·공통 정답셋 평가는 수행하지 않았습니다. 현재 앱의 OCR/텍스트 지연은 [성능 문서](../docs/performance.md)에 별도로 기록합니다.
