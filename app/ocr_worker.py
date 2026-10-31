"""OCR 모델을 재사용하는 작업 프로세스. 표준 출력은 JSON 응답 전용입니다."""

import contextlib
import json
import os
import sys
import time
from pathlib import Path


def create_engine():
    with contextlib.redirect_stdout(sys.stderr):
        import cv2
        import onnxruntime as ort
        from omegaconf import flag_override
        from PIL import Image
        from rapidocr import OCRVersion, RapidOCR

        models = Path(os.environ["SLANG_OCR_MODELS"])
        for name in ("det.onnx", "rec.onnx", "dict.txt"):
            if not (models / name).is_file():
                raise RuntimeError("Required local OCR model is missing")
        # CPU 2개 제한에서 ONNX 세션과 OpenCV 스레드의 경합을 줄입니다.
        cv2.setNumThreads(1)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.log_severity_level = 4
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        engine = RapidOCR(
            params={
                "Global.use_cls": False,
                "Global.return_word_box": True,
                "Global.text_score": 0.25,
                "Global.max_side_len": 16000,
                "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                "Det.model_path": str(models / "det.onnx"),
                "Det.limit_side_len": 960,
                "Rec.model_path": str(models / "rec.onnx"),
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.lang_type": "korean",
                "Rec.rec_keys_path": str(models / "dict.txt"),
            }
        )
        # 명시적인 ONNX 세션을 주입해 대기 스레드 회전과 실행 제공자를 제어합니다.
        with flag_override(engine.cfg, "allow_objects", True):
            for section, filename in (("Det", "det.onnx"), ("Rec", "rec.onnx")):
                engine.cfg[section].session = ort.InferenceSession(
                    str(models / filename),
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
        # 준비 완료 응답 전에 지연 로딩과 예열을 마쳐 첫 요청에서도 세션을 재사용합니다.
        engine._load_det_model()
        engine._load_rec_model()
        engine(Image.new("L", (96, 96), 255))
        engine(Image.new("L", (320, 48), 255), use_det=False)
        engine.use_det = True
        providers = engine.text_det.session.session.get_providers()
        if providers != ["CPUExecutionProvider"]:
            raise RuntimeError("Unexpected OCR execution provider")
        return engine, providers[0]


def recognize(engine, image, layout):
    with contextlib.redirect_stdout(sys.stderr):
        engine.text_det.limit_side_len = 1600 if layout == 6 else 960
        output = engine(image)
        words = []
        if output.txts:
            for line, items in enumerate(output.word_results):
                for text, score, polygon in items:
                    if not text.strip() or polygon is None:
                        continue
                    x = max(0, int(min(point[0] for point in polygon)))
                    y = max(0, int(min(point[1] for point in polygon)))
                    right = min(image.width, int(max(point[0] for point in polygon)))
                    bottom = min(image.height, int(max(point[1] for point in polygon)))
                    if right <= x or bottom <= y:
                        continue
                    words.append(
                        {
                            "text": text,
                            "confidence": round(float(score) * 100, 2),
                            "x": x,
                            "y": y,
                            "width": right - x,
                            "height": bottom - y,
                            "line": line,
                        }
                    )
    return words


def main():
    from PIL import Image

    engine, backend = create_engine()
    print(json.dumps({"event": "ready", "backend": backend}), flush=True)
    while header := sys.stdin.buffer.readline(1025):
        request = json.loads(header)
        width, height, layout = request["width"], request["height"], request["layout"]
        if not (0 < width <= 16000 and 0 < height <= 16000 and width * height <= 16_000_000):
            raise ValueError("Invalid image dimensions")
        if layout not in {6, 11}:
            raise ValueError("Invalid OCR layout")
        raw = sys.stdin.buffer.read(width * height)
        if len(raw) != width * height:
            raise ValueError("Truncated image payload")
        image = Image.frombytes("L", (width, height), raw)
        started = time.perf_counter()
        try:
            words = recognize(engine, image, layout)
            response = {
                "id": request["id"],
                "words": words,
                "backend": backend,
                "inference_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except Exception:
            response = {"id": request["id"], "error": "inference_failed", "backend": backend}
        finally:
            image.close()
            del raw
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
