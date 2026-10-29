# 수집 데이터 출처 및 변경 고지

`app/data/lexicon.json`은 아래 공개 자료에서 성적 표현 관련 문자열을 선별·중복 제거하고, 분류·원형 후보·출처 정보를 추가한 파생 데이터입니다. 모든 일반 욕설을 성착취로 분류하지 않습니다. 수집 시점, 정확한 커밋, 원본 URL, 원본 파일 SHA-256, 원본·선별 항목 수는 `app/data/manifest.json`에 기록합니다.

| 출처 | 저작권자 | 라이선스 | 포함 범위 |
|---|---|---|---|
| [korcen](https://github.com/Tanat05/korcen) | Tanat, 2026 | MIT | SEXUAL_PROFANITY_PATTERNS의 리터럴 문자열 및 오탐 제외 문자열 |
| [korean-bad-words](https://github.com/doublems/korean-bad-words) | Doublem.org, 2019 | MIT | 성적·촬영·유포 관련 어근에 해당하는 문자열 |
| [badwords-ko](https://github.com/yoonheyjung/badwords-ko) | upstream LICENSE의 저작권 표기 유지 | MIT | 같은 선별 기준에 해당하는 문자열 |
| [LDNOOBW](https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words) | Shutterstock 및 기여자 | CC BY 4.0 | Korean 목록 중 같은 선별 기준에 해당하는 문자열 |
| [2021 아동·청소년 성착취 피해예방과 인권적 구제 방안 실태조사](https://www.archivecenter.net/kaitArchive/attach/90000/96477/20231017215752233.pdf) | 국가인권위원회 연구용역·이화여대 산학협력단, 2021 | 용어 사실의 제한적 이용 | PDF 450·466쪽의 피해 유형과 관련 용어 일부. 본문·사례·정의는 복제하지 않음 |

원본 MIT·CC BY 라이선스 전문은 `licenses/`에 보관합니다. CC BY 4.0: <https://creativecommons.org/licenses/by/4.0/>. 이 데이터는 원저작자가 해당 도구를 승인하거나 정확성을 보증한다는 의미가 아닙니다.

변경 사항: 일반 욕설·정규식 프로그램·URL·연령을 성적으로 묘사하는 조합을 제외하고, 관련 어휘만 선별했습니다. 일부 흔한 변형에 원형 후보를 붙였으며 확인되지 않은 표현은 표면형을 유지합니다. 피해지원 문서의 다의적 단어에는 뜻을 단정하지 않는 문맥 의존 분류를 붙였습니다. 초성은 실행 시 계산하며 실수집 데이터 개수에 포함하지 않습니다.

기본 11개 시드는 사용자 첨부 자료와 사용자가 지정한 원형 예시를 참고한 별도 검토 항목입니다. 실제 성착취 관련성 및 어휘의 모든 의미를 보증하지 않습니다.

## 이미지 OCR

한국어 OCR은 [RapidOCR](https://github.com/RapidAI/RapidOCR) (Apache-2.0), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) (Apache-2.0)의 한국어 PP-OCRv5 인식 및 경량 검출 ONNX 모델을 사용합니다. ONNX 변환 파일 제공자: [monkt/paddleocr-onnx](https://huggingface.co/monkt/paddleocr-onnx), Apache-2.0 표기. 고정 리비전·파일별 SHA-256·원본 경로는 `app/data/ocr_models.json`에 기록했습니다. 모델은 빌드 시 검증하며 학습 가중치를 변경하지 않았습니다. Apache-2.0 전문은 `licenses/PaddleOCR-Apache-2.0.txt`에 보관합니다.

새 Python 실행 의존성: Pillow(HPND 계열 라이선스, 이미지 검증·방향 보정), RapidOCR(Apache-2.0, OCR 처리·좌표), ONNX Runtime(MIT, CPU 추론). 전이 의존성의 라이선스 전문은 설치 패키지의 dist-info/license 및 배포 메타데이터에 포함됩니다. OpenCV는 headless 배포를 사용합니다. 테스트 이미지에만 추가한 Noto CJK 글꼴은 SIL OFL 1.1이며 프로덕션 이미지에는 포함하지 않습니다.
