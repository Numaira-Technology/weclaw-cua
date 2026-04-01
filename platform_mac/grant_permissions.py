"""macOS Accessibility 权限检查与授权提示。

最小实现目标：
1) 检查当前 Python 进程是否已获得 Accessibility 权限
2) 未授权时触发系统授权对话框
3) 若仍无权限则抛出明确异常（不静默失败）
"""

from __future__ import annotations

from typing import Any, Dict
import time


def _check_accessibility_trusted() -> bool:
    """检查当前进程是否已获 Accessibility 权限。"""
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore

        return bool(AXIsProcessTrusted())
    except Exception:
        # 部分环境可能没有 AXIsProcessTrusted，但 AXIsProcessTrustedWithOptions 通常可用
        try:
            from ApplicationServices import AXIsProcessTrustedWithOptions  # type: ignore
            from CoreFoundation import kCFBooleanFalse  # type: ignore

            options: Dict[str, Any] = {"AXTrustedCheckOptionPrompt": kCFBooleanFalse}
            return bool(AXIsProcessTrustedWithOptions(options))
        except Exception:
            return False


def _request_accessibility_permission() -> None:
    """触发系统授权提示。"""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions  # type: ignore
        from CoreFoundation import kCFBooleanTrue  # type: ignore

        options: Dict[str, Any] = {"AXTrustedCheckOptionPrompt": kCFBooleanTrue}
        # 返回值不可靠：核心是触发 TCC 授权提示。
        AXIsProcessTrustedWithOptions(options)
    except Exception as e:
        raise RuntimeError(
            "触发 macOS Accessibility 授权提示失败。请手动前往：\n"
            "System Settings > Privacy & Security > Accessibility"
        ) from e


def ensure_permissions() -> None:
    """确保当前进程已获得 macOS Accessibility 权限。

    未授权：
      - 触发系统授权对话框
      - 重新检查权限
      - 仍无权限则抛出清晰异常（包含目标路径）
    """
    if _check_accessibility_trusted():
        return

    _request_accessibility_permission()

    # 给用户一个授权窗口的时间（授权完成后通常要重新启动终端才完全生效）。
    for _ in range(10):
        time.sleep(0.3)
        if _check_accessibility_trusted():
            return

    raise PermissionError(
        "\n"
        "═══════════════════════════════════════════════════════════\n"
        " macOS Accessibility 权限未授予！\n"
        "\n"
        " 请去开启：\n"
        "   System Settings > Privacy & Security > Accessibility\n"
        "\n"
        " 并把当前终端应用（Terminal / iTerm / VS Code 等）加入并启用。\n"
        " 授权后通常需要重新启动你的终端进程才会生效。\n"
        "═══════════════════════════════════════════════════════════\n"
    )
