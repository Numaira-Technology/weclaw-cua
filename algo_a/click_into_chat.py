"""点击 sidebar 会话行并等待右侧面板 ready（Mac 视觉方案）。

单会话流程：
  activate → click → wait_ready（失败时 rescan + 重试一次）

多会话流程：
  process_unread_chats — 逐个点击 → 等 ready → rescan → 下一个

重要：每次点击会改变 sidebar 状态（未读消失、排序变化），
所以处理完一个会话后必须 rescan 获取最新 ChatInfo。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from PIL import Image

from platform_mac.sidebar_detector import ChatInfo, Rect, scan_sidebar_once
from platform_mac.chat_panel_detector import (
    extract_chat_header_title,
    sidebar_name_matches_config_group,
    titles_match,
)


def _sidebar_confirms_target_chat(
    window_img: Image.Image,
    window_rect: Rect,
    target_name: str,
    anchor_row_rect: Optional[Rect],
) -> bool:
    chats = scan_sidebar_once(
        window_img,
        only_unread=False,
        window_bounds=window_rect,
    )
    matches: List[ChatInfo] = []
    for c in chats:
        if not c.name:
            continue
        if sidebar_name_matches_config_group(c.name, target_name) or titles_match(
            c.name, target_name,
        ):
            matches.append(c)
    if not matches:
        return False
    if anchor_row_rect is None:
        return any(sidebar_name_matches_config_group(c.name, target_name) for c in matches)
    ay = anchor_row_rect.y + anchor_row_rect.height // 2
    slack = max(120, int(anchor_row_rect.height * 1.4))
    for c in matches:
        if c.row_rect is None:
            continue
        ry = c.row_rect.y + c.row_rect.height // 2
        if abs(ry - ay) <= slack:
            return True
    return len(matches) == 1


@dataclass
class ClickResult:
    """单次 click_into_chat 的结构化结果。"""
    ready: bool
    target_name: str
    detected_title: str = ""
    click_point: tuple[int, int] = (0, 0)
    attempts: int = 0
    retries_used: int = 0
    reason: str = ""
    error: str = ""


def _retina_to_logical(pixel_val: int, scale: float = 2.0) -> int:
    return int(pixel_val / scale)


def click_chat_row(driver, chat_info: ChatInfo) -> tuple[int, int]:
    """根据 row_rect + window_rect 计算屏幕坐标并点击。

    点击行中心偏左（避开右侧时间/静音图标），返回 (x, y) 逻辑坐标。
    """
    row = chat_info.row_rect
    win = chat_info.window_rect
    assert row is not None, "ChatInfo.row_rect 未设置"
    assert win is not None, "ChatInfo.window_rect 未设置"

    row_center_x_px = row.x + int(row.width * 0.40)
    row_center_y_px = row.y + row.height // 2

    click_x = win.x + _retina_to_logical(row_center_x_px)
    click_y = win.y + _retina_to_logical(row_center_y_px)

    driver.click_point(click_x, click_y)
    return click_x, click_y


def wait_chat_panel_ready(
    driver,
    target_name: str,
    timeout: float = 5.0,
    interval: float = 0.3,
    anchor_row_rect: Optional[Rect] = None,
) -> ClickResult:
    """循环截图检测右侧 header title，确认已切换到目标会话。

    需要连续两次稳定信号才算 ready。除标题 OCR 外，若提供 anchor_row_rect（点击前的侧栏行），
    则在标题未识别时用语义匹配 + 行位置核对侧栏，避免 header 裁切/Vision 失败导致误判超时。
    """
    start = time.time()
    attempts = 0
    prev_title = ""
    stable_count = 0

    while time.time() - start < timeout:
        attempts += 1
        img, wb = driver.capture_wechat_window_with_bounds()
        win_rect = Rect(wb.x, wb.y, wb.width, wb.height)
        title = extract_chat_header_title(img, match_hint=target_name)
        header_ok = bool(title and titles_match(title, target_name))
        sidebar_ok = False
        if anchor_row_rect is not None and not header_ok:
            sidebar_ok = _sidebar_confirms_target_chat(
                img, win_rect, target_name, anchor_row_rect,
            )

        if header_ok or sidebar_ok:
            sig = title if header_ok else target_name
            if sig == prev_title:
                stable_count += 1
            else:
                stable_count = 1
            prev_title = sig
            if stable_count >= 2:
                return ClickResult(
                    ready=True,
                    target_name=target_name,
                    detected_title=title if header_ok else target_name,
                    attempts=attempts,
                    reason="title_matched" if header_ok else "sidebar_matched",
                )
        else:
            prev_title = title or ""
            stable_count = 0

        time.sleep(interval)

    return ClickResult(
        ready=False,
        target_name=target_name,
        detected_title=prev_title,
        attempts=attempts,
        reason="timeout",
        error=f"等待 {timeout}s 后标题仍未匹配: detected={prev_title!r} target={target_name!r}",
    )


def click_into_chat(driver, chat_info: ChatInfo,
                    timeout: float = 5.0,
                    max_retries: int = 1) -> ClickResult:
    """完整流程：激活 → 点击 → 等 ready，失败时重试。

    重试策略：rescan sidebar（扫描全部行，不限 unread）找到最新
    row_rect，重新点击。
    """
    driver.activate_wechat()
    time.sleep(0.2)

    if bool(getattr(chat_info, "selected", False)):
        return ClickResult(
            ready=True,
            target_name=chat_info.name,
            detected_title=chat_info.name,
            reason="already_selected",
        )

    last_result: Optional[ClickResult] = None

    for retry in range(1 + max_retries):
        if retry > 0:
            time.sleep(0.3)
            # 重试前 rescan 全部行（不限 unread，因为 badge 可能已消失）
            fresh = _rescan_all(driver)
            updated = _find_chat_by_name(fresh, chat_info.name)
            if updated is None:
                result = ClickResult(
                    ready=False,
                    target_name=chat_info.name,
                    retries_used=retry,
                    reason="retry_target_not_found",
                    error=f"重试第 {retry} 次: sidebar 中未找到 {chat_info.name!r}",
                )
                if last_result:
                    result.attempts = last_result.attempts
                    result.detected_title = last_result.detected_title
                    result.click_point = last_result.click_point
                return result
            chat_info = updated
            time.sleep(0.2)

        cx, cy = click_chat_row(driver, chat_info)
        time.sleep(0.3)

        result = wait_chat_panel_ready(
            driver,
            chat_info.name,
            timeout=timeout,
            anchor_row_rect=chat_info.row_rect,
        )
        result.click_point = (cx, cy)
        result.retries_used = retry

        if result.ready:
            return result

        last_result = result

    assert last_result is not None
    return last_result


def rescan_unread(driver) -> List[ChatInfo]:
    """重新截图 + 扫描 sidebar（仅未读），获取最新 ChatInfo[]。"""
    time.sleep(0.3)
    img, wb = driver.capture_wechat_window_with_bounds()
    win_rect = Rect(wb.x, wb.y, wb.width, wb.height)
    return scan_sidebar_once(img, only_unread=True, window_bounds=win_rect)


def _rescan_all(driver) -> List[ChatInfo]:
    """重新截图 + 扫描 sidebar（全部行），用于重试时查找目标。"""
    time.sleep(0.3)
    img, wb = driver.capture_wechat_window_with_bounds()
    win_rect = Rect(wb.x, wb.y, wb.width, wb.height)
    return scan_sidebar_once(img, only_unread=False, window_bounds=win_rect)


def _find_chat_by_name(chats: List[ChatInfo], name: str) -> Optional[ChatInfo]:
    """在 ChatInfo 列表中按名称查找：先精确再模糊（与 find_unread_chat_by_name 一致）。"""
    if not name:
        return None
    for c in chats:
        if c.name and sidebar_name_matches_config_group(c.name, name):
            return c
    for c in chats:
        if c.name and titles_match(c.name, name):
            return c
    return None


def process_unread_chats(
    driver,
    chats: List[ChatInfo],
    on_chat_ready: Optional[Callable[[ChatInfo, ClickResult], None]] = None,
    timeout_per_chat: float = 5.0,
    max_retries: int = 1,
) -> List[ClickResult]:
    """逐个点击多个未读会话，每次确认 ready 后再处理下一个。

    流程（对每个 chat）：
      1. click_into_chat（含重试）
      2. 如果 ready，调用 on_chat_ready 回调
      3. rescan sidebar 获取最新 ChatInfo
      4. 在最新列表中找下一个目标

    返回每个 chat 的 ClickResult 列表。
    """
    results: List[ClickResult] = []
    remaining_names = [c.name for c in chats if c.name]

    driver.activate_wechat()
    time.sleep(0.3)

    for idx, target_name in enumerate(remaining_names):
        if idx == 0:
            current_chats = chats
        else:
            current_chats = rescan_unread(driver)

        target = _find_chat_by_name(current_chats, target_name)
        if target is None:
            results.append(ClickResult(
                ready=False,
                target_name=target_name,
                reason="not_found_in_sidebar",
                error=f"第 {idx+1} 个: sidebar 中未找到 {target_name!r}（可能已无未读）",
            ))
            continue

        result = click_into_chat(
            driver, target,
            timeout=timeout_per_chat,
            max_retries=max_retries,
        )
        results.append(result)

        if result.ready and on_chat_ready is not None:
            on_chat_ready(target, result)

        time.sleep(0.3)

    return results
