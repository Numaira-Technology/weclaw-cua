# WeClaw

**Vision-based WeChat message capture and report generation from the command line.**

License: Apache-2.0 Platform

Capture chats · Generate reports · Search messages · Export · Statistics

---

## Highlights

- **Vision-based capture** — uses screenshots + vision LLM to extract messages, no database decryption needed
- **Cross-platform** — macOS (Accessibility API + Quartz) and Windows (UI Automation)
- **10 commands** — init, run, capture, report, sessions, history, search, export, stats, unread, new-messages
- **AI-first** — JSON output by default, designed for LLM agent tool calls
- **Fully local** — all UI automation runs on your machine, data never leaves unless you choose an LLM provider
- **Morning triage** — automatic report generation summarizing key decisions and action items

---

## How It Works

Unlike tools that decrypt WeChat's local SQLite databases, WeClaw uses a **pure vision approach**:

1. Locates the WeChat desktop window via OS-level APIs
2. Scans the sidebar for unread chats using vision AI
3. Clicks into each chat, scrolls through messages, captures screenshots
4. Stitches screenshots into long images (OpenCV-based template matching)
5. Sends stitched images to a vision LLM for structured message extraction
6. Post-processes and deduplicates extracted messages into clean JSON

This means WeClaw works with **any WeChat version** and requires **no key extraction or database access**.

---

## Installation

### pip (Recommended)

```bash
pip install weclaw
```

Requires Python >= 3.10.

### npm

```bash
npm install -g @anthropic-ai/weclaw
```

> Currently ships a **macOS arm64** binary. Other platforms can use the pip method.

**Update to the latest version:**

```bash
npm update -g @anthropic-ai/weclaw
```

### From Source

```bash
git clone https://github.com/anthropic-ai/weclaw.git
cd weclaw
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
pip install -e .
```

---

## Installation (For AI Agents)

Paste the following into Claude Code, Cursor, or any AI coding agent:

```
Help me install and configure WeClaw: pip install weclaw
```

Or for npm:

```
Help me install: npm install -g @anthropic-ai/weclaw
```

---

## Quick Start

### Step 1 — Initialize

```bash
weclaw init
```

This creates `config/config.json` from the template and verifies platform prerequisites.

#### macOS: Grant Accessibility Permission

Before running, make sure your terminal app has **Accessibility** access:

