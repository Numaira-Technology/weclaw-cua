"""Check and request macOS Accessibility permissions for UI tree access.

Usage:
    from platform_mac.grant_permissions import ensure_permissions
    ensure_permissions()  # crashes if permission denied

Input spec:
    - None. Reads system permission state.

Output spec:
    - check_accessibility_permission() -> bool: True if granted.
    - request_accessibility_permission() -> None: opens System Preferences prompt.
    - ensure_permissions() -> None: asserts permission is granted, crashes if not.
"""


def check_accessibility_permission() -> bool:
    """Return True if this process has Accessibility permission."""
    raise NotImplementedError("check macOS Accessibility trust via ApplicationServices.AXIsProcessTrusted")


def request_accessibility_permission() -> None:
    """Prompt the user to grant Accessibility permission in System Preferences."""
    raise NotImplementedError("prompt Accessibility permission via AXIsProcessTrustedWithOptions")


def ensure_permissions() -> None:
    """Assert Accessibility permission is granted. Crash if denied after prompting."""
    raise NotImplementedError("call check -> request -> check -> assert")
