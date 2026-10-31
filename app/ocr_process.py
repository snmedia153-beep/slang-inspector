"""크기·시간을 제한한 메모리 파이프로 재사용 가능한 OCR 프로세스를 관리합니다."""

import json
import os
import queue
import subprocess
import sys
import threading
import time


class OcrProcess:
    def __init__(self, timeout=40):
        self.timeout = timeout
        self.process = None
        self.responses = None
        self.sequence = 0
        self.backend = None
        self.startup_ms = None

    @property
    def ready(self):
        return self.process is not None and self.process.poll() is None and self.backend is not None

    @staticmethod
    def _read_responses(stream, responses):
        try:
            while line := stream.readline(4 * 1024 * 1024 + 1):
                if len(line) > 4 * 1024 * 1024:
                    raise ValueError("OCR response exceeds protocol limit")
                responses.put(json.loads(line), timeout=1)
        except (OSError, ValueError, queue.Full):
            pass
        finally:
            try:
                responses.put(None, timeout=1)
            except queue.Full:
                pass

    def _receive(self, deadline):
        try:
            response = self.responses.get(timeout=max(0, deadline - time.perf_counter()))
        except queue.Empty as exc:
            raise TimeoutError("OCR worker deadline exceeded") from exc
        if response is None:
            raise OSError("OCR worker exited or returned invalid JSON")
        if not isinstance(response, dict):
            raise ValueError("Invalid OCR protocol response")
        return response

    def start(self, deadline=None):
        if self.ready:
            return
        self.close()
        started = time.perf_counter()
        if deadline is None:
            deadline = started + self.timeout
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "app.ocr_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "OMP_THREAD_LIMIT": "2"},
            )
            self.responses = queue.Queue(maxsize=2)
            threading.Thread(
                target=self._read_responses,
                args=(self.process.stdout, self.responses),
                daemon=True,
                name="ocr-responses",
            ).start()
            response = self._receive(deadline)
            if (
                response.get("event") != "ready"
                or response.get("backend") != "CPUExecutionProvider"
            ):
                raise ValueError("OCR worker did not become ready")
            self.backend = response["backend"]
            self.startup_ms = round((time.perf_counter() - started) * 1000, 1)
        except Exception:
            self.close()
            raise

    def recognize(self, pixels, width, height, layout):
        deadline = time.perf_counter() + self.timeout
        self.start(deadline)
        self.sequence += 1
        request_id = self.sequence
        header = (
            json.dumps(
                {"id": request_id, "width": width, "height": height, "layout": layout}
            ).encode()
            + b"\n"
        )
        responses, stream = self.responses, self.process.stdin

        def send():
            try:
                stream.write(header)
                stream.write(pixels)
                stream.flush()
            except (OSError, ValueError):
                try:
                    responses.put(None, timeout=1)
                except queue.Full:
                    pass

        try:
            threading.Thread(target=send, daemon=True, name="ocr-request").start()
            response = self._receive(deadline)
            if response.get("id") != request_id or response.get("backend") != self.backend:
                raise ValueError("OCR response does not match the current request")
            if response.get("error"):
                raise OSError("OCR inference failed")
            return response
        except Exception:
            # 만료된 작업의 응답이 다음 이미지에 섞이지 않도록 프로세스를 종료합니다.
            self.close()
            raise

    def close(self):
        process, self.process = self.process, None
        self.backend = None
        self.responses = None
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
