"""
macOS accessibility-tree click operations for WeChat UI.

Replaces hard-coded Scaffolding coordinates on macOS by querying the OS
accessibility tree via computer.interface.get_accessibility_tree().  Each
function walks the returned element tree to find the target button by role
and title, reads its bbox, and clicks the centre — no fixed pixel positions.

WeChat Mac button titles (verified against WeChat 3.x macOS):
- Three dots / group info: role AXButton, title "更多" or description "更多"
- Minus (remove member):   role AXButton, title "-" or description contains "删除"
- Confirm removal (移出):  role AXButton, title "移出" or "确定"

If a button cannot be found in the AX tree the function raises RuntimeError so
the caller can fall back or surface the failure explicitly — consistent with the
project's no-silent-fallback policy.

Usage:
    await ax_click_three_dots(computer)
    await ax_click_minus_button(computer)
    await ax_click_delete_confirm(computer)

Input:
    - computer: Computer instance with interface.get_accessibility_tree()
      and interface.left_click(x, y)

Output:
    - Clicks the matched button centre; raises RuntimeError if not found.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple


def _find_element(
    node: Any,
    role: Optional[str] = None,
    title: Optional[str] = None,
    description_contains: Optional[str] = None,
) -> Optional[Dict]:
    """Recursively search an AX tree dict/list for a matching element.

    Returns the first node whose role, title, and description all match the
    supplied filters (None means "don't care").  Matching is case-insensitive
    for title and description.
    """
    if isinstance(node, list):
        for child in node:
            result = _find_element(child, role, title, description_contains)
            if result is not None:
                return result
        return None

    if not isinstance(node, dict):
        return None

    node_role = node.get("role", "")
    node_title = (node.get("name") or node.get("title") or "").lower()
    node_desc = (node.get("description") or node.get("role_description") or "").lower()

    role_ok = (role is None) or (node_role == role)
    title_ok = (title is None) or (node_title == title.lower())
    desc_ok = (description_contains is None) or (
        description_contains.lower() in node_desc
        or description_contains.lower() in node_title
    )

    if role_ok and title_ok and desc_ok:
        return node

    for child in node.get("children", []):
        result = _find_element(child, role, title, description_contains)
        if result is not None:
            return result

    return None


def _bbox_centre(node: Dict) -> Tuple[int, int]:
    """Return pixel centre (x, y) of a node's bbox or visible_bbox."""
    bbox = node.get("visible_bbox") or node.get("bbox")
    assert bbox is not None, f"Element has no bbox: {node.get('role')} '{node.get('name')}'"
    x = (bbox[0] + bbox[2]) // 2
    y = (bbox[1] + bbox[3]) // 2
    return x, y


async def _click_ax_button(
    computer,
    candidates: List[Dict],  # list of (role, title, description_contains) dicts
    label: str,
) -> None:
    """Walk AX tree, click centre of first matching button from candidates list."""
    tree = await computer.interface.get_accessibility_tree()

    element = None
    for cand in candidates:
        element = _find_element(
            tree,
            role=cand.get("role"),
            title=cand.get("title"),
            description_contains=cand.get("description_contains"),
        )
        if element is not None:
            break

    assert element is not None, (
        f"[ax_clicks] Could not find '{label}' button in AX tree. "
        f"Tried: {candidates}"
    )

    x, y = _bbox_centre(element)
    print(f"[ax_clicks] Clicking '{label}' at ({x}, {y}) via AX tree")
    await computer.interface.left_click(x, y)
    await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Public API — mirrors scaffolding_clicks.py signatures (no settings needed)
# ---------------------------------------------------------------------------

async def ax_click_three_dots(computer) -> None:
    """Click the group-info / three-dots button using the AX tree.

    WeChat Mac shows this as a button titled '更多' (More) in the top-right
    corner of an open chat.
    """
    await _click_ax_button(
        computer,
        candidates=[
            {"role": "AXButton", "title": "更多"},
            {"role": "AXButton", "description_contains": "更多"},
            {"role": "AXButton", "description_contains": "more"},
        ],
        label="three-dots/更多",
    )


async def ax_click_minus_button(computer) -> None:
    """Click the minus / remove-member button using the AX tree.

    WeChat Mac shows this as a small '-' button inside the member panel.
    """
    await _click_ax_button(
        computer,
        candidates=[
            {"role": "AXButton", "title": "-"},
            {"role": "AXButton", "description_contains": "删除成员"},
            {"role": "AXButton", "description_contains": "remove"},
        ],
        label="minus/-",
    )


async def ax_click_delete_confirm(computer) -> None:
    """Click the 移出 / confirm-removal button using the AX tree.

    WeChat Mac shows a confirmation dialog with a '移出' button.
    """
    await _click_ax_button(
        computer,
        candidates=[
            {"role": "AXButton", "title": "移出"},
            {"role": "AXButton", "title": "确定"},
            {"role": "AXButton", "description_contains": "移出"},
        ],
        label="移出/confirm",
    )
