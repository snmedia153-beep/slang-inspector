"""연령·동의·불법성을 추정하지 않고 게시글의 축약 표현과 구조 단서를 설명합니다."""

import re
from datetime import date

RULES = (
    {
        "id": "exposure_abbreviation",
        "pattern": re.compile(r"(?<![가-힣ㄱ-ㅎ])꼭[ \t._·-]*노(?![가-힣ㄱ-ㅎ])"),
        "expansion": "유두 노출(추정)",
        "canonical": "신체 노출을 가리킬 수 있는 축약 표현",
        "category": "노출 관련 은어 후보",
        "note": (
            "짧은 축약어의 가능한 해석입니다. 원형은 확정하지 않았으며 "
            "실제 인물·사진의 노출 여부를 확인하지 않았습니다."
        ),
        "evidence": "inferred_alias",
        "score": 50,
        "needs_context": True,
    },
    {
        "id": "animal_pregnancy_request",
        "pattern": re.compile(
            r"(?<![가-힣])(?:강아지|고양이|돼지|동물|개|말)(?:한테|에게|와|랑|하고)"
            r"[ \t]*(?:(?:나|저|자신)을[ \t]*)?임신(?:을)?[ \t]*"
            r"(?:시켜[ \t]*(?:달라(?:는|고)?|줘)|시키라고)"
        ),
        "expansion": "동물 대상 성적 행위·임신 요구를 암시하는 문구",
        "canonical": "여러 단어가 결합된 동물 관련 성적 문맥",
        "category": "문맥 조합 검토",
        "note": (
            "동물 지칭과 임신을 시키라는 요구의 결합을 검출했습니다. "
            "일반 반려동물 임신 소식과 구분하며 실제 사건·가능성의 확인 결과가 아닙니다."
        ),
        "evidence": "context_combination",
        "score": 75,
        "needs_context": False,
    },
    {
        "id": "child_content_term",
        "pattern": re.compile(
            r"(?:아동(?:[ \t·ㆍ/-]*청소년)?|청소년)[ \t._·-]*포[ \t._·-]*르[ \t._·-]*노"
        ),
        "expansion": "아동·청소년 성착취물",
        "canonical": "성착취물 관련 직접 표현",
        "category": "직접 표현",
        "note": (
            "사용자가 제시한 직접 표현을 설명합니다. "
            "게시물의 실제 내용·위법성을 확인한 결과가 아닙니다."
        ),
        "score": 90,
        "needs_context": False,
    },
    {
        "id": "split_upload",
        "pattern": re.compile(r"(?:나눠|나누어)[ \t._-]*(?:올리기|올려(?:요)?|올림|업로드)"),
        "expansion": "나누어 올리기 / 분할 업로드",
        "canonical": "업로드 방식 표현",
        "category": "일반 게시글 표현",
        "note": (
            "일반 게시물에도 쓰는 표현입니다. 검열 회피나 불법 유포를 뜻한다고 단정하지 않습니다."
        ),
        "score": 50,
        "needs_context": True,
    },
    {
        "id": "no_reupload",
        "pattern": re.compile(
            r"재[ \t._-]*업(?:로드)?[ \t:._-]*(?:ㄴ[ \t._-]*ㄴ|금지|하지[ \t]*마|no[ \t]*no)"
        ),
        "expansion": "재업로드 금지",
        "canonical": "재게시를 원하지 않는다는 요청",
        "category": "일반 게시글 축약어",
        "note": (
            "재업은 재업로드, ㄴㄴ는 부정·금지 표현입니다. "
            "이 문구만으로 동의 여부를 판단할 수 없습니다."
        ),
        "score": 60,
        "needs_context": True,
    },
)
BIRTH_YEAR = re.compile(
    r"(?<![a-z0-9_@])(?P<year>(?:19|20)[0-9]{2}|[0-9]{2}|xx|\*\*|\?\?|○○)[ \t]*년[ \t]*생"
)
HANDLE = re.compile(r"(?<![a-z0-9_.@])@[a-z0-9_][a-z0-9_.]{0,29}(?![a-z0-9_.])")
POST_DATE = re.compile(r"(?<![0-9])(?:19|20)[0-9]{2}-[0-9]{2}-[0-9]{2}(?![0-9])")
COMMENT_COUNT = re.compile(r"\[[ \t]*[0-9]{1,6}[ \t]*\]")
PERSON_LABEL = re.compile(
    r"(?:ㅌㅌ|틱톡|ㅌㅇㅌ|트위터|인스타(?:그램)?)[ \t]+"
    r"(?P<label>[가-힣]{2,4})[ \t]+꼭[ \t._·-]*노(?![가-힣])"
)


def posting_signals(text, spans, original):
    signals = []

    def add(match, kind, explanation, note, group=0):
        start, end = match.span(group)
        a, b = spans[start][0], spans[end - 1][1]
        signals.append(
            {
                "start": a,
                "end": b,
                "surface": original[a:b],
                "kind": kind,
                "explanation": explanation,
                "note": note,
            }
        )

    for match in POST_DATE.finditer(text):
        try:
            date.fromisoformat(match.group())
        except ValueError:
            continue
        add(
            match,
            "post_date",
            "게시글 날짜 형식",
            (
                "목록의 날짜 표기만 검출했습니다. "
                "실제 게시 시각이나 촬영 시각을 확인한 결과가 아닙니다."
            ),
        )
    for match in COMMENT_COUNT.finditer(text):
        add(
            match,
            "comment_count",
            "댓글 수 등 목록 숫자 표기 후보",
            "대괄호 숫자는 댓글 수·번호 등의 표기일 수 있으며 나이나 은어로 해석하지 않습니다.",
        )
    for match in PERSON_LABEL.finditer(text):
        add(
            match,
            "person_label",
            "표제의 이름형 문자열 후보",
            (
                "실제 인물인지 확인하지 않았습니다. "
                "신원과 행동을 추론하지 않고 문맥 모델 입력에서 가립니다."
            ),
            "label",
        )

    for match in BIRTH_YEAR.finditer(text):
        year = match.group("year")
        if not year.isdigit():
            explanation = "출생연도를 가리거나 생략한 표기"
        elif len(year) == 2:
            explanation = f"두 자리 출생연도 '{year}' 표기 · 세기 미확인"
        else:
            explanation = f"출생연도 '{year}년'이라고 쓴 표기"
        add(
            match,
            "birth_year",
            explanation,
            "작성된 표기만 검출했습니다. 실제 출생연도·나이·미성년 여부는 확인하지 않았습니다.",
        )
    for match in HANDLE.finditer(text):
        prefix = text[max(0, match.start() - 20) : match.start()]
        platform = (
            "인스타그램 "
            if re.search(r"(?:인스타(?:그램)?|instagram)[ \t:：]*$", prefix)
            else "SNS "
        )
        add(
            match,
            "social_account",
            platform + "계정 표기",
            "계정을 조회하지 않았습니다. 계정명 속 숫자를 출생연도나 나이로 해석하지 않습니다.",
        )
    return sorted(signals, key=lambda item: item["start"])
