# Platform Guide: Windows vs macOS

This document describes, in full detail, how the WeChat removal workflow operates on **Windows** and **macOS**. The two platforms follow fundamentally different strategies at every layer of the stack — screenshot capture, coordinate space, click delivery, and AI prompting — and must not share logic across those boundaries.

---

## Table of Contents

1. [Overview: Two Separate Strategies](#overview-two-separate-strategies)
2. [Launching the Right Mode](#launching-the-right-mode)
3. [Screenshot Capture](#screenshot-capture)
4. [Coordinate Systems](#coordinate-systems)
5. [Click Delivery](#click-delivery)
6. [AI Prompts and Vision Queries](#ai-prompts-and-vision-queries)
7. [Coordinate Conversion — Step by Step](#coordinate-conversion--step-by-step)
8. [Removal Flow — Scaffolding vs AX Tree](#removal-flow--scaffolding-vs-ax-tree)
9. [Screen Region Reference](#screen-region-reference)
10. [Config Files](#config-files)
11. [Adding Support for a New Display Resolution](#adding-support-for-a-new-display-resolution)
12. [Contamination Rules](#contamination-rules)

---

## Overview: Two Separate Strategies

| Concern | Windows | macOS |
|---|---|---|
| Screenshot sent to AI | **Cropped sub-image** (sidebar, panel, or dialog region) | **Full screen** at native Retina resolution |
| Click delivery | `pynput` — operates in **logical points** (same as screen pixels on 1:1 displays) | Quartz `CGEventPost` — operates in **logical points** (via `_get_retina_scale()` conversion from physical px) |
| Button finding | **Hard-coded screen coordinates** from `computer_windows.yaml` (scaffolding) | **Vision queries** (`mac_find_*_prompt`) — AI locates buttons in the full screenshot |
| AI coordinate space | 0-1000 **normalized** against the cropped sub-image dimensions | 0-1000 **normalized** against the full physical-pixel screenshot |
| Prompt wording | Mentions crop dimensions, gives pixel-spacing hints | Mentions "complete desktop screenshot", no spacing hints |
| `parse_height` / `reader_height` | Crop height (1440 px) | Physical screen height (e.g., 1964 px on a 16" MacBook Pro) |

---

## Launching the Right Mode

### From the Control Panel

Check the **"Running on Mac"** checkbox in the System Control card before clicking **Start System**. The checkbox state is saved in `artifacts/panel_state.json` (`force_mac_mode`) and persists across restarts.

When the system starts, the control panel passes `--mac` to the workflow backend if either condition is true:

```python
use_mac = self.state.force_mac_mode or sys.platform == "darwin"
if use_mac:
    cmd.append("--mac")
```

### From the command line

```bash
# Windows
python -m workflow.run_wechat_removal --step-mode

# macOS
python -m workflow.run_wechat_removal --step-mode --mac
```

The `--mac` flag causes `orchestrate_step_mode` to load `config/computer_mac.yaml` instead of `config/computer_windows.yaml`, which sets `os_type: macos` on the `ComputerSettings` object. Every downstream branch is gated on `computer_settings.os_type`.

---

## Screenshot Capture

### Windows

The computer server captures a full-resolution screenshot via `PIL.ImageGrab.grab()` and, on Windows, this returns logical pixels (identical to physical pixels on a non-HiDPI display). The workflow then **crops** the full screenshot to a small sub-region before sending it to the AI:

```
Full screenshot (2560×1440)
        │
        ▼  crop_region.crop_image(bytes)
Cropped image (e.g., 218×1440 for the chat list sidebar)
        │
        ▼
Sent to LLM
```

The crop reduces token usage and upload time, and lets the AI focus on the relevant UI area.

### macOS

`vendor/computer-server/computer_server/handlers/macos.py` captures via `PIL.ImageGrab.grab()` with **no resizing or cropping** applied:

```python
async def screenshot(self) -> Dict[str, Any]:
    screenshot = ImageGrab.grab()
    # No max_width cap — returns native Retina resolution (e.g. 3024×1964)
    buffered = BytesIO()
    screenshot.save(buffered, format="PNG", optimize=True)
    ...
```

On a 16" MacBook Pro (3024×1964 physical pixels), the image sent to the AI is the full 3024×1964 PNG. The AI is instructed to locate the chat list within the full screenshot rather than receiving a pre-cropped view.

The actual image dimensions are confirmed at startup by `_calibrate_scale()` in `StepModeRunner`, which takes a test screenshot and compares it to the values in `computer_mac.yaml`. A mismatch logs a warning and prompts you to update the config.

---

## Coordinate Systems

### Windows

Three coordinate spaces are in play, and `CropRegion` in `crop_utils.py` converts between them:

```
NORMALIZED (0–1000)          CROP (pixels)              SCREEN (pixels)
   from AI response    ──▶   within sub-image    ──▶   absolute on display
                             ×(width/1000)              + x_start / y_start
                             ×(height/1000)
```

- **SCREEN** coordinates are absolute pixels on the 2560×1440 display. This is what `pynput` receives.
- **CROP** coordinates are pixels measured from the top-left of a cropped sub-image.
- **NORMALIZED** coordinates are the 0–1000 scale values the AI returns. They are always relative to whichever image the AI saw (the crop, in the Windows case).

Conversion:

```python
# normalized_to_screen_coords() in CropRegion
crop_x = int((normalized_x / 1000.0) * self.width)
crop_y = int((normalized_y / 1000.0) * self.height)
screen_x = crop_x + self.x_start
screen_y = crop_y + self.y_start
```

Example (MEMBER_SELECT_REGION, x: 925–1630, y: 425–970):

```
AI returns: normalized (100, 300)
→ crop_x  = 100/1000 × 705  = 70
→ crop_y  = 300/1000 × 545  = 163
→ screen_x = 70  + 925 = 995
→ screen_y = 163 + 425 = 588
→ pynput clicks (995, 588)
```

### macOS

There are only **two** logical coordinate spaces on Mac — NORMALIZED and PHYSICAL PIXELS — because the AI always sees the full screenshot. The conversion to Quartz logical points happens transparently at the click boundary:

```
NORMALIZED (0–1000)              PHYSICAL PIXELS                 QUARTZ LOGICAL POINTS
   from AI response    ──▶       click target computation  ──▶   CGEventPost destination
                         × (img_w or img_h / 1000)                  ÷ _get_retina_scale()
                                                                     (e.g. ÷ 2.0 on Retina)
```

No crop-to-screen offset is needed. The conversion in `_remove_suspect_in_session`:

```python
img_x = round(click_x / 1000.0 * self._img_w)   # physical px
img_y = round(click_y / 1000.0 * self._img_h)   # physical px
screen_x, screen_y = self._to_logical(img_x, img_y)
# _to_logical is a pass-through: return img_x, img_y
# → left_click(screen_x, screen_y) divides by scale in macos.py before CGEventPost
```

`self._img_w` and `self._img_h` are the actual pixel dimensions of the screenshot captured by `_calibrate_scale()` at startup (e.g., 3024×1964). They are also updated on the first successful vision query if `_calibrate_scale()` was skipped.

For the `parse_classification` step, the AI returns a `y` value in 0–1000 space against the full screen height:

```python
pixel_y = int((normalized_y / 1000.0) * image_height)
# image_height = self._img_h (e.g. 1964) or computer_settings.screen_height as fallback
```

The resulting `pixel_y` is stored in `GroupThread.y` and used later as the direct physical-pixel click target. When passed to `left_click`, `macos.py` divides by the retina scale before `CGEventPost`.

---

## Click Delivery

### Windows — pynput

`pynput.mouse.Controller` is used for all clicks. On Windows, pynput coordinates are logical pixels, which on a standard (non-HiDPI) 2560×1440 monitor are identical to physical pixels.

Scaffolding clicks read hardcoded positions from `ComputerSettings`:

```python
x, y = settings.wechat_three_dots   # e.g. (2525, 48) from computer_windows.yaml
await computer.interface.left_click(x, y)
```

Vision-guided clicks use `CropRegion.normalized_to_screen_coords()` to convert AI output to screen pixels, then call `left_click`.

### macOS — Quartz CGEventPost + Retina scale correction

`pynput` is **not** used for clicking on macOS. All clicks go through Apple's Quartz CoreGraphics framework via `CGEventPost`.

**Critical detail — coordinate spaces on a Retina display:**

| API | Coordinate space | Example (16" MBP) |
|---|---|---|
| `PIL.ImageGrab.grab()` | Physical pixels (full Retina buffer) | 3024×1964 |
| `CGEventPost` / `CGDisplayBounds` / AX API | **Logical points** (OS display scale) | 1512×982 |
| Scale factor | physical / logical | 2.0× |

Because the screenshot the AI sees is 3024×1964 but `CGEventPost` expects 1512×982, all incoming physical-pixel coordinates must be divided by the retina scale factor before posting.

This is handled in `vendor/computer-server/computer_server/handlers/macos.py` by `_get_retina_scale()`, which computes the ratio at runtime by comparing `ImageGrab.grab().width` (physical) to `CGDisplayPixelsWide()` (logical). The result is cached after the first call:

```python
def _get_retina_scale() -> float:
    logical_w = CGDisplayPixelsWide(CGMainDisplayID())   # e.g. 1512
    physical_w = ImageGrab.grab().width                   # e.g. 3024
    return physical_w / logical_w                         # → 2.0
```

Every click method (`left_click`, `right_click`, `double_click`) divides the incoming coords before posting:

```python
scale = _get_retina_scale()           # 2.0 on Retina
pos = (x / scale, y / scale)          # 3024 physical px → 1512 logical pts
CGEventPost(kCGHIDEventTap, ...)
```

This means the rest of the codebase (prompts, parsing, `_MACOS_REGIONS`) can all work in physical pixel space, and the scale correction happens transparently at the final click boundary.

**Important note — WeChat has no AX tree:** WeChat Mac uses a web-based Electron/flue framework that renders its entire UI in a WebView. The macOS Accessibility API (`kAXPositionAttribute`, `AXButton`, etc.) returns **zero buttons and zero windows** for WeChat's main interface — only menu bar items are exposed. This means `ax_clicks.py` (which was the original Mac click strategy) cannot find any WeChat UI elements.

The current Mac approach for removal buttons is therefore **vision-based**: each button (three-dots, minus, confirm) is located by sending the full screenshot to the AI with a prompt asking for its normalized coordinates, then clicking at those coordinates.

**Two-path summary (updated):**

| Click source | Coordinate space | Method used | Scale applied? |
|---|---|---|---|
| AI vision output (normalized) | Physical pixels after `÷ 1000 × img_w/h` | `left_click(x, y)` | Yes — `÷ _get_retina_scale()` |
| AX tree bbox (if ever used) | Logical points from `kAXPositionAttribute` | `left_click_logical(x, y)` | No — already in point space |

**TuriX comparison:** TuriX's `actions.py` uses the same `CGEventPost` approach but derives the screen size from `CGDisplayPixelsWide` (logical points) and expects the AI coordinates to already be in 0–1000 normalized space relative to a downscaled screenshot. Their `capture_screenshot()` downscales Retina captures by 2× before sending to the AI, so the AI's normalized output, when multiplied back by `CGDisplayPixelsWide`, lands in the logical point range — matching `CGEventPost`. Both approaches achieve the same result through different paths; ours avoids downscaling (preserves image quality for the AI) and handles the correction at the click boundary instead.

---

## AI Prompts and Vision Queries

All prompt functions and parsers accept an `os_type` argument and branch on it. The two paths are entirely separate strings — neither borrows from the other.

### Classification prompt

**Windows** — describes a 218×1440 cropped sidebar, gives pixel-spacing hints for Y coordinates:

```python
"这是微信会话列表的裁剪截图（宽218像素，高1440像素，仅显示左侧聊天列表栏）。"
"提示：第一个会话的头像中心大约在y=73，每个会话间隔约49。"
```

**macOS** — describes the full desktop screenshot, no spacing hints (the AI locates the sidebar itself):

```python
"这是完整的桌面截图。请找到左侧的微信会话列表栏。"
"对于每个会话，估算其头像中心点相对于整个截图高度的Y坐标（0-1000归一化值）。"
```

### Message reader prompt

**Windows** — gives pixel-spacing hints for the retry-y coordinate (chat list is cropped):

```python
"提示：第一个会话约在y=97，每个会话间隔约35"
```

**macOS** — describes coordinates against the full screen height, no spacing hints:

```python
"估算该会话头像中心相对于整个截图高度的Y坐标（0-1000归一化值，0=顶部，1000=底部）"
```

### Removal executor prompts

Every prompt function (`verify_panel_opened_prompt`, `find_minus_button_prompt`, `verify_panel_and_find_minus_prompt`, `verify_member_dialog_opened_prompt`, `select_user_for_removal_prompt`, `verify_removal_prompt`) has separate `if os_type == "macos": ... else: ...` branches.

**Windows** prompts mention the specific crop dimensions (e.g., "宽260像素，高1440像素") and calibrate the AI to a narrow panel crop.

**macOS** prompts tell the AI it is looking at a full screenshot and to locate the target UI element within the complete image.

### Vision query routing

`_vision_query()` in `StepModeRunner` is the single dispatch point:

```python
async def _vision_query(self, prompt, task_label, region, model):
    if self.is_mac:
        # Full screenshot — region argument is ignored
        return await run_vision_query(self.computer, model, prompt, ...)
    # Windows — crop to region before sending
    return await run_cropped_vision_query(self.computer, model, prompt, ..., region)
```

The `region` argument is passed through on every call but **only used on Windows**. On Mac, `run_vision_query` sends the raw full-screen PNG with no cropping.

---

## Coordinate Conversion — Step by Step

### Windows: classify → click chat

```
1. AI sees: 218×1440 crop of chat list sidebar
2. AI returns: {"threads": [{"name": "群A", "y": 73, ...}, ...]}
3. parse_classification(text, image_height=1440):
       pixel_y = int(73/1000 * 1440) = 105
       → GroupThread(name="群A", y=105)
4. handle_read_messages:
       regions = get_regions("windows")   # chat_list: x=58–276
       click_x, screen_y = regions.chat_list.to_screen_coords(
           regions.chat_list.width // 2,   # centre of 218px strip = 109
           105,                             # crop_y from step 3
       )
       # screen_x = 109 + 58 = 167
       # screen_y = 105 + 0  = 105
5. pynput clicks (167, 105) on screen
```

### macOS: classify → click chat

```
1. AI sees: 3024×1964 full screenshot (physical pixels)
2. AI returns: {"threads": [{"name": "群A", "y": 54, ...}, ...]}
3. parse_classification(text, image_height=1964):
       pixel_y = int(54/1000 * 1964) = 106  (physical px)
       → GroupThread(name="群A", y=106)
4. handle_read_messages:
       regions = get_regions("macos")   # chat_list: x=70–310 physical px
       img_x = (70 + 310) // 2 = 190   # centre of Mac chat list column (physical px)
       click_x, screen_y = _to_logical(190, 106)   # pass-through: (190, 106)
5. left_click(190, 106) → macos.py scales by ÷2 → CGEventPost at (95, 53) logical pts ✓
```

### Windows: remove user

```
1. AI sees: 705×545 crop of member-select dialog
2. AI returns: {"user_found": true, "click_x": 100, "click_y": 300}
3. regions.member_select.normalized_to_screen_coords(100, 300):
       crop_x = 100/1000 * 705 = 70
       crop_y = 300/1000 * 545 = 163
       screen_x = 70 + 925 = 995
       screen_y = 163 + 425 = 588
4. pynput clicks (995, 588)
```

### macOS: remove user

```
1. AI sees: 3024×1964 full screenshot (physical pixels)
2. AI returns: {"user_found": true, "click_x": 570, "click_y": 380}
3. img_x = round(570/1000 * 3024) = 1724  (physical px)
   img_y = round(380/1000 * 1964) = 746   (physical px)
   screen_x, screen_y = _to_logical(1724, 746)  # pass-through
4. left_click(1724, 746) → macos.py: scale=2.0 → CGEventPost at (862, 373) logical pts ✓
```

---

## Removal Flow — Scaffolding vs AX Tree

The removal process (`_remove_suspect_in_session`) has two completely different implementations for the button-clicking phase.

### Windows — Scaffolding

Every button position is read from `computer_windows.yaml`:

| Button | Config key | Default position |
|---|---|---|
| Three dots (group info) | `wechat_three_dots_x / y` | (2525, 48) |
| Minus (enter removal mode) | `wechat_minus_button_x / y` | (2525, 200) |
| 移出 confirm | `wechat_delete_button_x / y` | (1345, 920) |

Flow:

```
[scaffolding] click three dots
       │
       ▼
[vision, heavy model] verify_panel_and_find_minus_prompt
  ← Returns: panel_opened, button_found, click_x, click_y
       │
       ▼  (normalized → screen via member_panel region)
[click] minus button at calculated position
       │
       ▼
[vision, fast model] verify_member_dialog_opened_prompt
       │
       ▼
[vision, heavy model] select_user_for_removal_prompt
  ← Returns: user_found, click_x, click_y
       │
       ▼  (normalized → screen via member_select region)
[click] user checkbox
       │
       ▼
[scaffolding] click 移出 confirm at (1345, 920)
       │
       ▼
[vision, fast model] verify_removal_prompt
```

### macOS — Vision-Based Button Finding

WeChat Mac uses a web-based Electron/flue framework — its UI is rendered inside a WebView and the macOS Accessibility API exposes **zero AXButton or AXWindow elements** for WeChat's interface (only menu bar items are visible in the AX tree). All button clicks therefore use vision queries on the full screenshot:

```
[vision, heavy model] mac_find_three_dots_prompt
  (full screenshot — AI returns normalized click coords for ⋯ button)
       │
       ▼  (normalized × img_w / img_h → physical pixels → left_click → ÷ scale → CGEventPost)
[click] three-dots button
       │
       ▼
[vision, heavy model] mac_find_minus_button_prompt
  (full screenshot — AI returns normalized click coords for − button)
       │
       ▼  (same conversion)
[click] minus button
       │
       ▼
[vision, fast model] verify_member_dialog_opened_prompt
  (full screenshot)
       │
       ▼
[vision, heavy model] select_user_for_removal_prompt
  (full screenshot)
  ← Returns: user_found, click_x, click_y (normalized against full screen)
       │
       ▼  (normalized × img_w / img_h → physical pixels → left_click → ÷ scale → CGEventPost)
[click] user checkbox
       │
       ▼
[vision, heavy model] mac_find_confirm_removal_prompt
  (full screenshot — AI returns normalized click coords for 移出 button)
       │
       ▼  (same conversion)
[click] confirm / 移出 button
       │
       ▼
[vision, fast model] verify_removal_prompt
  (full screenshot)
```

All vision prompts and parsers are in `modules/removal_executor.py`. The `mac_find_*_prompt` functions return `{"button_found": true, "click_x": N, "click_y": N}` parsed by `parse_mac_button_response()`.

---

## Screen Region Reference

Regions are defined in `modules/crop_utils.py` via `get_regions(os_type)`. All values are in the screen's native pixel space for that platform.

### Windows (2560×1440)

| Region | x range | y range | Size | Purpose |
|---|---|---|---|---|
| `chat_list` | 58–276 | 0–1440 | 218×1440 | Thread classification, click-to-open chat |
| `member_panel` | 2300–2560 | 0–1440 | 260×1440 | Panel/removal verification |
| `member_select` | 925–1630 | 425–970 | 705×545 | Member-selection dialog |

These are cropped from the full screenshot and sent to the AI.

### macOS (3024×1964 on a 16" MacBook Pro)

| Region | x range | y range | Size | Purpose |
|---|---|---|---|---|
| `chat_list` | 70–310 | 0–1964 | 240×1964 | Used only to compute x centre for clicking |
| `member_panel` | 1980–2560 | 0–1964 | 580×1964 | Passed to `_vision_query` but ignored (full screen used) |
| `member_select` | 830–1730 | 430–1050 | 900×620 | Passed to `_vision_query` but ignored (full screen used) |

On macOS, `_vision_query` always calls `run_vision_query` (full screen) and ignores the `region` argument. The macOS `CropRegion` values are kept for the `chat_list.x_start / x_end` x-centre calculation when clicking a thread — other than that, they are informational.

---

## Config Files

### `config/computer_windows.yaml`

```yaml
os_type: windows
screen_width: 2560
screen_height: 1440

# Hard-coded WeChat button positions (absolute screen pixels)
wechat_three_dots_x: 2525
wechat_three_dots_y: 48
wechat_minus_button_x: 2525
wechat_minus_button_y: 200
wechat_delete_button_x: 1345
wechat_delete_button_y: 920
```

If your Windows display is a different resolution or WeChat is positioned differently, adjust all six `wechat_*` values and the crop regions in `crop_utils.py`.

### `config/computer_mac.yaml`

```yaml
os_type: macos
screen_width: 3024    # Physical pixels — confirm with:
screen_height: 1964   # python3 -c "from PIL import ImageGrab; img=ImageGrab.grab(); print(img.width, img.height)"
```

No button positions are defined because Mac uses the AX tree. `screen_width` and `screen_height` must match the actual Retina capture dimensions. Run the one-liner above to verify. `_calibrate_scale()` logs a warning on startup if there is a mismatch.

---

## Adding Support for a New Display Resolution

### Changing Windows resolution

1. Update `screen_width` and `screen_height` in `config/computer_windows.yaml`.
2. Update the six `wechat_*` button coordinates to match the new layout.
3. Update `_WINDOWS_REGIONS` in `modules/crop_utils.py` with new crop boundaries.
4. Re-run the workflow and verify all six `[scaffolding] Clicking ...` log lines hit the intended targets.

### Changing macOS display

1. Run:
   ```bash
   python3 -c "from PIL import ImageGrab; img=ImageGrab.grab(); print(img.width, img.height)"
   ```
2. Update `screen_width` and `screen_height` in `config/computer_mac.yaml`.
3. Update `_MACOS_REGIONS.chat_list.x_start` and `x_end` in `modules/crop_utils.py` to match the chat-list column position on your screen (used for the x-centre click calculation).
4. No button coordinates need updating — the AX tree finds buttons by title regardless of position.

---

## Contamination Rules

The following rules are enforced in code and must not be broken:

1. **No hardcoded `1440` or `1964` in runtime paths.** Both `parse_height` and `reader_height` are derived from `self._img_h` (actual screenshot) or `self.computer_settings.screen_height` (config) — never from a literal constant.

2. **`parse_classification` and `parse_reader_response` have no default for `image_height` / `screen_height`.** Callers must always pass the correct value explicitly; the function will assert-fail rather than silently use the wrong platform's height.

3. **`control_panel_pro.py` does not default `parse_height` to 1440.** If `parse_height` is absent from the step result, an assertion fires so the user re-runs the classify step. Silent fallback to a Windows height while running on Mac is forbidden.

4. **`_vision_query` always sends the full screenshot on Mac.** The `region` argument exists for API symmetry but is unused on Mac. Never add cropping logic inside the `if self.is_mac:` branch.

4. **No button coordinates need updating for Mac** — vision queries find buttons dynamically; no fixed positions anywhere in the Mac path.

5. **`scaffolding_clicks.py`** dispatches by OS. On Mac, `click_three_dots` / `click_minus_button` / `click_delete_confirm` still exist for API compatibility, but the Mac removal flow in `_remove_suspect_in_session` bypasses them entirely and uses inline vision queries. On Windows, all three functions use hard-coded positions from settings.

6. **`ax_clicks.py` is kept for reference** but is not called by the current WeChat Mac workflow (WeChat's WebView-based UI has no accessible elements). It would be useful for other macOS native apps that expose a proper AX tree.

7. **`get_regions(os_type)` is the only way to obtain region constants.** The legacy bare-name aliases (`CHAT_LIST_REGION`, etc.) are Windows-only and exist for backward compatibility only; new code must not use them.
