"""사전과 일치하는 한글 늘임만 복원하고 원문 전체 구간을 보존합니다."""

import re
from bisect import bisect_right
from collections import defaultdict

TOKEN = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣa-z0-9_]+")
HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]+")
PRIVATE = re.compile(r"https?://\S+|(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}|@[\w가-힣ㄱ-ㅎ]+", re.I)


def syllable(char):
    value = ord(char) - 0xAC00
    if 0 <= value < 11172:
        return value // 588, (value % 588) // 28, value % 28
    return None


def fold_token(token, spans):
    """3회 이상 반복과 같은 모음의 연장을 접고 마지막 종성을 원음절에 합칩니다."""
    compact = []
    i = 0
    while i < len(token):
        end = i + 1
        while end < len(token) and token[end] == token[i]:
            end += 1
        if end - i >= 3:
            compact.append((token[i], (spans[i][0], spans[end - 1][1])))
        else:
            compact.extend((token[j], spans[j]) for j in range(i, end))
        i = end
    chars, mapped = [], []
    i = 0
    while i < len(compact):
        char, source_span = compact[i]
        parts = syllable(char)
        end = i + 1
        if parts is not None and parts[2] == 0:
            onset, vowel, coda = parts
            while end < len(compact):
                following = syllable(compact[end][0])
                if following is None or following[0] != 11 or following[1] != vowel:
                    break
                coda = following[2]
                end += 1
                if coda:
                    break
            if end > i + 1:
                char = chr(0xAC00 + onset * 588 + vowel * 28 + coda)
                source_span = (source_span[0], compact[end - 1][1][1])
        chars.append(char)
        mapped.append(source_span)
        i = end
    return "".join(chars), mapped


class ElongationNormalizer:
    def __init__(self, forms, suffix):
        self.forms = {word for word in forms if 2 <= len(word) <= 60 and HANGUL.fullmatch(word)}
        self.suffix = suffix
        self.by_first = defaultdict(list)
        for word in sorted(self.forms, key=lambda word: (-len(word), word)):
            self.by_first[word[0]].append(word)

    def accepts(self, word):
        if word in self.forms:
            return True
        # 20,000자 입력에서도 사전 분할 탐색 비용이 커지지 않도록 제한합니다.
        if len(word) > 128:
            return False
        reachable = [False] * (len(word) + 1)
        reachable[0] = True
        for start in range(len(word)):
            if not reachable[start]:
                continue
            if start and self.suffix.fullmatch(word[start:]):
                return True
            for form in self.by_first.get(word[start], []):
                if word.startswith(form, start):
                    reachable[start + len(form)] = True
        return reachable[-1]

    def fold(self, normalized, spans, original, protected=()):
        intervals = sorted(
            [
                *protected,
                *(
                    (spans[m.start()][0], spans[m.end() - 1][1])
                    for m in PRIVATE.finditer(normalized)
                ),
            ]
        )
        merged = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        private_starts = [a for a, _ in merged]
        private_ends = [b for _, b in merged]
        pieces, mapped, events = [], [], []
        cursor, offset = 0, 0
        for match in TOKEN.finditer(normalized):
            start, end = match.span()
            token = match.group()
            if token in self.forms or not HANGUL.fullmatch(token):
                continue
            a, b = spans[start][0], spans[end - 1][1]
            private_index = bisect_right(private_ends, a)
            if private_index < len(merged) and private_starts[private_index] < b:
                continue
            restored, restored_spans = fold_token(token, spans[start:end])
            if restored == token or not self.accepts(restored):
                continue
            prefix = normalized[cursor:start]
            pieces.extend((prefix, restored))
            mapped.extend(spans[cursor:start])
            mapped.extend(restored_spans)
            offset += len(prefix)
            events.append(
                {
                    "start": a,
                    "end": b,
                    "surface": original[a:b],
                    "restored": restored,
                    "normalized_start": offset,
                    "normalized_end": offset + len(restored),
                    "kind": "elongation",
                    "review_required": True,
                }
            )
            offset += len(restored)
            cursor = end
        pieces.append(normalized[cursor:])
        mapped.extend(spans[cursor:])
        return "".join(pieces), mapped, events
