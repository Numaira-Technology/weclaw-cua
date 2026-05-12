"""macOS 平台驱动：视觉混合方案。

核心能力（均已实现）：
- ensure_permissions / find_wechat_window / activate_wechat
- capture_wechat_window — Quartz 精确窗口截图
- get_window_bounds     — 获取窗口屏幕坐标
- scroll_sidebar        — CGEvent 滚轮事件
- dump_menubar          — AX 读 menubar (唯一可用的 AX 通道)

WeChat 内容区域（sidebar / chat）不暴露 AX 元素，
全部通过截图 + 视觉检测 + 局部 OCR 实现。
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

import Quartz  # type: ignore
from PIL import Image

from platform_mac.find_wechat_window import WechatWindow, find_wechat_window as _find_wechat_window
from platform_mac.grant_permissions import ensure_permissions as _ensure_permissions
from platform_mac.screenshot import (
    capture_window as _capture_window,
    WindowBounds,
    _find_wechat_cg_window_id,
)


class MacDriver:
    def __init__(self) -> None:
        self._window: Optional[WechatWindow] = None

    # ── 权限 / 窗口 ──────────────────────────────────────

    def ensure_permissions(self) -> None:
        _ensure_permissions()

    def find_wechat_window(self, app_name: str = "WeChat") -> WechatWindow:
        self._window = _find_wechat_window(app_name)
        return self._window

    def activate_wechat(self) -> None:
        """把微信激活到前台（支持跨 Space 切换）。

        用 `open -a WeChat` 确保 Space 切换完成，然后轮询 OnScreenOnly 确认可见。
        """
        import subprocess

        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None

        subprocess.run(["open", "-a", "WeChat"], capture_output=True, timeout=5)

        # 轮询确认窗口可见（最多 3 秒）
        for _ in range(15):
            time.sleep(0.2)
            wl = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
            )
            for w in wl:
                if w.get("kCGWindowOwnerPID", 0) == self._window.pid:
                    if w.get("kCGWindowLayer", -1) == 0:
                        b = w.get("kCGWindowBounds", {})
                        if int(b.get("Width", 0)) >= 200:
                            return
        time.sleep(0.5)

    # ── 截图 ─────────────────────────────────────────────

    def capture_wechat_window(self) -> Image.Image:
        """截取微信窗口，返回 PIL Image（Retina 物理像素）。"""
        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None
        img, _ = _capture_window(self._window.pid)
        return img

    def capture_wechat_window_with_bounds(self) -> tuple[Image.Image, WindowBounds]:
        """截取微信窗口，同时返回窗口屏幕坐标。"""
        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None
        return _capture_window(self._window.pid)

    def get_window_bounds(self) -> WindowBounds:
        """返回微信窗口的屏幕坐标（逻辑像素）。"""
        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None
        _, bounds = _find_wechat_cg_window_id(self._window.pid)
        return bounds

    # ── 点击 ─────────────────────────────────────────────

    def click_point(self, x: int, y: int) -> None:
        """在屏幕绝对坐标 (x, y)（逻辑像素）处模拟鼠标左键单击。"""
        point = Quartz.CGPoint(x, y)
        mouse_down = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
        )
        mouse_up = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_down)
        time.sleep(0.05)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_up)
        time.sleep(0.15)

    # ── 滚动 ─────────────────────────────────────────────

    def _sidebar_scroll_point(self) -> Quartz.CGPoint:
        """返回 sidebar 中心的屏幕坐标（缓存一次 bounds 查询）。"""
        bounds = self.get_window_bounds()
        return Quartz.CGPoint(
            bounds.x + int(bounds.width * 0.11),
            bounds.y + int(bounds.height * 0.5),
        )

    def _chat_panel_point(self) -> Quartz.CGPoint:
        """右侧聊天区中心（与 scroll_chat_panel / focus 一致）。"""
        bounds = self.get_window_bounds()
        return Quartz.CGPoint(
            bounds.x + int(bounds.width * 0.60),
            bounds.y + int(bounds.height * 0.50),
        )

    def scroll_sidebar(self, delta: int = -5) -> None:
        """向 sidebar 中心发送滚轮事件。

        delta < 0 : 向下滚（显示更多会话）
        delta > 0 : 向上滚
        单位为 kCGScrollEventUnitLine（系统行高）。
        """
        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None

        point = self._sidebar_scroll_point()
        event = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitLine, 1, delta
        )
        Quartz.CGEventSetLocation(event, point)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.4)

    def scroll_chat_panel(self, delta: int = -5, bursts: int = 1) -> None:
        """向右侧聊天面板中心发送滚轮事件。

        delta < 0 : 向下滚（显示更早消息 / 更多内容）
        delta > 0 : 向上滚
        bursts : 连续发送几次滚动事件（WeChat 单次 delta 有上限，
                 用多次 burst 实现大距离滚动）
        """
        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None

        point = self._chat_panel_point()
        for _ in range(bursts):
            event = Quartz.CGEventCreateScrollWheelEvent(
                None, Quartz.kCGScrollEventUnitLine, 1, delta
            )
            Quartz.CGEventSetLocation(event, point)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(0.05)
        time.sleep(0.25)

    def move_mouse_to_sidebar(self) -> None:
        """将鼠标移到 sidebar 区域，避免触发聊天区 hover 菜单。"""
        bounds = self.get_window_bounds()
        point = Quartz.CGPoint(
            bounds.x + int(bounds.width * 0.08),
            bounds.y + int(bounds.height * 0.50),
        )
        move_event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, move_event)

    def move_mouse_to_chat_panel(self) -> None:
        """将鼠标移到聊天区中心。滚轮事件在多数 App 下以光标位置为准，滚动前必须移回聊天区。"""
        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None
        point = self._chat_panel_point()
        move_event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, move_event)

    def focus_chat_panel(self) -> None:
        """点击右侧聊天区中心，使窗口获得焦点（对齐 wechat-admin-bot chat_whole_pic 的 pyautogui 点击）。"""
        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None
        p = self._chat_panel_point()
        self.click_point(int(p.x), int(p.y))

    def scroll_sidebar_to_top(self, max_scrolls: int = 15) -> None:
        """连续向上滚动 sidebar 直到回到顶部。"""
        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None
        assert max_scrolls >= 0

        point = self._sidebar_scroll_point()
        for _ in range(max_scrolls + 2):
            ev = Quartz.CGEventCreateScrollWheelEvent(
                None, Quartz.kCGScrollEventUnitLine, 1, 10
            )
            Quartz.CGEventSetLocation(ev, point)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.05)
        time.sleep(0.5)

    # ── AX (仅 menubar 可用) ─────────────────────────────

    def dump_menubar(self, max_depth: int = 2) -> str:
        """返回微信 menubar 的 AX tree（唯一可读的 AX 通道）。"""
        from platform_mac.ui_tree_reader import dump_tree, get_attribute_safe, iter_children

        if self._window is None:
            self.find_wechat_window()
        assert self._window is not None
        app_children = iter_children(self._window.ax_app)
        for child in app_children:
            role = get_attribute_safe(child, "AXRole")
            if role == "AXMenuBar":
                title = get_attribute_safe(child, "AXTitle", default="")
                if not title:
                    return dump_tree(child, max_depth=max_depth)
        return "(未找到 AXMenuBar)"
