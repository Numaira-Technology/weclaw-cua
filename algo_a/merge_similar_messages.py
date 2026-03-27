"""长文本相似去重（同 sender 广告微调重复）。"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List


def _norm_for_similarity(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip())


def merge_similar_content(
    messages: List[Dict[str, Any]],
    ratio: float = 0.88,
    min_len: int = 30,
    max_window: int = 5,
) -> List[Dict[str, Any]]:
    if not messages:
        return []
    out: List[Dict[str, Any]] = []
    for m in messages:
        t = m.get("type", "text")
        if t not in ("text", "other"):
            out.append(m)
            continue
        a_raw = str(m.get("content", ""))
        a = _norm_for_similarity(a_raw)
        if len(a) < min_len:
            out.append(m)
            continue
        dup = False
        for prev in out[-max_window:]:
            if prev.get("sender") != m.get("sender"):
                continue
            if prev.get("type") != t:
                continue
            b = _norm_for_similarity(str(prev.get("content", "")))
            if len(b) < min_len:
                continue
            if difflib.SequenceMatcher(None, a, b).ratio() >= ratio:
                dup = True
                if m.get("time") and not prev.get("time"):
                    prev["time"] = m["time"]
                break
        if not dup:
            out.append(m)
    return out
