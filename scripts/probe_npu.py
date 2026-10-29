"""OpenVINO device/FP32 linear-ReLU smoke test; NOT a language-model benchmark."""

import argparse
import json
import statistics
import time
from pathlib import Path

import numpy as np
import openvino as ov
from openvino import opset13 as ops


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/npu-probe.json")
    args = parser.parse_args()
    core = ov.Core()
    result = {
        "openvino_version": ov.__version__,
        "devices": core.available_devices,
        "notice": "Synthetic fixed-shape linear/ReLU graph, not an NLP model or LLM benchmark.",
        "results": [],
    }
    rng = np.random.default_rng(42)
    data = rng.normal(size=(1, 128, 768)).astype(np.float32)
    node = x = ops.parameter([1, 128, 768], np.float32, name="input")
    for _ in range(3):
        w = rng.normal(0, 0.02, (768, 768)).astype(np.float32)
        node = ops.relu(ops.matmul(node, ops.constant(w), False, False))
    model = ov.Model([node], [x])
    reference = None
    for device in core.available_devices:
        record = {"device": device}
        try:
            record["name"] = core.get_property(device, "FULL_DEVICE_NAME")
            start = time.perf_counter()
            compiled = core.compile_model(model, device, {"PERFORMANCE_HINT": "LATENCY"})
            record["compile_ms"] = round((time.perf_counter() - start) * 1000, 2)
            request = compiled.create_infer_request()
            request.infer({"input": data})
            times = []
            for _ in range(20):
                start = time.perf_counter()
                request.infer({"input": data})
                times.append((time.perf_counter() - start) * 1000)
            output = request.get_output_tensor(0).data.copy()
            if reference is None:
                reference = output
            error = float(np.max(np.abs(reference - output)))
            record.update(
                status="ok",
                median_ms=round(statistics.median(times), 3),
                runs=len(times),
                max_abs_error_vs_first=round(error, 6),
                finite=bool(np.isfinite(output).all()),
                within_tolerance=bool(np.allclose(reference, output, atol=0.02, rtol=0.02)),
            )
        except Exception as exc:
            record.update(status="failed", error=str(exc)[:2000])
        result["results"].append(record)
        print(json.dumps(record, ensure_ascii=True), flush=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if not any(
        r.get("status") == "ok" and r["device"].startswith("NPU") for r in result["results"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
