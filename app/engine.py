import json
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from kiwipiepy import Kiwi

from app.post_rules import RULES, posting_signals
from app.watchlist import NEUTRAL, Watchlist

TRIGGERS = {
    "연락 경로": ("텔그", "텔레그램", "오픈채팅"),
    "접근 안내": ("좌표", "비번", "입장코드", "링크"),
    "거래·유포": ("교환", "판매", "공유방", "배포", "구매"),
}
PROTECTIVE = ("신고", "예방", "근절", "피해", "수사", "교육", "연구", "보도", "금지", "주의")
POLYSEMOUS = {"고등어", "골뱅이", "국산", "국노", "망가", "유모", "노모", "에로", "하드코어"}
STOP = set(
    (
        "영상 사진 자료 콘텐츠 파일 오늘 내일 이것 저것 사람 확인 가능 무료 유료 "
        "신청 이름 사용 안내 문맥 테스트"
    ).split()
)
STOP.update(word for words in TRIGGERS.values() for word in words)
STOP.update(PROTECTIVE)
CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNGSUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONGSUNG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
GAP = r"[ \t.·_\-~!@#$%^&*♡♥☆★0-9]{0,3}"


def normalize(text):
    """NFKC per grapheme-like cluster, preserving original Unicode code-point spans."""
    clusters = []
    for i, char in enumerate(text):
        # Canonical Jamo and combining marks belong with the preceding cluster.
        if clusters and (unicodedata.combining(char) or "\u1160" <= char <= "\u11ff"):
            clusters[-1][0] += char
            clusters[-1][2] = i + 1
        else:
            clusters.append([char, i, i + 1])
    chars, spans = [], []
    for cluster, start, end in clusters:
        # NFC after NFKC composes decomposed Hangul while retaining span provenance.
        for char in unicodedata.normalize("NFC", unicodedata.normalize("NFKC", cluster)):
            if unicodedata.category(char) == "Cf":
                continue
            # Keep compatibility Jamo for readable initial-consonant aliases.
            if "\u1100" <= char <= "\u11ff":
                char = unicodedata.normalize("NFKD", char)
                lookup = {unicodedata.normalize("NFKD", x): x for x in CHOSUNG + JUNGSUNG}
                char = lookup.get(char, char)
            for lower_char in char.lower():
                chars.append(lower_char)
                spans.append((start, end))
    return "".join(chars), spans


