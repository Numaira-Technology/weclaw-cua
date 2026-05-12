"""capture test-img command: compare live VLM responses across image encodings.

Usage:
    weclaw-cua capture test-img
    weclaw-cua capture test-img --target chat --variant webp:q90 --variant jpeg:q85
    weclaw-cua capture test-img --prompt-file prompt.txt --max-tokens 8192

Input spec:
    - Captures one WeChat screenshot target: chat, sidebar, or full.
    - Variants are png, webp_lossless, webp[:qN], jpeg[:qN], or webm aliases.

Output spec:
    - Writes the source image, prompt, encoded variants, and response files.
    - Prints per-variant size, timing, and model response for manual comparison.
"""

from __future__ import annotations

import os
import sys
import time

import click
from PIL import Image

from ..output.formatter import output


_FULL_IMAGE_TEST_PROMPT = (
    "Describe this WeChat screenshot. Focus on whether visible text, chat names, "
    "message bubbles, timestamps, and UI details are readable after compression."
)


@click.command("test-img")
@click.option("--target", default="chat", type=click.Choice(["chat", "sidebar", "full"]),
              help="Screenshot target to test")
@click.option("--variant", "variant_specs", multiple=True,
              help="Image variant: png, webp_lossless, webp:q90, jpeg:q85")
@click.option("--workers", default=0, type=int,
              help="Concurrent VLM requests (default: one per variant)")
@click.option("--max-tokens", default=4096, type=int,
              help="Max response tokens for each VLM request")
@click.option("--prompt-file", default=None,
              help="Use a custom prompt file instead of the target default")
@click.option("--output-dir", default=None,
              help="Directory for source images, variants, and responses")
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def capture_test_img(
    ctx,
    target,
    variant_specs,
    workers,
    max_tokens,
    prompt_file,
    output_dir,
    fmt,
):
    """Capture once, then send multiple encoded copies to the configured VLM."""
    from ..context import load_app_context

    app = load_app_context(ctx)
    root = app["root"]
    if root not in sys.path:
        sys.path.insert(0, root)

    from shared.vlm_format_benchmark import run_vlm_format_benchmark
    from shared.vlm_image_variants import parse_vlm_image_variants

    if not output_dir:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(app["output_dir"], "vlm_format_tests", stamp)
    os.makedirs(output_dir, exist_ok=True)

    image = _capture_target_image(app["config"], target)
    source_path = os.path.join(output_dir, f"source_{target}.png")
    image.save(source_path, format="PNG")

    prompt = _load_prompt(target, prompt_file)
    prompt_path = os.path.join(output_dir, "prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    variants = parse_vlm_image_variants(tuple(variant_specs))
    resolved_workers = workers if workers > 0 else len(variants)
    results = run_vlm_format_benchmark(
        config=app["config"],
        image=image,
        prompt=prompt,
        output_dir=output_dir,
        variants=variants,
        max_tokens=max_tokens,
        workers=resolved_workers,
    )
    payload = {
        "mode": "vlm_format_test",
        "target": target,
        "output_dir": os.path.abspath(output_dir),
        "source_image": os.path.abspath(source_path),
        "prompt_file": os.path.abspath(prompt_path),
        "workers": resolved_workers,
        "results": results,
    }
    output(payload if fmt == "json" else _format_text(payload), fmt)


def _capture_target_image(config, target: str) -> Image.Image:
    full = _capture_full_wechat_image(config)
    if target == "full":
        return full.copy()
    if target == "sidebar":
        width = int(full.width * 0.3)
        return full.crop((0, 0, width, full.height))
    if target == "chat":
        x1 = int(full.width * 0.31)
        y1 = 50
        x2 = int(full.width * 0.95)
        y2 = full.height - 50
        return full.crop((x1, y1, x2, y2))
    raise AssertionError("target must be chat, sidebar, or full")


def _capture_full_wechat_image(config) -> Image.Image:
    if sys.platform == "win32":
        from platform_win.find_wechat_window import find_wechat_window
        from platform_win.vision import _force_foreground_window
        from platform_win.vision import capture_window

        hwnd = find_wechat_window(app_name=config.wechat_app_name)
        assert hwnd, "WeChat window not found"
        _force_foreground_window(hwnd)
        time.sleep(0.3)
        full = capture_window(hwnd)
        assert full, "Failed to capture WeChat window"
        return full
    if sys.platform == "darwin":
        from platform_mac.find_wechat_window import find_wechat_window
        from platform_mac.grant_permissions import ensure_permissions
        from platform_mac.macos_window import activate_pid
        from platform_mac.macos_window import capture_window_pid

        ensure_permissions()
        window = find_wechat_window(config.wechat_app_name)
        activate_pid(window.pid)
        time.sleep(0.3)
        full = capture_window_pid(window.pid)
        assert full, "Failed to capture WeChat window"
        return full
    raise NotImplementedError(f"Platform {sys.platform} not supported")


def _load_prompt(target: str, prompt_file: str | None) -> str:
    if prompt_file:
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    if target == "chat":
        from shared.vision_prompts import CHAT_PANEL_PROMPT

        return CHAT_PANEL_PROMPT
    if target == "sidebar":
        from shared.vision_prompts import SIDEBAR_PROMPT

        return SIDEBAR_PROMPT
    return _FULL_IMAGE_TEST_PROMPT


def _format_text(payload: dict) -> str:
    lines = [
        f"VLM format test complete: {payload['target']}",
        f"Output dir: {payload['output_dir']}",
        f"Source image: {payload['source_image']}",
        f"Prompt: {payload['prompt_file']}",
        "",
    ]
    for result in payload["results"]:
        lines.extend([
            (
                f"== {result['variant']} | {result['bytes']} bytes "
                f"({result['png_ratio']}x png) | encode {result['encode_ms']} ms "
                f"| request {result['request_ms']} ms =="
            ),
            f"image: {result['image_file']}",
            f"response: {result['response_file']}",
            result["response"],
            "",
        ])
    return "\n".join(lines).rstrip()
