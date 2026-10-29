# 초기 작업 결과 — 2026-10-29

이 문서는 초기 구축 결과입니다. 후속 게시글·로컬 모델 문맥 해석 업데이트 및 최신 38개 테스트 결과는 `UPDATE_REPORT.md`를 참고하세요.

## 1. 원인

작업 폴더는 비어 있었습니다. 첨부 문서의 아이디어를 실제로 실행할 프로젝트, 사전, 서버 및 Web UI가 필요했습니다. 형태소 분석만으로는 삽입 기호·초성·새로운 은어를 충분히 해독할 수 없으며, 자료의 `add_alias_word`, `add_re_word(score=...)` 예시는 현재 Python 공개 API와 다릅니다.

## 2. 수정 내용

- FastAPI + Kiwi 0.24 `cong` + SQLite 기반 Web UI를 새로 구현했습니다.
- 원문 위치를 보존한 유니코드 정규화, 사전 표현 사이 삽입 기호·숫자·공백 복원, 명시적 원형·의미 매핑, 자모 편집 유사도, 문맥 규칙을 적용했습니다.
- `ㄱㄷ → 고딩`, `ㄷㄸ → 대딸`처럼 문맥 없이도 등록된 원형을 표시합니다. 동일 초성에 원형이 여러 개면 함께 제시합니다.
- 공개 사전 네 곳의 데이터와 피해지원 연구자료의 용어를 실제 수집·정리했습니다. 수집 묶음 635개, 기본 시드 11개를 중복 제거하여 **활성 표현 643개**를 적용했습니다. 현재 **초성 대조 398종**을 계산합니다. 초성 수는 실수집 데이터 수와 합산하지 않습니다.
- 표현별 출처·라이선스·분류를 표시합니다. 원본 커밋·해시는 manifest에 기록했고, 배포 묶음의 무결성을 시작 시 확인합니다. 153개 문자열 기반 오탐 제외 규칙을 반영했습니다.
- 사전 등록·삭제·검색·페이지 이동·JSON 내보내기, UTF-8 TXT 입력, 반복 후보 발굴 및 검토 후 등록 기능을 제공합니다. 입력 원문은 저장하지 않습니다.
- Docker named volume에 사전과 후보만 보관하며, 기존 DB를 마이그레이션합니다. 삭제한 수집 표현은 재가동 시 복원하지 않습니다.
- 다른 실행·중지 컨테이너의 예약 포트와 Windows 바인딩 가능 여부를 확인해 `127.0.0.1:18640`을 선택했습니다. 기존 컨테이너를 변경하지 않았습니다.

## 3. 변경 파일

신규 프로젝트이므로 모두 추가 파일입니다. 전체 상대경로 목록은 `CHANGED_FILES.txt`에 있습니다.

| 파일 / 디렉터리 | 내용 |
|---|---|
| `app/engine.py` | 정규화·초성 원형·사전·자모·문맥 분석 |
| `app/store.py`, `app/seeds.json` | DB·기본 시드·마이그레이션·삭제 기록 |
| `app/main.py`, `app/__init__.py` | 서버·API·입력 검증·보안 헤더 |
| `app/static/` | 분석·사전·후보 발굴·API 안내 UI |
| `app/data/` | 수집 사전·오탐 제외 문자열·출처 manifest |
| `licenses/`, `THIRD_PARTY_NOTICES.md` | 원본 라이선스 및 변경 고지 |
| `Dockerfile`, `compose.yaml` | 런타임·테스트 빌드·볼륨·healthcheck |
| `requirements*.txt`, `requirements.lock`, `pyproject.toml` | 의존성·테스트·정적 분석 설정 |
| `scripts/Start-Slang.ps1` | 포트 검사·빌드·기동·준비 상태 확인 |
| `scripts/collect_lexicon.py` | 공개 데이터 재수집 및 검증 |
| `scripts/verify-ui.cjs`, `tests/test_engine.py` | 브라우저·분석·API·회귀 검증 |
| `scripts/Package-Slang.ps1` | 소스·문서만 ZIP 패키징 |
| `README.md`, `DATASET.md`, `REPORT.md` | 실행·수집·검증 및 적용 안내 |
| `.dockerignore`, `.gitignore` | 사용자 데이터·캐시·빌드 산출물 제외 |

