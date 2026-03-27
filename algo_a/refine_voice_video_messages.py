"""将 LLM 输出的语音/视频占位与误拆时长行规范为 type=voice|video。"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_DURATION_ONLY = re.compile(
    r"^(\d{1,2}[:：]\d{2}(:\d{2})?|\d{1,3}[\"'″′秒sS]?|\d+\s*秒)$",
)


def infer_video_voice_types(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """[视频]/[语音] 占位 → type=video|voice（修正误标为 text/unsupported 的条目）。"""
    out: List[Dict[str, Any]] = []
    for m in messages:
        t = m.get("type", "text")
        c = str(m.get("content", "")).strip()
        if t in ("unsupported", "other", "text"):
            if c.startswith("[视频]") or c == "[视频]":
                m2 = dict(m)
                m2["type"] = "video"
                out.append(m2)
                continue
            if c.startswith("[语音]") or re.match(r"^\[语音\]", c):
                m2 = dict(m)
                m2["type"] = "voice"
                out.append(m2)
                continue
        out.append(m)
    return out


def drop_redundant_voice_duration_lines(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去掉紧跟在 [语音]… 后的单独时长行（如误拆的 2\"）。"""
    if not messages:
        return []
    out: List[Dict[str, Any]] = [messages[0]]
    for m in messages[1:]:
        prev = out[-1]
        if _is_redundant_after_voice(prev, m):
            continue
        out.append(m)
    return out


def _is_redundant_after_voice(prev: Dict[str, Any], cur: Dict[str, Any]) -> bool:
    if prev.get("sender") != cur.get("sender"):
        return False
    if prev.get("type") != "voice":
        return False
    pc = str(prev.get("content", ""))
    if "[语音]" not in pc:
        return False
    cc = str(cur.get("content", "")).strip()
    ct = cur.get("type", "text")
    if ct not in ("text", "unsupported", "other", "voice"):
        return False
    if len(cc) > 16:
        return False
    if not _DURATION_ONLY.match(cc):
        return False
    compact_p = re.sub(r"\s+", "", pc)
    compact_c = re.sub(r"\s+", "", cc)
    if compact_c and compact_c in compact_p:
        return True
    digits_c = re.sub(r"\D", "", cc)
    digits_p = re.sub(r"\D", "", pc)
    if digits_c and digits_c == digits_p:
        return True
    return False
