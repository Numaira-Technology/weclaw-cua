"""
Computer session lifecycle for desktop mode.

Usage:
  from pathlib import Path
  settings = load_computer_settings(Path("config/computer_windows.yaml"))
  computer = build_computer(settings)
  await computer.run()

Input:
  - config_path: Path to YAML file with use_host_computer_server, os_type,
    api_port, display, timeout, telemetry_enabled, screenshot_delay, screen
    dimensions, (Windows only) wechat UI positions, and scroll tuning knobs.

Output:
  - ComputerSettings dataclass populated from config.
  - Initialized Computer instance connected to local computer-server.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
COMPUTER_PKG = VENDOR / "computer"
CORE_PKG = VENDOR / "core"
for pkg in [COMPUTER_PKG, CORE_PKG]:
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))

from computer import Computer  # type: ignore  # noqa: E402


@dataclass
class ComputerSettings:
    """Computer and WeChat UI configuration.

    wechat_* position fields are in SCREEN COORDINATES (absolute pixels).
    They are only used on Windows; on macOS the AX accessibility tree is used
    instead and these fields default to (0, 0).

    scroll_* fields tune the multi-pass scroll reader (step 5) and the chat
    list pagination.  They have sensible defaults and are optional in both
    platform configs.
    """

    use_host_computer_server: bool
    os_type: str
    api_port: int
    display: str
    timeout: int
    telemetry_enabled: bool
    screenshot_delay: float
    screen_width: int   # SCREEN: display width in pixels (e.g., 2560)
    screen_height: int  # SCREEN: display height in pixels (e.g., 1440)
    # Windows-only click coords; ignored on macOS (AX tree used instead)
    wechat_three_dots: Tuple[int, int] = field(default=(0, 0))
    wechat_minus_button: Tuple[int, int] = field(default=(0, 0))
    wechat_delete_button: Tuple[int, int] = field(default=(0, 0))
    wechat_banner: Tuple[int, int] = field(default=(0, 0))
    # Scroll tuning — shared across platforms
    scroll_chat_window_clicks_per_pass: int = field(default=5)
    scroll_max_chat_window_passes: int = field(default=4)
    scroll_chat_list_clicks_per_scroll: int = field(default=15)


def _parse_simple_yaml(path: Path) -> Dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    pairs = []
    for raw in lines:
        if not raw.strip():
            continue
        if raw.strip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        pairs.append((key.strip(), value))
    return {k: v for k, v in pairs}


def load_computer_settings(path: Path) -> ComputerSettings:
    data = _parse_simple_yaml(path)
    return ComputerSettings(
        use_host_computer_server=str(
            data.get("use_host_computer_server", "true")
        ).lower()
        == "true",
        os_type=data.get("os_type", "windows"),
        api_port=int(data.get("api_port", 8000)),
        display=data.get("display", "1280x720"),
        timeout=int(data.get("timeout", 120)),
        telemetry_enabled=str(data.get("telemetry_enabled", "false")).lower() == "true",
        screenshot_delay=float(data.get("screenshot_delay", 0.5)),
        screen_width=int(data.get("screen_width", 2560)),
        screen_height=int(data.get("screen_height", 1440)),
        # wechat_* coords are Windows-only; default to (0,0) for macOS configs
        wechat_three_dots=(
            int(data.get("wechat_three_dots_x", 0)),
            int(data.get("wechat_three_dots_y", 0)),
        ),
        wechat_minus_button=(
            int(data.get("wechat_minus_button_x", 0)),
            int(data.get("wechat_minus_button_y", 0)),
        ),
        wechat_delete_button=(
            int(data.get("wechat_delete_button_x", 0)),
            int(data.get("wechat_delete_button_y", 0)),
        ),
        wechat_banner=(
            int(data.get("wechat_banner_x", 0)),
            int(data.get("wechat_banner_y", 0)),
        ),
        scroll_chat_window_clicks_per_pass=int(
            data.get("scroll_chat_window_clicks_per_pass", 5)
        ),
        scroll_max_chat_window_passes=int(
            data.get("scroll_max_chat_window_passes", 4)
        ),
        scroll_chat_list_clicks_per_scroll=int(
            data.get("scroll_chat_list_clicks_per_scroll", 15)
        ),
    )


def build_computer(settings: ComputerSettings) -> Computer:
    return Computer(
        display=settings.display,
        os_type=settings.os_type,  # type: ignore[arg-type]
        use_host_computer_server=settings.use_host_computer_server,
        api_port=settings.api_port,
        timeout=settings.timeout,
        telemetry_enabled=settings.telemetry_enabled,
    )


async def ensure_running(computer: Computer) -> Computer:
    await computer.run()
    return computer


def run_blocking(computer: Computer) -> None:
    asyncio.run(ensure_running(computer))
