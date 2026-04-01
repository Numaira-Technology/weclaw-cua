# WeClaw

OpenClaw skill for extracting unread WeChat messages and generating customized reports.

## How It Works

1. A **platform layer** (`platform_mac/` or `platform_win/`) interfaces with the OS to locate the WeChat window and read its UI tree.
2. **algo_a** uses the platform layer to find unread chats, scroll through messages, and extract structured message data into JSON files.
3. **algo_b** loads those JSON files, combines them with a user-customized prompt, and calls an LLM to generate a report.

Delivery channels (Telegram, Feishu, etc.) are handled by OpenClaw, not this repo.

### OpenClaw packaging

- Skill source: `openclaw_skill/weclaw/SKILL.md` (AgentSkills / OpenClaw frontmatter).
- Host entry writes **`last_run.json`** in your configured `output_dir` after each `./run.sh` (paths to message JSON, ok/error for cron and agents).
- Install into the active workspace `skills/weclaw/`:

  ```bash
  ./scripts/install_openclaw_skill.sh
  ```

  Override workspace root with `OPENCLAW_WORKSPACE` if needed; when `openclaw` is on `PATH`, the script defaults to the `workspaceDir` reported by `openclaw skills list --json`.

- Verify packaging without running WeChat:

  ```bash
  python3 scripts/verify_openclaw_packaging.py
  ```

### Supported Platforms

| Platform | Directory | UI Automation API |
|----------|-----------|-------------------|
| macOS | `platform_mac/` | Accessibility API (AXUIElement via pyobjc) |
| Windows | `platform_win/` | UI Automation (IUIAutomation via comtypes) |

## Setup

### 环境与依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### macOS：分步调试（按顺序）

| Step | 脚本 | 说明 |
|------|------|------|
| 0 | `debug_mac_wechat_tree.py` | 可选，查看 AX 树 |
| 1 | `debug_mac_sidebar_unread.py` | 扫描侧栏未读 |
| 2 | `debug_mac_click_chat.py` | 点击进入会话 |
| 3 | `debug_mac_capture_chat.py` | 滚动截图并拼接长图 → `debug_outputs/capture/long_image.png` |
| 4 | 见下节 | 对长图做 LLM 提取 |

```bash
python3 scripts/debug_mac_wechat_tree.py
python3 scripts/debug_mac_sidebar_unread.py
python3 scripts/debug_mac_click_chat.py
python3 scripts/debug_mac_capture_chat.py
```

### 长图消息提取（OpenRouter）

需设置 `OPENROUTER_API_KEY`。`--chat` 填微信窗口**标题栏**里的会话名（仅作 LLM 上下文，不是路径），应与 Step 3 时打开的会话一致。默认读取项目内 `debug_outputs/capture/long_image.png`。

```bash
export OPENROUTER_API_KEY="sk-or-v1-你的key"
python3 scripts/debug_mac_read_visible_messages.py --chat "test-1"
```

常用可选参数：`--max-side` 缩小长图；`--chunk-max-height` 默认 2400（按高度自动分段，最多 `--chunk-max-count 10`）；`--chunk-max-height 0` 时用 `--chunks` 固定条数（1～10）。示例：

```bash
python3 -u scripts/debug_mac_read_visible_messages.py \
  --chat "会话名" \
  --max-side 256 \
  --model openrouter/google/gemini-3-flash-preview
```

### 单群闭环（滚动 + LLM + JSON）

需已 `export OPENROUTER_API_KEY`。第二条与 Step 4 同款 `read_long_image` 路径；分段参数见上节。

```bash
python3 -u scripts/debug_process_one_chat.py
python3 -u scripts/debug_process_one_chat.py --read-visible --chat "会话名"
```

### 多未读批量

`--read-visible` 与单群长图流程一致。

```bash
python3 scripts/debug_mac_multiple_chats.py
python3 scripts/debug_mac_multiple_chats.py --read-visible --max-chats 3 --max-side 768
```

**macOS:** Accessibility permission is required. On first run, the system will prompt you to grant access in System Preferences > Privacy & Security > Accessibility.

**Windows:** UI Automation generally works without extra permissions. If WeChat is running as admin, run the script elevated too (`Run as Administrator`).

### macOS: 滚动拼接 / 长图提取

长图拼接与 Step 4 消息提取已改为 **纯 NumPy**，不依赖 OpenCV。若你本地仍安装旧版脚本依赖的 `opencv-python` 且 `import cv2` 报错，可卸载或按官方说明重装 wheel；与本仓库当前主路径无关。

