"""Measure OCR API end to end without caching; save synthetic-input result fingerprints."""

import argparse
import hashlib
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


def fingerprint(data):
    stable = {
        "text": data["text"],
        "words": [
            {k: w[k] for k in ("text", "x", "y", "width", "height", "line")} for w in data["words"]
        ],
        "regions": [{k: r[k] for k in ("surface", "expansion", "boxes")} for r in data["regions"]],
    }
    return hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18640")
    parser.add_argument("--output", required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--images", nargs="+", default=["artifacts/ocr-sample.png", "artifacts/ocr-neutral.png"]
    )
    args = parser.parse_args()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    records = []
    for image in args.images:
        raw = Path(image).read_bytes()
        rows = []
        for i in range(args.runs):
            req = urllib.request.Request(
                args.url + "/api/ocr/analyze", data=raw, headers={"Content-Type": "image/png"}
            )
            start = time.perf_counter()
            with opener.open(req, timeout=60) as response:
                data = json.load(response)
            row = {
                "run": i + 1,
                "wall_ms": round((time.perf_counter() - start) * 1000, 2),
                "server_ms": data["ocr_elapsed_ms"],
                "words": len(data["words"]),
                "regions": len(data["regions"]),
                "fingerprint": fingerprint(data),
                "timings": data.get("ocr_timings", {}),
                "backend": data.get("ocr_backend"),
            }
            rows.append(row)
            print(json.dumps({"image": Path(image).name, **row}), flush=True)
        records.append(
            {
                "image": Path(image).name,
                "runs": rows,
                "median_ms": round(statistics.median(r["wall_ms"] for r in rows), 2),
            }
        )
    Path(args.output).write_text(json.dumps(records, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
