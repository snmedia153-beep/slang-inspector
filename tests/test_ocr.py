import io
import subprocess

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.main import create_app
from app.ocr import MAX_UPLOAD, OcrReview, analyze_words


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(create_app(tmp_path_factory.mktemp("ocr"))) as client:
        yield client


def make_image(text=None, size=(1200, 300), fmt="PNG", **options):
    image = Image.new("RGB", size, "white")
    if text:
        font_path = subprocess.check_output(
            ["fc-match", "-f", "%{file}", "Noto Sans CJK KR"]
        ).decode()
        font = ImageFont.truetype(font_path, 48)
        ImageDraw.Draw(image).text((40, 50), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def word(text, x=10, line=0):
    return {
        "text": text,
        "x": x,
        "y": 10 + line * 40,
        "width": 30,
        "height": 25,
        "confidence": 90,
        "line": line,
    }


def test_mapping_preserves_repeated_words_unicode_and_compound_boxes(client):
    words = [
        word("🧪", 0),
        word("몸사", 40),
        word("판매", 80),
        word("몸사", 10, 1),
        word("판매", 50, 1),
    ]
    result = analyze_words(words, 200, 200, client.app.state.engine)
    matches = [r for r in result["regions"] if "몸사" in r["surface"]]
    assert len(matches) == 2
    assert matches[0]["boxes"][0]["x"] == 40
    assert matches[1]["boxes"][0]["x"] == 10
    assert all(result["text"][r["start"] : r["end"]] == r["surface"] for r in result["regions"])
    result = analyze_words([word("교복", 10), word("업스", 50)], 200, 100, client.app.state.engine)
    region = next(r for r in result["regions"] if "업스" in r["surface"])
    assert len(region["boxes"]) == 2


def test_neutral_words_are_not_red_and_unknown_listed_word_is_visible(client):
    result = analyze_words(
        [word("서울"), word("학생", 50), word("용돈", 90)], 200, 100, client.app.state.engine
    )
    assert result["regions"] == []
    result = analyze_words([word("야상극")], 200, 100, client.app.state.engine)
    assert result["regions"][0]["origin"] == "unresolved_watchlist"
    contextual = analyze_words(
        [word("몸사"), word("판매", 50), word("맘눌뎀", 90)], 200, 100, client.app.state.engine
    )
    assert any(
        r["surface"] == "맘눌뎀" and r["origin"] == "watchlist_context"
        for r in contextual["regions"]
    )


def test_manual_correction_restores_initials_without_changing_geometry(client):
    words = [word("O"), word("2", 50)]
    words[0]["text"], words[1]["text"] = "ㅇ", "ㄹ"
    response = client.post(
        "/api/ocr/reanalyze", json={"words": words, "image_width": 200, "image_height": 100}
    )
    assert response.status_code == 200
    data = response.json()
    region = next(r for r in data["regions"] if "오랄" in r["expansion"])
    assert region["word_ids"] == [0, 1]
    assert [b["x"] for b in region["boxes"]] == [10, 50]
    words[0]["text"] = words[1]["text"] = ""
    assert (
        client.post(
            "/api/ocr/reanalyze", json={"words": words, "image_width": 200, "image_height": 100}
        ).json()["regions"]
        == []
    )


@pytest.mark.parametrize("change", [{"x": -1}, {"width": 1000}, {"confidence": 101}, {"line": -1}])
def test_review_rejects_invalid_geometry(client, change):
    response = client.post(
        "/api/ocr/reanalyze",
        json={"words": [{**word("몸사"), **change}], "image_width": 200, "image_height": 100},
    )
    assert response.status_code == 422


def test_review_rejects_nan_and_excessive_image_pixels():
    with pytest.raises(ValueError):
        OcrReview(
            image_width=200, image_height=100, words=[{**word("몸사"), "confidence": float("nan")}]
        )
    with pytest.raises(ValueError):
        OcrReview(image_width=5000, image_height=5000, words=[])


def test_invalid_upload_size_type_and_options(client):
    assert client.post("/api/ocr/analyze", content=b"not an image").status_code == 422
    assert client.post("/api/ocr/analyze", content=b"x" * (MAX_UPLOAD + 1)).status_code == 413
    assert client.post("/api/ocr/analyze", content=b"").status_code == 413
    assert client.post("/api/ocr/analyze?layout=99", content=b"x").status_code == 422
    assert client.post("/api/ocr/analyze?threshold=3", content=b"x").status_code == 422


def test_actual_korean_ocr_detects_keywords_and_coordinates(client):
    assert client.get("/api/ocr/info").json()["available"]
    response = client.post(
        "/api/ocr/analyze",
        content=make_image("몸사 판매 지인합성 야상극"),
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "지인합성" in data["text"].replace(" ", "")
    assert any("몸사" in r["surface"].replace(" ", "") for r in data["regions"])
    assert any(r["origin"] == "unresolved_watchlist" for r in data["regions"])
    assert data["image_width"] == 1200 and data["image_height"] == 300
    for region in data["regions"]:
        assert region["boxes"]
        for box in region["boxes"]:
            assert 0 <= box["x"] < box["x"] + box["width"] <= 1200
            assert 0 <= box["y"] < box["y"] + box["height"] <= 300


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_actual_ocr_neutral_image_has_no_red_keywords(client, fmt):
    response = client.post("/api/ocr/analyze", content=make_image("서울 학생 용돈 관리", fmt=fmt))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["words"]
    assert data["regions"] == []


def test_blank_image_and_exif_orientation(client):
    assert client.post("/api/ocr/analyze", content=make_image()).json()["words"] == []
    exif = Image.Exif()
    exif[274] = 6
    data = client.post(
        "/api/ocr/analyze", content=make_image(size=(200, 100), fmt="JPEG", exif=exif)
    ).json()
    assert (data["image_width"], data["image_height"]) == (100, 200)


def test_worker_timeout_failure_and_bad_response_are_explicit(client, monkeypatch):
    raw = make_image()

    def timeout(*args, **kwargs):
        raise TimeoutError("ocr")

    monkeypatch.setattr(client.app.state.ocr.worker, "recognize", timeout)
    assert client.post("/api/ocr/analyze", content=raw).status_code == 504

    def failed(*args, **kwargs):
        raise OSError("ocr")

    monkeypatch.setattr(client.app.state.ocr.worker, "recognize", failed)
    assert client.post("/api/ocr/analyze", content=raw).status_code == 503
    monkeypatch.setattr(
        client.app.state.ocr.worker,
        "recognize",
        lambda *args, **kwargs: {"words": [word("몸사", 2000)]},
    )
    assert client.post("/api/ocr/analyze", content=raw).status_code == 502


def test_warm_worker_reused_across_layouts_and_different_images(client):
    service = client.app.state.ocr
    assert service.info()["warmed_up"]
    process = service.worker.process
    raw = make_image("몸사 판매 지인합성 야상극")
    first = client.post("/api/ocr/analyze", content=raw).json()
    fine = client.post("/api/ocr/analyze?layout=6", content=raw)
    assert fine.status_code == 200
    assert fine.json()["words"]
    blank = client.post("/api/ocr/analyze", content=make_image()).json()
    assert blank["words"] == [] and blank["regions"] == []
    again = client.post("/api/ocr/analyze", content=raw).json()
    for key in ("text", "words", "regions"):
        assert first[key] == again[key]
    assert service.worker.process is process
    assert again["ocr_backend"] == "CPUExecutionProvider"
    assert again["ocr_timings"]["inference_ms"] > 0


def test_worker_deadline_kills_process_and_next_request_recovers():
    from app.ocr_process import OcrProcess

    worker = OcrProcess()
    try:
        worker.start()
        old = worker.process
        worker.timeout = 0
        with pytest.raises(TimeoutError):
            worker.recognize(b"\xff" * 1200 * 300, 1200, 300, 11)
        assert old.poll() is not None and not worker.ready
        worker.timeout = 40
        result = worker.recognize(b"\xff" * 1200 * 300, 1200, 300, 11)
        assert result["words"] == []
        assert worker.process.pid != old.pid
        current = worker.process
    finally:
        worker.close()
    assert current.poll() is not None


def test_worker_rejects_mismatched_response_and_restarts(monkeypatch):
    from app.ocr_process import OcrProcess

    worker = OcrProcess()
    try:
        worker.start()
        old = worker.process
        with monkeypatch.context() as patch:
            patch.setattr(
                worker, "_receive", lambda deadline: {"id": -1, "backend": worker.backend}
            )
            with pytest.raises(ValueError, match="current request"):
                worker.recognize(b"\xff" * 96 * 96, 96, 96, 11)
        assert old.poll() is not None
        assert worker.recognize(b"\xff" * 96 * 96, 96, 96, 11)["words"] == []
    finally:
        worker.close()


def test_busy_guard_is_released_and_cross_site_upload_is_rejected(client):
    gate = client.app.state.ocr.gate
    assert gate.acquire(blocking=False)
    try:
        assert client.post("/api/ocr/analyze", content=make_image()).status_code == 429
    finally:
        gate.release()
    assert client.post("/api/ocr/analyze", content=b"bad").status_code == 422
    assert (
        client.post(
            "/api/ocr/analyze", content=b"x", headers={"Origin": "https://example.com"}
        ).status_code
        == 403
    )