**OpenRouter / litellm**：请求前会设置 ASCII 的 `OR_APP_NAME` / `OR_SITE_URL` 并注入 `X-Title`，避免 `OR_APP_NAME` 含中文导致 `ascii codec can't encode`。长图解析失败时仍会尽量保留 `long_image.png`（拼接阶段已写入；LLM 失败时再尝试写盘）。

**长图送 LLM 分段**：默认按 `chunk_max_strip_height_px`（如 2400px）估算竖向条数，不超过 `chunk_max_count`（默认 10）。拼接接缝处的重复消息由 prompt、分段合并与后处理去重共同抑制。

## Usage

```bash
./run.sh                       
```

## Directory Structure

```
weclaw/
├── run.sh                              # one-command entry point (runs scripts/run_full_pipeline.py)
├── openclaw_skill/weclaw/SKILL.md      # OpenClaw / AgentSkills skill
├── scripts/install_openclaw_skill.sh   # copy skill into OpenClaw workspace skills/
├── scripts/run_full_pipeline.py        # algo_a + algo_b + last_run.json
├── scripts/verify_openclaw_packaging.py
├── requirements.txt
│
├── config/
│   ├── __init__.py
│   ├── weclaw_config.py                # WeclawConfig dataclass + load_config()
│   └── config.json.example
│
├── shared/                             # cross-cutting utilities
│   ├── __init__.py
│   ├── platform_api.py               # PlatformDriver Protocol (interface contract)
│   ├── llm_client.py                  # thin OpenRouter API wrapper
│   └── message_schema.py             # Message dataclass + serialization
│
├── platform_mac/                       # macOS platform layer (implements PlatformDriver)
│   ├── __init__.py                    # exports create_driver()
│   ├── driver.py                     # MacDriver class — all 14 methods to implement
│   ├── grant_permissions.py           # check/prompt macOS Accessibility permission
│   ├── find_wechat_window.py          # locate WeChat window, return WechatWindow
│   └── ui_tree_reader.py             # generic AXUIElement tree traversal helpers
│
├── platform_win/                       # Windows platform layer (implements PlatformDriver)
│   ├── __init__.py                    # exports create_driver()
│   ├── driver.py                     # WinDriver class — all 14 methods to implement
│   ├── grant_permissions.py           # check Windows prerequisites (admin, platform)
│   ├── find_wechat_window.py          # locate WeChat window via UI Automation
│   └── ui_tree_reader.py             # generic IUIAutomation tree traversal helpers
│
├── algo_a/                             # message collection (DONE)
│   ├── __init__.py
│   ├── pipeline_a.py                  # orchestrate: auto-detect platform, run collection
│   ├── list_unread_chats.py           # scan sidebar for unread badges (scrolls if needed)
│   ├── click_into_chat.py            # click sidebar row + wait for panel ready
│   ├── scroll_chat_to_bottom.py      # scroll message panel to bottom
│   ├── read_messages_from_uitree.py  # extract + classify messages from UI tree
│   ├── write_messages_json.py         # write messages to JSON file
│   ├── TESTING.md                    # test plan with edge cases
│   └── DEVGUIDE.md                   # instructions for platform developers
│
├── algo_b/                             # report generation
│   ├── __init__.py
│   ├── pipeline_b.py                  # orchestrate full report flow
│   ├── load_messages.py              # read JSON files from algo_a
│   ├── build_report_prompt.py        # combine messages + custom prompt
│   └── generate_report.py           # call LLM, return report
│
└── test/
    └── __init__.py
```

## Data Flow

```
algo_a                                          algo_b
┌─────────────────────────────────────┐        ┌──────────────────────────────┐
│ list_unread_chats                   │        │ load_messages                │
│         │                           │        │         │                    │
│         v                           │        │         v                    │
│ click_into_chat                     │        │ build_report_prompt          │
│         │                           │        │         │                    │
│         v                           │        │         v                    │
│ scroll_chat_to_bottom               │        │ generate_report              │
│         │                           │        │         │                    │
│         v                           │        │         v                    │
│ read_messages_from_uitree           │        │ report text (stdout/file)    │
│         │                           │        └──────────────────────────────┘
│         v                           │                  ^
│ write_messages_json ── JSON files ──┼──────────────────┘
│         │                           │
│    (loop next chat)                 │
└─────────────────────────────────────┘
```
