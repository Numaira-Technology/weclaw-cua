"""Debug PNGs for stitched chat-panel images sent to the vision model.

Usage:
    session = new_chat_stitch_session_basename()
    save_chat_stitch_for_vlm(session, chat_name, chunk_index, stitched_image)

Input spec:
    - stitched_image: PIL Image passed to VisionBackend.query / VisionAI.query.
    - chunk_index: 0-based index matching the driver extraction loop (reverse order ok).

Output spec:
    - Default: debug_outputs/chat_stitch/chat_stitch_<ms>_<chat>_chunk_<n>.png
    - If WECLAW_DEBUG_STITCH_DIR is set: same filenames under that directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from time import time

from PIL import Image

_DEFAULT_DIR = Path("debug_outputs/chat_stitch")


def _sanitize_chat_name(chat_name: str) -> str:
    base = chat_name.replace("/", "_").replace("\\", "_").strip()[:100]
    return base or "chat"


def resolve_chat_stitch_debug_dir() -> Path:
    raw = os.environ.get("WECLAW_DEBUG_STITCH_DIR", "").strip()
    if raw:
        return Path(raw)
    return _DEFAULT_DIR


def new_chat_stitch_session_basename() -> str:
    return f"chat_stitch_{int(time() * 1000)}"


def save_chat_stitch_for_vlm(
    session_basename: str,
    chat_name: str,
    chunk_index: int,
    image: Image.Image,
) -> None:
    assert session_basename
    assert chat_name
    assert chunk_index >= 0
    assert image is not None
    d = resolve_chat_stitch_debug_dir()
    d.mkdir(parents=True, exist_ok=True)
    safe = _sanitize_chat_name(chat_name)
    path = d / f"{session_basename}_{safe}_chunk_{chunk_index + 1}.png"
    image.save(path)
    print(f"[DEBUG] Chat stitch (VLM input) saved: {path}")


def save_chat_frame_before_stitch(
    session_basename: str,
    chat_name: str,
    frame_index: int,
    image: Image.Image,
) -> None:
    assert session_basename
    assert chat_name
    assert frame_index >= 0
    assert image is not None
    d = resolve_chat_stitch_debug_dir()
    d.mkdir(parents=True, exist_ok=True)
    safe = _sanitize_chat_name(chat_name)
    path = d / f"{session_basename}_{safe}_frame_{frame_index + 1:03d}.png"
    image.save(path)
    print(f"[DEBUG] Chat frame (before stitch) saved: {path}")
