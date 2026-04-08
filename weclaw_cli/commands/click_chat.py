"""click-chat command — click a sidebar row by coordinates.

Usage:
    weclaw click-chat --x 120 --y 350      # click at absolute screen coords
    weclaw click-chat --name "Group A"      # click by chat name (needs LLM bbox)

The agent gets row coordinates from parsing the sidebar screenshot
with its own LLM, then calls this to navigate to a specific chat.
"""

import sys
import time

import click

from ..output.formatter import output


@click.command("click-chat")
@click.option("--x", "click_x", type=int, default=None, help="Absolute screen X coordinate")
@click.option("--y", "click_y", type=int, default=None, help="Absolute screen Y coordinate")
@click.option("--sidebar-y", type=int, default=None,
              help="Y coordinate in normalized 0-1000 space within the sidebar crop")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]))
@click.pass_context
def click_chat(ctx, click_x, click_y, sidebar_y, fmt):
    """Click a chat in the WeChat sidebar to navigate to it.

    \b
    Two modes:
      --x/--y: absolute screen pixel coordinates (agent calculated)
      --sidebar-y: normalized Y in sidebar (0=top, 1000=bottom),
                   WeClaw calculates the screen coordinates

    \b
    Typical agent workflow:
      1. weclaw screenshot sidebar → agent parses with LLM
      2. LLM returns rows with y-coordinates (0-1000 normalized)
      3. Agent calls: weclaw click-chat --sidebar-y 73
      4. Agent waits, then: weclaw screenshot chat
    """
    from ..context import load_app_context
    app = load_app_context(ctx)
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    import pyautogui
    from platform_mac.grant_permissions import ensure_permissions
    from platform_mac.find_wechat_window import find_wechat_window
    from platform_mac.macos_window import activate_pid, main_window_bounds

    ensure_permissions()
    ww = find_wechat_window(app["config"].wechat_app_name)
    pid = ww.pid
    activate_pid(pid)
    time.sleep(0.3)

    if click_x is not None and click_y is not None:
        target_x, target_y = click_x, click_y
    elif sidebar_y is not None:
        left, top, right, bottom = main_window_bounds(pid)
        sidebar_width = int((right - left) * 0.3)
        target_x = left + sidebar_width // 2
        target_y = top + int((bottom - top) * sidebar_y / 1000)
    else:
        click.echo("Provide --x/--y or --sidebar-y.", err=True)
        ctx.exit(1)

    pyautogui.moveTo(target_x, target_y, duration=0.25)
    pyautogui.click()
    time.sleep(1.0)

    result = {
        "clicked": {"x": target_x, "y": target_y},
        "instructions": "Wait 1-2 seconds, then run 'weclaw screenshot chat' to verify the correct chat opened.",
    }
    output(result, fmt)


@click.command("double-click-nav")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]))
@click.pass_context
def double_click_nav(ctx, fmt):
    """Double-click the Messages nav icon to jump to next unread chat.

    \b
    Agent workflow for unread navigation:
      1. weclaw screenshot sidebar → parse with LLM
      2. If unreads exist: weclaw double-click-nav
      3. Wait, then: weclaw screenshot sidebar → re-parse
      4. weclaw screenshot scroll-capture → extract messages
      5. Repeat until no more unreads
    """
    from ..context import load_app_context
    app = load_app_context(ctx)
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    import pyautogui
    from platform_mac.grant_permissions import ensure_permissions
    from platform_mac.find_wechat_window import find_wechat_window
    from platform_mac.macos_window import activate_pid, main_window_bounds
    from platform_mac.left_nav_messages_icon import nav_messages_unread_badge_present
    from platform_mac.macos_window import capture_window_pid

    ensure_permissions()
    ww = find_wechat_window(app["config"].wechat_app_name)
    pid = ww.pid
    activate_pid(pid)
    time.sleep(0.3)

    full = capture_window_pid(pid)
    has_unread = nav_messages_unread_badge_present(full) if full else False

    left, top, right, bottom = main_window_bounds(pid)
    nav_x = left + 25
    nav_y = top + 85

    pyautogui.moveTo(nav_x, nav_y, duration=0.12)
    pyautogui.doubleClick(interval=0.06)
    time.sleep(0.8)

    result = {
        "had_unread_badge": has_unread,
        "clicked": {"x": nav_x, "y": nav_y},
        "instructions": "Wait 1 second, then 'weclaw screenshot sidebar' to see which chat is now active.",
    }
    output(result, fmt)
