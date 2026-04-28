"""Local keep-alive task service for desktop app integration."""

from __future__ import annotations

import json
import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .pipeline_runner import execute_run_pipeline


@dataclass
class TaskRecord:
    id: str
    created_at: float
    status: str = "queued"
    params: dict[str, Any] = field(default_factory=dict)
    started_at: float | None = None
    ended_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "params": self.params,
            "result": self.result,
            "error": self.error,
        }


class KeepAliveService:
    def __init__(self, app_context: dict[str, Any]):
        self.app_context = app_context
        self._tasks: dict[str, TaskRecord] = {}
        self._task_order: list[str] = []
        self._q: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def create_task(self, params: dict[str, Any]) -> TaskRecord:
        task_id = uuid.uuid4().hex
        rec = TaskRecord(id=task_id, created_at=time.time(), params=params)
        with self._lock:
            self._tasks[task_id] = rec
            self._task_order.append(task_id)
        self._q.put(task_id)
        return rec

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            ids = self._task_order[-limit:]
            return [self._tasks[i].to_dict() for i in reversed(ids)]

    def warmup_ocr(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            from shared.ocr_hunyuan import get_ocr_engine

            engine = get_ocr_engine()
            if hasattr(engine, "_ensure_model"):
                engine._ensure_model()  # type: ignore[attr-defined]
            elapsed = time.perf_counter() - started
            return {"ok": True, "elapsed_sec": round(elapsed, 3)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _worker_loop(self) -> None:
        while True:
            task_id = self._q.get()
            rec = self.get_task(task_id)
            if rec is None:
                continue
            with self._lock:
                rec.status = "running"
                rec.started_at = time.time()
            try:
                result = execute_run_pipeline(
                    self.app_context,
                    no_llm=bool(rec.params.get("no_llm", False)),
                    openclaw_gateway=bool(rec.params.get("openclaw_gateway", False)),
                    work_dir=rec.params.get("work_dir"),
                )
                with self._lock:
                    rec.status = "done"
                    rec.result = result
            except Exception as e:
                with self._lock:
                    rec.status = "failed"
                    rec.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            finally:
                with self._lock:
                    rec.ended_at = time.time()


class _ServiceHandler(BaseHTTPRequestHandler):
    service: KeepAliveService

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"ok": True, "service": "weclaw-cua", "status": "up"})
            return
        if path == "/tasks":
            self._send_json(200, {"ok": True, "tasks": self.service.list_tasks()})
            return
        if path.startswith("/tasks/"):
            task_id = path.split("/", 2)[2].strip()
            rec = self.service.get_task(task_id)
            if rec is None:
                self._send_json(404, {"ok": False, "error": "task_not_found"})
                return
            self._send_json(200, {"ok": True, "task": rec.to_dict()})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/warmup":
            body = self._read_json()
            if body.get("ocr", True):
                result = self.service.warmup_ocr()
                self._send_json(200 if result.get("ok") else 500, result)
                return
            self._send_json(200, {"ok": True, "note": "nothing_to_warmup"})
            return
        if path == "/tasks":
            body = self._read_json()
            params = {
                "no_llm": bool(body.get("no_llm", False)),
                "openclaw_gateway": bool(body.get("openclaw_gateway", False)),
                "work_dir": body.get("work_dir"),
            }
            rec = self.service.create_task(params)
            self._send_json(202, {"ok": True, "task_id": rec.id, "task": rec.to_dict()})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args) -> None:
        return


def run_keep_alive_server(app_context: dict[str, Any], host: str, port: int) -> None:
    service = KeepAliveService(app_context)
    handler_cls = type("KeepAliveHandler", (_ServiceHandler,), {})
    handler_cls.service = service
    server = ThreadingHTTPServer((host, port), handler_cls)
    print(f"[*] WeClaw keep-alive service listening on http://{host}:{port}")
    print("[*] Endpoints: GET /health, POST /warmup, POST /tasks, GET /tasks, GET /tasks/{id}")
    server.serve_forever()
