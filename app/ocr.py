"""이미지를 검증하고 OCR 단어 좌표를 텍스트 분석의 원문 위치에 연결합니다."""

import importlib.util
import io
import os
import threading
import time
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.ocr_process import OcrProcess

MAX_UPLOAD = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_WORDS = 2000
MAX_TEXT = 20000


class OcrError(Exception):
    def __init__(self, message, status=422):
        self.status = status
        super().__init__(message)


class OcrWord(BaseModel):
    text: str = Field(max_length=100)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    confidence: float = Field(ge=0, le=100)
    line: int = Field(ge=0, le=MAX_WORDS)


class OcrReview(BaseModel):
    image_width: int = Field(gt=0, le=16000)
    image_height: int = Field(gt=0, le=16000)
    words: list[OcrWord] = Field(max_length=MAX_WORDS)
    threshold: float = Field(default=0.82, ge=0.75, le=0.98)
    discover: bool = True

    @model_validator(mode="after")
    def bounds(self):
        if self.image_width * self.image_height > MAX_PIXELS:
            raise ValueError("이미지는 1,600만 픽셀 이하로 선택하세요.")
        if any(
            w.x + w.width > self.image_width or w.y + w.height > self.image_height
            for w in self.words
        ):
            raise ValueError("OCR 단어 상자가 이미지 범위를 벗어났습니다.")
        if sum(len(w.text) + 1 for w in self.words) > MAX_TEXT:
            raise ValueError("OCR 텍스트는 20,000자 이하로 입력하세요.")
        return self


def analyze_words(words, width, height, engine, threshold=0.82, discover=True):
    """줄 경계를 유지한 OCR 텍스트를 분석하고 겹치는 원래 단어 상자를 반환합니다."""
    parts, indexed, offset, previous = [], [], 0, None
    for word in words:
        text = word["text"].replace("\n", " ").replace("\r", " ").strip()
        if not text:
            continue
        separator = "" if not parts else " " if word["line"] == previous else "\n"
        parts.extend((separator, text))
        offset += len(separator)
        indexed.append(
            {**word, "text": text, "id": len(indexed), "start": offset, "end": offset + len(text)}
        )
        offset += len(text)
        previous = word["line"]
    text = "".join(parts)
    if len(text) > MAX_TEXT:
        raise OcrError("OCR 텍스트가 20,000자를 넘었습니다. 이미지를 나누어 분석하세요.")
    analysis = engine.analyze(text, threshold, discover)
    targets = [{**m, "origin": "analysis"} for m in analysis["matches"]]
    for hit in analysis.get("watchlist_hits", []):
        if hit["assessment"] not in {"unresolved", "contextual"} or any(
            hit["start"] < t["end"] and hit["end"] > t["start"] for t in targets
        ):
            continue
        targets.append(
            {
                **hit,
                "expansion": hit["meaning"],
                "origin": "unresolved_watchlist"
                if hit["assessment"] == "unresolved"
                else "watchlist_context",
            }
        )
    regions = []
    for target in sorted(targets, key=lambda t: t["start"]):
        covered = [w for w in indexed if target["start"] < w["end"] and target["end"] > w["start"]]
        if not covered:
            continue
        regions.append(
            {
                "id": len(regions),
                "start": target["start"],
                "end": target["end"],
                "surface": target["surface"],
                "expansion": target.get("expansion")
                or (
                    "원형 미확인 · 초성 검토 후보"
                    if target.get("evidence") == "unresolved_reference"
                    else None
                ),
                "alternatives": target.get("alternatives", []),
                "origin": target["origin"],
                "category": target.get("category", target.get("group_label", "검토 후보")),
                "word_ids": [w["id"] for w in covered],
                "confidence": round(min(w["confidence"] for w in covered), 1),
                "boxes": [{k: w[k] for k in ("x", "y", "width", "height")} for w in covered],
            }
        )
    return {
        "text": text,
        "image_width": width,
        "image_height": height,
        "words": indexed,
        "analysis": analysis,
        "regions": regions,
        "notice": (
            "빨간 표식은 OCR 텍스트의 검토 후보입니다. "
            "OCR 오인식·초성 다의성이 있으며 불법성 판정이 아닙니다. "
            "상자는 해당 표현이 포함된 인식 단어 전체를 표시합니다."
        ),
    }


