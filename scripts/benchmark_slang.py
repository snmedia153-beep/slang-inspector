"""Run inside the existing app container; no model pulls or app configuration changes."""

import argparse
import json
import statistics
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from app.contextual import ContextInterpreter

SAMPLES = {
    "ordinary": "오늘 ㅇㄹ 레시피를 알려줘. 병원에서 ㅅㅅ 예약을 확인했어요.",
    "ambiguous": "서울에서 몸사를 보내면 용돈 줄게. #맘눌피 #야상극 ㅇㄹ",
    "listing": "2026-10-29 ㅌㅌ 가상인물 꼭노 [3] 2026-10-29 재업ㄴㄴ",
}


def request(url, payload=None, timeout=75):
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=timeout
    ) as r:
        return json.load(r)


def micro_compare(args):
    model = "qwen3.5:4b"
    result = {
        "model": model,
        "notice": (
            "Short 2048-context generation microbenchmark, "
            "not the app's analysis prompt or an accuracy test."
        ),
        "runs": [],
    }
    for device, num_gpu in [("cpu_requested", 0), ("gpu_requested", 999)]:
        for index in range(2):
            print(f"Microbenchmark {device}, run {index + 1}", flush=True)
            start = time.perf_counter()
            response = request(
                args.ollama + "/api/chat",
                {
                    "model": model,
                    "stream": False,
                    "think": False,
                    "keep_alive": "2m",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "한국어 텍스트 분석에서 문맥을 확인해야 하는 이유를 "
                                "10개 항목으로 자세히 설명하세요."
                            ),
                        }
                    ],
                    "options": {
                        "temperature": 0,
                        "num_ctx": 2048,
                        "num_predict": 128,
                        "num_gpu": num_gpu,
                    },
                },
                timeout=120,
            )
            duration = response.get("eval_duration") or 0
            loaded = request(args.ollama + "/api/ps").get("models", [])
            item = {
                "device": device,
                "index": index,
                "wall_s": round(time.perf_counter() - start, 3),
                "load_s": round(response.get("load_duration", 0) / 1e9, 3),
                "output_tokens": response.get("eval_count"),
                "tokens_s": round(response.get("eval_count", 0) * 1e9 / duration, 2)
                if duration
                else None,
                "placement": [
                    {k: m.get(k) for k in ("name", "size", "size_vram", "context_length")}
                    for m in loaded
                    if m["name"] == model
                ],
            }
            result["runs"].append(item)
            print(json.dumps(item), flush=True)
    request(args.ollama + "/api/generate", {"model": model, "keep_alive": 0})
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--ollama", default="http://host.docker.internal:11434")
    parser.add_argument(
        "--models", nargs="+", default=["qwen3.5:9b", "qwen3.5:4b", "qwen2.5:7b-instruct"]
    )
    parser.add_argument("--output", default="/tmp/slang-performance.json")
    parser.add_argument("--micro-only", action="store_true")
    args = parser.parse_args()
    installed = {m["name"] for m in request(args.ollama + "/api/tags")["models"]}
    if args.micro_only:
        if "qwen3.5:4b" not in installed:
            raise SystemExit("qwen3.5:4b is not installed; this tool never pulls models.")
        micro_compare(args)
        return
    result = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "fast": [],
        "models": [],
        "api_deep": [],
    }
    fast = {}
    for label, text in SAMPLES.items():
        times = []
        for _ in range(10):
            start = time.perf_counter()
            response = request(args.api + "/api/analyze", {"text": text})
            times.append((time.perf_counter() - start) * 1000)
        fast[label] = response
        result["fast"].append(
            {
                "sample": label,
                "chars": len(text),
                "runs": len(times),
                "median_ms": round(statistics.median(times), 2),
                "max_ms": round(max(times), 2),
                "engine_ms": response["elapsed_ms"],
                "matches": response["summary"]["total"],
            }
        )
    print("Fast API measurements finished", flush=True)
    for model in args.models:
        if model not in installed:
            result["models"].append({"model": model, "status": "not_installed"})
            continue
        interpreter = ContextInterpreter(url=args.ollama, model=model)
        original = interpreter.request
        metrics = []

        def tracked(path, payload=None, timeout=3, _original=original, _metrics=metrics):
            response = _original(path, payload, timeout)
            if path == "/api/chat":
                usage = {
                    key: response.get(key)
                    for key in (
                        "load_duration",
                        "total_duration",
                        "prompt_eval_count",
                        "prompt_eval_duration",
                        "prompt_eval_cached_count",
                        "eval_count",
                        "eval_duration",
                        "done_reason",
                    )
                }
                duration = usage.get("eval_duration") or 0
                usage["generation_tokens_s"] = (
                    round((usage.get("eval_count") or 0) * 1e9 / duration, 2) if duration else None
                )
                usage["payload_chars"] = len(json.dumps(payload, ensure_ascii=False))
                usage["requested_context"] = payload["options"]["num_ctx"]
                _metrics.append(usage)
            return response

        interpreter.request = tracked
        for index, (label, text) in enumerate(SAMPLES.items()):
            print(f"Measuring {model} / {label}", flush=True)
            before = len(metrics)
            start = time.perf_counter()
            response = interpreter.interpret(text, fast[label])
            elapsed = (time.perf_counter() - start) * 1000
            active = request(args.ollama + "/api/ps").get("models", [])
            metric = metrics[-1] if len(metrics) > before else {}
            item = {
                "model": model,
                "sample": label,
                "first_call_for_model": index == 0,
                "status": response["status"],
                "wall_ms": round(elapsed, 2),
                "candidate_count": response.get("candidate_count"),
                "items": len(response["items"]),
                "usage": metric,
                "placement": [
                    {k: m.get(k) for k in ("name", "size", "size_vram", "context_length")}
                    for m in active
                    if m["name"] == model
                ],
            }
            result["models"].append(item)
            print(json.dumps(item, ensure_ascii=True), flush=True)
    # Measure real production endpoint once warm. Full original text is never saved in output.
    for label in ("ordinary", "ambiguous"):
        start = time.perf_counter()
        response = request(args.api + "/api/context/interpret", {"text": SAMPLES[label]})
        result["api_deep"].append(
            {
                "sample": label,
                "status": response["status"],
                "wall_ms": round((time.perf_counter() - start) * 1000, 2),
                "candidate_count": response.get("candidate_count"),
            }
        )
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"Saved measurements: {args.output}", flush=True)


if __name__ == "__main__":
    main()
