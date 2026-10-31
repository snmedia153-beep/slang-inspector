"""Measure synthetic text-analysis cases; never store uploaded/user text."""

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18640")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    samples = {
        "ordinary": "간단한 설명을 보고 친구와 식사했습니다.",
        "elongated": "간다아아아아아안 몸사 판매 만남",
        "long_repeat": "간다" + "아" * 15000 + "안",
    }
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rows = []
    for label, text in samples.items():
        times = []
        for i in range(21):
            request = urllib.request.Request(
                args.url + "/api/analyze",
                data=json.dumps({"text": text}, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"},
            )
            started = time.perf_counter()
            with opener.open(request, timeout=30) as response:
                result = json.load(response)
            elapsed = (time.perf_counter() - started) * 1000
            if i:
                times.append(elapsed)
        row = {
            "sample": label,
            "characters": len(text),
            "n": len(times),
            "median_ms": round(statistics.median(times), 3),
            "max_ms": round(max(times), 3),
            "matches": len(result["matches"]),
            "normalizations": len(result.get("normalizations", [])),
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    Path(args.output).write_text(json.dumps(rows, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
