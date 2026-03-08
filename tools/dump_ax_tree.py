"""
Dump the WeChat AX tree directly via the macOS Accessibility API.

Usage (with WeChat open and a group chat visible):
    uv run python tools/dump_ax_tree.py

No running server required — queries AX API directly.
Output: all AXButton nodes + role/name sample from WeChat window.
"""

import json
import sys
from pathlib import Path

from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCopyAttributeNames,
    AXUIElementCreateApplication,
    kAXChildrenAttribute,
    kAXErrorSuccess,
    kAXRoleAttribute,
    kAXTitleAttribute,
    kAXDescriptionAttribute,
    kAXPositionAttribute,
    kAXSizeAttribute,
    kAXEnabledAttribute,
    kAXValueCGPointType,
    AXValueGetType,
    AXValueGetValue,
)
import Quartz
from AppKit import NSWorkspace


def ax_attr(element, attr):
    err, val = AXUIElementCopyAttributeValue(element, attr, None)
    if err == kAXErrorSuccess:
        return val
    return None


def walk(element, depth=0, max_depth=12, results=None):
    if results is None:
        results = []
    if depth > max_depth:
        return results

    role = ax_attr(element, kAXRoleAttribute) or ""
    title = ax_attr(element, kAXTitleAttribute) or ""
    desc = ax_attr(element, kAXDescriptionAttribute) or ""

    # Get position (logical pts)
    pos_val = ax_attr(element, kAXPositionAttribute)
    pos_str = ""
    if pos_val and AXValueGetType(pos_val) == 1:
        import Quartz as Q
        pt = Q.CGPoint()
        AXValueGetValue(pos_val, 1, pt)
        pos_str = f"({pt.x:.0f},{pt.y:.0f})"

    results.append({
        "depth": depth,
        "role": role,
        "title": title,
        "description": desc,
        "pos": pos_str,
    })

    children = ax_attr(element, kAXChildrenAttribute)
    if children:
        for child in children:
            walk(child, depth + 1, max_depth, results)
    return results


def main():
    workspace = NSWorkspace.sharedWorkspace()
    running = workspace.runningApplications()

    wechat_pid = None
    for app in running:
        name = app.localizedName() or ""
        bundle = app.bundleIdentifier() or ""
        if "wechat" in name.lower() or "微信" in name or "com.tencent.xinWeChatMac" in bundle or "com.tencent.wechat" in bundle.lower():
            wechat_pid = app.processIdentifier()
            print(f"Found WeChat: name={name} bundle={bundle} pid={wechat_pid}")
            break

    if wechat_pid is None:
        print("WeChat not found in running apps!")
        print("Running apps:")
        for app in running:
            print(f"  {app.localizedName()} [{app.bundleIdentifier()}]")
        sys.exit(1)

    app_elem = AXUIElementCreateApplication(wechat_pid)
    print(f"\nWalking AX tree for WeChat (pid={wechat_pid})...")
    nodes = walk(app_elem, max_depth=10)

    print(f"\nTotal nodes: {len(nodes)}")
    print("\n--- All AXButton nodes ---")
    buttons = [n for n in nodes if n["role"] == "AXButton"]
    for b in buttons:
        print(f"  depth={b['depth']} title={repr(b['title'])} desc={repr(b['description'])} pos={b['pos']}")

    print(f"\nTotal AXButtons: {len(buttons)}")

    print("\n--- Sample of all role/title combos (first 60) ---")
    seen = set()
    for n in nodes:
        key = (n["role"], n["title"][:30], n["description"][:30])
        if key not in seen:
            seen.add(key)
            print(f"  role={n['role']!r} title={repr(n['title'])} desc={repr(n['description'])}")
        if len(seen) >= 60:
            break


if __name__ == "__main__":
    main()
