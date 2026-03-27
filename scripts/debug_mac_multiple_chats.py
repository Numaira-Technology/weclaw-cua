#!/usr/bin/env python3
"""多未读群批量处理调试：Step 2 列表 → 逐个点进 → 长图 → LLM → 每群一个 JSON。

输出目录：debug_outputs/batch_multichat/
  {群名}.json  — 顶层 chat_name、messages[].sender|time|content|type
  {群名}/      — long_image.png、中间产物（与 process_one_chat 一致）

用法：
  export OPENROUTER_API_KEY=...
  python3 scripts/debug_mac_multiple_chats.py
  python3 scripts/debug_mac_multiple_chats.py --max-chats 2
  python3 scripts/debug_mac_multiple_chats.py --passes 8 --max-side 768
  # 与 debug_mac_read_visible_messages 同一路径解析长图：
  python3 scripts/debug_mac_multiple_chats.py --read-visible --chunks 2
"""

from __future__ import annotations


def main() -> None:
    import argparse
    import os
    import sys
    import time

    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    root = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.join(root, "..")
    sys.path.insert(0, repo_root)

    from platform_mac.driver import MacDriver
    from algo_a.capture_chat import CaptureSettings
    from algo_a.extract_messages import DEFAULT_EXTRACT_MODEL
    from algo_a.list_unread_chats import list_unread_chats
    from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
    from algo_a.process_multiple_chats import UnreadBatchConfig, process_unread_chats_batch

    output_dir = os.path.join(repo_root, "debug_outputs", "batch_multichat")

    parser = argparse.ArgumentParser(description="多未读会话批量处理（调试用）")
    parser.add_argument(
        "--max-chats",
        type=int,
        default=None,
        help="最多处理几个未读（默认全部）",
    )
    parser.add_argument("--model", type=str, default=DEFAULT_EXTRACT_MODEL)
    parser.add_argument("--passes", type=int, default=15, help="每群滚动截图最大帧数")
    parser.add_argument(
        "--direction",
        type=str,
        default="up",
        choices=["up", "down"],
        help="滚动方向",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=DEFAULT_MAX_SIDE_PIXELS,
        help="送 LLM 前长图长边像素上限",
    )
    parser.add_argument("--save-frames", action="store_true", help="保存每帧截图")
    parser.add_argument(
        "--click-timeout",
        type=float,
        default=8.0,
        help="等待聊天面板标题匹配（秒）",
    )
    parser.add_argument(
        "--click-retries",
        type=int,
        default=2,
        help="单次进入会话时 click_into_chat 内 rescan 重试次数",
    )
    parser.add_argument(
        "--rounds-per-chat",
        type=int,
        default=3,
        help="整轮（点击+截图+LLM）失败后的最大重试轮数",
    )
    parser.add_argument(
        "--read-visible",
        action="store_true",
        help="长图解析走 read_long_image_messages（与 debug_mac_read_visible_messages 一致）；默认 extract_messages",
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=300.0,
        help="仅 --read-visible：vision 请求超时（秒）",
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
        help="仅 --read-visible：单条最大高度(px)自动算条数；0=用 --chunks 固定",
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
    print("  多未读群批量处理", flush=True)
    print("=" * 60, flush=True)
    print("[提示] 需已配置 OPENROUTER_API_KEY；每群含滚动与 LLM，总耗时可能很长。", flush=True)

    driver = MacDriver()
    driver.ensure_permissions()
    driver.find_wechat_window()
    driver.activate_wechat()
    time.sleep(0.4)

    print("[debug] 扫描未读会话（list_unread_chats）…", flush=True)
    unread = list_unread_chats(driver)
    if args.max_chats is not None:
        unread = unread[: max(0, args.max_chats)]

    print(f"[debug] 将处理 {len(unread)} 个会话:", flush=True)
    for i, c in enumerate(unread):
        print(
            f"    {i + 1}. {c.name!r}  badge={c.badge_type}  unread={c.unread_count}",
            flush=True,
        )

    if not unread:
        print("[!] 无未读会话，退出。", flush=True)
        sys.exit(0)

    if not any(c.name and str(c.name).strip() for c in unread):
        print(
            "[!] 未读会话名称 OCR 为空（无法按群名匹配与点击）。"
            "请放大微信窗口、避免 sidebar 过窄，或稍后重试 list_unread_chats。",
            flush=True,
        )
        sys.exit(1)

    eb = "read_long_image" if args.read_visible else "extract_messages"
    cfg = UnreadBatchConfig(
        click_timeout=args.click_timeout,
        click_max_retries=args.click_retries,
        max_rounds_per_chat=args.rounds_per_chat,
        capture_settings=CaptureSettings(
            max_passes=args.passes,
            scroll_direction=args.direction,
        ),
        model=args.model,
        save_frames=args.save_frames,
        vision_max_side_pixels=args.max_side,
        extract_backend=eb,
        extract_llm_timeout=args.llm_timeout,
        read_long_chunk_count=args.chunks,
        read_long_chunk_overlap=args.chunk_overlap,
        read_long_chunk_max_strip_height_px=args.chunk_max_height,
        read_long_chunk_max_count=args.chunk_max_count,
    )

    print(f"\n[debug] 输出目录: {os.path.abspath(output_dir)}\n", flush=True)

    results = process_unread_chats_batch(driver, unread, output_dir, cfg)

    print("\n" + "=" * 60, flush=True)
    print("  汇总", flush=True)
    print("=" * 60, flush=True)
    ok = sum(1 for r in results if r.success)
    print(f"  成功: {ok}/{len(results)}", flush=True)
    for r in results:
        st = "✓" if r.success else "✗"
        print(f"  {st} {r.chat_name}: ", end="", flush=True)
        if r.success:
            print(f"{r.message_count} 条 → {r.json_path}", flush=True)
        else:
            print(f"{r.error}", flush=True)
        if r.timings:
            t = r.timings.get("total", 0)
            print(f"      total {t:.1f}s", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
