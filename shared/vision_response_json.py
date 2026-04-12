"""Extract one JSON object from vision-model text (fences, preamble, trailing junk)."""

from __future__ import annotations

import json
import re


def _strip_code_fences(text: str) -> str:
    s = text.strip()
    m = re.search(r"```(?:json)?\s*\n?", s, re.IGNORECASE)
    if not m:
        return s
    rest = s[m.end() :]
    k = rest.find("\n```")
    if k == -1:
        return rest.strip()
    return rest[:k].strip()


def parse_json_object_from_model_text(text: str) -> dict:
    """Return the first top-level JSON object; model may wrap it in markdown or prose."""
    assert text
    s = _strip_code_fences(text)
    decoder = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(s[i:])
            assert isinstance(obj, dict)
            return obj
        except json.JSONDecodeError:
            continue
    head = s[:500].replace("\n", "\\n")
    assert False, f"no valid JSON object in model text (len={len(s)} head={head!r})"