1. Open **System Settings > Privacy & Security > Accessibility**
2. Add your terminal app (Terminal, iTerm2, or your IDE's terminal)
3. Restart the terminal after enabling

#### Windows: Match Elevation

If WeChat is running as admin, run the script elevated too (`Run as Administrator`).

### Step 2 — Configure

Edit `config/config.json`:

```json
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["*"],
  "sidebar_unread_only": true,
  "report_custom_prompt": "Summarize key decisions and action items.",
  "openrouter_api_key": "sk-or-YOUR-KEY-HERE",
  "llm_model": "openai/gpt-4o",
  "output_dir": "output"
}
```

Set your API key either in the config or via environment variable:

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key"
```

### Step 3 — Use It

```bash
weclaw run                                   # full pipeline: capture + report
weclaw capture                               # capture only
weclaw report                                # report from existing captures
weclaw sessions                              # list captured chats
weclaw history "Group A" --limit 20          # view messages
weclaw search "deadline" --chat "Team"       # search
```

---

## Using with AI Agents

WeClaw is designed as an AI agent tool. All commands output structured JSON by default.

### Claude Code

Add to your project's `CLAUDE.md`:

```markdown
## WeClaw

You can use `weclaw` to capture and query my WeChat messages.

Common commands:
- `weclaw run` — capture unread chats + generate report
- `weclaw capture` — capture unread chats to JSON
- `weclaw sessions` — list captured chats
- `weclaw history "NAME" --limit 20 --format text` — view chat messages
- `weclaw search "KEYWORD" --chat "CHAT_NAME"` — search messages
- `weclaw stats "CHAT" --format text` — chat statistics
- `weclaw export "CHAT" --format markdown` — export chat
- `weclaw unread` — scan sidebar for unread chats
- `weclaw new-messages` — incremental new messages
- `weclaw report` — generate report from captures
```

Then you can ask Claude things like:

- "Capture my unread WeChat messages and summarize them"
- "Search for messages about the project deadline in the Team group"
- "Export the AI discussion group chat as markdown"

### Cursor / OpenClaw / MCP Integration

WeClaw works with any AI tool that can execute shell commands:

```bash
# Full pipeline
weclaw run --format text

# Capture only
weclaw capture

# Query captured data
weclaw sessions --limit 5
weclaw history "Alice" --limit 30 --format text
weclaw search "report" --limit 10

# Monitor for new messages
weclaw new-messages --format text
```

---

## Command Reference

### `init` — First-Time Setup

```bash
weclaw init                        # create config + verify permissions
weclaw init --force                # overwrite existing config
weclaw init --config-dir /path     # custom config directory
```

### `run` — Full Pipeline

```bash
weclaw run                         # capture + report (JSON)
weclaw run --format text           # human-readable output
```

### `capture` — Capture Messages

```bash
weclaw capture                     # capture unread chats
weclaw capture --format text       # human-readable output
```

### `report` — Generate Report

```bash
weclaw report                                    # from latest captures
weclaw report --input output/GroupA.json          # from specific files
weclaw report --format text                      # human-readable
```

### `sessions` — List Captured Chats

```bash
weclaw sessions                    # all captured chats (JSON)
weclaw sessions --limit 10        # last 10
weclaw sessions --format text     # human-readable
```

### `history` — View Chat Messages

```bash
weclaw history "Group A"                         # last 50 messages
weclaw history "Group A" --limit 100 --offset 50 # pagination
weclaw history "Alice" --type text               # text messages only
weclaw history "Alice" --format text             # human-readable
```

**Options:** `--limit`, `--offset`, `--type`, `--format`

### `search` — Search Messages

```bash
weclaw search "hello"                            # global search
weclaw search "hello" --chat "Alice"             # in specific chat
weclaw search "meeting" --chat "A" --chat "B"    # multiple chats
weclaw search "report" --type text               # text only
```

**Options:** `--chat` (repeatable), `--limit`, `--offset`, `--type`, `--format`

### `export` — Export Chat

```bash
weclaw export "Alice" --format markdown          # to stdout
weclaw export "Alice" --format txt --output chat.txt  # to file
weclaw export "Team" --limit 1000                # more messages
```

**Options:** `--format markdown|txt`, `--output`, `--limit`

### `stats` — Chat Statistics

```bash
weclaw stats "Group A"             # JSON stats
weclaw stats "Alice" --format text # human-readable
```

### `unread` — Scan for Unread Chats

```bash
weclaw unread                      # scan sidebar via vision AI
weclaw unread --limit 10           # at most 10
weclaw unread --format text        # human-readable
```

### `new-messages` — Incremental Messages

```bash
weclaw new-messages                # first: save state, return all
weclaw new-messages                # subsequent: only new since last
```

State saved at `<output_dir>/last_check.json`. Delete to reset.

---

## Message Types

The `--type` option (on `history` and `search`):

| Value       | Description                  |
|-------------|------------------------------|
| text        | Text messages                |
| system      | System messages              |
| link_card   | Links and shared content     |
| image       | Images                       |
| file        | File attachments             |
| recalled    | Recalled messages            |
| unsupported | Unsupported message types    |

---

## System Requirements

| Platform              | Status      | Notes                                          |
|-----------------------|-------------|------------------------------------------------|
| macOS (Apple Silicon) | Supported   | Requires Accessibility permission              |
| macOS (Intel)         | Supported   | Requires Accessibility permission              |
| Windows               | Supported   | Match elevation with WeChat if needed          |

- **Python** >= 3.10
- **WeChat Desktop** — any version (vision-based, no version dependency)
- **OpenRouter API key** — for vision LLM message extraction and report generation

---

## Configuration

### `config/config.json`

```json
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["*"],
  "sidebar_unread_only": true,
  "report_custom_prompt": "Summarize key decisions and action items.",
  "openrouter_api_key": "",
  "llm_model": "openai/gpt-4o",
  "output_dir": "output"
}
```

| Field                | Description                                                       |
|----------------------|-------------------------------------------------------------------|
| `wechat_app_name`    | Window title for WeChat (usually "WeChat")                        |
| `groups_to_monitor`  | `["*"]` = all groups, or list specific chat names                 |
| `sidebar_unread_only`| `true` = only process chats with unread badges                    |
| `report_custom_prompt`| Custom instructions for the LLM report                           |
| `openrouter_api_key` | API key (or use `OPENROUTER_API_KEY` env var)                     |
| `llm_model`          | LLM model identifier for report generation                       |
| `output_dir`         | Directory for output JSON files                                   |

---

## Architecture

```
weclaw/
├── weclaw_cli/                 # CLI layer (click commands)
│   ├── main.py                # CLI entry point
│   ├── context.py             # Config loading
│   ├── commands/              # All CLI commands
│   └── output/                # JSON/text formatter
│
├── algo_a/                     # Vision-based message capture
│   ├── pipeline_a_win.py     # Main pipeline (both platforms)
│   ├── capture_chat.py        # Screenshot scroll-capture engine
│   ├── extract_messages.py    # Vision LLM message extraction
│   └── ...                    # Sidebar scan, click, stitch, dedup
│
├── algo_b/                     # LLM report generation
│   ├── pipeline_b.py         # Report pipeline
│   ├── build_report_prompt.py # Prompt construction
│   └── generate_report.py    # LLM call
│
├── platform_mac/               # macOS platform layer
│   ├── driver.py              # Quartz screenshots + CGEvent
│   ├── mac_ai_driver.py       # Vision AI driver
│   └── ...                    # Window detection, OCR, stitching
│
├── platform_win/               # Windows platform layer
│   ├── driver.py              # Vision AI driver
│   └── ...                    # Window detection, UI Automation
│
├── shared/                     # Cross-cutting utilities
│   ├── platform_api.py        # PlatformDriver protocol
│   ├── message_schema.py      # Message dataclass
│   └── llm_client.py          # OpenRouter wrapper
│
├── npm/                        # npm binary distribution
│   ├── weclaw/                # Main npm package
│   ├── platforms/             # Per-platform binary packages
│   └── scripts/build.py      # PyInstaller build script
│
├── config/                     # Configuration
├── scripts/                    # Debug & utility scripts
├── pyproject.toml              # Python package config
├── entry.py                    # PyInstaller entry point
└── run.sh                      # Shell entry point
```

---

## Data Flow

```
weclaw run / weclaw capture
  │
  ├─ algo_a (vision capture)
  │   ├─ find WeChat window (OS API)
  │   ├─ scan sidebar for unread (vision AI)
  │   ├─ for each chat:
  │   │   ├─ click into chat
  │   │   ├─ scroll + capture screenshots
  │   │   ├─ stitch into long image
  │   │   ├─ vision LLM → structured JSON
  │   │   └─ post-process + dedup
  │   └─ write JSON files to output/
  │
  └─ algo_b (report generation)
      ├─ load message JSONs
      ├─ build report prompt
      ├─ call LLM
      └─ output report text
```

---

## License

Apache License 2.0

---

## Disclaimer

This project is a local UI automation tool for personal use only:

- **Read-only** — captures what is visible on screen, does not modify WeChat data
- **No database access** — uses pure vision, no decryption or memory scanning
- **No cloud transmission** — all automation runs locally; only LLM API calls leave your machine (to your configured provider)
- **Use at your own risk** — for personal learning and research purposes only
