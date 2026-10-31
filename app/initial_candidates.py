"""완성형 한글에 붙은 초성을 허용하고 더 긴 초성열의 부분 일치를 막습니다."""

import re

INITIAL = re.compile(r"[ㄱ-ㅎ]{2,10}")
EDGE = re.compile(r"[ㄱ-ㅎa-z0-9_]", re.I)
GAP = r"[ \t._·-]{0,2}"


def initial_key(text):
    compact = re.sub(r"[ \t._·-]", "", text)
    return compact if INITIAL.fullmatch(compact) else None


def initial_boundary(text, start, end):
    return not (
        (start and EDGE.fullmatch(text[start - 1]))
        or (end < len(text) and EDGE.fullmatch(text[end]))
    )
