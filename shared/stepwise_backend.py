"""StepwiseBackend: writes image+prompt to a work directory for an external agent.

Instead of calling an LLM, each query() call:
  1. Saves the image as {step_id}.<configured extension>
  2. Saves the prompt as {step_id}.prompt.txt
  3. Records the pending task in a manifest.json

The calling agent reads the manifest, processes each task with its own LLM,
and writes responses as {step_id}.response.txt.

The finalize command then reads those responses and continues the pipeline.
"""

import json
import os
import threading
import time

from PIL import Image

from shared.vision_image_codec import encode_vision_image
from shared.vision_image_codec import log_vision_timing


_EXTENSIONS = {
    "png": "png",
    "webp_lossless": "webp",
    "webp": "webp",
    "jpeg": "jpg",
}


class StepwiseBackend:
    def __init__(self, work_dir: str) -> None:
        assert work_dir
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)
        self._counter = 0
        self._lock = threading.Lock()
        self._manifest_path = os.path.join(work_dir, "manifest.json")
        self._tasks: list[dict] = []
        self._metadata: dict = {}
        if os.path.isfile(self._manifest_path):
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._tasks = data.get("tasks", [])
            self._metadata = data.get("metadata", {})
            self._counter = len(self._tasks)

    def _next_step_id(self) -> str:
        with self._lock:
            step_id = f"step_{self._counter:04d}"
            self._counter += 1
            return step_id

    def query(self, prompt: str, image: Image.Image, max_tokens: int = 2048) -> str | None:
        """Save image+prompt to work_dir. Returns None (agent must provide response later)."""
        step_id = self._next_step_id()

        started = time.perf_counter()
        payload = encode_vision_image(image)
        ext = _EXTENSIONS[payload.format_name]
        img_path = os.path.join(self.work_dir, f"{step_id}.{ext}")
        with open(img_path, "wb") as f:
            f.write(payload.raw_bytes)
        log_vision_timing(
            "stepwise",
            "encoded",
            step_id=step_id,
            format=payload.format_name,
            mime=payload.mime_type,
            width=payload.width,
            height=payload.height,
            bytes=payload.byte_count,
            b64_chars=payload.base64_char_count,
            encode_ms=round(payload.encode_seconds * 1000, 1),
            total_ms=round((time.perf_counter() - started) * 1000, 1),
            max_tokens=max_tokens,
        )

        prompt_path = os.path.join(self.work_dir, f"{step_id}.prompt.txt")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt)

        response_path = os.path.join(self.work_dir, f"{step_id}.response.txt")

        task = {
            "step_id": step_id,
            "image": os.path.basename(img_path),
            "image_mime_type": payload.mime_type,
            "image_format": payload.format_name,
            "image_bytes": payload.byte_count,
            "prompt_file": os.path.basename(prompt_path),
            "response_file": os.path.basename(response_path),
            "max_tokens": max_tokens,
            "completed": False,
        }
        self._tasks.append(task)
        self._write_manifest()

        print(f"[stepwise] Saved vision task: {img_path}")
        print(f"[stepwise] Prompt: {prompt_path}")
        print(f"[stepwise] Agent should write response to: {response_path}")

        if os.path.isfile(response_path):
            with open(response_path, "r", encoding="utf-8") as f:
                return f.read().strip() or None

        return None

    def get_pending_tasks(self) -> list[dict]:
        return [t for t in self._tasks if not t["completed"]]

    def set_metadata(self, metadata: dict) -> None:
        self._metadata.update(metadata)
        self._write_manifest()

    def mark_completed(self, step_id: str) -> None:
        for t in self._tasks:
            if t["step_id"] == step_id:
                t["completed"] = True
        self._write_manifest()

    def read_response(self, step_id: str) -> str | None:
        response_path = os.path.join(self.work_dir, f"{step_id}.response.txt")
        if not os.path.isfile(response_path):
            return None
        with open(response_path, "r", encoding="utf-8") as f:
            return f.read().strip() or None

    def _write_manifest(self) -> None:
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(
                {"metadata": self._metadata, "tasks": self._tasks},
                f,
                ensure_ascii=False,
                indent=2,
            )
