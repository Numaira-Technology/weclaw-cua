# WeClaw

**Vision-based WeChat message capture and report generation from the command line.**

License: Apache-2.0 Platform

Capture chats · Generate reports · Search messages · Export · Statistics

---

## Highlights

- **Vision-based capture** — uses screenshots + vision LLM to extract messages, no database decryption needed
- **Cross-platform** — macOS (Accessibility API + Quartz) and Windows (UI Automation)
- **No API key required** — stepwise mode lets the calling agent handle all LLM calls
- **AI-first** — JSON output by default, designed for LLM agent tool calls
- **Fully local** — all UI automation runs on your machine, no data leaves your machine
- **13 commands** — init, run, capture, finalize, report, build-report-prompt, sessions, history, search, export, stats, unread, new-messages

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
pip install weclaw                 # core only (stepwise mode, no LLM deps)
pip install weclaw[llm]            # with built-in OpenRouter LLM support
pip install weclaw[macos]          # with macOS-specific dependencies
pip install weclaw[llm,macos]      # everything
```

Requires Python >= 3.10.

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

## Using with AI Agents (Stepwise Mode)

WeClaw is designed for AI agents. In **stepwise mode** (`--no-llm`), WeClaw handles
all UI automation while the agent handles all LLM calls. No API key needed.

### How Stepwise Mode Works

```
Agent                          WeClaw                        WeChat
  |                              |                              |
  |-- weclaw capture --no-llm -->|                              |
  |                              |-- screenshot, scroll ------->|
  |                              |-- stitch images              |
  |                              |<-- stitched images           |
  |<-- manifest.json + images ---|                              |
  |                              |                              |
  |  (agent reads manifest.json)                                |
  |  (for each task: send .png + .prompt.txt to own LLM)        |
  |  (write response to .response.txt)                          |
  |                              |                              |
  |-- weclaw finalize ---------> |                              |
  |<-- messages.json ----------- |                              |
  |                              |                              |
  |-- weclaw build-report-prompt |                              |
  |<-- prompt text --------------|                              |
  |  (agent sends prompt to own LLM, gets report)               |
```

### Step-by-Step for Agents

1. **Capture** (no LLM needed):

```bash
weclaw capture --no-llm --work-dir /tmp/weclaw_work
```

This outputs a `manifest.json` listing all pending vision tasks, along with `.png` images and `.prompt.txt` files.

2. **Process vision tasks** (agent's responsibility):

For each task in `manifest.json`:
- Read the `.png` image and `.prompt.txt`
- Send to the agent's own vision LLM
- Write the model response to `.response.txt`

3. **Finalize** (produce message JSON):

```bash
weclaw finalize --work-dir /tmp/weclaw_work
```

4. **Get report prompt** (agent calls own LLM for report):

```bash
weclaw build-report-prompt
```

### Claude Code / Cursor Configuration

Add to your `CLAUDE.md` or `.cursor/rules/`:

```markdown
## WeClaw

You can use `weclaw` to capture and query WeChat messages.

Stepwise workflow (you handle LLM calls):
1. `weclaw capture --no-llm` — capture screenshots, no LLM needed
2. Process each task in manifest.json with your vision model
3. `weclaw finalize --work-dir <dir>` — produce message JSON
4. `weclaw build-report-prompt` — get report prompt, call your own LLM

Query commands (work on captured data, no LLM needed):
- `weclaw sessions` — list captured chats
- `weclaw history "NAME" --limit 20 --format text` — view messages
- `weclaw search "KEYWORD" --chat "CHAT_NAME"` — search messages
- `weclaw stats "CHAT" --format text` — statistics
- `weclaw export "CHAT" --format markdown` — export chat
- `weclaw new-messages` — incremental new messages
```

### Direct Mode (Built-in LLM)

If you prefer WeClaw to handle LLM calls directly (requires OpenRouter API key):

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key"
weclaw run                    # capture + report in one step
weclaw capture                # capture only
weclaw report                 # report from existing captures
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
weclaw run                         # capture + report (JSON, requires API key)
weclaw run --no-llm                # stepwise: capture only, agent handles LLM
weclaw run --format text           # human-readable output
```

### `capture` — Capture Messages

```bash
weclaw capture                     # capture with built-in LLM
weclaw capture --no-llm            # stepwise: output images+prompts only
weclaw capture --no-llm --work-dir /tmp/w  # custom work directory
weclaw capture --format text       # human-readable output
```

### `finalize` — Process Agent Responses

```bash
weclaw finalize --work-dir /tmp/weclaw_work  # produce final JSON from agent responses
```

### `report` — Generate Report

```bash
weclaw report                                    # full report (requires API key)
weclaw report --prompt-only                      # output prompt only (no LLM call)
weclaw report --input output/GroupA.json          # from specific files
weclaw report --format text                      # human-readable
```

### `build-report-prompt` — Get Report Prompt

```bash
weclaw build-report-prompt                       # output prompt for agent's own LLM
weclaw build-report-prompt --input output/A.json # from specific files
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
│   ├── commands/              # All CLI commands (capture, finalize, report, etc.)
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
│   ├── vision_backend.py      # VisionBackend protocol (pluggable LLM interface)
│   ├── stepwise_backend.py    # StepwiseBackend (writes images+prompts for agent)
│   ├── vision_ai.py           # OpenRouterBackend (built-in LLM, optional)
│   ├── message_schema.py      # Message dataclass
│   └── llm_client.py          # OpenRouter text wrapper (optional)
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
