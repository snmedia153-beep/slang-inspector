"""일반어를 단독 성적 근거로 삼지 않고 검토 목록과 문맥 조합을 대조합니다."""

import json
import re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from pathlib import Path

from app.initial_candidates import initial_boundary, initial_key
from app.post_rules import COMMENT_COUNT, POST_DATE

WORD = re.compile(r"[가-힣ㄱ-ㅎa-z0-9_]", re.I)
SUFFIX = re.compile(
    r"(?:은|는|이|가|을|를|도|만|의|에|에서|에게|한테|로|으로|와|과|랑|이나|나|부터|까지|"
    r"입니다|이다|이고|이야|이에요|예요|요|임|함|들|들만|들을|들은|들이|든|든지|"
    r"구함|구해요|구합니다|합니다|해요|해주세요|주세요|보내줘|보내면|줄게|줄게요|삽니다|팝니다|"
    r"필수|가능|금지)(?:도|는|만|요)?$"
)
PROTECTIVE = re.compile(r"신고|예방|근절|피해|수사|교육|연구|보도|금지|주의|상담")
REQUEST = re.compile(r"보내|보여|요구|찍어|주면|구매|판매|삽니|팝니|교환|거래|팔아")
PRIVATE = re.compile(r"https?://\S+|(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.I)
NEUTRAL = {"ordinary", "location", "body", "clothing", "number", "age", "identity", "identity_age"}


class Watchlist:
    def __init__(self):
        self.bundle = json.loads(
            (Path(__file__).parent / "data" / "context_watchlist.json").read_text("utf-8")
        )
        self.sources = {source["id"]: source for source in self.bundle["sources"]}
        self.patterns = [
            (
                entry,
                re.compile(
                    re.escape(entry["keyword"].lower())
                    if entry["group"] == "number"
                    else r"[ \t._·-]{0,2}".join(
                        re.escape(c) for c in entry["keyword"].lower() if not c.isspace()
                    )
                ),
            )
            for entry in self.bundle["entries"]
            if entry["status"] == "활성"
        ]

    def info(self):
        return {
            **self.bundle,
            "total": len(self.bundle["entries"]),
            "active": len(self.patterns),
            "types": dict(Counter(entry["type"] for entry in self.bundle["entries"])),
            "evidence_counts": dict(Counter(entry["evidence"] for entry in self.bundle["entries"])),
        }

    def scan(self, normalized, spans, original, signals, reserved_initials=()):
        if not spans:
            return [], []
        private = [(m.start(), m.end()) for m in PRIVATE.finditer(original)] + [
            (s["start"], s["end"])
            for s in signals
            if s["kind"] in {"social_account", "person_label", "post_date", "comment_count"}
        ]
        raw = []
        for entry, pattern in self.patterns:
            for match in pattern.finditer(normalized):
                start, end = match.span()
                if initial_key(entry["keyword"]) and not initial_boundary(normalized, start, end):
                    continue
                if initial_key(entry["keyword"]) and any(
                    a <= start and end <= b and (start, end) != (a, b) for a, b in reserved_initials
                ):
                    # OCR에서 나뉜 긴 초성을 짧은 접두어 후보보다 먼저 보존합니다.
                    continue
                a, b = spans[start][0], spans[end - 1][1]
                if any(a < y and b > x for x, y in private):
                    continue
                # 날짜·가격·버전·전화번호의 숫자를 나이 주장으로 해석하지 않습니다.
                if entry["group"] == "number" and (
                    (start and normalized[start - 1] in "0123456789-/:")
                    or (end < len(normalized) and normalized[end] in "0123456789-/:")
                    or (
                        start > 1
                        and normalized[start - 1] in ".,"
                        and normalized[start - 2].isdigit()
                    )
                    or (
                        end + 1 < len(normalized)
                        and normalized[end] in ".,"
                        and normalized[end + 1].isdigit()
                    )
                ):
                    continue
                if entry["keyword"] == "보지" and re.match(
                    r"(?:는|도|만)?[ \t]*(?:못|않|말|마(?:라|세요)?)(?=[가-힣\s.!?]|$)",
                    normalized[end:],
                ):
                    entry = {
                        **entry,
                        "group": "ordinary",
                        "meaning": "보다의 부정·명령형 문맥",
                        "evidence": "literal",
                        "candidates": [],
                        "note": "보지 못하다·보지 말다 등의 일반 동사 용례입니다.",
                    }
                raw.append((start, end, entry))
        # 등록어끼리 붙은 경우는 허용하되 긴 일반어 안의 부분 일치는 제외합니다.
        left_valid, right_valid = set(), set()
        for start, end, entry in sorted(raw, key=lambda row: row[:2]):
            if (
                start == 0
                or not WORD.fullmatch(normalized[start - 1])
                or start in left_valid
                or initial_key(entry["keyword"])
            ):
                left_valid.add(end)
        right_starts = set()
        for start, end, entry in sorted(raw, key=lambda row: row[:2], reverse=True):
            suffix = re.match(r"[가-힣ㄱ-ㅎa-z0-9_]+", normalized[end:])
            if (
                end == len(normalized)
                or not WORD.fullmatch(normalized[end])
                or end in right_starts
                or (suffix and SUFFIX.fullmatch(suffix.group()))
                or initial_key(entry["keyword"])
            ):
                right_starts.add(start)
                right_valid.add((start, end))
        accepted = [
            row
            for row in raw
            if (
                row[0] == 0
                or not WORD.fullmatch(normalized[row[0] - 1])
                or row[0] in left_valid
                or initial_key(row[2]["keyword"])
            )
            and row[:2] in right_valid
        ]
        kept = []
        for start, end, entry in sorted(accepted, key=lambda row: (row[0], -(row[1] - row[0]))):
            overlap = kept[-1] if kept and start < kept[-1]["normalized_end"] else None
            if overlap:
                if (start, end) == (overlap["normalized_start"], overlap["normalized_end"]):
                    overlap["keywords"].append(entry["keyword"])
                continue
            a, b = spans[start][0], spans[end - 1][1]
            kept.append(
                {
                    **entry,
                    "keywords": [entry["keyword"]],
                    "start": a,
                    "end": b,
                    "surface": original[a:b],
                    "normalized_start": start,
                    "normalized_end": end,
                    "group_label": self.bundle["group_labels"][entry["group"]],
                    "provenance": [self.sources[s] for s in entry["occurrence_sources"]],
                    "definition_sources": [
                        self.sources[s] for c in entry["candidates"] for s in c["sources"]
                    ],
                }
            )
        kept.sort(key=lambda hit: hit["start"])
        starts = [h["normalized_start"] for h in kept]
        boundaries = list(re.finditer(r"[\n!?。;]|\.(?=\s|$)", normalized))
        boundaries.extend(POST_DATE.finditer(normalized))
        boundaries.extend(COMMENT_COUNT.finditer(normalized))
        boundary_starts = sorted(m.start() for m in boundaries) + [len(normalized)]
        boundary_ends = [0] + sorted(m.end() for m in boundaries)
        for hit in kept:
            start, end = hit["normalized_start"], hit["normalized_end"]
            left = max(boundary_ends[bisect_right(boundary_ends, start) - 1], start - 80)
            right = min(boundary_starts[bisect_left(boundary_starts, end)], end + 80)
            clause = normalized[left:right]
            ordinary = [
                {"expansion": sense["expansion"], "support": hint}
                for sense in hit.get("ordinary_contexts", [])
                for hint in sense["hints"]
                if hint in clause
            ]
            # 단서가 충돌하면 단일 의미를 강제하지 않습니다.
            conflict = any(
                h is not hit
                and h["group"] in {"sexual", "abuse", "sexual_composite"}
                and h["normalized_start"] >= left
                and h["normalized_end"] <= right
                for h in kept[bisect_left(starts, left) : bisect_right(starts, right)]
            )
            if ordinary and not conflict and len({sense["expansion"] for sense in ordinary}) == 1:
                choice = ordinary[0]
                hit["ordinary_choice"] = choice
                hit["group"] = "ordinary"
                hit["group_label"] = self.bundle["group_labels"]["ordinary"]
                hit["meaning"] = choice["expansion"] + " (일상 문맥 후보)"
                hit["note"] = (
                    f"'{choice['support']}'라는 일상 단서와 함께 등장했습니다. "
                    "다른 뜻을 배제한 확정 풀이가 아닙니다."
                )
        contexts = []
        seen = set()
        for hit in kept:
            start, end = hit["normalized_start"], hit["normalized_end"]
            left = max(boundary_ends[bisect_right(boundary_ends, start) - 1], start - 80)
            right = min(boundary_starts[bisect_left(boundary_starts, end)], end + 80)
            nearby = [
                h
                for h in kept[bisect_left(starts, left) : bisect_right(starts, right)]
                if h["normalized_end"] <= right
            ]
            groups = {h["group"] for h in nearby}
            clause = normalized[left:right]
            labels = []
            if groups & {"age", "sexual_composite"} and groups & {
                "sexual",
                "sexual_composite",
                "abuse",
            }:
                labels.append(("age_sexual", "학교급·연령 표기와 성적·촬영 관련 표현이 함께 등장"))
            if "media" in groups and "reward" in groups and REQUEST.search(clause):
                labels.append(
                    (
                        "reward_media_request",
                        "사진·영상 관련 표현과 금전·물품 제공 및 요구 문구가 함께 등장",
                    )
                )
            if groups & {"media", "sexual", "abuse"} and "trade" in groups:
                labels.append(("media_trade", "사진·영상·성적 표현과 거래·제공 단서가 함께 등장"))
            if (
                "proxy" in groups
                and re.search(r"댈구|담댈", clause)
                and re.search(r"담배|술|전담", clause)
            ):
                labels.append(("proxy_purchase", "술·담배 대리구매 관련 표현이 함께 등장"))
            if groups & {"media", "abuse", "sexual"} and "contact" in groups:
                labels.append(("contact_media", "연락·만남 경로와 사진·영상·성적 표현이 함께 등장"))
            protective = bool(PROTECTIVE.search(clause))
            for kind, explanation in labels:
                support = tuple((h["start"], h["end"]) for h in nearby)
                key = kind, support
                if key in seen:
                    continue
                seen.add(key)
                a, b = spans[left][0], spans[right - 1][1]
                contexts.append(
                    {
                        "kind": kind,
                        "explanation": explanation,
                        "start": a,
                        "end": b,
                        "clause": original[a:b],
                        "keywords": [h["surface"] for h in nearby],
                        "protective": protective,
                        "note": "보도·예방·피해 대응 용례를 우선 확인하세요."
                        if protective
                        else (
                            "단어 조합을 검출한 규칙 결과입니다. "
                            "실제 의도·동의·연령·범죄 여부는 미확인입니다."
                        ),
                    }
                )
        links = defaultdict(set)
        original_starts = [h["start"] for h in kept]
        for context in contexts:
            # 문맥 구간은 최대 160자로 제한해 단서 결합이 멀리 번지지 않게 합니다.
            for hit in kept[
                bisect_left(original_starts, context["start"]) : bisect_right(
                    original_starts, context["end"]
                )
            ]:
                if hit["end"] <= context["end"]:
                    links[hit["start"], hit["end"]].add(context["kind"])
        for hit in kept:
            linked = sorted(links[hit["start"], hit["end"]])
            hit["context_rules"] = linked
            hit["assessment"] = (
                "unresolved"
                if hit["evidence"] == "unknown"
                else "neutral"
                if hit["group"] in NEUTRAL
                else "contextual"
                if linked
                else "candidate"
            )
            hit["detect"] = hit["group"] in {"abuse", "sexual", "sexual_composite"} or (
                hit["group"] in {"media", "ambiguous"} and bool(linked)
            )
        return kept, contexts
