"""对 LLM 提取的消息列表做后处理：normalize → refine_call → 去时间伪消息 → 去重 → 相似合并。

VALID_TYPES 与 algo_a/TESTING.md §3.3 对齐：含 video、voice、call、unsupported 等。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from algo_a.merge_similar_messages import merge_similar_content
from algo_a.refine_call_messages import refine_call_message_types
from algo_a.refine_voice_video_messages import (
    drop_redundant_voice_duration_lines,
    infer_video_voice_types,
)

VALID_TYPES = {
    "text",
    "system",
    "link_card",
    "image",
    "other",
    "unsupported",
    "call",
    "video",
    "voice",
}


def _normalize_type(raw: str) -> str:
    t = raw.strip().lower()
    if t in VALID_TYPES:
        return t
    if t in {"link", "card", "share", "mini_program", "miniprogram"}:
        return "link_card"
    if t in {"img", "photo", "sticker", "emoji"}:
        return "image"
    if t in {"notice", "recall", "join", "leave", "date"}:
        return "system"
    if t in {"voip", "phone_call", "voice_call", "video_call", "call_record", "audio_call"}:
        return "call"
    if t in {"movie", "short_video", "clip"}:
        return "video"
    if t in {"voice_message", "audio_message"}:
        return "voice"
    if t == "video":
        return "video"
    if t in {"voice", "audio"}:
        return "voice"
    if t in {"file", "document", "unknown"}:
        return "unsupported"
    return "other"


def normalize(
    messages: List[Dict[str, Any]],
    chat_name: str,
) -> List[Dict[str, Any]]:
    """统一字段名和值，过滤空消息。"""
    result: List[Dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        sender = str(m.get("sender", "UNKNOWN")).strip() or "UNKNOWN"
        time_val = m.get("time")
        if isinstance(time_val, str):
            time_val = time_val.strip() or None
        msg_type = _normalize_type(str(m.get("type", "text")))
        result.append({
            "chat_name": chat_name,
            "sender": sender,
            "time": time_val,
            "content": content,
            "type": msg_type,
        })
    return result


def _content_key(m: Dict[str, Any]) -> str:
    """用于去重比较的 key：sender + content（忽略时间差异）。"""
    return f"{m.get('sender', '')}||{m.get('content', '')}"


def deduplicate(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去掉相邻的完全重复消息（接缝区域的典型现象）。

    保留第一次出现的那条。只比较 sender+content，
    time 可能因帧差异稍有不同所以不参与比较。
    """
    if not messages:
        return []
    result = [messages[0]]
    for m in messages[1:]:
        if _content_key(m) == _content_key(result[-1]):
            if m.get("time") and not result[-1].get("time"):
                result[-1]["time"] = m["time"]
            continue
        result.append(m)
    return result


def _is_time_only_content(content: str) -> bool:
    """判断是否为纯时间/日期条（微信灰条上的日期或时钟，非气泡消息）。"""
    c = content.strip()
    if not c:
        return True
    if len(c) > 48:
        return False
    if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", c):
        return True
    if re.match(r"^\d{1,2}月\d{1,2}日(\s+\d{1,2}:\d{2})?$", c):
        return True
    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(\s+\d{1,2}:\d{2})?$", c):
        return True
    return False


def drop_time_only_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去掉内容仅为时间或日期的伪消息（LLM 误把分隔条当 system）。"""
    out: List[Dict[str, Any]] = []
    for m in messages:
        c = str(m.get("content", "")).strip()
        if _is_time_only_content(c):
            continue
        out.append(m)
    return out


def merge_adjacent(messages: List[Dict[str, Any]], max_window: int = 5) -> List[Dict[str, Any]]:
    """合并小窗口内（默认 3 条以内）的连续重复。

    当同一 sender 连续发了相同 content，只保留一条。
    这处理的是 LLM 在接缝区域重复提取同一条消息的情况。
    """
    if not messages:
        return []
    result = [messages[0]]
    for m in messages[1:]:
        is_dup = False
        window = result[-max_window:]
        for prev in window:
            if prev["sender"] == m["sender"] and prev["content"] == m["content"]:
                is_dup = True
                if m.get("time") and not prev.get("time"):
                    prev["time"] = m["time"]
                break
        if not is_dup:
            result.append(m)
    return result


def postprocess(
    messages: List[Dict[str, Any]],
    chat_name: str,
) -> List[Dict[str, Any]]:
    """完整后处理管线：normalize → refine_call → voice/video → drop_time_only → dedupe → merge。"""
    msgs = normalize(messages, chat_name)
    msgs = refine_call_message_types(msgs)
    msgs = infer_video_voice_types(msgs)
    msgs = drop_redundant_voice_duration_lines(msgs)
    msgs = drop_time_only_messages(msgs)
    msgs = deduplicate(msgs)
    msgs = merge_adjacent(msgs)
    msgs = merge_similar_content(msgs)
    return msgs
