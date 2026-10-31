# 모델 4종 GPU 비교 보고서 재현

## 1. 원인

기존 네 후보는 생성·완곡어법 분류·영어 슬랭 탐지 과제가 다르고, 공통 한국어 정답셋의 RTX 속도·정탐 평가가 없습니다. 서로 다른 점수를 종합 순위로 해석하지 않도록 조사와 실측의 범위를 분리했습니다.

## 2. 작업 내용

공식 모델 카드·논문 표·공개 평가 파일·GPU 런타임 문서를 조사했습니다. 현재 설치된 `qwen3.5:4b`를 대조 모델로 CPU 5회·GPU 10회와 준비 호출 각 1회를 새로 측정했습니다. 네 연구 후보를 실행한 실험으로 표시하지 않았습니다. 앱 소스·컨테이너 설정·프로덕션 의존성과 GitHub 원격 저장소는 변경하지 않았습니다.

## 3. 파일

`MODEL_COMPARISON_FILES.txt`에 이번 산출물만 나열했습니다. 주요 보고서는 `output/pdf/slang-model-gpu-comparison.pdf`이며 같은 내용의 Markdown, 회차별 측정 JSON/CSV, 공개 통계 CSV, 계산 결과 JSON, 두 재현 스크립트가 함께 있습니다. ZIP에 모델·venv·캐시·사용자 입력·이미지·DB·로그를 포함하지 않습니다.

## 4. 검증

CPU/GPU 배치·회차 수·128토큰 생성 길이를 확인하고, 공개 평가 JSONL 3,726/1,165개를 직접 세었습니다. 계산값·CSV·PDF의 정합성과 Python 구문·import·Ruff를 검사했습니다. PDF 8쪽을 렌더해 표·한글·잘림을 확인했습니다. 앱 코드를 수정하지 않아 기존 83개 앱 테스트와 Docker 빌드는 이번 조사에서 반복하지 않았습니다.

## 5. 미검증

네 후보의 직접 GPU 실행·같은 한국어 정답셋 정확도, TensorRT 변환 전후, 실제 네 모델 동시 경합, 장시간 부하·전력은 미검증입니다. 따라서 보고서는 한국어 속도·정탐 종합 우승자를 확정하지 않습니다. MLX의 공식 Linux CUDA 지원과 해당 한국어 LoRA의 실제 실행 성공을 구분했습니다.

## 6. 적용·재현 (PowerShell)

보고서는 바로 열어 읽을 수 있습니다. 앱에 적용할 패치는 없습니다. 아래 선택 의존성은 보고서 생성 전용입니다.

```powershell
Set-Location 'D:\Sub\slang'
python -m venv .\artifacts\report-venv
.\artifacts\report-venv\Scripts\python.exe -m pip install -r requirements-report.txt
.\artifacts\report-venv\Scripts\python.exe scripts/build_model_comparison_report.py
```

GPU 대조 실험 재측정은 Python 표준 라이브러리와 실행 중인 로컬 Ollama만 사용합니다. 기본 모델이 설치돼 있어야 하며 자동 다운로드하지 않습니다. CPU 5회·GPU 10회이므로 수 분 걸릴 수 있습니다.

```powershell
python -X utf8 scripts/benchmark_gpu_slang_micro.py --output artifacts/model-comparison-gpu-control.json
.\artifacts\report-venv\Scripts\python.exe scripts/build_model_comparison_report.py --measurements artifacts/model-comparison-gpu-control.json
```

생성기의 고정 보고서는 `qwen3.5:4b`, CPU 5회·GPU 10회 조건을 검사합니다. 글꼴은 Windows 맑은 고딕 기본값을 사용하며, 다른 환경에서는 한글 TTF 파일을 `--font`, `--font-bold`로 지정하세요. 원래 보고서의 첫 준비 시간·digest 등 환경 설명은 해당 원본 실험을 기록한 것이므로 다른 실험의 요약에 재사용하려면 함께 갱신해야 합니다.
