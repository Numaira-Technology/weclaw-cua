# Platform Developer Guide

This guide is for the two developers implementing `platform_mac/` and `platform_win/`.
Your job is to make the `PlatformDriver` interface work on your OS so that `algo_a` can
collect unread WeChat messages without knowing which platform it's running on.

---

## Architecture Overview

```
algo_a/  (DONE - do not modify)           shared/
├── pipeline_a.py                         ├── platform_api.py    <-- PlatformDriver Protocol
├── list_unread_chats.py                  └── message_schema.py
├── click_into_chat.py
├── scroll_chat_to_bottom.py              platform_mac/  (your job if macOS)
├── read_messages_from_uitree.py          ├── driver.py          <-- implement MacDriver here
└── write_messages_json.py                ├── find_wechat_window.py
                                          ├── grant_permissions.py
                                          └── ui_tree_reader.py

                                          platform_win/  (your job if Windows)
                                          ├── driver.py          <-- implement WinDriver here
                                          ├── find_wechat_window.py
                                          ├── grant_permissions.py
                                          └── ui_tree_reader.py
```

**Data flow:**

```
pipeline_a.py creates driver -> calls algo_a modules -> algo_a calls driver methods -> driver talks to OS
```

`algo_a` is **complete and ready to use**. It calls your driver through the methods defined in
`shared/platform_api.py`. You do NOT need to modify any file in `algo_a/`.

---

## What You Need to Implement

Your primary file is `platform_{mac,win}/driver.py`. It contains a class (`MacDriver` or `WinDriver`)
with every method stubbed as `raise NotImplementedError`. You also need to implement the helper files
(`find_wechat_window.py`, `grant_permissions.py`, `ui_tree_reader.py`) that your driver depends on.

### Step 1: `grant_permissions.py`

Implement permission checking so the driver can access the WeChat UI tree.

**macOS:**
- Use `ApplicationServices.AXIsProcessTrusted()` to check Accessibility permission.
- Use `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})` to prompt.
- `ensure_permissions()` should check, prompt if needed, re-check, then `assert` on failure.

**Windows:**
- `check_platform()` is already implemented (`assert sys.platform == "win32"`).
- Use `ctypes.windll.shell32.IsUserAnAdmin()` to check for elevation.
- `ensure_permissions()` should check platform, optionally warn about admin, then proceed.

### Step 2: `find_wechat_window.py`

Return a platform-specific window handle that your driver methods will use.

**macOS:**
- `NSWorkspace.sharedWorkspace().runningApplications()` to find WeChat by bundle ID or name.
- `AXUIElementCreateApplication(pid)` to get app ref.
- Query `kAXWindowsAttribute` to get the main window ref.
- Activate/raise the window if it's hidden or minimized.
- Return `WechatWindow(app_ref, window_ref, pid)`.

**Windows:**
- `comtypes.CoCreateInstance(CUIAutomation)` to get IUIAutomation.
- `automation.GetRootElement()` then `FindFirst` with Name condition matching app_name.
- Extract HWND via `CurrentNativeWindowHandle` and pid via `CurrentProcessId`.
- Return `WechatWindow(window_handle, automation_element, pid)`.

### Step 3: `driver.py` — The Main File

Each method in your driver class maps to a specific UI automation operation. Here's
exactly what each method must do, and how `algo_a` uses it:

---

#### `get_sidebar_rows(window) -> list[Any]`

**Called by:** `list_unread_chats.py` — scans for unread badges.

**What it must return:** A list of UI element handles, one per **currently visible** chat row
in the left sidebar. Order should match visual order (top to bottom).

**macOS approach:**
```
window_ref
  -> AXSplitGroup (first child)
    -> first AXScrollArea (this is the sidebar)
      -> AXList (or AXOutline)
        -> AXRow children  <-- return these
```
Use `ui_tree_reader.get_children()` and `ui_tree_reader.get_attribute(el, 'AXRole')` to navigate.

**Windows approach:**
```
automation_element
  -> FindFirst(TreeScope_Descendants, ControlType=List)  [sidebar list]
    -> FindAll(TreeScope_Children, TrueCondition)  <-- return these
```

---

#### `scroll_sidebar(window, direction) -> None`

**Called by:** `list_unread_chats.py` — scrolls down to discover more chats off-screen.

**What it must do:** Scroll the sidebar list by roughly one "page" in the given direction.

**macOS approach:** Either `perform_action(sidebar_scroll_area, 'AXScrollDown')` or use
`CGEventCreateScrollWheelEvent` targeting the sidebar area.

**Windows approach:** Get ScrollPattern from the sidebar List element, call
`Scroll(ScrollAmount_NoAmount, ScrollAmount_LargeIncrement)` for down.

---

#### `get_row_name(row) -> str`

**Called by:** `list_unread_chats.py` — to get the chat name for each row.

**Return:** The chat display name (e.g. "Alice", "Family Group").

**macOS:** Try `get_attribute(row, 'AXTitle')`, fall back to `get_attribute(row, 'AXValue')`,
or find the first `AXStaticText` child and read its `AXValue`.

