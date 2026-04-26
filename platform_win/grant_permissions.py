"""Check Windows prerequisites for UI Automation access.

Usage:
    from platform_win.grant_permissions import ensure_permissions
    ensure_permissions()  # crashes if prerequisites not met

Input spec:
    - None. Checks system state (platform, running-as-admin, WeChat process).

Output spec:
    - check_platform() -> None: asserts running on Windows.
    - check_admin_if_needed() -> bool: True if elevated privileges available.
    - ensure_permissions() -> None: asserts all prerequisites, crashes if not met.

Notes:
    Windows UI Automation generally works without special permissions,
    but some UIA operations on elevated processes require the caller
    to also run elevated (admin). This module validates that.
"""

import sys


def check_platform() -> None:
    """Assert we are running on Windows."""
    assert sys.platform == "win32", f"platform_win requires Windows, got {sys.platform}"


def check_prerequisites() -> None:
    """Entry point for weclaw init: verify platform only (UIA needs no extra grant)."""
    check_platform()


def check_admin_if_needed() -> bool:
    """Return True if the process has admin elevation (or elevation is unnecessary)."""
    raise NotImplementedError(
        "use ctypes.windll.shell32.IsUserAnAdmin() to check elevation"
    )


def ensure_permissions() -> None:
    """Assert all Windows prerequisites for UI Automation access."""
    raise NotImplementedError(
        "call check_platform -> check_admin_if_needed -> warn or assert"
    )
