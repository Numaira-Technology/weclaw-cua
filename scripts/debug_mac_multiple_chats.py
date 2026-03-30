#!/usr/bin/env python3
"""多未读群批量处理调试：Step 2 列表 → 逐个点进 → 长图 → LLM → 每群一个 JSON。

输出目录：debug_outputs/batch_multichat/
  {群名}.json  — 顶层 chat_name、messages[].sender|time|content|type
  {群名}/      — long_image.png、中间产物（与 process_one_chat 一致）

用法：
  默认读取仓库 config/config.json（wechat_app_name、groups_to_monitor、llm_model、openrouter_api_key）。
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

    from config import load_config
    from platform_mac.driver import MacDriver
    from algo_a.capture_chat import CaptureSettings
    from algo_a.list_unread_chats import filter_chats_by_groups_to_monitor, list_unread_chats
    from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
    from algo_a.process_multiple_chats import UnreadBatchConfig, process_unread_chats_batch

    output_dir = os.path.join(repo_root, "debug_outputs", "batch_multichat")

    parser = argparse.ArgumentParser(description="多未读会话批量处理（调试用）")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="config.json 路径（默认 <仓库>/config/config.json）",
    )
    parser.add_argument(
        "--max-chats",
        type=int,
        default=None,
        help="最多处理几个未读（默认全部）",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="vision 模型（默认使用 config.json 的 llm_model）",
    )
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

    config_path = args.config or os.path.join(repo_root, "config", "config.json")
    cfg = load_config(config_path)
    model = args.model if args.model is not None else cfg.llm_model

    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60, flush=True)
    print("  多未读群批量处理", flush=True)
    print("=" * 60, flush=True)
    print(f"[config] {os.path.abspath(config_path)}", flush=True)
    print(
        f"  wechat_app_name={cfg.wechat_app_name!r}  "
        f"groups_to_monitor 共 {len(cfg.groups_to_monitor)} 项: {cfg.groups_to_monitor!r}",
        flush=True,
    )
    print(
        "[提示] OpenRouter：export OPENROUTER_API_KEY，或在 config 中填写 openrouter_api_key；"
        "每群含滚动与 LLM，总耗时可能很长。",
        flush=True,
    )

    driver = MacDriver()
    driver.ensure_permissions()
    driver.find_wechat_window(cfg.wechat_app_name)
    driver.activate_wechat()
    time.sleep(0.4)

    print("[debug] 扫描未读会话（list_unread_chats）…", flush=True)
    all_unread = list_unread_chats(driver)
    unread = filter_chats_by_groups_to_monitor(all_unread, cfg.groups_to_monitor)
    print(
        f"[debug] 按 groups_to_monitor 过滤：{len(all_unread)} → {len(unread)} 个会话",
        flush=True,
    )
    if len(all_unread) > len(unread):
        allowed = {g.strip() for g in cfg.groups_to_monitor if g and str(g).strip()}
        skipped = [c for c in all_unread if c.name.strip() not in allowed]
        if skipped:
            print(
                "[debug] 未读但未在 groups_to_monitor（须与 OCR 解析名完全一致）:",
                flush=True,
            )
            for c in skipped:
                print(
                    f"    跳过: name={c.name!r}  badge={c.badge_type}  unread={c.unread_count}",
                    flush=True,
                )
    if all_unread and not unread:
        print(
            "[!] 侧栏扫到未读行，但群名与 config 的 groups_to_monitor 无精确匹配。"
            " 名称区 OCR（解析名 | 原始行@置信度）：",
            flush=True,
        )
        head = all_unread[:12]
        for i, c in enumerate(head, start=1):
            raw = c.name_ocr_raw.strip() or "(名称子区域无 OCR 文本)"
            print(f"    {i}. 解析={c.name!r}  |  {raw}", flush=True)
        if head and all(not c.name_ocr_raw.strip() for c in head):
            print(
                "[!] 仍无 Vision 文本时：未读行由红点检出，名称 ROI 可能落在空白/头像上；"
                "或列表行高与代码中 ROW_HEIGHT_DEFAULT=136 不一致。请跑 "
                "scripts/debug_mac_sidebar_unread.py 对照青框 name 与 name_preview。",
                flush=True,
            )
    if args.max_chats is not None:
        unread = unread[: max(0, args.max_chats)]

    print(f"[debug] 将处理 {len(unread)} 个会话:", flush=True)
    for i, c in enumerate(unread):
        extra = f"  ocr_raw={c.name_ocr_raw!r}" if c.name_ocr_raw.strip() else ""
        print(
            f"    {i + 1}. {c.name!r}  badge={c.badge_type}  unread={c.unread_count}{extra}",
            flush=True,
        )

    if not unread:
        if not all_unread:
            print(
                "[!] 无未读会话（红点未检出或窗口非聊天列表）。"
                "可跑 scripts/debug_mac_sidebar_unread.py 看侧栏裁切与逐行检测。",
                flush=True,
            )
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
        model=model,
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
