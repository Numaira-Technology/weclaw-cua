"""定位并激活 macOS 上的微信窗口（AX UI Tree 的入口）。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from AppKit import NSWorkspace  # type: ignore
from ApplicationServices import (  # type: ignore
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    kAXErrorSuccess,
)


@dataclass
class WechatWindow:
    """微信窗口句柄（兼容不同阶段的字段命名）。"""

    pid: int
    app_name: str
    title: str
    ax_app: Any
    ax_window: Any

    # 兼容字段：algo_a / 现有文档里常用 app_ref/window_ref
    app_ref: Optional[Any] = None
    window_ref: Optional[Any] = None

    def __post_init__(self) -> None:
        if self.app_ref is None:
            self.app_ref = self.ax_app
        if self.window_ref is None:
            self.window_ref = self.ax_window


def _matches_app_name(candidate_name: str, app_name: str) -> bool:
    """应用名匹配：兼容 'WeChat' 与 '微信' 等情况。"""
    c = (candidate_name or "").strip().lower()
    t = (app_name or "").strip().lower()
    if not c or not t:
        return False
    return t in c or c in t


def _find_wechat_app(app_name: str) -> Any | None:
    running_apps = NSWorkspace.sharedWorkspace().runningApplications()
    for app in running_apps:
        localized = app.localizedName() or ""
        bundle_id = app.bundleIdentifier() or ""
        # 常见 bundle id（主要用于增强匹配）
        if bundle_id in {"com.tencent.xinWeChat"} or _matches_app_name(localized, app_name):
            if not app.isTerminated():
                return app
    return None


def _activate_app(app: Any) -> None:
    """把应用激活到前台（不使用屏幕坐标）。"""
    import AppKit  # type: ignore

    app.activateWithOptions_(
        AppKit.NSApplicationActivateAllWindows
        | AppKit.NSApplicationActivateIgnoringOtherApps
    )
    time.sleep(0.5)


def _get_ax_main_window(ax_app: Any) -> Any | None:
    """尽量获取 AXMainWindow，否则退而求其次。"""
    err, main_win = AXUIElementCopyAttributeValue(ax_app, "AXMainWindow", None)
    if err == kAXErrorSuccess and main_win is not None:
        return main_win

    err, focused_win = AXUIElementCopyAttributeValue(ax_app, "AXFocusedWindow", None)
    if err == kAXErrorSuccess and focused_win is not None:
        return focused_win

    err, windows = AXUIElementCopyAttributeValue(ax_app, "AXWindows", None)
    if err == kAXErrorSuccess and windows is not None and len(windows) > 0:
        return windows[0]

    return None


def _get_window_title(ax_window: Any) -> str:
    """安全读取窗口标题。"""
    err, title = AXUIElementCopyAttributeValue(ax_window, "AXTitle", None)
    if err == kAXErrorSuccess and title:
        try:
            return str(title)
        except Exception:
            return ""
    return ""


def find_wechat_window(app_name: str = "WeChat") -> WechatWindow:
    """定位并返回微信主窗口的 AX 引用。

    行为要求：
    - 微信未启动：抛出清晰异常
    - 微信已启动但不在前台：先激活应用
    - 若有窗口：返回主窗口 AXUIElement
    """
    if not app_name:
        app_name = "WeChat"

    app = _find_wechat_app(app_name)
    if app is None:
        raise RuntimeError(
            "未找到正在运行的微信！\n"
            "请先启动 WeChat（WeChat/微信）应用，然后重新运行此脚本。"
        )

    app_name_actual = app.localizedName() or "WeChat"
    pid = int(app.processIdentifier())

    # 不在前台时先激活（尽量把窗口 raise 到前台）
    if not app.isActive():
        _activate_app(app)

    ax_app = AXUIElementCreateApplication(pid)
    if ax_app is None:
        raise RuntimeError(
            f"无法为微信 (PID={pid}) 创建 AX 引用。\n"
            "请确认 Accessibility 权限已正确授予。"
        )

    ax_window = _get_ax_main_window(ax_app)
    if ax_window is None:
        raise RuntimeError(
            f"微信 (PID={pid}) 已运行，但未找到可用窗口。\n"
            "请确认微信主窗口已打开（非最小化状态）。"
        )

    title = _get_window_title(ax_window)
    return WechatWindow(
        pid=pid,
        app_name=app_name_actual,
        title=title,
        ax_app=ax_app,
        ax_window=ax_window,
    )
