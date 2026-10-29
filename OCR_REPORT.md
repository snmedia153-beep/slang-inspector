# 이미지 OCR·은어 키워드 빨간 표식 구현 결과

작성일: 2026-10-29

## 1. 원인

기존 WebUI는 텍스트 입력만 분석했고, 이미지에서 글자를 읽거나 탐지한 표현을 이미지 좌표로 표시하는 기능이 없었습니다. OCR 문자열만 가져오면 원문 이미지의 어느 위치인지 연결할 수 없어 인식 단어 좌표와 Unicode 글자 위치를 함께 보존해야 했습니다.

실제 합성 이미지 비교에서는 초기 OCR 후보의 한국어 초성 인식이 부족했습니다. 일반 한국어와 등록 은어의 인식을 개선한 PP-OCRv5 한국어 인식 모델을 적용했습니다. 이 모델도 일부 초성을 잘못 읽으므로 원문 확인·수정 기능을 함께 제공합니다.

## 2. 수정 내용

- 기존 화면을 보존하고 사이드바에 **이미지 OCR** 화면을 추가했습니다.
- PNG·JPEG·WebP 파일 선택, 끌어놓기, 이미지 영역에서 붙여넣기를 지원합니다. 기본·작은 글씨 정밀 인식 크기를 선택할 수 있습니다.
- 이미지의 EXIF 방향을 맞추고 투명 배경을 흰색으로 합성한 뒤 메모리에서 OCR을 수행합니다. 검출은 경량 PaddleOCR 모델, 인식은 한국어 PP-OCRv5 모델, CPU 실행은 ONNX Runtime을 사용합니다.
- OCR 단어의 글자 시작·끝 위치를 구성하고 기존 사전·초성·문맥 규칙·첨부 목록과 대조합니다. 분석 후보, 문맥에 결합된 목록 단서, 원형 미확인 목록 표현에 빨간 검토 표식을 제공합니다. 서울·학생·용돈만 있는 중립 예문은 표시하지 않았습니다.
- 원본 미리보기 위에 SVG 상자를 겹쳐 크기 변경 시 같은 비율로 표시합니다. 개별 글자의 픽셀 경계를 단정하지 않고, 해당 표현이 포함된 인식 단어 전체를 표시합니다. 한 표현에 여러 OCR 단어가 걸치면 여러 상자가 연결됩니다.
- 키워드 선택·표식 선택 연동, 표식 숨기기, 추정 원형·OCR 인식 점수 확인, 표식 PNG 저장, 좌표·분석 JSON 저장을 추가했습니다.
- OCR 글자 확인·수정 후 **수정한 글자로 다시 분석**하면 기존 단어 좌표에 맞춰 새 표식을 만듭니다. 편집 중에는 이전 표식을 지우고 저장 버튼을 비활성화해 오래된 분석 결과를 저장하지 않도록 했습니다.
- **텍스트 화면에서 문맥 비교**로 OCR 글자를 옮겨 기존 로컬 언어모델 분석을 실행할 수 있습니다. OCR 기본 동작에서 큰 생성 모델을 호출하지 않습니다.
- 업로드 10MB, 1,600만 픽셀, 한 변 16,000px, OCR 단어 2,000개·20,000자 제한을 적용했습니다. 단어별 수정은 100자 이하입니다. 움직이는 이미지·지원하지 않는 형식·좌표 범위 오류는 명시적으로 거절합니다.
- OCR은 40초 제한의 별도 프로세스에서 1개씩 실행합니다. 시간 초과·엔진 실패·잘못된 응답·중복 실행을 성공으로 처리하지 않습니다. 이미지는 stdin으로 전달하며 이미지·OCR 원문을 서버 파일·DB에 기록하지 않습니다.

새 직접 실행 의존성은 **Pillow 13.0.0**(이미지 검증·방향 보정), **RapidOCR 3.10.0**(OCR와 단어 좌표), **ONNX Runtime 1.26.0**(CPU 추론)입니다. 기존 의존성에는 이미지 해석과 한국어 OCR 기능이 없어 추가했습니다. 전이 의존성도 lock 파일에 고정했습니다. 테스트에만 Noto CJK 글꼴·fontconfig를 사용하며 프로덕션 이미지에는 포함하지 않습니다.

