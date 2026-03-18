"""Generic helpers to read and interact with macOS AXUIElement trees.

Usage:
    from platform_mac.ui_tree_reader import get_children, get_attribute, find_elements_by_role, perform_action

Input spec:
    - element: an AXUIElement reference (from pyobjc or ApplicationServices).
    - attr: AX attribute name string, e.g. "AXRole", "AXValue", "AXTitle".
    - role: AX role string, e.g. "AXStaticText", "AXButton", "AXRow".
    - action: AX action string, e.g. "AXPress", "AXScrollDown".

Output spec:
    - get_children: returns list of child AXUIElements.
    - get_attribute: returns the attribute value (str, int, etc.) or None.
    - find_elements_by_role: returns all descendants matching the role.
    - perform_action: executes an accessibility action on the element.
"""

from typing import Any


def get_children(element: Any) -> list[Any]:
    """Return direct children of an AXUIElement."""
    assert element is not None
    raise NotImplementedError("AXUIElementCopyAttributeValue(element, kAXChildrenAttribute)")


def get_attribute(element: Any, attr: str) -> Any:
    """Return the value of an AX attribute, or None if not present."""
    assert element is not None
    assert attr
    raise NotImplementedError("AXUIElementCopyAttributeValue(element, attr)")


def find_elements_by_role(root: Any, role: str) -> list[Any]:
    """Recursively find all descendants of root with the given AXRole."""
    assert root is not None
    assert role
    raise NotImplementedError("BFS/DFS traversal filtering by AXRole == role")


def perform_action(element: Any, action: str) -> None:
    """Perform an accessibility action (e.g. AXPress, AXScrollDown) on the element."""
    assert element is not None
    assert action
    raise NotImplementedError("AXUIElementPerformAction(element, action)")