class OcrService:
    def __init__(self):
        self.gate = threading.BoundedSemaphore(1)
        self.worker = OcrProcess()
        self.startup_error = None

    def start(self):
        if not self.info()["available"]:
            return
        try:
            self.worker.start()
            self.startup_error = None
        except (OSError, ValueError, TimeoutError):
            # 텍스트 분석은 계속 제공하고 다음 이미지 요청에서 작업 프로세스를 재시도합니다.
            self.startup_error = "OCR 사전 준비에 실패했습니다. 이미지 분석 시 다시 시도합니다."

    def close(self):
        self.worker.close()

    def info(self):
        models = Path(os.environ.get("SLANG_OCR_MODELS", Path(__file__).parent / "ocr_models"))
        ready = all((models / name).is_file() for name in ("det.onnx", "rec.onnx", "dict.txt"))
        ready = ready and all(
            importlib.util.find_spec(name) for name in ("rapidocr", "onnxruntime")
        )
        return {
            "available": bool(ready),
            "engine": "RapidOCR / PP-OCRv5 Korean",
            "message": "한국어 OCR 준비됨"
            if ready
            else "OCR 모델이 없습니다. 최신 Docker 이미지를 빌드하세요.",
            "max_bytes": MAX_UPLOAD,
            "max_pixels": MAX_PIXELS,
            "warmed_up": self.worker.ready,
            "backend": self.worker.backend,
            "startup_ms": self.worker.startup_ms,
            "startup_error": self.startup_error,
        }

    def recognize(self, raw, engine, threshold=0.82, discover=True, layout=11):
        started = time.perf_counter()
        if not self.gate.acquire(blocking=False):
            raise OcrError("다른 이미지의 OCR이 진행 중입니다. 잠시 후 다시 실행하세요.", 429)
        try:
            if not raw or len(raw) > MAX_UPLOAD:
                raise OcrError("이미지는 비어 있지 않은 10MB 이하 파일로 선택하세요.", 413)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.format not in {"PNG", "JPEG", "WEBP"}:
                            raise OcrError("PNG·JPEG·WebP 이미지만 지원합니다.")
                        if getattr(source, "n_frames", 1) != 1:
                            raise OcrError("움직이는 이미지는 정지 이미지로 저장해 선택하세요.")
                        if source.width * source.height > MAX_PIXELS or max(source.size) > 16000:
                            raise OcrError(
                                "이미지는 1,600만 픽셀, 한 변 16,000px 이하로 선택하세요.", 413
                            )
                        image = ImageOps.exif_transpose(source).convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                pixels = ImageOps.grayscale(background).tobytes()
                width, height = image.size
            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                Image.DecompressionBombWarning,
                Image.DecompressionBombError,
            ) as exc:
                raise OcrError(
                    "이미지를 해석하지 못했습니다. 정상 PNG·JPEG·WebP 파일을 선택하세요."
                ) from exc
            if layout not in {6, 11}:
                raise OcrError("지원하지 않는 OCR 배치 설정입니다.")
            if not self.info()["available"]:
                raise OcrError("OCR 모델이 없습니다. 최신 Docker 이미지를 빌드하세요.", 503)
            prepared = time.perf_counter()
            try:
                response = self.worker.recognize(pixels, width, height, layout)
                self.startup_error = None
            except FileNotFoundError as exc:
                raise OcrError(
                    "OCR 엔진이 없습니다. 최신 Docker 이미지를 빌드하세요.", 503
                ) from exc
            except TimeoutError as exc:
                raise OcrError(
                    "OCR 처리 시간이 40초를 넘었습니다. 필요한 부분을 잘라 다시 시도하세요.", 504
                ) from exc
            except OSError as exc:
                raise OcrError(
                    "OCR 처리에 실패했습니다. 엔진과 언어 데이터를 확인하세요.", 503
                ) from exc
            except ValueError as exc:
                raise OcrError("OCR 응답의 요청 식별자를 확인하지 못했습니다.", 502) from exc
            try:
                reviewed = OcrReview(
                    image_width=width, image_height=height, words=response["words"]
                )
                words = [word.model_dump() for word in reviewed.words]
            except (KeyError, ValueError, TypeError, ValidationError) as exc:
                raise OcrError("OCR 응답의 좌표·텍스트 형식을 확인하지 못했습니다.", 502) from exc
            recognized = time.perf_counter()
            result = analyze_words(words, width, height, engine, threshold, discover)
            completed = time.perf_counter()
            return {
                **result,
                "ocr_elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "ocr_engine": "RapidOCR PP-OCRv5 Korean / ONNX CPU",
                "ocr_backend": response["backend"],
                "ocr_timings": {
                    "preprocess_ms": round((prepared - started) * 1000, 1),
                    "worker_ms": round((recognized - prepared) * 1000, 1),
                    "inference_ms": response["inference_ms"],
                    "analysis_ms": round((completed - recognized) * 1000, 1),
                },
                "layout": layout,
                "message": "인식된 글자가 없습니다. 더 선명한 이미지나 정밀 모드를 시도하세요."
                if not words
                else "OCR과 은어 대조를 완료했습니다.",
            }
        finally:
            self.gate.release()