def jamo(text):
    result = []
    for char in text:
        n = ord(char) - 0xAC00
        if 0 <= n < 11172:
            result.extend((CHOSUNG[n // 588], JUNGSUNG[(n % 588) // 28]))
            if n % 28:
                result.append(JONGSUNG[n % 28])
        else:
            result.append(char)
    return "".join(result)


def initials(text):
    compact = text.replace(" ", "")
    if not 2 <= len(compact) <= 10 or not all("가" <= c <= "힣" for c in compact):
        return None
    return "".join(CHOSUNG[(ord(c) - 0xAC00) // 588] for c in compact)


def similarity(left, right):
    left, right = jamo(left), jamo(right)
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        nxt = [i]
        for k, b in enumerate(right, 1):
            nxt.append(min(nxt[-1] + 1, row[k] + 1, row[k - 1] + (a != b)))
        row = nxt
    return 1 - row[-1] / max(len(left), len(right), 1)


def context_at(text, start, end):
    # Sentence-local and within 64 characters; unrelated paragraphs cannot lend evidence.
    left = (
        max(
            text.rfind("\n", 0, start),
            text.rfind("!", 0, start),
            text.rfind("?", 0, start),
            text.rfind("。", 0, start),
        )
        + 1
    )
    right = min([pos for sep in "\n!?。" if (pos := text.find(sep, end)) >= 0] + [len(text)])
    window = text[max(left, start - 64) : min(right, end + 64)]
    found = [
        {"group": group, "words": [w for w in words if w in window]}
        for group, words in TRIGGERS.items()
        if any(w in window for w in words)
    ]
    protective = [word for word in PROTECTIVE if word in window]
    return found, protective


class Engine:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.version = -1
        self.kiwi = None
        self.watchlist = Watchlist()
        bundle = json.loads((Path(__file__).parent / "data" / "lexicon.json").read_text("utf-8"))
        self.exclusion_pattern = re.compile(
            "|".join("[ \\t]*".join(re.escape(c) for c in word) for word in bundle["exclusions"])
        )
        knowledge = json.loads(
            (Path(__file__).parent / "data" / "context_knowledge.json").read_text("utf-8")
        )
        sources = {source["id"]: source for source in knowledge["sources"]}
        self.reference_initials = defaultdict(list)
        for entry in knowledge["entries"]:
            if not entry.get("fast_detection"):
                continue
            for candidate in entry["candidates"]:
                self.reference_initials[entry["term"]].append(
                    {
                        "alias": entry["term"],
                        "expansion": candidate["expansion"],
                        "canonical": entry["category"],
                        "category": entry["category"],
                        "needs_context": True,
                        "note": entry["note"],
                        "evidence": "reference_initial",
                        "provenance": [
                            {**sources[s], "license": sources[s].get("license", "용례 참고")}
                            for s in candidate["sources"]
                        ],
                    }
                )
        self.reload()

    def reload(self):
        with self.lock:
            version = self.store.version()
            if version == self.version:
                return
            entries = self.store.entries()
            kiwi = Kiwi(num_workers=2, model_type="cong")
            for canonical in sorted({entry["canonical"] for entry in entries}):
                kiwi.add_user_word(canonical, "NNP", 5.0)
            # Public Python API: add_user_word(..., orig_word=...), not add_alias_word.
            for entry in entries:
                kiwi.add_user_word(entry["alias"], "NNP", 5.0, orig_word=entry["canonical"])
            kiwi.add_re_word(r"[ㄱ-ㅎ]{2,4}물?", "NNP")
            kiwi.tokenize("분석기 준비")
            self.kiwi = kiwi
            self.entries = entries
            self.alias_map = {normalize(e["alias"])[0]: e["canonical"] for e in entries}
            self.initial_index = defaultdict(list)
            for entry in entries:
                for key in {initials(entry["alias"]), initials(entry["expansion"])} - {None}:
                    self.initial_index[key].append(entry)
            self.patterns = [
                (entry, re.compile(GAP.join(re.escape(c) for c in normalize(entry["alias"])[0])))
                for entry in entries
            ]
            self.version = version

    def analyze(self, text, threshold=0.82, discover=True):
        started = time.perf_counter()
        with self.lock:
            self.reload()
            normalized, spans = normalize(text)
            signals = posting_signals(normalized, spans, text)
            watchlist_hits, watchlist_contexts = self.watchlist.scan(
                normalized, spans, text, signals
            )
            neutral_spans = [
                (h["start"], h["end"]) for h in watchlist_hits if h["group"] in NEUTRAL
            ]
            account_spans = [
                (s["start"], s["end"])
                for s in signals
                if s["kind"] in {"social_account", "person_label"}
            ]
            matches = []

            def add(start, end, entry, method, score, reasons, sim=None):
                original_start, original_end = spans[start][0], spans[end - 1][1]
                triggers, protective = context_at(normalized, start, end)
                if protective:
                    score = max(15, score - 25)
                    reasons.append("보도·예방·피해 대응 용례 가능: " + ", ".join(protective))
                if entry and entry["needs_context"] and len(triggers) < 2:
                    reasons.append("문맥 단서가 부족하여 의미를 확정할 수 없습니다.")
                matches.append(
                    {
                        "start": original_start,
                        "end": original_end,
                        "surface": text[original_start:original_end],
                        "term": normalized[start:end],
                        "expansion": entry["expansion"] if entry else None,
                        "alternatives": [],
                        "canonical": entry["canonical"] if entry else "미등록 은어 검토 후보",
                        "category": entry["category"] if entry else "문맥 후보",
                        "provenance": entry.get("provenance", []) if entry else [],
                        "evidence": entry.get("evidence", "manual") if entry else "heuristic",
                        "method": method,
                        "score": score,
                        "similarity": sim,
                        "reasons": reasons,
                        "context": triggers,
                        "note": entry["note"]
                        if entry
                        else "주변 단서로 추출한 명사이며 은어 여부는 미확인입니다.",
                        "review_required": True,
                    }
                )

            for rule in RULES:
                for match in rule["pattern"].finditer(normalized):
                    entry = {
                        **rule,
                        "source": "rules",
                        "evidence": rule.get("evidence", "posting_rule"),
                    }
                    add(
                        *match.span(),
                        entry,
                        "pattern",
                        rule["score"],
                        [
                            "게시글의 복합 표현·축약 규칙 일치",
                            "주변 문구와 실제 내용은 별도로 검토해야 합니다.",
                        ],
                    )
                    matches[-1]["rule_id"] = rule["id"]

            for hit in watchlist_hits:
                if not hit["detect"]:
                    continue
                entry = {
                    "expansion": hit["meaning"],
                    "canonical": hit["group_label"],
                    "category": "첨부 목록 · " + hit["group_label"],
                    "needs_context": True,
                    "note": hit["note"],
                    "evidence": "watchlist_" + hit["evidence"],
                    "provenance": hit["definition_sources"],
                }
                add(
                    hit["normalized_start"],
                    hit["normalized_end"],
                    entry,
                    "watchlist",
                    40,
                    [
                        "첨부 목록의 활성 항목 일치",
                        "뜻의 근거: " + hit["evidence"],
                        "목록 일치와 문맥 조합은 실제 의도·불법성 판정이 아닙니다.",
                    ],
                )
                matches[-1]["alternatives"] = [c["expansion"] for c in hit["candidates"]]

            excluded_spans = [match.span() for match in self.exclusion_pattern.finditer(normalized)]
            for entry, pattern in self.patterns:
                for match in pattern.finditer(normalized):
                    start, end = match.span()
                    if any(spans[start][0] < b and spans[end - 1][1] > a for a, b in account_spans):
                        continue
                    if entry["source"] == "corpus" and any(
                        start < b and end > a for a, b in excluded_spans
                    ):
                        continue
                    if entry["alias"].isascii() and (
                        (start and normalized[start - 1].isalnum())
                        or (end < len(normalized) and normalized[end].isalnum())
                    ):
                        continue
                    # Short initials must not match the middle of a larger initial sequence.
                    if re.fullmatch(r"[ㄱ-ㅎ]+", entry["alias"]):
                        if (start and re.match(r"[가-힣ㄱ-ㅎa-z]", normalized[start - 1])) or (
                            end < len(normalized) and re.match(r"[가-힣ㄱ-ㅎa-z]", normalized[end])
                        ):
                            continue
                    triggers, _ = context_at(normalized, start, end)
                    if entry["alias"] in POLYSEMOUS and len(triggers) < 2:
                        if normalized.strip() != normalize(entry["alias"])[0]:
                            continue
                    raw = text[spans[start][0] : spans[end - 1][1]]
                    method = "dictionary" if raw == entry["alias"] else "normalized"
                    base_score = 35 if entry["source"] == "corpus" else 55
                    score = (base_score if entry["needs_context"] else 90) + min(
                        20, len(triggers) * 7
                    )
                    add(
                        start,
                        end,
                        entry,
                        method,
                        min(score, 95),
                        [f"사전 표제어 '{entry['alias']}' 일치", "원문 위치를 보존한 복원 매칭"],
                    )

            # Prefer longer dictionary matches, retaining each repeated occurrence.
            matches.sort(
                key=lambda x: (-(x["end"] - x["start"]), x["method"] == "watchlist", -x["score"])
            )
            kept = []
            for item in matches:
                overlap = next(
                    (
                        other
                        for other in kept
                        if item["start"] < other["end"] and item["end"] > other["start"]
                    ),
                    None,
                )
                if overlap and (item["start"], item["end"]) == (overlap["start"], overlap["end"]):
                    overlap["alternatives"] = sorted(
                        set(overlap.get("alternatives", []) + item.get("alternatives", []))
                    )
                if not overlap:
                    kept.append(item)
            matches = kept
            for match in re.finditer(r"(?<![가-힣ㄱ-ㅎ])[ㄱ-ㅎ]{2,10}(?![가-힣ㄱ-ㅎ])", normalized):
                start, end = match.span()
                if any(
                    h.get("ordinary_choice")
                    and spans[start][0] < h["end"]
                    and spans[end - 1][1] > h["start"]
                    for h in watchlist_hits
                ):
                    continue
                options = self.initial_index.get(match.group(), []) + self.reference_initials.get(
                    match.group(), []
                )
                if not options or any(
                    spans[start][0] < item["end"] and spans[end - 1][1] > item["start"]
                    for item in matches
                ):
                    continue
                alternatives = sorted({entry["expansion"] for entry in options})
                add(
                    start,
                    end,
                    options[0],
                    "initials",
                    45,
                    [
                        "등록된 표현·원형에서 생성한 초성 대조 후보",
                        "초성이 같아도 뜻이 다를 수 있으므로 가능한 원형을 함께 확인하세요.",
                    ],
                )
                matches[-1]["alternatives"] = alternatives
            tokens = self.kiwi.tokenize(normalized)
            terms = {
                (m.start(), m.end(), m.group())
                for m in re.finditer(r"[가-힣ㄱ-ㅎ]{2,20}", normalized)
            }
            terms.update(
                (t.start, t.start + t.len, normalized[t.start : t.start + t.len])
                for t in tokens
                if t.tag in {"NNG", "NNP", "SL"} and 2 <= t.len <= 20
            )
            for start, end, term in sorted(terms, key=lambda t: (t[0], -(t[1] - t[0]))):
                if (
                    not spans
                    or term in STOP
                    or any(spans[start][0] < b and spans[end - 1][1] > a for a, b in neutral_spans)
                    or any(spans[start][0] < b and spans[end - 1][1] > a for a, b in account_spans)
                    or any(
                        spans[start][0] < m["end"] and spans[end - 1][1] > m["start"]
                        for m in matches
                    )
                ):
                    continue
                triggers, protective = context_at(normalized, start, end)
                if len(triggers) < 2 or protective:
                    continue
                nearest = None
                if len(term) >= 3:
                    options = [
                        (similarity(term, entry["alias"]), entry)
                        for entry in self.entries
                        if len(entry["alias"]) >= 3 and abs(len(term) - len(entry["alias"])) <= 1
                    ]
                    nearest = max(options, key=lambda x: x[0], default=None)
                if nearest and nearest[0] >= threshold and nearest[0] < 1:
                    sim, entry = nearest
                    add(
                        start,
                        end,
                        entry,
                        "jamo",
                        55 + min(15, len(triggers) * 5),
                        [
                            f"'{entry['alias']}'와 자모 편집 유사도 {sim:.2f}",
                            f"서로 다른 문맥 단서 {len(triggers)}종 동시 출현",
                        ],
                        round(sim, 3),
                    )
                elif discover and any(
                    t.start == start and t.start + t.len == end and t.tag in {"NNG", "NNP"}
                    for t in tokens
                ):
                    add(
                        start,
                        end,
                        None,
                        "context",
                        30 + min(15, len(triggers) * 5),
                        [
                            f"명사 주변에 서로 다른 문맥 단서 {len(triggers)}종 출현",
                            "학습 모델 판정이 아닌 규칙 기반 검토 후보",
                        ],
                    )
            matches.sort(key=lambda x: x["start"])
            return {
                "text": text,
                "normalized": normalized,
                "matches": matches,
                "signals": signals,
                "watchlist_hits": watchlist_hits,
                "watchlist_contexts": watchlist_contexts,
                "watchlist_version": self.watchlist.bundle["version"],
                "summary": {
                    "total": len(matches),
                    "dictionary": sum(m["method"] in {"dictionary", "normalized"} for m in matches),
                    "patterns": sum(m["method"] == "pattern" for m in matches),
                    "signals": len(signals),
                    "watchlist": len(watchlist_hits),
                    "watchlist_rules": len(watchlist_contexts),
                    "watchlist_matches": sum(m["method"] == "watchlist" for m in matches),
                    "candidates": sum(
                        m["method"] in {"jamo", "context", "initials"} for m in matches
                    ),
                },
                "tokens": [
                    {
                        "form": t.form,
                        "canonical": self.alias_map.get(normalize(t.form)[0], t.form),
                        "surface": normalized[t.start : t.start + t.len],
                        "tag": t.tag,
                        "start": spans[t.start][0],
                        "end": spans[min(t.start + t.len, len(spans)) - 1][1],
                    }
                    for t in tokens
                    if t.len > 0 and t.start < len(spans)
                ],
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "engine": "Kiwi + 사전 + 자모 편집 거리 + 문맥 규칙",
                "notice": (
                    "점수는 규칙의 근거 강도이며 은어일 확률이나 불법성 판정이 아닙니다. "
                    "미등록 은어를 모두 탐지하지 못합니다."
                ),
                "dictionary_version": self.version,
            }

    def discover(self, texts, min_count=2):
        counts, groups = Counter(), defaultdict(set)
        for text in texts:
            result = self.analyze(text)
            terms = {m["term"]: m for m in result["matches"] if m["method"] in {"context", "jamo"}}
            for term, item in terms.items():
                counts[term] += 1
                groups[term].update(trigger["group"] for trigger in item["context"])
        return [
            {"term": term, "document_count": count, "trigger_groups": sorted(groups[term])}
            for term, count in counts.most_common(100)
            if count >= min_count
        ]
