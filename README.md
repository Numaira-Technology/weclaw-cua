# WeClaw

OpenClaw skill for extracting unread WeChat messages and generating customized reports.

## How It Works

1. A **platform layer** (`platform_mac/` or `platform_win/`) interfaces with the OS to locate the WeChat window and read its UI tree.
2. **algo_a** uses the platform layer to find unread chats, scroll through messages, and extract structured message data into JSON files.
3. **algo_b** loads those JSON files, combines them with a user-customized prompt, and calls an LLM to generate a report.

Delivery channels (Telegram, Feishu, etc.) are handled by OpenClaw, not this repo.

### Supported Platforms

| Platform | Directory | UI Automation API |
|----------|-----------|-------------------|
| macOS | `platform_mac/` | Accessibility API (AXUIElement via pyobjc) |
| Windows | `platform_win/` | UI Automation (IUIAutomation via comtypes) |

## Setup

```bash
pip install -r requirements.txt
```

**macOS:** Accessibility permission is required. On first run, the system will prompt you to grant access in System Preferences > Privacy & Security > Accessibility.

**Windows:** UI Automation generally works without extra permissions. If WeChat is running as admin, run the script elevated too (`Run as Administrator`).

## Usage

```bash
./run.sh                       
```

## Directory Structure

```
weclaw/
├── run.sh                              # one-command entry point
├── requirements.txt
│
├── config/
│   ├── __init__.py
│   ├── weclaw_config.py                # WeclawConfig dataclass + load_config()
│   └── config.json.example
│
├── platform_mac/                          # macOS platform layer
│   ├── __init__.py
│   ├── grant_permissions.py            # check/prompt macOS Accessibility permission
│   ├── find_wechat_window.py           # locate WeChat window, return WechatWindow
│   └── ui_tree_reader.py              # generic AXUIElement tree traversal helpers
│
├── platform_win/                          # Windows platform layer
│   ├── __init__.py
│   ├── grant_permissions.py            # check Windows prerequisites (admin, platform)
│   ├── find_wechat_window.py           # locate WeChat window via UI Automation
│   └── ui_tree_reader.py              # generic IUIAutomation tree traversal helpers
│
├── algo_a/                             # message collection
│   ├── __init__.py
│   ├── pipeline_a.py                   # orchestrate full collection flow
│   ├── list_unread_chats.py            # scan sidebar for unread badges
│   ├── click_into_chat.py             # AXPress on a sidebar chat row
│   ├── scroll_chat_to_bottom.py       # scroll message panel to bottom
│   ├── read_messages_from_uitree.py   # extract messages from AX tree
│   └── write_messages_json.py          # write messages to JSON file
│
├── algo_b/                             # report generation
│   ├── __init__.py
│   ├── pipeline_b.py                   # orchestrate full report flow
│   ├── load_messages.py               # read JSON files from algo_a
│   ├── build_report_prompt.py         # combine messages + custom prompt
│   └── generate_report.py            # call LLM, return report
│
├── shared/
│   ├── __init__.py
│   ├── llm_client.py                  # thin OpenRouter API wrapper
│   └── message_schema.py             # Message dataclass + serialization
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
