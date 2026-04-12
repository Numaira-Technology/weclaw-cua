"""WeChat window geometry, activation, and screenshots on macOS."""

import time

import Quartz
from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication


def activate_pid(pid: int) -> None:
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    assert app is not None
    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    time.sleep(0.25)


def main_window_bounds(pid: int) -> tuple[int, int, int, int]:
    lst = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    best_area = 0
    best = None
    for w in lst:
        if w.get("kCGWindowOwnerPID") != pid:
            continue
        if w.get("kCGWindowLayer", 0) != 0:
            continue
        b = w.get("kCGWindowBounds")
        if not b:
            continue
        area = int(b["Width"]) * int(b["Height"])
        if area > best_area:
            best_area = area
            best = b
    assert best is not None, f"No on-screen window for pid {pid}"
    left = int(best["X"])
    top = int(best["Y"])
    w = int(best["Width"])
    h = int(best["Height"])
    return (left, top, left + w, top + h)


def capture_window_pid(pid: int):
    """Full WeChat window as PIL Image via Quartz (avoids ImageGrab bbox/Retina issues)."""
    img, _ = capture_window_pid_and_bounds(pid)
    return img


def capture_window_pid_and_bounds(pid: int):
    activate_pid(pid)
    from platform_mac.screenshot import capture_window

    return capture_window(pid)


def window_image_px_to_screen_pt(
    ix: float,
    iy: float,
    img_w: int,
    img_h: int,
    wb,
) -> tuple[int, int]:
    """Map a point in full-window screenshot pixel space to pyautogui screen points."""
    assert img_w > 0 and img_h > 0
    sx = wb.x + int(ix / img_w * wb.width)
    sy = wb.y + int(iy / img_h * wb.height)
    return sx, sy


def vision_bbox_to_center_window_px(
    bbox: list,
    img_w: int,
    img_h: int,
) -> tuple[float, float]:
    x0, y0, x1, y1 = [float(b) for b in bbox]
    if max(x0, y0, x1, y1) <= 1000.0:
        cx = (x0 + x1) / 2.0 / 1000.0 * img_w
        cy = (y0 + y1) / 2.0 / 1000.0 * img_h
    else:
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
    return cx, cy


def vision_bbox_center_to_screen_pt(bbox: list, img_w: int, img_h: int, wb) -> tuple[int, int]:
    cx, cy = vision_bbox_to_center_window_px(bbox, img_w, img_h)
    return window_image_px_to_screen_pt(cx, cy, img_w, img_h, wb)
