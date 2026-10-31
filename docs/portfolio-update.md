# 포트폴리오 공개 자료 정돈

작성일: 2026-10-31.

## 1. 원인

README에 기능 추가 시점의 보고가 누적되어 제품 소개·실행·설계·측정 결과를 한눈에 보기 어려웠습니다. 이전 보고서가 루트에 흩어져 있었고, 화면의 첨부 자료 표현과 일부 가상 입력 문구가 실제 운영 도구의 안내와 섞여 있었습니다.

## 2. 수정 내용

- README 상단에 실행 중 Web UI의 텍스트→OCR 흐름 GIF, 실제 OCR 화면, 실측 지연 개선 그래프와 표를 배치했습니다.
- 소개·빠른 실행·API 연결·설계 선택·데이터 범위를 중심으로 README를 재작성하고 상세 문서를 분리했습니다.
- 성능 원시 JSON을 함께 보관하고 측정일·회수·준비 비용·백엔드·한계를 명시했습니다. 10월 29일의 전후 비교와 10월 31일 재측정값을 구분합니다.
- 제품의 문맥 목록·입력 안내를 정리하고 핵심 모듈에 책임과 설계 이유를 설명하는 한국어 주석을 보완했습니다.
- 이전 보고서와 당시 파일 목록은 `docs/history/`로 옮겼습니다. 전체 패키지 스크립트가 새 문서 구조를 따르도록 수정했습니다.
- `.env.example`과 문서 캡처·그래프 생성·링크 검사 스크립트를 제공합니다. 생성 중간 파일과 PDF 출력 폴더는 Git/Docker 빌드 대상에서 제외합니다.
- 기존 로컬의 늘임 복원·OCR 초성 수정 코드와 회귀 검사도 같은 저장소 버전에 포함합니다.

## 3. 변경 파일

| 범위 | 주요 파일 |
|---|---|
| 소개·설명 | `README.md`, `DATASET.md`, `CONTEXT_RESEARCH.md` |
| 상세 문서 | `docs/usage.md`, `docs/architecture.md`, `docs/performance.md`, `docs/development.md` |
| 실제 미디어 | `docs/media/workflow.gif`, `performance.png`, `text.png`, `ocr.png`, `mobile.png`, `ocr-input.png` |
| 측정 근거 | `docs/benchmarks/*.json`, `reports/README.md` 및 기존 모델 비교 측정 자료 |
| 설계 주석·문구 | `app/*.py`, `app/static/`, `app/data/context_watchlist.json` |
| 생성·검증 | `scripts/build_portfolio_media.py`, `capture_portfolio.cjs`, `verify-docs.cjs`, `requirements-portfolio.txt` |
| 이력·패키지 | `docs/history/`, `scripts/Package-Slang.ps1`, `.gitignore`, `.dockerignore`, `.env.example` |
| 기존 로컬 수정 | `app/elongation.py`, `app/initial_candidates.py` 및 관련 엔진·UI·회귀 검사 |

프로덕션 의존성은 추가하지 않았습니다. Matplotlib·Pillow의 별도 문서 환경은 그래프와 GIF 생성에만 사용합니다.

## 4. 검증 결과

- 전체 pytest 139개 통과. Starlette/httpx 의존성의 사용 중단 예정 경고 1개가 있습니다.
- Ruff 및 포맷 검사, Python 구문 컴파일, JavaScript 구문 검사 통과.
- Docker 검사 이미지와 실제 서비스 이미지 빌드, Compose 설정·healthcheck 및 기존 loopback 포트 확인.
- 실제 Chromium의 텍스트·OCR·늘임·초성 화면 검사 통과. 표식 좌표·다운로드·글자 수정·빈 결과·반응형·콘솔 오류를 확인했습니다.
- GIF는 실제 API 응답이 반영된 화면 4장을 사용합니다. GIF 간격은 편집된 장면 간격이며 벤치마크 시간이 아닙니다.
- README의 로컬 링크와 이미지 파일 검증, Markdown 렌더링 후 PC·모바일 이미지 로딩 및 가로 넘침 확인.
- OCR 전후 지문의 일치와 회차별 중앙값을 다시 계산했습니다. 그래프 수치는 원시 측정 JSON에서 생성합니다.

## 5. 미검증 항목

별도의 한국어 도메인 정답셋 정확도·장시간 부하·GPU/NPU OCR은 평가하지 않았습니다. 이번 문서 정리에서 선택적 Ollama 모델의 실응답 검사는 반복하지 않았으며, 관련 결과 검증은 기존 자동 회귀 검사로 확인했습니다. 외부 사용자 인증·외부 공개 배포를 새로 구축한 변경이 아닙니다. 저장소 공개 범위는 유지합니다.

## 6. 적용 방법

같은 Git 저장소에서 최신 커밋을 받은 뒤 프로젝트 루트에서 실행합니다.

```powershell
git pull --ff-only
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Slang.ps1
```

수정 파일 ZIP은 추가·수정된 상대경로만 포함합니다. 이전 루트 보고서의 이동까지 반영하려면 Git 갱신을 사용하세요. 사용자 이미지·원문·DB·로그·캐시·모델은 패키지와 커밋에 포함하지 않습니다. GitHub에는 README의 미디어와 확인한 측정 자료만 함께 게시합니다.
