FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SLANG_DATA_DIR=/data SLANG_OCR_MODELS=/opt/slang-ocr
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt -c requirements.lock \
    && useradd --uid 10001 --create-home slang \
    && mkdir /data && chown slang:slang /data
COPY scripts/fetch_ocr_models.py app/data/ocr_models.json /tmp/ocr-build/
RUN python /tmp/ocr-build/fetch_ocr_models.py /tmp/ocr-build/ocr_models.json /opt/slang-ocr \
    && rm -rf /tmp/ocr-build
COPY app ./app
COPY licenses ./licenses
COPY THIRD_PARTY_NOTICES.md ./
USER slang
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "20"]

FROM runtime AS test
USER root
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk fontconfig \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY pyproject.toml ./
COPY tests ./tests
COPY scripts/import_watchlist.py ./scripts/import_watchlist.py
USER slang
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
