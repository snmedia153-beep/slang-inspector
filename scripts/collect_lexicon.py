"""Rebuild the bundled moderation lexicon from licensed, pinned public sources.

Only data strings are parsed. Downloaded Python is never imported or executed.
Run explicitly; application startup never performs collection.
"""

import ast
import hashlib
import json
import re
import urllib.request
import warnings
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "app" / "data"
SOURCES = [
    ("korcen", "Tanat05/korcen", "main", "korcen/korcen.py", "MIT"),
    ("doublems", "doublems/korean-bad-words", "master", "korean-bad-words.md", "MIT"),
    ("badwords-ko", "yoonheyjung/badwords-ko", "main", "src/badwords.ko.config.json", "MIT"),
    (
        "ldnoobw",
        "LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words",
        "master",
        "ko",
        "CC-BY-4.0",
    ),
]
REPORT_URL = "https://www.archivecenter.net/kaitArchive/attach/90000/96477/20231017215752233.pdf"
FAMILIES = {
    "불법촬영": ("몰카", "불촬", "도촬", "직촬", "불법촬영", "불법촬영물", "비동의촬영"),
    "비동의 유포·협박": (
        "몸캠피싱",
        "몸캠",
        "유포협박",
        "비동의유포",
        "리벤지포르노",
        "유출본",
        "유출물",
        "유포물",
        "유출영상",
    ),
    "합성·성적 괴롭힘": (
        "지인능욕",
        "지인합성",
        "합성음란물",
        "허위영상물",
        "딥페이크",
        "불법합성물",
    ),
    "성착취 관련 표현": (
        "성착취물",
        "성착취",
        "디지털성범죄",
        "사이버성폭력",
        "디지털성폭력",
        "온라인그루밍",
        "그루밍",
        "성매매",
        "조건만남",
        "원조교제",
        "강간",
        "겁탈",
        "성폭행",
    ),
    "성인 콘텐츠 표현": (
        "야동",
        "야사",
        "야설",
        "야애니",
        "포르노",
        "노모",
        "유모",
        "은꼴",
        "에로",
        "망가",
        "성인물",
        "성인동영상",
        "누드",
        "국노",
        "국산",
    ),
    "성적 은어·변형": (
        "섹스",
        "섹",
        "쎅",
        "쎽",
        "쌕",
        "색스",
        "sex",
        "porn",
        "야스",
        "대딸",
        "딸딸이",
        "자위",
        "스와핑",
        "근친",
        "노콘",
        "사까시",
        "빠구리",
        "페티쉬",
        "패티쉬",
        "페티시",
    ),
    "신체 관련 비속표현": (
        "보지",
        "보짓",
        "보짖",
        "보즤",
        "뵤즤",
        "봊이",
        "bozi",
        "자지",
        "쟈지",
        "자짓",
        "잦이",
        "불알",
        "부랄",
        "부럴",
        "좆",
        "조옷",
        "후장",
    ),
}
ORIGINALS = {
    "섹스": (
        "sex",
        "색스",
        "셱스",
        "섁스",
        "쉑스",
        "섿스",
        "쌕스",
        "야스",
        "세엑스",
        "썩스",
        "쎅스",
        "섹수",
        "쉐스",
        "쉐엑스",
        "색수",
    ),
    "보지": ("bozi", "보ㅈㅣ", "보g", "보즤", "뵤즤", "봊이", "보짖"),
    "자지": ("ja지", "자ㅈ", "잦이", "쟈지"),
    "불알": ("부랄", "뽕알", "뿅알", "뿌랄", "뿔알", "부럴"),
    "몰래카메라": ("몰카",),
}
DOMAIN = {
    "딥페이크": "합성·성적 괴롭힘",
    "허위영상물": "합성·성적 괴롭힘",
    "아동청소년성착취물": "성착취 관련 표현",
    "아동성착취물": "성착취 관련 표현",
    "그루밍": "성착취 관련 표현",
    "성착취물": "성착취 관련 표현",
    "불법촬영물": "불법촬영",
    "불법촬영": "불법촬영",
    "비동의촬영": "불법촬영",
    "비동의유포": "비동의 유포·협박",
    "온라인성착취": "성착취 관련 표현",
    "온라인그루밍": "성착취 관련 표현",
    "몸캠피싱": "비동의 유포·협박",
    "유포협박": "비동의 유포·협박",
    "사이버성폭력": "성착취 관련 표현",
    "디지털성폭력": "성착취 관련 표현",
    "지인능욕": "합성·성적 괴롭힘",
    "국노": "문맥 의존 암어",
    "고등어": "문맥 의존 암어",
    "골뱅이": "문맥 의존 암어",
    "국산": "문맥 의존 암어",
    "ㄷㅊ": "문맥 의존 암어",
    "은꼴": "성인 콘텐츠 표현",
}
# General anatomical/sexual vocabulary is not classified as exploitation evidence.
EXCLUDE_AGE = re.compile(r"초딩|중딩|고딩|로리|유아|유치원|어린이|소아|미성년")


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "SlangInspector-Dataset/1.0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        data = response.read(5_000_001)
    if len(data) > 5_000_000:
        raise ValueError("Unexpected source size")
    return data


