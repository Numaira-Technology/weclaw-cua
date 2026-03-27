"""多未读会话：rescan → 点击 → 长图 → LLM → JSON（按群名输出）。

输入为 Step 2 得到的 ChatInfo 列表（顺序即处理顺序）。
每处理完一个会话后重新扫描 sidebar 未读，再处理下一个。

用法：
    from algo_a.process_multiple_chats import UnreadBatchConfig, process_unread_chats_batch
    process_unread_chats_batch(driver, unread_list, output_dir="output", config=...)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from platform_mac.sidebar_detector import ChatInfo

from algo_a.capture_chat import CaptureSettings
from algo_a.extract_messages import DEFAULT_EXTRACT_MODEL
from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
from algo_a.process_one_chat import ProcessResult, process_one_chat
from algo_a.sidebar_find_chat import find_unread_chat_by_name


@dataclass
class UnreadBatchConfig:
    """批量未读处理的可调参数。"""
    click_timeout: float = 8.0
    click_max_retries: int = 2
    max_rounds_per_chat: int = 3
    capture_settings: Optional[CaptureSettings] = None
    model: str = DEFAULT_EXTRACT_MODEL
    save_frames: bool = False
    vision_max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS
    pause_between_chats_sec: float = 0.5


def process_unread_chats_batch(
    driver,
    unread_chats: List[ChatInfo],
    output_dir: str,
    config: Optional[UnreadBatchConfig] = None,
) -> List[ProcessResult]:
    """按顺序处理列表中的每个未读会话；每步前在 sidebar 中滚动查找未读行。

    若某会话消失（已读/滑走），整轮重试至多 max_rounds_per_chat。
    """
    cfg = config or UnreadBatchConfig()
    names = [c.name.strip() for c in unread_chats if c.name and c.name.strip()]
    results: List[ProcessResult] = []

    if unread_chats and not names:
        return [
            ProcessResult(
                chat_name="",
                success=False,
                error="no_valid_chat_name_ocr_batch_requires_name",
            ),
        ]

    for idx, name in enumerate(names):
        print(
            f"[batch] ({idx + 1}/{len(names)}) 会话: {name!r}",
            flush=True,
        )
        last: Optional[ProcessResult] = None
        for round_i in range(cfg.max_rounds_per_chat):
            target = find_unread_chat_by_name(driver, name)
            if target is None:
                print(
                    f"[batch]   sidebar 未读中未找到（round {round_i + 1}/{cfg.max_rounds_per_chat}）",
                    flush=True,
                )
                time.sleep(0.6)
                continue
            last = process_one_chat(
                driver,
                target,
                output_dir=output_dir,
                capture_settings=cfg.capture_settings,
                model=cfg.model,
                skip_click=False,
                save_frames=cfg.save_frames,
                vision_max_side_pixels=cfg.vision_max_side_pixels,
                click_timeout=cfg.click_timeout,
                click_max_retries=cfg.click_max_retries,
            )
            if last.success:
                break
            print(
                f"[batch]   失败: {last.error} — 重试 round {round_i + 2}",
                flush=True,
            )
            time.sleep(0.8)

        if last is None:
            last = ProcessResult(
                chat_name=name,
                success=False,
                error="not_in_unread_sidebar_after_retries",
            )
        results.append(last)
        time.sleep(cfg.pause_between_chats_sec)

    return results