OCR 모델은 고정된 리비전과 SHA-256으로 **빌드 시** 검증해 이미지에 포함합니다. 지정한 모델 세 파일은 약 15.1MiB이며 모델 캐시·가중치는 업데이트 ZIP에 넣지 않습니다. 실행 중 외부로 이미지를 보내거나 모델을 내려받지 않습니다. [RapidOCR의 로컬 모델 구성](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/how_to_use_offline_model/), [단어 좌표 옵션](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/parameters/), [변환 모델 출처](https://huggingface.co/monkt/paddleocr-onnx)를 참고했습니다. 고정 리비전·해시는 `app/data/ocr_models.json`, 라이선스·저작권 표기는 `THIRD_PARTY_NOTICES.md`에 있습니다.

## 3. 변경 파일

전체 경로 목록은 `OCR_FILES.txt`에 있습니다. `artifacts/slang-ocr-update.zip`은 이번 변경 파일만 담은 패키지입니다.

| 파일 | 역할 |
| --- | --- |
| `app/ocr.py`, `app/ocr_worker.py` | 이미지 검증·OCR 프로세스·좌표 연결·재분석 |
| `app/main.py` | OCR 준비 상태·바이너리 업로드·수정 재분석 API |
| `app/data/ocr_models.json`, `scripts/fetch_ocr_models.py` | 모델 리비전·해시 및 빌드 시 검증 다운로드 |
| `app/static/ocr.js`, `index.html`, `app.js`, `styles.css` | 이미지 화면·업로드·표식·수정·저장 |
| `app/static/api.html` | 추가 API 안내 |
| `requirements.txt`, `requirements.lock`, `Dockerfile` | CPU OCR 실행 환경·모델 포함 |
| `tests/test_ocr.py` | 실제 OCR 및 좌표·실패 처리 회귀 검사 |
| `scripts/make_ocr_sample.py`, `scripts/verify-ocr-ui.cjs` | 합성 이미지 생성·브라우저 검증 |
| `README.md`, `THIRD_PARTY_NOTICES.md`, `licenses/PaddleOCR-Apache-2.0.txt` | 사용 방법·추가 의존성·라이선스 |
| `OCR_REPORT.md`, `OCR_FILES.txt` | 결과와 적용 안내 |

## 4. 검증 결과

- 최종 Docker 테스트 이미지에서 외부 소스 마운트 없이 **pytest 80개 통과**. 네트워크 차단·메모리 2GiB·CPU 2개 조건에서 실제 한국어 OCR을 포함해 검사했습니다. 기존 Starlette/httpx 사용 중단 예고 경고 1건이 있고 실패는 없습니다.
- 실제 OCR로 한국어 키워드·정상 문장·PNG/JPEG/WebP·빈 이미지·EXIF 방향 보정을 검사했습니다. Unicode 위치·반복 표현·여러 상자에 걸친 표현·초성 수정·문맥 단서·원형 미확인 표시를 확인했습니다.
- 잘못된 이미지·업로드 크기·좌표 범위·NaN 점수·중복 실행·40초 시간 초과·엔진 실패·잘못된 좌표 응답·다른 사이트 요청 거절을 검사했습니다.
- Python 구문·import·Ruff·JavaScript 구문·`pip check`·`docker compose config` 통과. 정적 JavaScript 프로젝트이므로 별도 TypeScript 검사나 Node 번들 빌드는 없습니다.
- Chromium에서 실제 OCR·빨간 SVG 표식·키워드 선택·표식 숨기기·수정 재분석·PNG 다운로드·텍스트 화면 이동·EXIF 방향·끌어놓기·붙여넣기·이미지 지우기를 확인했습니다. OCR 브라우저 검사 콘솔 오류 0건입니다.
- 1440px 데스크톱 및 768/390px 화면에서 이미지와 SVG의 경계 오차 1px 미만·가로 넘침 없음을 확인했습니다. 스크린샷도 검토했습니다.
- 최종 합성 이미지에서 **18개 OCR 단어·6개 검토 표현**, OCR·분석 약 **3.98초**였습니다. 실행 중인 다른 앱이 있는 환경의 단일 사례이며 일반 성능 보장은 아닙니다.
- 저장된 PNG는 1200×460 크기를 유지했고 실제 빨간 픽셀을 확인했습니다. 다운로드 기능이 원본만 저장하는 오류가 없는지 검사했습니다.
- 기존 텍스트 분석·사전 등록/삭제·TXT 입력·JSON 내보내기·Unicode/XSS·모바일 화면과 문맥 목록·게시글 분석을 브라우저 회귀 검사했습니다.
- runtime·test Docker 이미지 실제 빌드, 고정 모델 파일 SHA-256 검증, 오프라인 실제 OCR, 기존 서비스 health 및 OCR 준비 상태 확인 완료. 기존 주소 **http://127.0.0.1:18640/**에서 정상 실행 중입니다. 기존 포트 선택 스크립트로 다른 컨테이너의 예약 포트와 충돌 여부를 확인했습니다.
- 최종 diff를 검토했습니다. 기존 텍스트 분석 엔진·사전·DB 스키마·Compose 설정을 변경하지 않았습니다.

## 5. 미검증 항목과 한계

OCR이 읽지 못하거나 잘못 읽은 글자는 은어 사전에 있어도 자동으로 표시되지 않을 수 있습니다. 합성 예시에서도 일부 `ㄱㄷ·ㅇㄹ` 표기는 잘못 읽혔습니다. 인식된 단어를 실제 이미지와 비교하고 수정 기능을 사용해야 합니다. 모델이 출력한 글자를 특정 은어가 되도록 임의 치환하지 않습니다.

작은 글씨·복잡한 배경·저대비·특수 글꼴·손글씨·물리적으로 회전한 글·여러 열 화면 전체에 대한 정확도 평가는 수행하지 않았습니다. 단어 상자는 OCR 모델이 추정한 범위이며 글자 단위의 정밀 위치를 보장하지 않습니다. 수동 수정은 원래 상자를 유지하므로 이미지에 없는 단어를 입력하면 그 상자에 수정한 후보가 표시됩니다.

미등록 은어의 모든 의미, 실제 사람의 나이·의도·동의 여부·게시물의 불법성은 판정하지 않습니다. 빨간색은 검토 표시입니다. OCR 점수는 은어일 확률이나 불법성 확률이 아닙니다. 이미지 자체의 시각적 성적 내용을 분류하거나 얼굴을 식별하지 않습니다.

최대 크기 이미지의 장시간 부하·모든 EXIF 회전 조합·모든 Windows 배율·실제 시스템 클립보드 권한/브라우저별 차이는 검증하지 않았습니다. 드롭·붙여넣기 브라우저 검사는 합성 File/DataTransfer 이벤트로 동작을 확인했습니다. NPU/GPU OCR은 적용하지 않았습니다.

## 6. 적용 방법

현재 작업 폴더와 Docker 서비스에는 적용 완료했습니다. WebUI를 새로고침한 뒤 **이미지 OCR → 이미지 선택 → OCR 및 은어 분석** 순서로 사용하세요.

기존 프로젝트에 변경 ZIP을 다시 적용할 때의 PowerShell:

```powershell
Set-Location -LiteralPath 'D:\Sub\slang'
Expand-Archive -LiteralPath '.\artifacts\slang-ocr-update.zip' -DestinationPath '.' -Force
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Slang.ps1
```

이미지 빌드에는 Python 패키지와 고정 OCR 모델을 받을 네트워크 연결이 필요합니다. 기존 Docker 볼륨을 삭제할 필요가 없습니다. 시작 스크립트가 다른 포트를 선택했다면 출력된 Ready 주소로 접속하세요.

API 직접 확인:

```powershell
Invoke-RestMethod 'http://127.0.0.1:18640/api/ocr/info'
Invoke-RestMethod 'http://127.0.0.1:18640/api/ocr/analyze' -Method Post -ContentType image/png -InFile '.\sample.png'
```

분석 요청 본문은 이미지 바이너리입니다. 수정 재분석은 `POST /api/ocr/reanalyze`에 `{image_width,image_height,words}` JSON을 보냅니다. 재현용 합성 이미지·브라우저 검증 명령은 README에 있습니다. ZIP에 사용자 이미지·원문·DB·로그·가상환경·패키지 캐시·OCR 가중치·빌드 산출물은 포함하지 않습니다.