def plain(value):
    # Reject regex programs, URLs, names of sites and complete sexual sentences.
    return isinstance(value, str) and bool(re.fullmatch(r"[가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9]{2,24}", value))


def category(word):
    return next(
        (group for group, roots in FAMILIES.items() if any(root in word.lower() for root in roots)),
        None,
    )


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    entries, exclusions, sources = {}, set(), []
    original_map = {alias: original for original, aliases in ORIGINALS.items() for alias in aliases}
    for source_id, repo, branch, filename, license_id in SOURCES:
        metadata = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits/{branch}"))
        revision = metadata["sha"]
        url = f"https://raw.githubusercontent.com/{repo}/{revision}/{filename}"
        raw = fetch(url)
        license_raw = fetch(f"https://raw.githubusercontent.com/{repo}/{revision}/LICENSE")
        if (license_id == "MIT" and b"MIT License" not in license_raw) or (
            license_id == "CC-BY-4.0" and b"Attribution 4.0" not in license_raw
        ):
            raise ValueError(f"License changed; review {repo} before collecting")
        (licenses / f"{source_id}.txt").write_bytes(license_raw)
        decoded = raw.decode("utf-8-sig")
        if source_id == "korcen":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(decoded)
            lists = {
                node.targets[0].id: ast.literal_eval(node.value)
                for node in tree.body
                if isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id
                in {"SEXUAL_PROFANITY_PATTERNS", "FALSE_POSITIVE_PATTERNS_SEXUAL"}
            }
            words = lists["SEXUAL_PROFANITY_PATTERNS"]
            exclusions.update(v for v in lists["FALSE_POSITIVE_PATTERNS_SEXUAL"] if plain(v))
        elif source_id == "badwords-ko":
            words = json.loads(decoded)["badWords"]
        else:
            words = decoded.splitlines()
        retained = 0
        for value in words:
            word = value.strip()
            if not plain(word) or EXCLUDE_AGE.search(word):
                continue
            group = category(word)
            if source_id == "korcen" and group is None:
                group = "성적 은어·변형"
            if group is None:
                continue
            retained += 1
            entry = entries.setdefault(
                word,
                {
                    "alias": word,
                    "expansion": original_map.get(word, word),
                    "canonical": group,
                    "category": group,
                    "note": (
                        "공개 필터링 사전에서 수집한 표현. 성착취 여부·동의 여부는 미확인입니다."
                    ),
                    "needs_context": True,
                    "evidence": "observed",
                    "sources": [],
                },
            )
            entry["sources"].append(source_id)
        sources.append(
            {
                "id": source_id,
                "repository": f"https://github.com/{repo}",
                "url": url,
                "revision": revision,
                "license": license_id,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_items": len(words),
                "retained_items": retained,
            }
        )
    for word, group in DOMAIN.items():
        entries[word] = {
            "alias": word,
            "expansion": word,
            "canonical": group,
            "category": group,
            "needs_context": True,
            "evidence": "curated",
            "sources": ["nhrck-2021"],
            "note": (
                "피해지원 연구자료의 용어를 정리한 검토 항목. "
                "일상 용례와 구분이 필요하며 뜻을 확정하지 않습니다."
            ),
        }
    sources.append(
        {
            "id": "nhrck-2021",
            "url": REPORT_URL,
            "title": "2021 아동·청소년 성착취 피해예방과 인권적 구제 방안 실태조사",
            "pages": "PDF 133, 450, 457, 458, 466쪽: 피해 유형 및 관련 용어",
            "license": "용어 사실만 사용; 본문·정의 재배포 안 함",
            "retained_items": len(DOMAIN),
        }
    )
    exclusions.update(
        {
            "보지마",
            "보지말",
            "보지않",
            "보지못",
            "살펴보지",
            "지켜보지",
            "바라보지",
            "자위권",
            "자위대",
        }
    )
    bundle = {
        "entries": sorted(entries.values(), key=lambda x: x["alias"]),
        "exclusions": sorted(exclusions),
    }
    encoded = (json.dumps(bundle, ensure_ascii=False, indent=2) + "\n").encode()
    (OUTPUT / "lexicon.json").write_bytes(encoded)
    manifest = {
        "collected_at": datetime.now(UTC).isoformat(),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "entries": len(entries),
        "categories": dict(Counter(e["category"] for e in entries.values())),
        "sources": sources,
        "generated_variants_included": False,
        "notice": "은어 전체를 보장하지 않습니다. 성적 표현과 성착취 근거는 구분해야 합니다.",
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(
        json.dumps(
            {
                "entries": len(entries),
                "categories": manifest["categories"],
                "sources": len(sources),
                "exclusions": len(exclusions),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
