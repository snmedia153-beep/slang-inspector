"""Import tab-separated admin rows, retaining existing reviewed annotations."""

import argparse
import json
import re
from pathlib import Path

ROW = re.compile(
    r"^([^\t]+)\t(은어|일반|유인문구)\t(활성|비활성)\t"
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\t.*)?$"
)


def parse_rows(text):
    rows = []
    seen = set()
    for line in text.lstrip("\ufeff").splitlines():
        match = ROW.fullmatch(line.strip())
        if match:
            keyword, kind, status = match.groups()
            keyword = keyword.strip()
            if keyword in seen:
                raise ValueError(f"중복 키워드: {keyword}")
            seen.add(keyword)
            rows.append({"keyword": keyword, "type": kind, "status": status})
        elif "\t" in line and not line.startswith("키워드\t"):
            raise ValueError("키워드 행의 열·타입·상태·등록일 형식을 확인하세요.")
    if not rows:
        raise ValueError("가져올 키워드 행이 없습니다.")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = parse_rows(args.input.read_text("utf-8-sig"))
    bundle = (
        json.loads(args.output.read_text("utf-8"))
        if args.output.exists()
        else {
            "version": "1",
            "notice": "사용자 표에서 가져온 미검증 목록입니다.",
            "group_labels": {"unknown": "원형 미확인"},
            "sources": [
                {
                    "id": "attached-watchlist",
                    "title": "사용자 제공 키워드 관리 표",
                    "purpose": "원문 표기·타입·상태만 확인. 뜻의 검증 자료가 아님",
                }
            ],
            "entries": [],
        }
    )
    previous = {entry["keyword"]: entry for entry in bundle["entries"]}
    bundle["entries"] = [
        {
            "group": "unknown",
            "meaning": "원형 미확인",
            "evidence": "unknown",
            "candidates": [],
            "occurrence_sources": ["attached-watchlist"],
            "note": "사용자 제공 목록의 항목. 원형 검증 필요.",
            **previous.get(row["keyword"], {}),
            **row,
        }
        for row in rows
    ]
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"rows": len(rows), "active": sum(r["status"] == "활성" for r in rows)}))


if __name__ == "__main__":
    main()
