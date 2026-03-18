"""Generic helpers to read and interact with Windows UI Automation element trees.

Usage:
    from platform_win.ui_tree_reader import (
        get_children, get_attribute, find_elements_by_control_type, perform_action,
    )

Input spec:
    - element: an IUIAutomationElement (from comtypes UIAutomationCore).
    - attr: UIA property name string, e.g. "Name", "AutomationId", "ClassName".
    - control_type: UIA ControlType int constant, e.g. UIA_ButtonControlTypeId.
    - pattern: UIA pattern interface for invoking actions (Invoke, Scroll, etc.).

Output spec:
    - get_children: returns list of child IUIAutomationElements.
    - get_attribute: returns the property value (str, int, etc.) or None.
    - find_elements_by_control_type: returns all descendants matching the ControlType.
    - perform_invoke: executes the Invoke pattern on the element (equivalent to click).
    - perform_scroll: scrolls within a scrollable container.
"""

from typing import Any


def get_children(element: Any) -> list[Any]:
    """Return direct children of a UI Automation element."""
    assert element is not None
    raise NotImplementedError(
        "use IUIAutomationElement.FindAll with TreeScope_Children and TrueCondition"
    )


def get_attribute(element: Any, attr: str) -> Any:
    """Return the value of a UIA property, or None if not present."""
    assert element is not None
    assert attr
    raise NotImplementedError(
        "map attr name to UIA property id, call element.GetCurrentPropertyValue(prop_id)"
    )


def find_elements_by_control_type(root: Any, control_type: int) -> list[Any]:
    """Find all descendants of root with the given UIA ControlType."""
    assert root is not None
    raise NotImplementedError(
        "use IUIAutomation.CreatePropertyCondition(UIA_ControlTypePropertyId, control_type) "
        "then root.FindAll(TreeScope_Descendants, condition)"
    )


def perform_invoke(element: Any) -> None:
    """Invoke (click) an element via the UIA Invoke pattern."""
    assert element is not None
    raise NotImplementedError(
        "element.GetCurrentPattern(UIA_InvokePatternId).Invoke()"
    )


def perform_scroll(element: Any, direction: str = "down") -> None:
    """Scroll within a scrollable container via the UIA Scroll pattern."""
    assert element is not None
    assert direction in ("up", "down")
    raise NotImplementedError(
        "element.GetCurrentPattern(UIA_ScrollPatternId).Scroll(horizontal, vertical)"
    )
