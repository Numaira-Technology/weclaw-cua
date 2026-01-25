"""
Extract suspects flagged by the agent for a given thread.

Usage:
  suspects = extract_suspects(thread, text_output, screenshot_paths)

Input:
  - thread: GroupThread in context.
  - text_output: Text returned by the agent, containing JSON with suspects array.
  - screenshot_paths: list of Paths captured during this thread run.

Output:
  - List[Suspect] with avatar_path bound to the last screenshot when available.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from modules.task_types import GroupThread, Suspect


def _extract_json_from_text(text: str) -> dict:
    """Extract JSON object from text that may contain surrounding prose."""
    # #region agent log
    import json as _json

    open(
        r"d:\Documents\Project Bird\code\cua\.cursor\debug.log", "a", encoding="utf-8"
    ).write(
        _json.dumps(
            {
                "location": "suspicious_detector.py:_extract_json_from_text",
                "message": "attempting JSON extraction",
                "data": {"text_len": len(text), "text_preview": text[:200]},
                "timestamp": __import__("time").time(),
                "sessionId": "debug-session",
                "hypothesisId": "B-fix",
            }
        )
        + "\n"
    )
    # #endregion
    # Try parsing the whole string first (in case it's already pure JSON)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find JSON object pattern: starts with { and ends with }
    # Use regex to find the last JSON-like object (agent often puts JSON at the end)
    matches = list(
        re.finditer(r'\{[^{}]*"suspects"[^{}]*\[.*?\]\s*\}', text, re.DOTALL)
    )
    if matches:
        json_str = matches[-1].group(0)
        # #region agent log
        import json as _json

        open(
            r"d:\Documents\Project Bird\code\cua\.cursor\debug.log",
            "a",
            encoding="utf-8",
        ).write(
            _json.dumps(
                {
                    "location": "suspicious_detector.py:_extract_json_from_text:regex_match",
                    "message": "found JSON via regex",
                    "data": {"json_str": json_str[:300]},
                    "timestamp": __import__("time").time(),
                    "sessionId": "debug-session",
                    "hypothesisId": "B-fix",
                }
            )
            + "\n"
        )
        # #endregion
        return json.loads(json_str)
    # Fallback: find any JSON object starting with {"thread_id" or {"suspects"
    for pattern in [r'\{"thread_id".*?\}(?=\s*$)', r'\{"suspects".*?\}(?=\s*$)']:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
    # Last resort: find balanced braces containing "suspects"
    start_idx = text.find('{"')
    if start_idx == -1:
        start_idx = text.find('{ "')
    if start_idx != -1:
        # Find matching closing brace
        brace_count = 0
        for i, char in enumerate(text[start_idx:], start_idx):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    json_str = text[start_idx : i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        break
    raise json.JSONDecodeError("No valid JSON object found in text", text, 0)


def extract_suspects(
    thread: GroupThread, text_output: str, screenshot_paths: List[Path]
) -> List[Suspect]:
    payload = _extract_json_from_text(text_output)
    entries = payload.get("suspects", [])
    avatar_path = screenshot_paths[-1] if screenshot_paths else Path()
    return [
        Suspect(
            sender_id=str(item.get("sender_id", "")),
            sender_name=str(item.get("sender_name", "")),
            avatar_path=avatar_path,
            evidence_text=str(item.get("evidence_text", "")),
            thread_id=thread.thread_id,
        )
        for item in entries
    ]
