# 성능 측정

## OCR 지연 개선

![OCR 요청 지연 비교](media/performance.png)

2026-10-29 같은 1200×460 PNG 두 개를 개선 전후 조건별 5회 순차 요청했습니다. Windows 호스트에서 loopback HTTP 요청을 시작해 JSON을 모두 읽을 때까지 측정했습니다. Docker의 CPU 2개·메모리 2GiB 제한을 유지했고, 모델 준비를 마친 뒤 매번 실제 OCR 추론을 실행했습니다. 이미지 결과 캐시는 사용하지 않습니다.

| 이미지 | 개선 전 중앙값 | 개선 후 중앙값 | 감소율 | 배속 |
|---|---:|---:|---:|---:|
| 검토 표현 · 18단어 · 6표현 | 2,260.64ms | 414.69ms | 81.66% | 5.45배 |
| 일반 문장 · 4단어 · 표식 없음 | 2,047.48ms | 364.26ms | 82.21% | 5.62배 |

원본 회차는 [개선 전 JSON](benchmarks/ocr-before.json), [개선 후 JSON](benchmarks/ocr-after.json)에 저장했습니다. 각 이미지의 인식 문자열·단어 위치·줄·표식 풀이/상자를 SHA-256으로 비교했으며 전후 모든 회차가 일치합니다. 신뢰도 수치와 실행 시간은 지문에서 제외합니다. 그래프 생성기가 중앙값·회차 수·지문 일치를 다시 확인합니다.

개선 항목은 요청별 모델 초기화 제거, 세션·작업 프로세스 재사용, 회색조 픽셀의 메모리 전달, 중간 PNG 압축 제거, ONNX/OpenCV 스레드 경합 감소입니다. 변경 전과 같은 모델·인식 기준을 유지했습니다. 구현은 [아키텍처](architecture.md#ocr-자원-관리)를 참고하세요.

### 현재 버전 재측정

2026-10-31 같은 입력으로 기능 유지 여부와 현재 지연을 다시 확인했습니다. 이 값은 위의 전후 비교와 다른 실행 세션이므로 별도 기록합니다.

| 입력 | 회수 | HTTP 중앙값 | 결과 |
|---|---:|---:|---|
| 검토 표현 이미지 | 5 | 650.39ms | 18단어 · 6표현 |
| 일반 문장 이미지 | 5 | 529.63ms | 4단어 · 표식 없음 |
| 일반 텍스트 22자 | 20 | 5.419ms | 검토 표현 없음 |
| 늘임 포함 텍스트 17자 | 20 | 5.867ms | 복원 1개 · 검토 표현 2개 |
| 반복 입력 15,003자 | 20 | 44.977ms | 복원 1개 · 검토 표현 없음 |

[현재 OCR 회차](benchmarks/ocr-current.json) · [현재 텍스트 요약](benchmarks/text-current.json). OCR의 문자열·좌표·표식 지문은 기존 비교 입력과 일치합니다. 텍스트는 입력별 준비 요청 1회를 제외한 20회의 HTTP 중앙값입니다. 소규모 합성 입력 실험이며 장시간 부하 시험이나 실제 서비스의 지연 분포를 대표하지 않습니다.

## 측정 해석

- OCR은 `CPUExecutionProvider`입니다. TensorRT·CUDA·NPU로 측정한 수치가 아닙니다.
- 모델 예열은 서버 시작 때 수행하므로 요청 지연에 포함하지 않습니다. 시작 비용은 `/api/ocr/info`의 `startup_ms`에서 별도로 확인합니다.
- 응답의 `ocr_timings.worker_ms`는 `inference_ms`를 포함합니다. 두 값을 더하지 않습니다. `wall_ms`는 호스트에서 관찰한 HTTP 전체 시간입니다.
- PNG 크기·글자 수·정밀 모드·호스트 부하·콜드 스타트에 따라 시간이 달라집니다. 제한된 n=5의 중앙값을 처리량·p95·정밀도·재현율로 해석하지 않습니다.
- OCR 결과 지문 일치는 비교한 두 입력의 회귀 확인입니다. 대규모 정답 이미지에서의 OCR 정확도 검증을 대신하지 않습니다.
- 별도의 한국어 도메인 정답셋이 없어 슬랭 탐지 정확도 점수를 제시하지 않습니다. 테스트 통과 개수도 정확도 비율이 아닙니다.

## 재현

실행 중인 서비스와 `slang-inspector:test` 이미지가 필요합니다. 검사 전용 이미지에는 한글 글꼴이 포함됩니다.

```powershell
docker build --target test -t slang-inspector:test .
docker run --rm --network none --mount "type=bind,source=$((Get-Location).Path),target=/src" -w /src slang-inspector:test python scripts/make_ocr_sample.py
python -X utf8 scripts/benchmark_ocr_speed.py --output artifacts/ocr-measured.json --runs 5
python -X utf8 scripts/benchmark_elongation.py --output artifacts/text-measured.json
```

명령은 각 입력을 다시 추론하며 사용자 이미지·실제 개인정보를 수집하지 않습니다. 기존 측정과 글꼴이 다르면 PNG와 결과 지문이 달라질 수 있으므로 동일 이미지 파일로 비교해야 합니다. 측정값을 바꾸면 README 표와 그래프를 함께 갱신하고 측정일·조건을 기록하세요.

## 모델 비교 연구

[모델 비교 기록](history/MODEL_COMPARISON_README.md)과 `reports/`의 수치는 선택 모델에 대한 별도 조사입니다. 4개 연구 후보를 같은 한국어 정답셋에서 직접 경합시킨 결과가 아닙니다. Qwen 4B의 CPU/GPU 생성 대조 실험도 현재 OCR 또는 슬랭 정탐률의 지표로 합산하지 않습니다.
