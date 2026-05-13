"""Windows sidebar OCR debug artifacts and terminal diagnostics.

Usage:
    prefix = new_sidebar_debug_prefix()
    save_sidebar_crop(prefix, sidebar_image)
    print_ocr_lines("OCR raw lines", raw_lines)
    write_sidebar_debug(prefix, raw_lines, vlm_threads, row_debug_entries)

Input spec:
    - `sidebar_image` is a PIL image of the Windows WeChat sidebar crop.
    - OCR lines expose `text`, `bbox`, `conf`, `center_x`, and `center_y`.
    - VLM threads and row debug entries are dictionaries.

Output spec:
    - Writes `debug_outputs/sidebar_ocr/windows_sidebar_<timestamp>.png`.
    - Writes `debug_outputs/sidebar_ocr/windows_sidebar_<timestamp>.json`.
    - Prints OCR rows and final row diagnostics to the terminal.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any

from PIL import Image

_DEBUG_DIR = Path("debug_outputs/sidebar_ocr")


def new_sidebar_debug_prefix() -> Path:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    return _DEBUG_DIR / f"windows_sidebar_{int(time() * 1000)}"


def save_sidebar_crop(prefix: Path, sidebar_image: Image.Image) -> None:
    path = prefix.with_suffix(".png")
    sidebar_image.save(path)
    print(f"[DEBUG] Windows sidebar OCR crop saved: {path}")


def _line_dict(line: Any) -> dict[str, Any]:
    return {
        "text": str(getattr(line, "text", "")),
        "bbox": list(getattr(line, "bbox", ())),
        "conf": float(getattr(line, "conf", 0.0)),
        "center_x": int(getattr(line, "center_x", 0)),
        "center_y": int(getattr(line, "center_y", 0)),
    }


def print_ocr_lines(label: str, lines: list[Any]) -> None:
    print(f"[DEBUG] {label}: {len(lines)}")
    for idx, line in enumerate(lines):
        d = _line_dict(line)
        print(
            f"  #{idx:02d} text={d['text']!r} "
            f"bbox={tuple(d['bbox'])} conf={d['conf']:.3f}"
        )


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        "name": str(getattr(row, "name", "")),
        "badge_text": getattr(row, "badge_text", None),
        "is_group": bool(getattr(row, "is_group", False)),
        "selected": bool(getattr(row, "selected", False)),
        "bbox": list(getattr(row, "bbox", ())),
    }


def write_sidebar_debug(
    prefix: Path,
    raw_lines: list[Any],
    vlm_threads: list[dict],
    row_debug_entries: list[dict[str, Any]],
) -> None:
    payload = {
        "raw_lines": [_line_dict(line) for line in raw_lines],
        "vlm_threads": vlm_threads,
        "rows": row_debug_entries,
    }
    path = prefix.with_suffix(".json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DEBUG] Windows sidebar OCR details saved: {path}")
    print(f"[DEBUG] VLM threads: {len(vlm_threads)}")
    for idx, thread in enumerate(vlm_threads):
        print(
            f"  VLM #{idx:02d} name={thread.get('name')!r} "
            f"unread={thread.get('unread')!r} unread_badge={thread.get('unread_badge')!r} "
            f"is_group={thread.get('is_group')!r} selected={thread.get('selected')!r} "
            f"y={thread.get('y')!r}"
        )
    print(f"[DEBUG] Final sidebar rows: {len(row_debug_entries)}")
    for idx, entry in enumerate(row_debug_entries):
        row = entry.get("row", {})
        vlm_thread = entry.get("vlm_thread") or {}
        print(
            f"  #{idx:02d} name={row.get('name')!r} badge={row.get('badge_text')!r} "
            f"is_group={row.get('is_group')!r} selected={row.get('selected')!r} "
            f"bbox={tuple(row.get('bbox') or [])} "
            f"vlm_name={vlm_thread.get('name')!r}"
        )


def make_row_debug_entry(
    ocr_line: Any | None,
    row: Any,
    vlm_thread: dict | None,
) -> dict[str, Any]:
    return {
        "ocr_line": _line_dict(ocr_line) if ocr_line is not None else None,
        "row": _row_dict(row),
        "vlm_thread": vlm_thread or {},
    }
