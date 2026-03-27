"""将微信通话 UI 单行文案（如 Canceled）规范为 type=call 与 content=[通话] ..."""

from __future__ import annotations

import re
from typing import Any, Dict, List

_CALL_EN = re.compile(
    r"^(Canceled|Cancelled|Declined|Missed|Busy|No Answer|Ended|Calling|Ringing)$",
    re.IGNORECASE,
)

_CALL_CN_SHORT = frozenset({
    "已取消",
    "未接听",
    "通话已取消",
    "对方已取消",
    "忙线",
    "无应答",
    "已拒绝",
    "已挂断",
    "语音通话",
    "视频通话",
})


def _is_call_line_content(content: str) -> bool:
    c = content.strip()
    if not c:
        return False
    if c.startswith("[通话]"):
        return True
    if len(c) > 48:
        return False
    if _CALL_EN.match(c):
        return True
    if c in _CALL_CN_SHORT:
        return True
    if c.startswith("通话时长") and len(c) < 28:
        return True
    return False


def refine_call_message_types(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将误标为 text 的通话行改为 type=call，并按 TESTING 约定加 [通话] 前缀。"""
    out: List[Dict[str, Any]] = []
    for m in messages:
        t = m.get("type", "text")
        c = str(m.get("content", "")).strip()
        if t in ("text", "call") and _is_call_line_content(c):
            m2 = dict(m)
            m2["type"] = "call"
            if not c.startswith("[通话]"):
                m2["content"] = f"[通话] {c}"
            out.append(m2)
            continue
        out.append(m)
    return out
