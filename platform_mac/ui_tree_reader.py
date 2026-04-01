"""macOS Accessibility (AX) 树遍历与打印工具。

核心修复：
- 使用 AXUIElementCopyAttributeValue（单数）获取 AXChildren，
  而非 CopyAttributeValues（复数），后者对某些元素会返回垃圾数据
- 对 children 列表做 AXUIElement 类型过滤，排除 str/int 等非元素对象
"""

from __future__ import annotations

from typing import Any, List

import Foundation  # type: ignore
from ApplicationServices import (  # type: ignore
    AXUIElementCopyAttributeValue,
    AXUIElementSetAttributeValue,
    AXUIElementGetTypeID,
    AXUIElementPerformAction,
    AXValueGetType,
    AXValueGetValue,
    kAXErrorSuccess,
    kAXValueCGSizeType,
    kAXValueCGPointType,
)


def _is_ax_element(obj: Any) -> bool:
    """判断一个 pyobjc 对象是否是 AXUIElementRef。"""
    if obj is None:
        return False
    if isinstance(obj, (str, int, float, bool, bytes)):
        return False
    try:
        return Foundation.CFGetTypeID(obj) == AXUIElementGetTypeID()
    except Exception:
        return False


def get_attribute_safe(element: Any, attr_name: str, default: Any = None) -> Any:
    """安全读取 AX 属性。使用 CopyAttributeValue（单数形式）。"""
    try:
        err, value = AXUIElementCopyAttributeValue(element, attr_name, None)
        if err == kAXErrorSuccess and value is not None:
            return value
    except Exception:
        pass
    return default


def iter_children(element: Any) -> list:
    """获取 AX 元素的子节点列表（仅保留 AXUIElementRef 类型）。"""
    children = get_attribute_safe(element, "AXChildren")
    if children is None:
        children = get_attribute_safe(element, "AXVisibleChildren")
    if children is None:
        return []
    return [c for c in children if _is_ax_element(c)]


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        s = str(value)
        if len(s) > 160:
            return s[:157] + "..."
        return s
    except Exception:
        return "<unreadable>"


def _format_frame(element: Any) -> str:
    """格式化 position + size → (x, y, w, h)。"""
    pos_val = get_attribute_safe(element, "AXPosition")
    size_val = get_attribute_safe(element, "AXSize")

    x, y, w, h = "?", "?", "?", "?"

    if pos_val is not None:
        try:
            if AXValueGetType(pos_val) == kAXValueCGPointType:
                ok, point = AXValueGetValue(pos_val, kAXValueCGPointType, None)
                if ok:
                    x = f"{point.x:.0f}"
                    y = f"{point.y:.0f}"
        except Exception:
            pass

    if size_val is not None:
        try:
            if AXValueGetType(size_val) == kAXValueCGSizeType:
                ok, size = AXValueGetValue(size_val, kAXValueCGSizeType, None)
                if ok:
                    w = f"{size.width:.0f}"
                    h = f"{size.height:.0f}"
        except Exception:
            pass

    return f"({x}, {y}, {w}, {h})"


def dump_tree(element: Any, max_depth: int = 4, max_children: int = 50) -> str:
    """遍历 AX 树并生成可读文本。

    每行包含: role / subrole / title / value / description / frame
    层级用缩进表示，属性读取失败不崩。
    """
    lines: List[str] = []
    _walk(element, lines, depth=0, max_depth=max_depth, max_children=max_children)
    return "\n".join(lines)


def _walk(element: Any, lines: List[str], depth: int, max_depth: int, max_children: int) -> None:
    indent = "  " * depth

    role = _safe_str(get_attribute_safe(element, "AXRole")) or "<none>"
    subrole = _safe_str(get_attribute_safe(element, "AXSubrole", default=""))
    title = _safe_str(get_attribute_safe(element, "AXTitle", default=""))
    value = _safe_str(get_attribute_safe(element, "AXValue", default=""))
    desc = _safe_str(get_attribute_safe(element, "AXDescription", default=""))
    frame = _format_frame(element)

    parts = [f"[{role}]"]
    if subrole:
        parts.append(f"subrole={subrole}")
    if title:
        parts.append(f'title="{title}"')
    if value:
        parts.append(f'value="{value}"')
    if desc:
        parts.append(f'desc="{desc}"')
    parts.append(f"frame={frame}")

    lines.append(f"{indent}{' '.join(parts)}")

    if depth >= max_depth:
        kids = iter_children(element)
        if kids:
            lines.append(f"{indent}  ... {len(kids)} children omitted (max_depth)")
        return

    kids = iter_children(element)
    shown = 0
    for child in kids:
        if shown >= max_children:
            lines.append(f"{indent}  ... {len(kids) - shown} more children omitted")
            break
        _walk(child, lines, depth + 1, max_depth, max_children)
        shown += 1


def enable_enhanced_ui(ax_app: Any) -> bool:
    """尝试启用 AXEnhancedUserInterface，让应用暴露更多无障碍信息。"""
    try:
        AXUIElementSetAttributeValue(ax_app, "AXEnhancedUserInterface", True)
        return True
    except Exception:
        return False


def get_content_from_sections(ax_window: Any) -> Any | None:
    """尝试从 AXSections 取 AXContent 的 SectionObject。"""
    sections = get_attribute_safe(ax_window, "AXSections")
    if not sections:
        return None
    for sec in sections:
        try:
            uid = sec.get("SectionUniqueID", "")
            if uid == "AXContent":
                obj = sec.get("SectionObject")
                if obj is not None and _is_ax_element(obj):
                    return obj
        except Exception:
            continue
    return None


# ── 兼容旧接口（供 algo_a 使用） ──


def get_children(element: Any) -> list[Any]:
    """Return direct children of an AXUIElement。"""
    return iter_children(element)


def get_attribute(element: Any, attr: str) -> Any:
    """Return the value of an AX attribute, or None."""
    return get_attribute_safe(element, attr)


def find_elements_by_role(root: Any, role: str) -> list[Any]:
    """Recursively find all descendants with the given AXRole."""
    if root is None:
        return []
    out: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        node_role = _safe_str(get_attribute_safe(node, "AXRole"))
        if node_role == role:
            out.append(node)
        stack.extend(iter_children(node))
    return out


def perform_action(element: Any, action: str) -> None:
    """Perform an accessibility action (e.g. AXPress)."""
    if element is None or not action:
        return
    try:
        AXUIElementPerformAction(element, action)
    except Exception:
        return
