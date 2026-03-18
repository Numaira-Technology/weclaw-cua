"""Walk the message list UI elements and extract structured message data.

Usage:
    from algo_a.read_messages_from_uitree import read_messages_from_uitree
    messages = read_messages_from_uitree(driver, window, "Group A")

Input spec:
    - driver: PlatformDriver instance.
    - window: platform-specific window handle.
    - chat_name: name of the currently active chat (used to tag messages).

Output spec:
    - Returns list[dict] where each dict has keys:
      chat_name, sender, time, content, type.
    - type is one of: "text", "system", "link_card", "image", "unsupported".
    - Messages are in chronological order (top to bottom in the UI).
"""

from typing import Any

from shared.platform_api import PlatformDriver

_SYSTEM_ROLES = {"AXStaticText"}
_IMAGE_ROLES = {"AXImage"}
_LINK_ROLES = {"AXLink"}


def _classify_element(driver: PlatformDriver, element: Any) -> str:
    """Determine the message type from the UI element's subtree structure."""
    role = driver.get_element_role(element)

    if role in _SYSTEM_ROLES:
        return "system"
    if role in _IMAGE_ROLES:
        return "image"

    children = driver.get_element_children(element)

    for child in children:
        child_role = driver.get_element_role(child)
        if child_role in _LINK_ROLES:
            return "link_card"
        if child_role in _IMAGE_ROLES:
            grandchildren = driver.get_element_children(child)
            has_text_sibling = any(
                driver.get_element_role(gc) == "AXStaticText" for gc in grandchildren
            )
            if has_text_sibling:
                return "link_card"
            return "image"

    return "text"


def _extract_all_text(driver: PlatformDriver, element: Any) -> str:
    """Recursively collect all text content from an element and its descendants."""
    parts: list[str] = []
    text = driver.get_element_text(element)
    if text:
        parts.append(text)
    for child in driver.get_element_children(element):
        child_text = _extract_all_text(driver, child)
        if child_text:
            parts.append(child_text)
    return " ".join(parts)


def _extract_sender_and_content(
    driver: PlatformDriver, element: Any, msg_type: str
) -> tuple[str, str]:
    """Extract sender name and content text from a message element.

    For system messages, sender is "system".
    For regular messages, the first AXStaticText child is typically the sender name,
    and the remaining text is the content.
    """
    if msg_type == "system":
        return "system", _extract_all_text(driver, element)

    children = driver.get_element_children(element)
    sender = ""
    content_parts: list[str] = []

    for i, child in enumerate(children):
        child_role = driver.get_element_role(child)
        child_text = driver.get_element_text(child)

        if i == 0 and child_role == "AXStaticText" and child_text:
            sender = child_text
            continue

        extracted = _extract_all_text(driver, child)
        if extracted:
            content_parts.append(extracted)

    content = " ".join(content_parts) if content_parts else _extract_all_text(driver, element)

    if msg_type == "image":
        content = content or "[图片]"
    elif msg_type == "link_card":
        content = content or "[链接]"

    return sender, content


def read_messages_from_uitree(
    driver: PlatformDriver, window: Any, chat_name: str
) -> list[dict]:
    """Extract all visible messages from the active chat's UI tree."""
    assert window is not None
    assert chat_name

    elements = driver.get_message_elements(window)
    current_time: str | None = None
    messages: list[dict] = []

    for element in elements:
        msg_type = _classify_element(driver, element)

        if msg_type == "system":
            text = _extract_all_text(driver, element)
            if _looks_like_timestamp(text):
                current_time = text
                continue

        sender, content = _extract_sender_and_content(driver, element, msg_type)

        messages.append({
            "chat_name": chat_name,
            "sender": sender,
            "time": current_time,
            "content": content,
            "type": msg_type,
        })

    return messages


def _looks_like_timestamp(text: str) -> bool:
    """Heuristic: detect if a system message is actually a time separator.

    WeChat time separators look like: "14:32", "昨天 14:32",
    "星期三 14:32", "2025年1月1日 14:32".
    """
    if not text:
        return False
    time_indicators = [":", "：", "昨天", "星期", "年", "月", "日", "上午", "下午"]
    return any(ind in text for ind in time_indicators)
