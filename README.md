# 은어 렌즈

한국어 텍스트에서 사전 표현·난독화·초성 원형·자모 유사 후보를 찾고, 선택적으로 로컬 언어모델로 문맥을 비교하는 Web UI입니다. FastAPI, Kiwi, SQLite와 HTML/CSS/JavaScript로 구성합니다. 외부 분석 API, API 키, GPU가 필요하지 않습니다.

## 실행

Windows 11, Docker Desktop의 Linux 컨테이너 모드에서 PowerShell로 실행합니다.

```powershell
Set-Location 'D:\Sub\slang'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Slang.ps1
```

시작 스크립트는 실행·중지 상태의 모든 다른 컨테이너의 포트 바인딩과 Windows 실제 포트 바인딩 가능 여부를 확인합니다. 18640부터 빈 포트를 찾고 `.env`에 저장합니다. 자기 컨테이너가 사용 중인 포트는 재실행 시 재사용합니다. 포트 확인과 실제 실행 사이에 다른 프로그램이 포트를 차지하면 Docker가 오류를 반환하므로 다시 실행하세요.

기본 접속: [http://127.0.0.1:18640](http://127.0.0.1:18640). 선택된 포트가 다르면 스크립트 출력의 주소를 사용하세요. 호스트의 loopback 주소로만 공개됩니다. 기존 컨테이너는 변경하지 않습니다.

```powershell
# 다른 시작 포트에서 선택
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Slang.ps1 -PreferredPort 18650
# 상태, 로그, 재시작, 중지
docker compose ps
docker compose logs --tail 80
docker compose restart web
docker compose stop
```

첫 빌드에는 PyPI·Docker Hub 접근이 필요하며 Kiwi 모델이 이미지에 포함됩니다. 이후 텍스트 분석은 외부 요청 없이 실행됩니다. 처음 형태소 분석기를 준비하거나 사전 변경 후 재구성할 때 수 초가 걸릴 수 있습니다. Compose에는 메모리 2GB, CPU 2개 상한이 설정되어 있습니다.

## 사용법

- **텍스트 분석:** 입력 또는 UTF-8 TXT 파일을 불러온 후 분석합니다. 최대 20,000자입니다. `Ctrl+Enter`로 실행할 수 있습니다.
- **추정 원형:** `ㄱㄷ`는 `고딩`, `ㄷㄸ`는 `대딸`, `끄.딩.물`은 `고딩물`을 후보로 표시합니다. 초성만 입력해도 사전에 대응 원형이 있으면 표시합니다.
- **자동 초성 대조:** 사전의 표현·원형에서 초성을 생성합니다. 예를 들어 `몰카`의 초성 `ㅁㅋ`도 원형 후보 `몰래카메라`로 연결됩니다. 여러 원형의 초성이 같으면 가능한 원형을 함께 표시합니다.
- **결과 확인:** 원문 표시, 추정 원형, 의미·분류, 근거 강도, 주변 단서, 원문 문자 위치, Kiwi 형태소를 확인합니다. JSON으로 전체 결과를 저장할 수 있습니다.
- **은어 사전:** 표현, 추정 원형, 의미·설명, 분류, 메모, 문맥 의존 여부를 등록하거나 삭제합니다. 최대 5,000개입니다. 원형 생략 시 입력 표현을 유지합니다. 다음 분석부터 적용됩니다.
- **새 후보 발굴:** 서로 다른 문서를 한 줄에 하나씩 입력합니다. 2~100개, 문서당 5,000자·전체 50,000자 이하입니다. 2개 이상 문서에 반복된 문맥·자모 후보를 모읍니다. 원형·의미를 검토하고 사전 등록을 완료하면 반영됩니다. 자동 승인하지 않습니다.

입력 원문과 파일은 서버에 저장하지 않습니다. 분석 결과 JSON은 사용자가 다운로드할 때만 생성됩니다. 사전과 후보의 표현·빈도·단서 분류는 Docker named volume `slang-inspector_slang-data`에 저장되어 컨테이너 재생성 후에도 유지됩니다. 기존 사전 DB는 원형 필드가 자동 추가됩니다.

## 실행 흐름

```text
Web UI → POST /api/analyze → 입력 검증
  → NFKC/NFC·제로폭 문자 정규화 + 원문 위치 대응표
  → 사전 표현 사이 기호·숫자·띄어쓰기 삽입 매칭
  → 사전 원형·초성 인덱스 대조
  → Kiwi 명사 + 자모 편집 거리 + 가까운 주변 단서 규칙
  → 근거·추정 원형·원문 위치가 포함된 JSON → 안전한 DOM 하이라이트

POST /api/discover → 문서 중복 제거 → 후보 문서 빈도
  → SQLite 검토 대기 → 사용자 검토 → 사전 등록 → 다음 분석 시 Kiwi 재구성
```

한글 전체의 띄어쓰기·시각적 유사 문자를 무조건 치환하지 않습니다. 알려진 사전 표현에서 글자 사이 최대 3개 기호·숫자·공백을 허용해 복원합니다. 원문의 서로 다른 문단을 이어 붙이지 않습니다. 원문 위치는 Python Unicode 문자 기준이며 브라우저에서도 같은 기준으로 변환합니다.

## 첨부 자료와 구현 범위

구현한 기능은 전처리, Kiwi 동적 사용자 사전, 명시적 별칭→원형·대표 의미 매핑, 자모 편집 유사도, 규칙에 따른 미등록 문맥 후보, 검토 후 사전 반영입니다. 순수 초성에는 사전 기반 원형 추정도 제공합니다.

Kiwi Python API에는 자료 예시와 동일한 `add_alias_word()`가 없으므로 실제 공개 API인 `add_user_word(..., orig_word=...)`와 별도 매핑을 사용합니다. `orig_word`가 `token.form` 자체를 대표 의미로 바꾼다고 가정하지 않습니다. `/api/analyze`의 `tokens`는 `form`과 `canonical`을 따로 제공합니다. `add_re_word`에는 지원하지 않는 `score` 인자를 전달하지 않습니다. Kiwi 0.24 기본 제공 `cong` 모델을 사용합니다. [Kiwi 공식 API 문서](https://bab2min.github.io/kiwipiepy/)

KcELECTRA/KoCharELECTRA 학습 분류기, MLM probing, FastText 임베딩, G2P, 시각 임베딩과 크롤러는 포함하지 않습니다. 도메인 학습 데이터·분류기·평가셋이 제공되지 않았으므로 이를 학습 모델 판정으로 표시하지 않습니다. 별도로 설치된 로컬 Ollama 모델을 사용해 문맥을 비교하는 선택 기능을 제공합니다. 구현·참고 자료·해석 한계는 `CONTEXT_RESEARCH.md`를 참고하세요. [FastAPI 공식 Docker 배포 문서](https://fastapi.tiangolo.com/deployment/docker/)에 맞춰 Python 이미지에서 서버를 실행합니다.

배포 사전은 공개 수집 묶음 **635개**와 기본 **11개 시드**를 중복 제거한 **643개 표현**입니다. 공개 필터링 사전 네 곳 및 국가인권위원회 연구용역 자료의 관련 용어를 반영했습니다. 일반 성적 은어·비속표현·신체 표현도 포함되며, 643개 모두가 성착취 은어라는 뜻은 아닙니다. 포괄적인 은어 전체를 보장하지 않습니다. 출처·라이선스·커밋·해시는 `app/data/manifest.json`, 변경 및 저작권 고지는 `THIRD_PARTY_NOTICES.md`에 있습니다. 일반 명사는 서로 다른 주변 단서가 2종 이상 나타나면 후보가 될 수 있으므로 오탐이 가능합니다. 신고·예방·연구 등의 단서가 있으면 점수를 낮추고 문맥 신규 후보 추출을 억제합니다. 근거 점수는 확률·위험도·법적 판정이 아니며, 미탐도 가능합니다.

## API

| 메서드 | 경로 | 기능 |
|---|---|---|
| GET | `/api/health` | 준비 상태·사전 수 |
| GET | `/api/dataset` | 수집 출처·라이선스·사전 및 초성 개수 |
| POST | `/api/analyze` | 단일 텍스트 분석 |
| GET / POST | `/api/lexicon` | 사전 조회 / 등록 |
| DELETE | `/api/lexicon/{id}` | 사전 항목 삭제 |
| POST | `/api/discover` | 문서 묶음에서 후보 발굴·저장 |
| GET | `/api/candidates` | 검토 대기 후보 |
| DELETE | `/api/candidates/{id}` | 검토 대기에서 제외 |
| GET | `/api/docs` | API 스키마 문서 |

```powershell
$body = @{ text = 'ㄱㄷ ㄷㄸ'; threshold = 0.82; discover = $true } | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:18640/api/analyze' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

## 검증 실행

```powershell
docker compose config --quiet
docker build --target test -t slang-inspector:test .
docker run --rm --network none --memory 2g slang-inspector:test python -m pytest -q --tb=short -p no:cacheprovider
docker run --rm --network none slang-inspector:test ruff check app tests --no-cache
docker run --rm --network none -e PYTHONPYCACHEPREFIX=/tmp/pycache slang-inspector:test python -m compileall -q app
node --check .\app\static\app.js
```

브라우저 검증 스크립트는 개발용 Playwright와 Chromium이 필요합니다. 별도 개발 환경에서 `playwright`를 설치한 후 실행하거나 설치된 패키지를 `NODE_PATH`로 지정합니다. `SLANG_CHROMIUM_PATH`로 기존 Chromium 실행파일, `SLANG_UI_URL`로 접속 주소를 지정할 수 있습니다. 프로덕션 의존성에는 Playwright가 없습니다.

```powershell
node .\scripts\verify-ui.cjs
```

브라우저 검증은 임시 사전 항목을 등록·삭제하고 스크린샷을 `artifacts/`에 저장합니다. 최종 실행 결과와 미검증 항목은 `REPORT.md` 및 `UPDATE_REPORT.md`를 참고하세요. 문맥 모델의 실제 브라우저 검증은 `scripts/verify-context-ui.cjs`로 실행합니다.

## 파일 구성과 의존성

- `app/engine.py`: 정규화·사전·원형 추정·후보 분석
- `app/store.py`, `app/seeds.json`: SQLite 저장·초기 사전·스키마 보완
- `app/main.py`: API·요청 검증·정적 UI 제공
- `app/static/`: 반응형 Web UI
- `compose.yaml`, `Dockerfile`, `scripts/Start-Slang.ps1`: 빌드·기동·포트 선택
- `tests/test_engine.py`, `scripts/verify-ui.cjs`: 회귀 및 브라우저 검증
- `requirements.txt`, `requirements.lock`: 직접 의존성 및 검증한 전이 의존성 고정

새 프로덕션 의존성은 HTTP 서버를 위한 FastAPI·Uvicorn, 실제 한국어 형태소 분석을 위한 kiwipiepy입니다. 자모 처리와 저장은 표준 라이브러리를 사용하며 프런트엔드 프레임워크를 추가하지 않았습니다. `requirements-dev.txt`는 테스트 도구만 포함합니다.

## 첨부 관리 표의 문맥 목록

첨부 표의 200개 항목(은어 126·일반 35·유인문구 39)을 원문 타입·행 상태와 함께 대조합니다. 표 아래의 `비활성` 버튼은 행 상태로 해석하지 않습니다. 분석 결과의 **첨부 목록 대조**에서 원문 위치, 가능한 풀이, 뜻의 근거, 일상 표현 여부를 확인할 수 있습니다. **은어 사전 → 첨부 문맥 목록**에서 전체 목록을 검색합니다. `GET /api/watchlist`로 전체 자료를 조회할 수 있습니다.

`몸사를 보내면 용돈 줄게`처럼 사진·영상과 대가·요구 문구가 함께 있는 문맥, 촬영·거래·연락 조합을 표시합니다. 문장·게시글 경계를 넘겨 단서를 결합하지 않습니다. 숫자·학교급·성적 지향·지역·신체 부위만으로 성착취를 추정하지 않습니다. 날짜·연락 계정·URL에 든 문자열과 긴 단어 속 부분 일치는 제외합니다. 띄어쓰기·기호 변형과 조사, `몸사판매` 같은 등록어의 연속 결합을 지원합니다.

`ㅇㄹ`에는 사용자가 제시한 `오랄`, 용어집의 `오럴 / 구강성교`, 초성이 같은 `요리·아래·알림`을 비교 후보로 제공합니다. 레시피·식단, 하단·스크롤, 푸시·알림음 같은 지정 단서가 있고 다른 성적 단서와 충돌하지 않으면 일상 문맥 후보를 우선합니다. 이 경우 모델이 다른 뜻을 출력해도 결과에는 `일상 문맥 규칙`이라는 근거와 함께 후보를 표시합니다. 원형이 불확실한 목록 항목은 모델 출력만으로 확정하지 않습니다.

`app/data/context_watchlist.json`의 풀이 근거는 `documented`(출처에서 풀이 용례 확인), `literal`(일반·표면 의미), `hypothesis`(미확인 후보), `unknown`(원형 미확인)으로 나뉩니다. `occurrence_sources`는 검색어 용례이고, `candidates[].sources`는 해당 풀이를 뒷받침하는 자료입니다. 출처에 검색어로 나왔다는 이유만으로 뜻이 검증됐다고 표시하지 않습니다. 새로운 프로덕션 의존성은 추가하지 않았습니다.

새 관리 표는 다음처럼 가져올 수 있습니다. 입력은 UTF-8 TSV 형식의 **전체 표**이며, 출력에는 이번 입력의 행만 남기고 동일 키워드의 기존 풀이를 보존합니다. 기존 파일을 복사해 둔 뒤 실행하세요. 새 키워드는 원형 미확인으로 추가되며, 비활성 행은 분석에서 제외됩니다. 변경 후 컨테이너를 다시 빌드합니다.

```powershell
python .\scripts\import_watchlist.py .\keyword-list.txt .\app\data\context_watchlist.json
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Slang.ps1
node .\scripts\verify-watchlist-ui.cjs
```

이번 변경 내용·조사 자료·검증 범위는 `WATCHLIST_REPORT.md`를 참고하세요.

## 이미지 OCR와 빨간 표식

사이드바 **이미지 OCR**에서 PNG·JPEG·WebP 이미지를 선택하거나 끌어놓고, 이미지 영역에서 붙여넣을 수 있습니다. **OCR 및 은어 분석**을 누르면 한국어 글자를 읽고 기존 사전·초성·문맥 목록으로 대조한 검토 표현을 빨간 상자로 표시합니다. 표식과 키워드를 선택해 위치를 확인하고, 표식 이미지 PNG 또는 좌표·풀이 JSON을 저장할 수 있습니다. 일반어만 일치한 경우에는 빨간 표식을 만들지 않습니다.

OCR은 원본의 인식 단어 상자와 글자 위치를 연결합니다. 상자는 개별 글자 경계가 아닌 해당 표현이 포함된 인식 단어 전체이며, 한 표현이 여러 OCR 단어에 걸치면 여러 상자가 표시됩니다. 초성·저해상도·기울어진 글씨는 오인식될 수 있으므로 **OCR 글자 확인·수정 → 수정한 글자로 다시 분석**을 지원합니다. 수정은 원래 상자 위치에 적용됩니다. 긴 의미 비교는 **텍스트 화면에서 문맥 비교**로 옮겨 기존 로컬 모델 기능을 사용하세요.

업로드는 10MB·1,600만 픽셀·한 변 16,000px 이하, 인식 글자는 20,000자·단어 2,000개 이하입니다. 움직이는 이미지는 지원하지 않습니다. 작은 글씨는 정밀 인식 크기를 시도할 수 있습니다. OCR은 CPU에서 실행하고 이미지·인식 원문을 서버 파일이나 DB에 저장하지 않습니다. 처리 제한은 40초, 동시 OCR은 1개입니다. 업로드 이미지 자체의 성적 내용을 분류하는 기능은 아닙니다.

한국어 PP-OCRv5 모델과 경량 검출 모델은 Docker **빌드 시** 고정 리비전으로 내려받고 SHA-256을 확인합니다. 실행 중 모델을 내려받거나 이미지를 외부 서비스로 보내지 않습니다. 새 직접 의존성은 Pillow(이미지 검증), RapidOCR(한국어 OCR·단어 좌표), ONNX Runtime(CPU 추론)이며 버전은 requirements/lock에 고정했습니다. 원본 출처와 라이선스는 `THIRD_PARTY_NOTICES.md`를 참고하세요.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Slang.ps1
Invoke-RestMethod 'http://127.0.0.1:18640/api/ocr/info'
Invoke-RestMethod 'http://127.0.0.1:18640/api/ocr/analyze' -Method Post -ContentType image/png -InFile '.\sample.png'
```

API의 이미지 분석 요청 본문은 multipart가 아닌 이미지 바이너리입니다. `POST /api/ocr/reanalyze`는 반환받은 `words`와 `image_width`, `image_height`를 JSON으로 받습니다. `GET /api/ocr/info`에서 준비 상태를 확인할 수 있습니다.

브라우저 검증용 합성 이미지는 테스트 이미지에서 생성합니다. Playwright 준비 후 아래 스크립트를 실행합니다.

```powershell
docker run --rm --network none --mount "type=bind,source=$((Get-Location).Path),target=/src" -w /src slang-inspector:test python scripts/make_ocr_sample.py
node .\scripts\verify-ocr-ui.cjs
```

테스트 이미지 빌드와 검사 방법은 위의 검증 절차를 따릅니다. 상세 결과는 `OCR_REPORT.md`에 정리했습니다.

### OCR 속도 최적화

OCR 모델은 서버 시작 시 별도 프로세스에서 준비하고 다음 이미지에도 재사용합니다. 이미지마다 모델을 다시 읽거나 중간 PNG로 재압축하지 않습니다. ONNX 추론은 CPU 스레드 2개, OpenCV는 1개로 제한하고 ONNX 스레드의 대기 중 회전을 꺼서 Compose의 CPU 2개 제한에서 경합을 줄였습니다. 추가 프로덕션 의존성은 없습니다.

기존 이미지 처리 한도와 기본/정밀 모드는 유지합니다. OCR 추론 요청은 모델 재시작을 포함해 40초가 지나면 프로세스를 종료하며, 다음 요청에서 다시 준비합니다. 서버 종료 시에도 OCR 프로세스를 정리합니다. 이미지 결과를 캐시하거나 파일로 저장하지 않습니다. `GET /api/ocr/info`는 `warmed_up`, 실제 `backend`, 모델 준비 시간 `startup_ms`를, 분석 응답은 `ocr_timings`로 전처리·작업 프로세스·추론·텍스트 대조 시간을 제공합니다. `worker_ms`에는 `inference_ms`가 포함되므로 두 값을 더하지 않습니다.

동일한 합성 이미지 각 5회, CPU 2개·메모리 2GB에서 HTTP 전체 시간 중앙값은 검토 표현 샘플 **2.26초 → 0.41초**, 일반 문장 **2.05초 → 0.36초**였습니다. 실제 속도는 이미지 크기·글자 수·정밀 모드·다른 프로그램 부하에 따라 달라집니다. 이번 적용 백엔드는 CPU이며 TensorRT/CUDA/NPU 추론은 활성화하지 않았습니다. 상세 측정·검증과 적용 명령은 `OCR_SPEED_REPORT.md`를 참고하세요.

```powershell
Set-Location 'D:\Sub\slang'
python -X utf8 scripts/benchmark_ocr_speed.py --output artifacts/ocr-speed-measured.json --runs 5
```
