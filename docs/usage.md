# 사용법과 운영

## 텍스트 검토

텍스트를 붙여넣거나 UTF-8 TXT를 불러와 **텍스트 분석**을 실행합니다. `Ctrl+Enter`도 지원합니다. 최대 20,000자이며 결과에는 원문 강조, 추정 원형, 풀이 근거, 주변 단서, Kiwi 형태소가 포함됩니다. JSON으로 내보낼 수 있습니다.

초성은 단일 정답으로 해독하지 않습니다. 예를 들어 `ㅈㅇ`은 자료의 원형과 일상 후보를 함께 표시하고 채용·이력서 등 문맥을 비교합니다. `ㅇㄹㄴ`, `ㄱㄲ`는 참고 목록에 있지만 확인된 원형이 없어 미확인 후보로 표시합니다. `고오오딩`처럼 사전에 대응하는 늘임은 원문 위치를 보존해 복원합니다. `간다아아아아아안 → 간단`은 복원됐다는 이유만으로 성적 표현이 되지 않습니다.

## 이미지 검토

1. **이미지 OCR**에서 PNG·JPEG·WebP를 선택하거나 끌어놓습니다. 이미지 영역을 선택하고 붙여넣기도 가능합니다.
2. **OCR 및 은어 분석**을 실행하면 검토 표현이 포함된 인식 단어 전체에 빨간 상자가 표시됩니다.
3. 표식이나 키워드를 선택해 같은 위치를 확인합니다. 인식이 다르면 **OCR 글자 확인·수정 → 수정한 글자로 다시 분석**으로 갱신합니다.
4. 표식 PNG·OCR JSON을 저장하거나 **텍스트 화면에서 문맥 비교**로 옮깁니다.

한 표현이 여러 단어에 걸치면 원래 상자들을 함께 표시합니다. OCR에서 같은 줄의 초성이 나뉘거나 완성형 한글에 붙어도 대조합니다. 수정한 글자는 원래 단어 상자에 연결되며, 글자를 지우면 해당 단어를 제외합니다. 원본 이미지를 재작성하지 않습니다.

| 한도 | 값 |
|---|---|
| 이미지 | 10MB · 1,600만 픽셀 · 한 변 16,000px 이하 |
| OCR 글자/단어 | 20,000자 / 2,000단어 이하 |
| OCR 동시 실행 | 1개; 경합 시 429 |
| 작업 프로세스 제한 | 40초; 만료 후 종료 및 다음 요청 시 복구 |
| 인식 크기 | 기본 960 / 정밀 1600 검출 기준 |

작거나 흐린 초성은 잘못 읽힐 수 있습니다. 정밀 모드 또는 글자 수정으로 확인하세요. 이미지 장면 자체의 성적 내용을 분류하는 기능은 포함하지 않습니다.

## 사전과 후보

**은어 사전**에서 표현·추정 원형·의미·분류·메모를 등록하거나 삭제합니다. 최대 5,000개이며 변경은 다음 분석에 반영됩니다. 원형을 생략하면 입력 표현을 사용합니다. 문맥 검토 목록은 일반 단서, 자료로 풀이가 확인된 항목, 미확인 풀이를 구분해 검색합니다.

**새 후보 발굴**은 서로 다른 문서 2~100개를 한 줄에 하나씩 입력합니다. 문서당 5,000자·전체 50,000자 이하입니다. 반복 문서 빈도와 주변 단서를 보고 사람이 원형을 검토해 사전에 등록합니다. 재제출로 같은 묶음의 빈도가 누적되지 않습니다. 이 기능에서 추출한 표현·빈도·단서 정보는 로컬 DB에 저장합니다.

## 운영과 설정

Windows에서는 프로젝트 루트에서 실행합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Slang.ps1
```

시작 스크립트가 실행·중지된 다른 컨테이너의 포트와 실제 바인딩 가능 여부를 확인합니다. 기본 시작 포트는 18640이며 필요하면 `-PreferredPort 18650`을 지정합니다. 포트 확인 직후 다른 프로세스가 선점한 경우 다시 실행하세요.

`.env.example`은 선택 설정의 안내 파일입니다. 스크립트가 만든 `.env`에 필요한 값을 추가합니다. Linux/macOS의 직접 Compose 실행은 사용 가능한 포트를 `.env`에 설정하고 실행하세요.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `SLANG_PORT` | `18640` | 호스트 loopback 포트 |
| `SLANG_OLLAMA_URL` | `http://host.docker.internal:11434` | Docker에서 같은 PC의 Ollama에 접근 |
| `SLANG_CONTEXT_MODEL` | `qwen3.5:9b` | 이미 설치된 로컬 모델 이름 |

```powershell
docker compose up -d --build --wait --wait-timeout 180
docker compose ps
Invoke-RestMethod 'http://127.0.0.1:18640/api/health'
Invoke-RestMethod 'http://127.0.0.1:18640/api/ocr/info'
docker compose logs --tail 80
docker compose stop
```

OCR 모델은 첫 이미지 빌드 때 고정 리비전과 해시를 검증해 포함합니다. 실행 중 네트워크 다운로드는 하지 않습니다. SQLite는 named volume `slang-inspector_slang-data`에 저장됩니다. 컨테이너 재생성은 데이터를 유지하며, `down -v`는 볼륨을 삭제하므로 데이터가 필요한 환경에서 사용하지 마세요.

로컬 모델이 설치·연결되어 있으면 분석 설정의 **로컬 모델로 문장 속 원형 비교**를 선택할 수 있습니다. 최대 6,000자, 입력 후보 48개를 처리하며 모델은 응답 최대 32개·풀이 2개로 제한합니다. 모델은 자동 다운로드하지 않습니다. GPU는 선택 모델의 실행 환경에 따라 사용되며 현재 OCR은 CPU입니다.

## API

JSON 요청의 Content-Type은 `application/json`입니다. **이미지 분석만** 이미지 바이너리를 본문으로 전달하며 multipart를 사용하지 않습니다.

| 메서드 | 경로 | 기능 |
|---|---|---|
| GET | `/api/health`, `/api/ocr/info` | 서버·OCR 준비 상태 |
| GET | `/api/dataset`, `/api/watchlist` | 출처·라이선스·사전 통계·문맥 목록 |
| POST | `/api/analyze` | `{text, threshold, discover}` |
| POST | `/api/ocr/analyze` | PNG/JPEG/WebP 바이너리; `layout=11` 또는 `6` |
| POST | `/api/ocr/reanalyze` | `{image_width, image_height, words, threshold, discover}` |
| GET | `/api/context/info` | 로컬 모델 연결 상태 |
| POST | `/api/context/interpret` | 텍스트의 로컬 문맥 비교 |
| GET / POST | `/api/lexicon` | 사전 조회 / 등록 |
| DELETE | `/api/lexicon/{id}` | 사전 항목 삭제 |
| POST | `/api/discover` | `{texts, min_count}` 문서 묶음 후보 분석 |
| GET / DELETE | `/api/candidates`, `/api/candidates/{id}` | 후보 조회 / 제외 |
| GET | `/api/docs`, `/openapi.json` | 설명 / 전체 스키마 |

```powershell
Invoke-RestMethod 'http://127.0.0.1:18640/api/ocr/analyze' `
  -Method Post -ContentType image/png -InFile '.\review.png'
```

좌표 응답의 `start`, `end`는 Unicode 코드 포인트 기준의 반열린 구간입니다. JavaScript 클라이언트에서는 `Array.from(text).slice(start, end)`로 원문을 얻습니다. `review_required`와 원형 후보의 근거를 함께 확인하세요.