**Windows:** `row.CurrentName` property.

---

#### `get_row_badge_text(row) -> str | None`

**Called by:** `list_unread_chats.py` — the critical method for detecting unread status.

**Return values (must follow exactly):**
- `None` — no unread indicator at all. algo_a will skip this row.
- `""` (empty string) — muted chat with a red dot but no number. algo_a records `unread_count = -1`.
- `"3"`, `"99+"`, etc. — unread count text. algo_a parses the number.

**This is the most important method to get right.** WeChat has multiple badge styles:

| Visual | AX Structure (macOS) | UIA Structure (Windows) |
|--------|----------------------|------------------------|
| Red circle with number "3" | AXRow child with AXRole=AXStaticText containing "3" | Child element with Name="3" |
| Red dot (muted, no number) | AXRow child with badge role but **empty or no text** | Child element exists but Name is empty |
| No badge | No badge child at all | No badge child at all |

**macOS hints:** Iterate children of the row, look for a small AXStaticText or AXImage that
represents the badge. The badge element typically has a specific `AXDescription` or is positioned
at the top-right of the row. Compare its AXSize — badges are much smaller than the chat name element.

**Windows hints:** The badge may be a child Text element with a small bounding rectangle.
Use `element.CurrentBoundingRectangle` to distinguish it from the chat name Text element.

---

#### `click_row(row) -> None`

**Called by:** `click_into_chat.py` — to open a chat.

**macOS:** `perform_action(row, 'AXPress')`.

**Windows:** `row.GetCurrentPattern(UIA_InvokePatternId).Invoke()`, or
`row.GetCurrentPattern(UIA_SelectionItemPatternId).Select()`.

---

#### `wait_for_message_panel_ready(window) -> None`

**Called by:** `click_into_chat.py` — must block until the right-side message panel is loaded.

**Strategy (both platforms):**
1. Read the number of message elements (call `get_message_elements` internally).
2. Sleep 200ms.
3. Read again.
4. If the count matches for 2 consecutive reads, return.
5. Repeat up to 10 times, then return anyway (timeout).

This handles WeChat's async loading when switching chats.

---

#### `get_message_elements(window) -> list[Any]`

**Called by:** `read_messages_from_uitree.py` — to extract message data.

**What it must return:** Ordered list of message "bubble" elements in the active chat panel.
Include system messages (time separators, join notices) — algo_a classifies them.

**macOS approach:**
```
window_ref
  -> AXSplitGroup
    -> second AXScrollArea (message panel, NOT sidebar)
      -> AXList
        -> children  <-- return these
```

**Windows approach:**
```
automation_element
  -> FindAll(TreeScope_Descendants, ControlType=List)  [get the second/right List]
    -> FindAll(TreeScope_Children, TrueCondition)  <-- return these
```

**Caution:** The window has TWO list areas (sidebar + messages). Make sure you pick the right one.
On macOS, the sidebar is the first AXScrollArea child of AXSplitGroup, the message panel is the second.

---

#### `scroll_messages(window, direction) -> None`

**Called by:** `scroll_chat_to_bottom.py` — scrolls the message panel.

Same implementation pattern as `scroll_sidebar` but targeting the message panel's scroll area.

---

#### `get_message_scroll_position(window) -> float`

**Called by:** `scroll_chat_to_bottom.py` — to detect when scrolling is done.

**Return:** A float from 0.0 (fully scrolled up) to 1.0 (fully scrolled down).

**macOS:** Find the message AXScrollArea, find its vertical AXScrollBar child, read `AXValue`.

**Windows:** Get ScrollPattern from message List, read `VerticalScrollPercent / 100.0`.

---

#### `get_element_role(element) -> str`

**Called by:** `read_messages_from_uitree.py` — to classify message types.

**macOS:** `get_attribute(element, 'AXRole')`. Returns strings like `"AXStaticText"`, `"AXImage"`, etc.

**Windows:** Map `element.CurrentControlType` to macOS-compatible role strings:
- `UIA_TextControlTypeId` → `"AXStaticText"`
- `UIA_ImageControlTypeId` → `"AXImage"`
- `UIA_HyperlinkControlTypeId` → `"AXLink"`
- Everything else → `"AXGroup"`

**Important:** algo_a uses macOS-style role names internally. The Windows driver MUST map to these names.

---

#### `get_element_text(element) -> str | None`

**Called by:** `read_messages_from_uitree.py` — to extract text content from elements.

**macOS:** `get_attribute(element, 'AXValue')` or `get_attribute(element, 'AXTitle')`.
Return whichever is non-empty, preferring AXValue.

**Windows:** `element.CurrentName`, or get `ValuePattern` and read `CurrentValue`.

---

#### `get_element_children(element) -> list[Any]`

**Called by:** `read_messages_from_uitree.py` — to walk the element subtree.

**macOS:** `get_attribute(element, 'AXChildren')` or `[]` if None.

