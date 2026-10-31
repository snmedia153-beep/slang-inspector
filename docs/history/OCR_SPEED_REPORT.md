# OCR 속도 최적화 결과

## 1. 원인

이전 구현은 이미지마다 Python 프로세스를 실행하고 RapidOCR를 import한 뒤 검출·한국어 인식 ONNX 모델을 다시 초기화했습니다. 이미지 검증 후에는 회색조 PNG로 다시 압축하고 자식 프로세스에서 풀었습니다. 검출·인식 세션의 대기 스레드와 OpenCV 스레드가 CPU 2개 제한을 함께 사용했습니다.

사용자가 보고한 약 5초 지연을 조사했으며, 이번 비교 환경에서 재현한 기존 HTTP 전체 시간 중앙값은 검토 표현 샘플 2.26초, 일반 문장 2.05초였습니다. 사용자의 실제 원본 이미지와 동일한 5초 상황을 재현한 수치는 아닙니다.

전체 테스트에서는 여러 FastAPI 앱을 순서대로 생성·종료할 때 앱 라우트의 순환 참조가 이전 Kiwi 모델을 붙잡아 2GB 제한을 넘는 문제도 확인했습니다. 상세 재실행에서 테스트 컨테이너의 OOMKilled=true, exit=137을 확인한 뒤 종료 시 모델 참조를 즉시 해제하도록 수정했습니다.

## 2. 수정 내용

- 서버 시작 시 OCR 전용 프로세스 하나에서 두 모델을 읽고 합성 빈 이미지로 준비합니다. 이후 이미지는 같은 세션에서 매번 실제 추론합니다. 이미지 결과 캐시는 없습니다.
- 부모는 이미지 형식·용량·픽셀·EXIF·알파 검증을 유지하고, 동일한 회색조 픽셀을 메모리 파이프로 전달합니다. 중간 PNG 압축·해제를 제거했습니다.
- ONNX는 intra-op 2개·inter-op 1개, 전체 그래프 최적화를 사용합니다. 대기 중 스레드 회전을 끄고 OpenCV 스레드를 1개로 제한했습니다. 세션별 스레드가 회전하며 CPU를 사용한다는 동작은 [ONNX Runtime 공식 설명](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)을 근거로 확인하고 실제 성능을 비교했습니다.
- 요청 ID로 응답을 대조합니다. 재시작을 포함한 작업 프로세스 제한은 40초이며, 시간 초과·추론 실패·프로토콜 오류 시 프로세스를 종료하고 다음 요청에서 새로 시작합니다. 동시 OCR 1개·429 응답과 기존 입력 한도는 유지했습니다.
- 기본 960/정밀 1600 검출 크기를 매 요청에 적용합니다. 모델·인식 기준·사전·빨간 표식 매핑과 UI는 유지했습니다.
- 서버 종료 시 OCR 프로세스와 Kiwi 모델 참조를 해제합니다.
- `/api/ocr/info`에 실제 백엔드·준비 상태·준비 시간, 이미지 응답에 단계별 시간을 추가했습니다. `worker_ms`는 `inference_ms`를 포함합니다.

새 프로덕션 의존성은 없습니다. 기존에 고정 설치된 ONNX Runtime, OpenCV, OmegaConf를 사용합니다. 모델 변환·양자화·FP16 적용은 하지 않았습니다.

### TensorRT 확인 결과

RTX 3090은 노트북에서 인식됐고, 일회성 `--gpus all` 컨테이너에서 `/dev/dxg` 및 CUDA 드라이버 라이브러리 접근을 확인했습니다. 현재 OCR 이미지의 ONNX Runtime은 CPU 패키지이고 TensorRT 라이브러리는 설치돼 있지 않습니다. 실행 중 OCR 세션에서 확인한 제공자는 `CPUExecutionProvider`입니다.

이번 변경은 **CPU 최적화로 배포**했습니다. TensorRT 활성화나 GPU/NPU OCR 속도를 측정했다고 표시하지 않습니다. TensorRT를 추가하려면 GPU용 ONNX Runtime 및 호환 TensorRT/CUDA 라이브러리, 실행 제공자 연결, 동적 입력 크기의 엔진 준비와 별도 비교 검증이 필요합니다. 관련 조건은 [ONNX Runtime TensorRT 문서](https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html)와 [NVIDIA 지원 표](https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html)를 참고했습니다. 이번 측정에서 먼저 드러난 반복 초기화와 CPU 경합을 제거해 별도 GPU 의존성 없이 지연을 줄였습니다.

## 3. 변경 파일

| 파일 | 변경 목적 |
|---|---|
| `app/ocr_process.py` | 상주 OCR 프로세스·제한 시간·응답 ID·종료 처리 |
| `app/ocr_worker.py` | 세션 준비·재사용·스레드 설정·픽셀 입력 |
| `app/ocr.py` | 기존 이미지 검증과 상주 작업 연결·시간 지표 |
| `app/main.py` | 시작 시 OCR 준비·종료 시 프로세스/모델 해제 |
| `tests/test_ocr.py` | 기존 실패 검증 유지·재사용·모드 전환·종료/복구 회귀 |
| `scripts/benchmark_ocr_speed.py` | 실제 HTTP 지연과 결과 지문 측정 |
| `README.md` | 동작·측정·실행 안내 |
| `OCR_SPEED_REPORT.md` | 결과 보고서 |
| `OCR_SPEED_FILES.txt` | 변경 파일 ZIP 목록 |

Compose, Dockerfile, 프론트엔드 파일, 기존 사전 데이터는 이번 작업에서 변경하지 않았습니다. ZIP에는 위 9개 파일만 저장하며 모델·업로드·DB·로그·venv·캐시·빌드 산출물은 넣지 않습니다.

