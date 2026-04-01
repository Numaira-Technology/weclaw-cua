"""Write `last_run.json` after WeClaw pipeline runs for OpenClaw/cron integration.

Usage:
    from shared.run_manifest import build_last_run_payload, write_last_run

Input spec:
    - output_dir: directory for last_run.json (same as WeclawConfig.output_dir).
    - Fields: ok, config_path, weclaw_root, message_json_paths, report_generated, error.

Output spec:
    - Writes `output_dir/last_run.json`, returns absolute path.
    - JSON schema:
      {
        "ok": true,
        "finished_at_utc": "2026-04-01T12:00:00+00:00",
        "config_path": "/abs/config.json",
        "weclaw_root": "/abs/weclaw",
        "output_dir": "/abs/output",
        "message_json_paths": ["/abs/output/Chat.json"],
        "report_generated": true,
        "error": null
      }
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def build_last_run_payload(
    *,
    ok: bool,
    config_path: str,
    weclaw_root: str,
    output_dir: str,
    message_json_paths: list[str],
    report_generated: bool,
    error: str | None,
) -> dict:
    assert config_path
    assert weclaw_root
    assert output_dir
    assert isinstance(message_json_paths, list)
    out: dict = {
        "ok": ok,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": os.path.abspath(config_path),
        "weclaw_root": os.path.abspath(weclaw_root),
        "output_dir": os.path.abspath(output_dir),
        "message_json_paths": [os.path.abspath(p) for p in message_json_paths],
        "report_generated": report_generated,
        "error": error,
    }
    return out


def write_last_run(output_dir: str, payload: dict) -> str:
    assert output_dir
    assert isinstance(payload, dict)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "last_run.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return os.path.abspath(path)
