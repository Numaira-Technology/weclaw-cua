# WeClaw

OpenClaw skill for extracting unread WeChat messages and generating customized reports.

## How It Works

1. **algo_a** reads WeChat's UI tree (macOS Accessibility API) to find unread chats, scroll through messages, and extract structured message data into JSON files.
2. **algo_b** loads those JSON files, combines them with a user-customized prompt, and calls an LLM to generate a report.

Delivery channels (Telegram, Feishu, etc.) are handled by OpenClaw, not this repo.

## Setup

```bash
pip install -r requirements.txt
cp config/config.json.example config/config.json   # edit with your settings
cp .env.example .env                                # add your OPENROUTER_API_KEY
```

macOS Accessibility permission is required. On first run, the system will prompt you to grant access in System Preferences > Privacy & Security > Accessibility.

## Usage

```bash
./run.sh                        # uses config/config.json by default
./run.sh path/to/config.json    # custom config path
```

## Directory Structure

```
weclaw/
├── run.sh                              # one-command entry point
├── requirements.txt
├── .env.example
│
├── config/
│   ├── __init__.py
│   ├── weclaw_config.py                # WeclawConfig dataclass + load_config()
│   └── config.json.example
│
├── platform_mac/
│   ├── __init__.py
│   ├── grant_permissions.py            # check/prompt macOS Accessibility permission
│   ├── find_wechat_window.py           # locate WeChat window, return WechatWindow
│   └── ui_tree_reader.py              # generic AXUIElement tree traversal helpers
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

## Message JSON Schema

Each chat produces a JSON file in `output/`:

```json
[
  {
    "chat_name": "Group A",
    "sender": "Alice",
    "time": "14:32",
    "content": "Hello!",
    "type": "text"
  },
  {
    "chat_name": "Group A",
    "sender": "SYSTEM",
    "time": null,
    "content": "Bob joined the group",
    "type": "system"
  }
]
```

`type` is one of: `text`, `system`, `link_card`, `image`, `unsupported`.

## Config Schema

`config/config.json`:

```json
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["Group A", "Group B"],
  "report_custom_prompt": "Summarize key decisions and action items.",
  "openrouter_api_key": "sk-or-...",
  "llm_model": "google/gemini-3-flash-preview",
  "output_dir": "output"
}
```

## Parallel Work Boundaries (4 people)

| Person | Scope | Files |
|--------|-------|-------|
| A | macOS permissions + window | `platform_mac/grant_permissions.py`, `find_wechat_window.py`, `ui_tree_reader.py` |
| B | Sidebar scan + chat clicking | `algo_a/list_unread_chats.py`, `click_into_chat.py` |
| C | Message reading + writing | `algo_a/scroll_chat_to_bottom.py`, `read_messages_from_uitree.py`, `write_messages_json.py` |
| D | Report + config + integration | `algo_b/*`, `config/*`, `shared/*`, `run.sh`, `pipeline_a.py` |

Interfaces between modules: `WechatWindow` dataclass, `ChatInfo` dataclass, `Message` dicts, and JSON files on disk.