## 4. 검증 결과

### 실제 속도

Windows 호스트 → 실행 중 Docker의 HTTP 요청 전체 시간입니다. 기존과 최적화 후에 같은 합성 PNG 1200×460px 2개를 각 5회 순차 요청했습니다. Compose CPU 2개·메모리 2GB 제한을 유지했고, 같은 이미지도 OCR 추론을 다시 실행했습니다.

| 이미지 | 기존 중앙값 | 최적화 중앙값 | 감소 | 배속 |
|---|---:|---:|---:|---:|
| 검토 표현 샘플, 18단어·6표현 | 2,260.64ms | 414.69ms | 81.66% | 5.45배 |
| 일반 문장, 4단어·표식 없음 | 2,047.48ms | 364.26ms | 82.21% | 5.62배 |

재배포 후 첫 샘플 요청도 502.45ms였으며, 모델 준비는 서버 시작 전에 1,308.3ms 걸렸습니다. 최적화 후 샘플 5회의 범위는 396.27~530.25ms, 일반 문장은 337.08~389.21ms였습니다. 이는 제한된 합성 이미지 측정이며 모든 이미지에서 같은 속도를 보장하는 수치는 아닙니다.

서버에서 보고한 샘플 추론 시간은 382.8~513.6ms, 텍스트 대조는 1.5~3.9ms였습니다. 단계별 실측으로 모델 재사용 후의 비용도 확인했습니다. 모델 재사용만 적용한 중간 단계의 샘플 중앙값은 764.38ms였고, 스레드 설정까지 적용한 최종 값은 위 표와 같습니다.

변경 전후 모든 회차에서 인식 문자열·단어 위치·행·표식 풀이/상자의 SHA-256 지문이 이미지별로 정확히 일치했습니다. 신뢰도 수치와 분석 실행 시간은 지문 비교 대상에서 제외했습니다. 현재 작업 폴더의 `artifacts/ocr-speed-before.json`, `artifacts/ocr-speed-after.json`에 측정 원본이 있습니다. 이 파일에는 합성 샘플의 시간·개수·지문만 담았으며 변경 ZIP에는 포함하지 않습니다.

### 실행·회귀

전체 pytest **83개 통과(51.23초)**. 최종 소스를 읽기 전용으로 마운트한 Docker 테스트 환경에서 네트워크 없이 CPU 2개·메모리 2GB 제한을 적용했습니다. 기존 Starlette/httpx 사용 중단 예정 경고 1개가 있으며 테스트 실패는 없습니다. 종료 시 모델 해제를 보완한 뒤 앞서 발생한 전체 테스트 OOM 종료도 재발하지 않았습니다.

- OCR 전용 테스트 19개 통과: 실제 한국어 PNG/JPEG/WebP, 빈 이미지·EXIF·잘못된 입력·좌표, 시간 초과/실패/잘못된 응답, 기본→정밀→빈 이미지→기본 순서의 결과 일치, 프로세스 재사용·강제 종료·다음 요청 복구.
- 실제 Chromium OCR 검증 통과: 빨간 SVG 좌표, PNG 저장, 수동 초성 수정, 중립 문장, EXIF, drop/paste, 초기화, 1440/768/390px 정렬. 콘솔 오류 없음.
- 기존 텍스트 Chromium 검증 통과: 분석·Unicode 좌표·XSS 렌더링·TXT 입력·JSON 저장·사전 추가/삭제·후보 화면·반응형. 콘솔 오류 없음.
- 런타임/테스트 Docker 이미지 빌드, Compose 설정 검사, 실제 컨테이너 시작·healthcheck 통과. 기존 `127.0.0.1:18640` 포트와 데이터 볼륨 유지.
- Ruff 전체 앱/테스트 및 벤치마크 검사 통과. Python 구문·핵심 모듈 import 검사 통과.
- 수정 전 스냅샷과 diff 검토: UI·사전·Docker 설정이 그대로이며 변경 범위를 OCR 처리와 생명주기에 한정했습니다.

## 5. 미검증 항목

TensorRT/CUDA/NPU OCR 추론, 실제 사용자가 5초를 경험한 원본 이미지, 대규모 실제 이미지의 정확도/성능 분포는 검증하지 않았습니다. 초성 OCR의 기존 오인식 한계는 유지되며 수동 수정 기능으로 보완합니다. 정밀 모드와 글자가 많은 큰 이미지는 위 기본 모드 샘플보다 오래 걸릴 수 있습니다. UI가 순수 JavaScript이며 별도 TypeScript/Node production build 설정은 없습니다.

## 6. 적용 방법

현재 PC에는 이미 빌드·배포했습니다. [WebUI](http://127.0.0.1:18640/)를 새로고침하고 기존 이미지 분석 버튼을 사용하면 됩니다.

변경 ZIP을 적용할 때에는 프로젝트 루트에 상대경로를 유지해 압축을 풀고 아래 명령을 실행합니다. 현재 데이터 볼륨을 삭제할 필요는 없습니다.

```powershell
Set-Location 'D:\Sub\slang'
Expand-Archive -LiteralPath '.\artifacts\slang-ocr-speed-update.zip' -DestinationPath . -Force
.\scripts\Start-Slang.ps1
Invoke-RestMethod 'http://127.0.0.1:18640/api/ocr/info'
```

기존 합성 샘플이 있을 때 속도 재측정:

```powershell
python -X utf8 scripts/benchmark_ocr_speed.py --output artifacts/ocr-speed-measured.json --runs 5
```

호스트 Python에 Pillow가 설치돼 있다면 `python scripts/make_ocr_sample.py`로 합성 샘플을 생성할 수 있습니다. 새 샘플의 OS별 글꼴이 다르면 원래 측정 지문과 직접 비교할 수 없습니다.
