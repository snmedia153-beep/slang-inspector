# 개발과 검증

Python 3.12, Docker Desktop Linux 컨테이너, PowerShell을 기준으로 합니다. 화면은 순수 JavaScript이며 별도의 TypeScript 빌드나 프런트엔드 번들링 단계는 없습니다.

## 실행 검사

프로젝트 루트에서 실행합니다.

```powershell
docker compose config --quiet
docker build --target test -t slang-inspector:test .
docker run --rm --network none --cpus 2 --memory 2g slang-inspector:test
docker run --rm --network none slang-inspector:test ruff check app tests --no-cache
docker run --rm --network none slang-inspector:test ruff format --check app tests --no-cache
docker run --rm --network none -e PYTHONPYCACHEPREFIX=/tmp/pycache slang-inspector:test python -m compileall -q app
node --check app/static/app.js
node --check app/static/ocr.js
```

Docker 검사 이미지는 고정된 Python 의존성·OCR 모델·한글 글꼴을 포함합니다. 테스트는 임시 SQLite를 사용하며 사용자 데이터 볼륨을 수정하지 않습니다. 최종 앱 소스를 읽기 전용 마운트해 검사할 경우 `-e PYTHONPATH=/src -w /src`를 함께 지정합니다. 테스트 의존성의 Starlette/httpx 사용 중단 예정 경고가 출력될 수 있습니다.

핵심 회귀는 Unicode/이모지/NFD 원문 위치, 사전 변경·삭제 유지, 문맥 경계·일상 후보, 반복 글자, 초성의 긴 후보 우선 처리, 모델의 미확인 원형 생성 차단, 실제 한국어 OCR와 좌표, 실패·시간 제한·재시작 복구를 확인합니다.

## 브라우저 검사

개발 환경에 Playwright와 Chromium을 준비합니다. 프로덕션 Docker에는 설치하지 않습니다.

```powershell
npm install --no-save --package-lock=false playwright@1.58.2
npx playwright install chromium
docker run --rm --network none --mount "type=bind,source=$((Get-Location).Path),target=/src" -w /src slang-inspector:test python scripts/make_ocr_sample.py
node scripts/verify-ui.cjs
node scripts/verify-ocr-ui.cjs
node scripts/verify-elongation-ui.cjs
node scripts/verify-ocr-initials-ui.cjs
```

별도 경로의 Playwright는 `NODE_PATH`, 기존 Chromium은 `SLANG_CHROMIUM_PATH`, 다른 접속 주소는 `SLANG_UI_URL` 환경변수로 지정합니다. 검사 결과와 화면은 `artifacts/`에 생성합니다. 텍스트 UI 검사는 사전 항목 하나를 등록했다가 삭제하므로 개발용 인스턴스에서 실행하세요. 모델 연결까지 확인하는 `verify-context-ui.cjs`, `verify-watchlist-ui.cjs`는 설정된 로컬 Ollama 모델이 필요합니다.

## README 화면과 그래프 재생성

README 이미지는 실행 중인 앱을 촬영합니다. 원문·개인 식별자가 없는 제작 입력만 사용합니다. 촬영용 `docs/media/ocr-input.png`는 저장소에 포함되어 있습니다. 측정 JSON의 중앙값·회차 수·지문 검증 후 Matplotlib으로 성능 그래프를 만들고, Playwright 캡처를 Pillow로 GIF에 연결합니다. GIF는 실제 처리 속도를 재는 영상이 아닙니다.

```powershell
python -m venv artifacts/portfolio-venv
.\artifacts\portfolio-venv\Scripts\python.exe -m pip install -r requirements-portfolio.txt
.\artifacts\portfolio-venv\Scripts\python.exe scripts/build_portfolio_media.py --prepare
node scripts/capture_portfolio.cjs
.\artifacts\portfolio-venv\Scripts\python.exe scripts/build_portfolio_media.py
```

기본 글꼴은 Windows의 맑은 고딕 또는 설치된 Noto Sans CJK 등입니다. 다른 환경에서는 생성기에 `--font`로 한글 TTF/OTF를 지정합니다. 캡처는 `artifacts/portfolio-frames`, README 자산은 `docs/media`에 저장됩니다. 원문 결과를 바꾸거나 응답을 가로채지 않고 실제 완료된 API 결과를 촬영합니다.

`requirements-portfolio.txt`의 Matplotlib·Pillow는 문서 자산 생성 전용입니다. 앱의 프로덕션 의존성에는 추가하지 않습니다. PDF 모델 연구 보고서는 별도 `requirements-report.txt`와 `scripts/build_model_comparison_report.py`를 사용합니다.

## 문서·패키지 관리

- README에는 제품 소개·실제 화면·측정 조건·실행 방법을 둡니다. 상세 사용법·구조·성능·개발 절차는 `docs/`에서 관리합니다.
- 배포 데이터의 출처·라이선스는 `DATASET.md`, `THIRD_PARTY_NOTICES.md`, `app/data/manifest.json`에 유지합니다.
- 이전 작업 보고서는 `docs/history/`에 보존합니다. 당시 파일 목록은 현재 배포 목록으로 사용하지 않습니다.
- 사용자 입력·DB·로그·모델·캐시·프레임 중간 산출물은 커밋하지 않습니다. README용으로 확인한 캡처·GIF·그래프만 `docs/media/`에 둡니다.
- 전체 소스 패키지가 필요할 때만 `scripts/Package-Slang.ps1`을 실행합니다. Git 커밋·태그를 통한 배포를 기본으로 하며 일반 변경 전달에는 수정 파일만 묶습니다.

```powershell
node scripts/verify-docs.cjs
git diff --check
```