**Windows:** `element.FindAll(TreeScope_Children, TrueCondition)`.

---

## How to Verify Your Implementation

### Quick Smoke Test

```python
# test_driver.py (run from project root)
import sys
if sys.platform == "darwin":
    from platform_mac import create_driver
else:
    from platform_win import create_driver

driver = create_driver()

# 1. Permissions
driver.ensure_permissions()
print("✓ permissions OK")

# 2. Find window (WeChat must be open)
window = driver.find_wechat_window("WeChat")
print(f"✓ window found: {window}")

# 3. Sidebar rows
rows = driver.get_sidebar_rows(window)
print(f"✓ sidebar rows: {len(rows)}")
for row in rows[:5]:
    name = driver.get_row_name(row)
    badge = driver.get_row_badge_text(row)
    print(f"  {name}: badge={badge!r}")

# 4. Click first row with a badge
for row in rows:
    if driver.get_row_badge_text(row) is not None:
        name = driver.get_row_name(row)
        print(f"✓ clicking into: {name}")
        driver.click_row(row)
        driver.wait_for_message_panel_ready(window)
        break

# 5. Message elements
elements = driver.get_message_elements(window)
print(f"✓ message elements: {len(elements)}")
for el in elements[:5]:
    role = driver.get_element_role(el)
    text = driver.get_element_text(el)
    print(f"  role={role}, text={text!r}")

# 6. Scroll position
pos = driver.get_message_scroll_position(window)
print(f"✓ scroll position: {pos}")
```

### Full Pipeline Test

Once all driver methods work, run the full pipeline:

```bash
# Make sure config/config.json exists (copy from config.json.example)
python3 -c "
from config import load_config
from algo_a import run_pipeline_a

config = load_config('config/config.json')
paths = run_pipeline_a(config)
print(f'Wrote {len(paths)} files: {paths}')
"
```

Check the output JSON files in `output/` to verify messages are correctly extracted.

---

## Common Pitfalls

### macOS

1. **Accessibility permission caching.** After granting permission in System Preferences,
   you may need to restart the terminal or the Python process for `AXIsProcessTrusted()` to return True.

2. **Two scroll areas.** `AXSplitGroup` contains the sidebar ScrollArea first (left) and the
   message ScrollArea second (right). Don't mix them up.

3. **AXRow vs AXCell.** Depending on WeChat version, sidebar items might be AXRow or AXCell.
   Check both.

4. **Badge detection.** The badge element may not be a direct child of the row — it could be
   nested inside an AXGroup. Recursively search within each row.

5. **Stale AXUIElement refs.** If the user switches chats or scrolls while your code runs,
   previously captured element refs may become invalid. If `AXUIElementCopyAttributeValue`
   returns an error, skip that element gracefully.

### Windows

1. **COM initialization.** Call `comtypes.CoInitialize()` at the start of your thread if not
   on the main thread.

2. **Two List controls.** The window has a sidebar List and a message List. Use bounding rectangle
   comparison or child index to pick the correct one.

3. **Role mapping.** algo_a uses macOS-style role names (`AXStaticText`, `AXImage`, `AXLink`).
   Your `get_element_role` MUST map UIA ControlType IDs to these strings. If you skip this mapping
   algo_a will misclassify every message.

4. **Invoke vs SelectionItem.** Some WeChat ListItems support InvokePattern, others only
   SelectionItemPattern. Try Invoke first, fall back to SelectionItem.

5. **ScrollPattern availability.** Not all List elements support ScrollPattern. If it's not
   available, fall back to sending scroll wheel input via `SendInput`.

---

## File-by-File Checklist

### platform_mac/ developer

- [ ] `grant_permissions.py` — implement `check_accessibility_permission`, `request_accessibility_permission`, `ensure_permissions`
- [ ] `find_wechat_window.py` — implement `find_wechat_window`, return populated `WechatWindow`
- [ ] `ui_tree_reader.py` — implement `get_children`, `get_attribute`, `find_elements_by_role`, `perform_action`
- [ ] `driver.py` — implement all 14 methods of `MacDriver`
- [ ] Run smoke test above
- [ ] Run full pipeline test

### platform_win/ developer

- [ ] `grant_permissions.py` — implement `check_admin_if_needed`, `ensure_permissions`
- [ ] `find_wechat_window.py` — implement `find_wechat_window`, return populated `WechatWindow`
- [ ] `ui_tree_reader.py` — implement `get_children`, `get_attribute`, `find_elements_by_control_type`, `perform_invoke`, `perform_scroll`
- [ ] `driver.py` — implement all 14 methods of `WinDriver`
- [ ] Run smoke test above
- [ ] Run full pipeline test

---

## Reference: PlatformDriver Interface (source of truth)

See `shared/platform_api.py` for the full Protocol definition with type signatures.
Your driver class does NOT need to explicitly inherit from `PlatformDriver` — Python's
structural typing (Protocol + `@runtime_checkable`) validates conformance at runtime.

But the method names and signatures **must match exactly**.
