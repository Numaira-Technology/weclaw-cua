#!/usr/bin/env python3
"""单群闭环调试脚本：点击 → 截图 → 长图 → LLM → 后处理 → JSON。

用法：
  python scripts/debug_process_one_chat.py
  python scripts/debug_process_one_chat.py --chat "群聊名称"
  python scripts/debug_process_one_chat.py --chat "群聊名称" --skip-click
  python scripts/debug_process_one_chat.py --chat "群聊名称" --save-frames
  python scripts/debug_process_one_chat.py --passes 10 --direction down

输出到 debug_outputs/process/{chat_name}/
  long_image.png   — 拼接长图
  {chat_name}.json  — 结构化消息
  frames/          — 每帧截图（需 --save-frames）

注意：重依赖（OpenCV 等）在 main() 内导入，便于先打印启动信息；
若 OpenCV 的 .dylib 损坏，会在「进入流程后」才报错并给出修复命令。
"""

from __future__ import annotations


def main() -> None:
    import argparse
    import json
    import os
    import sys
    import time

    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    # 必须在任何项目内 import 之前打印，否则 cv2 等 dlopen 失败时终端「完全没反应」
    print("[weclaw] 启动 debug_process_one_chat …", flush=True)

    root = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.join(root, "..")
    sys.path.insert(0, repo_root)

    from platform_mac.driver import MacDriver
    from platform_mac.sidebar_detector import ChatInfo, Rect, scan_sidebar_once
    from platform_mac.chat_panel_detector import titles_match
    from algo_a.capture_chat import CaptureSettings
    from algo_a.extract_messages import DEFAULT_EXTRACT_MODEL
    from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
    from algo_a.process_one_chat import ProcessResult, process_one_chat

    output_dir = os.path.join(repo_root, "debug_outputs", "process")

    def _find_target_chat(driver: MacDriver, target_name: str | None) -> ChatInfo | None:
        img = driver.capture_wechat_window()
        bounds = driver.get_window_bounds()
        wb = Rect(bounds.x, bounds.y, bounds.width, bounds.height)
        chats = scan_sidebar_once(img, only_unread=False, window_bounds=wb)

        if target_name:
            for c in chats:
                if titles_match(c.name, target_name):
                    return c
            print(f"[!] 未找到名为 '{target_name}' 的会话")
            print(f"    可见会话: {[c.name for c in chats[:10]]}")
            return None

        unread = [c for c in chats if c.badge_type != "none"]
        if unread:
            print(f"[*] 找到 {len(unread)} 个未读会话，使用第一个: {unread[0].name}")
            return unread[0]

        if chats:
            print(f"[*] 无未读会话，使用第一个可见会话: {chats[0].name}")
            return chats[0]

        print("[!] sidebar 中未检测到任何会话")
        return None

    def _print_result(result: ProcessResult) -> None:
        print()
        print("=" * 60)
        print("  处理结果")
        print("=" * 60)

        status = "✓ 成功" if result.success else "✗ 失败"
        print(f"  状态:       {status}")
        print(f"  群聊:       {result.chat_name}")
        print(f"  消息数:     {result.message_count} (原始 {result.raw_message_count})")
        print(f"  帧数:       {result.frame_count}")
        print(f"  confidence: {result.extraction_confidence}")

        if result.json_path:
            print(f"  JSON:       {result.json_path}")
        if result.long_image_path:
            print(f"  长图:       {result.long_image_path}")
        if result.error:
            print(f"  错误:       {result.error}")

        if result.timings:
            print("\n  耗时明细:")
            for step, t in result.timings.items():
                print(f"    {step:>12s}: {t:.1f}s")

        print("=" * 60)

    def _print_messages_preview(json_path: str, max_lines: int = 10) -> None:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", data) if isinstance(data, dict) else data
            if not messages:
                print("\n  (无消息)")
                return
            print(f"\n  消息预览 (前 {min(max_lines, len(messages))} 条):")
            print(f"  {'─' * 56}")
            for i, m in enumerate(messages[:max_lines]):
                sender = m.get("sender", "?")
                content = m.get("content", "")
                msg_type = m.get("type", "?")
                time_str = m.get("time", "")
                preview = content[:50] + ("..." if len(content) > 50 else "")
                time_label = f" [{time_str}]" if time_str else ""
                type_label = f" ({msg_type})" if msg_type != "text" else ""
                print(f"  {i+1:>3}. {sender}{time_label}: {preview}{type_label}")
            if len(messages) > max_lines:
                print(f"  ... 还有 {len(messages) - max_lines} 条")
        except Exception as e:
            print(f"\n  消息预览失败: {e}")

    parser = argparse.ArgumentParser(description="单群闭环处理调试")
    parser.add_argument("--chat", type=str, default=None, help="指定会话名称")
    parser.add_argument(
        "--skip-click",
        action="store_true",
        help="跳过点击（已在目标会话中）",
    )
    parser.add_argument("--save-frames", action="store_true", help="保存每帧截图")
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_EXTRACT_MODEL,
        help="LLM 模型（默认与 whole_pic_message_extractor 一致）",
    )
    parser.add_argument(
        "--direction",
        type=str,
        default="up",
        choices=["up", "down"],
        help="滚动方向",
    )
    parser.add_argument("--passes", type=int, default=15, help="最大滚动帧数")
    parser.add_argument(
        "--max-side",
        type=int,
        default=DEFAULT_MAX_SIDE_PIXELS,
        help="送 LLM 前长图长边像素上限（0=不缩小）",
    )
    parser.add_argument(
        "--read-visible",
        action="store_true",
        help="长图解析走 read_long_image_messages（与 debug_mac_read_visible_messages 一致）；默认 whole_pic extract_messages",
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=300.0,
        help="仅 --read-visible：单次 vision 请求超时（秒）",
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=2,
        help="仅 --read-visible 且 --chunk-max-height=0：固定竖切条数（1～10）",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=float,
        default=0.08,
        help="仅 --read-visible：分段重叠比例",
    )
    parser.add_argument(
        "--chunk-max-height",
        type=int,
        default=2400,
        help="仅 --read-visible：单条最大高度(px)自动算条数，上限见 --chunk-max-count；0=用 --chunks 固定",
    )
    parser.add_argument(
        "--chunk-max-count",
        type=int,
        default=10,
        help="仅 --read-visible：自动分段最多条数",
    )
    args = parser.parse_args()
    if not (1 <= args.chunks <= 10):
        print("[!] --chunks 须在 1～10", flush=True)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60, flush=True)
    print("  单群闭环处理调试", flush=True)
    print("=" * 60, flush=True)
    print(
        "[提示] 滚动截图约 1–3 分钟；LLM 分析长图可能数分钟。",
        flush=True,
    )
    print("[debug] 加载驱动（若此前无输出而此处卡住，多为 OpenCV 动态库问题）…", flush=True)

    driver = MacDriver()
    driver.ensure_permissions()
    driver.find_wechat_window()
    driver.activate_wechat()
    time.sleep(0.5)
    print("[debug] 微信已激活，正在选会话…", flush=True)

    if args.skip_click and args.chat:
        target = ChatInfo(
            name=args.chat,
            unread_count=None,
            badge_type="none",
            source="manual",
            confidence=1.0,
        )
    else:
        target = _find_target_chat(driver, args.chat)
        if target is None:
            sys.exit(1)

    print(f"\n  目标: {target.name}")
    print(f"  badge={target.badge_type}, unread={target.unread_count}")
    print()

    settings = CaptureSettings(
        max_passes=args.passes,
        scroll_direction=args.direction,
    )

    eb = "read_long_image" if args.read_visible else "extract_messages"
    try:
        result = process_one_chat(
            driver=driver,
            chat_info=target,
            output_dir=output_dir,
            capture_settings=settings,
            model=args.model,
            skip_click=args.skip_click,
            save_frames=args.save_frames,
            vision_max_side_pixels=args.max_side,
            extract_backend=eb,
            extract_llm_timeout=args.llm_timeout,
            read_long_chunk_count=args.chunks,
            read_long_chunk_overlap=args.chunk_overlap,
            read_long_chunk_max_strip_height_px=args.chunk_max_height,
            read_long_chunk_max_count=args.chunk_max_count,
        )
    except RuntimeError as e:
        print(f"\n[致命] {e}", flush=True)
        sys.exit(1)

    _print_result(result)

    if result.success and result.json_path:
        _print_messages_preview(result.json_path)


if __name__ == "__main__":
    main()
