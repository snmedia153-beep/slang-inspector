"""Supplementary CPU/GPU timing control; does not benchmark the four research candidates."""

import argparse
import json
import statistics
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def request(url, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=180) as r:
        return json.load(r)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--cpu-runs", type=int, default=5)
    parser.add_argument("--gpu-runs", type=int, default=10)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if min(args.cpu_runs, args.gpu_runs) < 2:
        raise SystemExit("Use at least two measured runs per device.")
    installed = {m["name"]: m for m in request(args.url + "/api/tags")["models"]}
    if args.model not in installed:
        raise SystemExit("Model not installed. This tool never downloads models.")
    records = []
    try:
        for device, gpu_layers, count in [("cpu", 0, args.cpu_runs), ("gpu", 999, args.gpu_runs)]:
            request(args.url + "/api/generate", {"model": args.model, "keep_alive": 0})
            for i in range(count + 1):
                started = time.perf_counter()
                result = request(
                    args.url + "/api/chat",
                    {
                        "model": args.model,
                        "stream": False,
                        "think": False,
                        "keep_alive": "2m",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    "한국어 신조어 감다살과 기대컨의 의미를 설명하고, "
                                    "초성만 보고 뜻을 단정하면 생기는 문제를 10개 항목으로 자"
                                    "세히 설명하세요."
                                ),
                            }
                        ],
                        "options": {
                            "temperature": 0,
                            "seed": 42,
                            "num_ctx": 2048,
                            "num_predict": 128,
                            "num_gpu": gpu_layers,
                        },
                    },
                )
                wall_ms = (time.perf_counter() - started) * 1000
                active = request(args.url + "/api/ps")["models"]
                placement = next(m for m in active if m["name"] == args.model)
                vram, size = placement["size_vram"], placement["size"]
                if (device == "cpu" and vram != 0) or (device == "gpu" and vram < size * 0.95):
                    raise RuntimeError("Requested CPU/GPU placement was not verified")
                row = {
                    "device": device,
                    "warmup": i == 0,
                    "run": i,
                    "wall_ms": round(wall_ms, 3),
                    "load_ms": round(result.get("load_duration", 0) / 1e6, 3),
                    "prompt_tokens": result.get("prompt_eval_count"),
                    "output_tokens": result["eval_count"],
                    "tokens_s": round(result["eval_count"] * 1e9 / result["eval_duration"], 3),
                    "done_reason": result.get("done_reason"),
                    "size_bytes": size,
                    "size_vram_bytes": vram,
                }
                records.append(row)
                print(json.dumps(row), flush=True)
    finally:
        request(args.url + "/api/generate", {"model": args.model, "keep_alive": 0})
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(
                {
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                    "model": args.model,
                    "model_digest": installed[args.model]["digest"],
                    "model_details": installed[args.model].get("details", {}),
                    "notice": "Timing control; not accuracy of the four candidate models.",
                    "settings": {
                        "num_ctx": 2048,
                        "num_predict": 128,
                        "temperature": 0,
                        "seed": 42,
                        "think": False,
                    },
                    "runs": records,
                    "summary": [
                        {
                            "device": device,
                            "n": len(rows),
                            "median_ms": round(statistics.median(r["wall_ms"] for r in rows), 3),
                            "min_ms": min(r["wall_ms"] for r in rows),
                            "max_ms": max(r["wall_ms"] for r in rows),
                            "median_tokens_s": round(
                                statistics.median(r["tokens_s"] for r in rows), 3
                            ),
                        }
                        for device in ("cpu", "gpu")
                        if (
                            rows := [
                                r for r in records if r["device"] == device and not r["warmup"]
                            ]
                        )
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            "utf-8",
        )


if __name__ == "__main__":
    main()
