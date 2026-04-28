"""WeChat sidebar labels that are UI controls, not chat sessions.

Usage:
    from shared.sidebar_ui_chrome import is_sidebar_ui_chrome_label
    if is_sidebar_ui_chrome_label(row_name):
        skip row

Input: OCR or UI thread name string (may include spaces / fullwidth chars).
Output: True if the string denotes pinned-header chrome (fold/unfold), else False.
"""

from __future__ import annotations

import unicodedata

_CHROME_PHRASES = (
    "折叠置顶聊天",
    "展开置顶聊天",
)
_COMPACT_CHROME = frozenset(
    "".join(unicodedata.normalize("NFKC", p).split()) for p in _CHROME_PHRASES
)


def is_sidebar_ui_chrome_label(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    compact = "".join(unicodedata.normalize("NFKC", str(text)).split())
    return compact in _COMPACT_CHROME
