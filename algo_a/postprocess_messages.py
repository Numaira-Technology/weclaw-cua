"""对 LLM 提取的消息列表做后处理：规范化、去重、排序。

流程：
  1. normalize — 统一字段、过滤空消息、修正 type
  2. deduplicate — 去掉接缝附近的重复消息（相邻 content+sender 完全一致）
  3. merge_adjacent — 合并连续重复内容
  4. 保证消息顺序从上到下（输入已是视觉顺序，不做重排）
"""

from __future__ import annotations

from typing import Any, Dict, List

VALID_TYPES = {"text", "system", "link_card", "image", "other"}


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


def merge_adjacent(messages: List[Dict[str, Any]], max_window: int = 3) -> List[Dict[str, Any]]:
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
    """完整后处理管线：normalize → deduplicate → merge_adjacent。"""
    msgs = normalize(messages, chat_name)
    msgs = deduplicate(msgs)
    msgs = merge_adjacent(msgs)
    return msgs