프로덕션 직접 의존성은 FastAPI(HTTP API), Uvicorn(서버), kiwipiepy(한국어 형태소 분석)입니다. 저장·자모 처리에 별도 패키지를 추가하지 않았으며 브라우저 UI는 외부 프레임워크 없이 실행됩니다.

## 4. 검증 결과

| 검증 | 결과 |
|---|---|
| Docker Compose config | 통과 |
| Linux runtime 이미지 production build | 성공 |
| 실제 컨테이너 기동 및 healthcheck | healthy |
| pytest | **24 passed**, 11.09초. 테스트 클라이언트 httpx의 향후 변경 안내 경고 1개 |
| ruff | 통과: 앱·테스트 및 수집 스크립트 |
| Python compileall / import | 통과. 컨테이너 내 구문 검사 및 앱·Kiwi 실제 시작 확인 |
| JavaScript 구문 검사 | 앱·브라우저 검증 스크립트 통과 |
| Chromium UI | 분석·초성 원형·원문 위치·XSS 표시·TXT 입력·JSON 다운로드·사전 등록/삭제·후보 화면 통과 |
| 반응형 | 1280·768·390 CSS px, 세 화면에서 수평 overflow 없음 |
| 브라우저 콘솔 / pageerror | 오류 0개 |
| 실행 중 API | 원형 예시 2개·신규 수집 표현·API 문서 200 응답 확인 |
| 최종 컨테이너 로그 | 정상 시작, 오류 없음 |
| 원문·캐시·런타임 DB 제외 | ZIP 허용 목록으로 소스·문서만 패키징 |

실제 실행 결과: `ㄱㄷ ㄷㄸ` 입력의 추정 원형은 `고딩`, `대딸`이었습니다. 테스트용 일반 문장 5,500자는 후보 없이 약 60.3ms에 처리됐습니다. 이는 해당 장비의 단일 준비 완료 요청 측정이며 일반 성능 보장이 아닙니다. 사전 변경 직후 Kiwi를 재구성하는 첫 분석은 수 초 걸릴 수 있습니다.

## 5. 미검증 항목

- 비공개·신규 은어 전수 탐지, 실제 성착취 여부·의도 판정, 실제 데이터셋의 정밀도·재현율: 라벨 평가셋이 없어 측정하지 않았습니다. 643개 모두가 성착취 은어라는 의미가 아닙니다.
- 학습된 ELECTRA 분류기·MLM probing·FastText·G2P·시각 임베딩은 구현 범위에 포함하지 않았습니다. 현재 문맥 신규 후보는 규칙 기반입니다.
- 실제 불법 사이트 크롤링, 외부 공개 서비스·다중 사용자 인증, 장기 동시 부하 검증은 수행하지 않았습니다.
- Windows의 실제 125%·150% 디스플레이 배율, 모바일 실기기는 직접 검증하지 않았습니다. Chromium viewport로 반응형을 검증했습니다.

## 6. 적용 방법

현재 이미 실행 중입니다: **http://127.0.0.1:18640**

```powershell
Set-Location 'D:\Sub\slang'
# 이후 재빌드·재실행
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Slang.ps1
# 상태·로그
docker compose ps
docker compose logs --tail 80
# 중지
docker compose stop
```

산출물 `artifacts/slang-inspector-files.zip`에는 상대경로를 유지한 추가 소스·설정·사전·라이선스·문서만 포함합니다. `.env`, 런타임 DB, 입력 데이터, 로그, 캐시, 이미지 빌드 산출물, 테스트 스크린샷은 제외합니다. 다른 위치에 적용하려면 ZIP을 빈 프로젝트 디렉터리에 풀고 해당 위치에서 `scripts/Start-Slang.ps1`을 실행하세요. 기존 프로젝트에 덮어쓰는 경우에는 먼저 소스를 백업하세요.

수집 데이터 갱신은 `DATASET.md`의 명시적 수집 명령으로 실행합니다. 실행 중 텍스트를 외부 API로 전송하지 않으며 자동 수집 일정은 생성하지 않았습니다.
