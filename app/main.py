import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.contextual import ContextInterpreter
from app.engine import Engine, initials, normalize
from app.ocr import MAX_UPLOAD, OcrError, OcrReview, OcrService, analyze_words
from app.store import Store


class AnalyzeInput(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    threshold: float = Field(default=0.82, ge=0.75, le=0.98)
    discover: bool = True

    @field_validator("text")
    @classmethod
    def meaningful(cls, value):
        if not normalize(value)[0].strip():
            raise ValueError("분석할 텍스트를 입력하세요.")
        return value


class EntryInput(BaseModel):
    alias: str = Field(min_length=2, max_length=30, pattern=r"^[가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9]+$")
    expansion: str = Field(default="", max_length=60)
    canonical: str = Field(min_length=2, max_length=60)
    category: str = Field(default="사용자 사전", min_length=1, max_length=30)
    note: str = Field(default="사용자가 등록한 검토용 표현", max_length=500)
    needs_context: bool = True

    @field_validator("canonical", "category")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("공백만 입력할 수 없습니다.")
        return value.strip()


class ContextInput(AnalyzeInput):
    text: str = Field(min_length=1, max_length=6000)


class DiscoveryInput(BaseModel):
    texts: list[str] = Field(min_length=2, max_length=100)
    min_count: int = Field(default=2, ge=2, le=100)

    @field_validator("texts")
    @classmethod
    def limit_size(cls, texts):
        if sum(map(len, texts)) > 50000 or any(len(t) > 5000 for t in texts):
            raise ValueError("각 문서는 5,000자, 전체는 50,000자 이하로 입력하세요.")
        if len({t.strip() for t in texts if t.strip()}) < 2:
            raise ValueError("서로 다른 문서 2개 이상을 입력하세요.")
        return list(dict.fromkeys(t.strip() for t in texts if t.strip()))


def create_app(data_dir=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(Path(data_dir or os.environ.get("SLANG_DATA_DIR", "data")))
        app.state.engine = Engine(app.state.store)
        app.state.contextual = ContextInterpreter()
        app.state.ocr = OcrService()
        await run_in_threadpool(app.state.ocr.start)
        try:
            yield
        finally:
            await run_in_threadpool(app.state.ocr.close)
            # FastAPI route closures retain the app after lifespan shutdown.
            # Release the large Kiwi model rather than waiting for cyclic GC,
            # especially when multiple app lifespans run in one test process.
            del app.state.engine

    app = FastAPI(
        title="은어 렌즈 API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    static = Path(__file__).parent / "static"

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse(
                    {"detail": "다른 사이트에서의 변경 요청은 허용하지 않습니다."}, 403
                )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "외부 사이트 요청은 허용하지 않습니다."}, 403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "kiwi": True,
            "model": "rules+jamo",
            "entries": len(app.state.store.entries()),
            "version": app.state.store.version(),
        }

    @app.get("/api/dataset")
    def dataset():
        manifest_path = Path(__file__).parent / "data" / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        entries = app.state.store.entries()
        manifest["active_entries"] = len(entries)
        manifest["initial_forms"] = len(
            {
                key
                for entry in entries
                for key in (initials(entry["alias"]), initials(entry["expansion"]))
                if key
            }
        )
        return manifest

    @app.get("/api/docs", include_in_schema=False)
    def api_docs():
        return FileResponse(static / "api.html")

    @app.post("/api/analyze")
    def analyze(body: AnalyzeInput):
        return app.state.engine.analyze(body.text, body.threshold, body.discover)

    @app.get("/api/context/info")
    def context_info():
        return app.state.contextual.info()

    @app.post("/api/context/interpret")
    def interpret_context(body: ContextInput):
        fast = app.state.engine.analyze(body.text, body.threshold, body.discover)
        return app.state.contextual.interpret(body.text, fast)

    @app.get("/api/lexicon")
    def lexicon():
        return {"entries": app.state.store.entries(), "version": app.state.store.version()}

    @app.get("/api/ocr/info")
    def ocr_info():
        return app.state.ocr.info()

    @app.post("/api/ocr/analyze")
    async def analyze_image(
        request: Request,
        threshold: float = Query(0.82, ge=0.75, le=0.98),
        discover: bool = True,
        layout: int = Query(11),
    ):
        if layout not in {6, 11}:
            raise HTTPException(422, "OCR 인식 크기는 기본(11) 또는 정밀(6)로 선택하세요.")
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "이미지는 10MB 이하로 선택하세요.")
            raw.extend(chunk)
        try:
            return await run_in_threadpool(
                app.state.ocr.recognize, bytes(raw), app.state.engine, threshold, discover, layout
            )
        except OcrError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @app.post("/api/ocr/reanalyze")
    def reanalyze_image(body: OcrReview):
        try:
            return analyze_words(
                [w.model_dump() for w in body.words],
                body.image_width,
                body.image_height,
                app.state.engine,
                body.threshold,
                body.discover,
            )
        except OcrError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @app.get("/api/watchlist")
    def watchlist():
        return app.state.engine.watchlist.info()

    @app.post("/api/lexicon", status_code=201)
    def add_entry(body: EntryInput):
        try:
            with app.state.engine.lock:
                entry = body.model_dump()
                entry["expansion"] = entry["expansion"].strip() or entry["alias"]
                entry_id = app.state.store.add(entry)
            return {"id": entry_id, "message": "등록되었습니다. 다음 분석부터 적용됩니다."}
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "이미 등록된 표현입니다.") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/lexicon/{entry_id}")
    def delete_entry(entry_id: int):
        with app.state.engine.lock:
            if not app.state.store.delete(entry_id):
                raise HTTPException(404, "사전 항목을 찾을 수 없습니다.")
        return {"deleted": True}

    @app.post("/api/discover")
    def discover(body: DiscoveryInput):
        candidates = app.state.engine.discover(body.texts, body.min_count)
        app.state.store.save_candidates(candidates)
        return {
            "candidates": candidates,
            "documents": len(body.texts),
            "notice": (
                "배치 내 문서 빈도입니다. 같은 배치를 재실행해도 빈도가 누적되지 않습니다. "
                "원문은 저장하지 않습니다."
            ),
        }

    @app.get("/api/candidates")
    def candidates():
        return {"candidates": app.state.store.candidates()}

    @app.delete("/api/candidates/{candidate_id}")
    def dismiss(candidate_id: int):
        if not app.state.store.dismiss(candidate_id):
            raise HTTPException(404, "대기 중인 후보를 찾을 수 없습니다.")
        return {"dismissed": True}

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app


app = create_app()
