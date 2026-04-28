# Installation Guide

**WeClaw-CUA** — vision-based WeChat message capture and report generation from the command line.

WeClaw-CUA uses screenshots and a vision LLM to read your WeChat messages. It does not decrypt any local databases, requires no WeChat version-specific hooks, and runs entirely on your machine.

---

## Table of Contents

- [System Requirements](#system-requirements)
- [CLI Installation](#cli-installation)
- [Quick Start](#quick-start)
- [Usage Modes](#usage-modes)
- [Command Reference](#command-reference)
- [Desktop App](#desktop-app)
- [License & Disclaimer](#license--disclaimer)

---

## System Requirements

| Requirement | Details |
|---|---|
| Python | >= 3.10 |
| Operating System | macOS (Apple Silicon or Intel) · Windows 10/11 |
| WeChat Desktop | Any version |
| LLM access | OpenClaw gateway (recommended) or OpenRouter API key |

> **Linux is not supported.** The capture pipeline relies on macOS Accessibility APIs (Quartz / CGEvent) and Windows UI Automation; there is no Linux equivalent.

---

## CLI Installation

### Step 1 — Install from PyPI

Create a virtual environment first (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows PowerShell
```

Then install:

```bash
# macOS
pip install "weclaw-cua[macos,llm]"

# Windows
pip install "weclaw-cua[llm]"

# Core only (stepwise mode, no built-in LLM calls)
pip install weclaw-cua
```

The PyPI project name `weclaw` is an **unrelated third-party package** — install `weclaw-cua` (with the `-cua` suffix).

Verify the installation:

```bash
weclaw-cua --version
```

After installation, `weclaw-cua` is available as a console command. The shorter alias `weclaw` also works.

> **For contributors:** to run from a local checkout, clone the repo and install in editable mode instead of installing from PyPI:
> ```bash
> git clone https://github.com/Numaira-Technology/weclaw-cua.git
> cd weclaw-cua
> python3 -m venv .venv
> ./.venv/bin/pip install -e ".[macos,llm]"   # macOS
> .venv\Scripts\pip install -e ".[llm]"        # Windows
> ```

### Step 2 — Grant platform permissions

**macOS — Accessibility**

WeClaw-CUA drives WeChat's UI via the macOS Accessibility API. Before running for the first time:

1. Open **System Settings → Privacy & Security → Accessibility**
2. Add your terminal application (Terminal, iTerm2, or your IDE's built-in terminal)
3. Restart the terminal after enabling

**Windows — Elevation**

If WeChat is running as Administrator, the script must also run with Administrator privileges. Right-click your terminal and choose **Run as administrator**.

---

## Quick Start

### Before You Start

Before the first run, make sure:

- WeChat Desktop is installed, open, and already logged in
- The WeChat window is visible on screen
- You are running commands from the project directory (or a subdirectory where `config/config.json` can be auto-discovered)
- On macOS, your terminal already has Accessibility permission
- On Windows, if WeChat is running as administrator, your terminal is elevated too

### 1. Initialize

```bash
weclaw-cua init
```

This creates `config/config.json` from the built-in template and verifies that platform prerequisites are met.

> **Config auto-discovery:** WeClaw-CUA walks up from the current directory looking for `config/config.json`. Run all subsequent commands from the same directory (or any subdirectory) and the config is found automatically. Set `WECLAW_CONFIG_PATH` or pass `--config <path>` only when running from a different working directory.

### 2. Configure

Open `config/config.json` and fill in your settings:

```json
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["*"],
  "sidebar_unread_only": true,
  "report_custom_prompt": "Summarize key decisions and action items.",
  "llm_provider": "openrouter",
  "openrouter_api_key": "",
  "openai_api_key": "",
  "llm_model": "openai/gpt-4o",
  "output_dir": "output"
}
```

Set `llm_provider` to `openrouter` or `openai`. Fill the matching key only when using built-in LLM mode. Leave keys empty if you run through OpenClaw gateway or stepwise mode.

| Field | Description |
|---|---|
| `wechat_app_name` | Window title of your WeChat app — usually `"WeChat"` for English locale or `"微信"` for Chinese locale |
| `groups_to_monitor` | `["*"]` monitors all chats (both group chats and direct messages); list specific names to filter |
| `sidebar_unread_only` | `true` = only process chats with unread badges |
| `report_custom_prompt` | Custom instruction appended to the LLM report prompt |
| `llm_provider` | Built-in LLM provider: `openrouter` or `openai` |
| `openrouter_api_key` | Your OpenRouter key (or use `OPENROUTER_API_KEY`) |
| `openai_api_key` | Your OpenAI key (or use `OPENAI_API_KEY`) |
| `llm_model` | LLM model ID for report generation; use provider-native names such as `gpt-4o` for OpenAI |
| `output_dir` | Directory where captured JSON files are written |

### 3. Run

```bash
# Recommended — via local OpenClaw gateway
weclaw-cua run --openclaw-gateway

# Fallback — built-in LLM mode
# Requires the matching API key for llm_provider
weclaw-cua run
```

---

## Usage Modes

### OpenClaw Gateway (Recommended)

If you already run a local [OpenClaw](https://openclaw.ai) gateway, WeClaw-CUA can route all LLM calls through it. No separate OpenRouter key needed inside WeClaw-CUA.

**One-time gateway setup**

Enable the OpenAI-compatible HTTP endpoint in `~/.openclaw/openclaw.json`:

```json5
{
  gateway: {
    http: {
      endpoints: {
        chatCompletions: { enabled: true },
      },
    },
  },
}
```

Restart the OpenClaw gateway, then verify:

```bash
curl -sS http://127.0.0.1:18789/v1/models \
  -H "Authorization: Bearer YOUR_GATEWAY_TOKEN"
```

A JSON response listing model IDs (e.g. `openclaw/default`) confirms the gateway is ready.

**Run**

```bash
weclaw-cua run --openclaw-gateway
```

WeClaw-CUA auto-discovers the gateway URL, token, and model from `~/.openclaw/openclaw.json`. You do not need to set any environment variables manually in most cases.

> If you run the command from outside the project directory (where `config/config.json` lives), set `WECLAW_CONFIG_PATH` or pass `--config <path>` to point to the config file explicitly.

Optional overrides:

```bash
# macOS
export OPENCLAW_GATEWAY_URL="http://127.0.0.1:18789/v1"
export OPENCLAW_API_KEY="YOUR_GATEWAY_TOKEN"
export OPENCLAW_MODEL="openclaw/default"
export OPENCLAW_BACKEND_MODEL="openrouter/google/gemini-2.5-flash"
```

```powershell
# Windows PowerShell
$env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789/v1"
$env:OPENCLAW_API_KEY = "YOUR_GATEWAY_TOKEN"
$env:OPENCLAW_MODEL = "openclaw/default"
$env:OPENCLAW_BACKEND_MODEL = "openrouter/google/gemini-2.5-flash"
```

---

### Built-In LLM Mode (Fallback / Testing)

Use this mode when you do not have a local OpenClaw gateway, or for debugging.

```bash
# macOS
export OPENROUTER_API_KEY="sk-or-v1-your-key"
export OPENAI_API_KEY="sk-your-openai-key"
weclaw-cua run          # capture + report in one step
weclaw-cua capture      # capture only
weclaw-cua report       # generate report from existing captures
```

```powershell
# Windows PowerShell
$env:OPENROUTER_API_KEY = "sk-or-v1-your-key"
$env:OPENAI_API_KEY = "sk-your-openai-key"
weclaw-cua run          # capture + report in one step
weclaw-cua capture      # capture only
weclaw-cua report       # generate report from existing captures
```

You can also put the key directly in `config/config.json` under `openrouter_api_key` or `openai_api_key`.

---

### Stepwise / AI Agent Mode

In stepwise mode (`--no-llm`), WeClaw-CUA handles all UI automation while your AI agent handles all LLM calls. No API key is required in WeClaw-CUA itself.

```
Agent                          WeClaw-CUA                    WeChat
  |                              |                              |
  |-- weclaw-cua capture --no-llm -->                           |
  |                              |-- screenshot, scroll ------->|
  |                              |-- stitch images              |
  |<-- manifest.json + images ---|                              |
  |                              |                              |
  |  (for each task in manifest.json:                           |
  |   send .png + .prompt.txt to your LLM                       |
  |   write response to .response.txt)                          |
  |                              |                              |
  |-- weclaw-cua finalize ------->                              |
  |<-- messages.json ------------|                              |
  |                              |                              |
  |-- weclaw-cua build-report-prompt                            |
  |<-- prompt text --------------|                              |
  |  (send prompt to your LLM, get report)                      |
```

**Step-by-step**

```bash
# 1. Capture (no LLM needed)
weclaw-cua capture --no-llm --work-dir ./weclaw_work

# 2. Your agent processes manifest.json:
#    read .png + .prompt.txt → call vision LLM → write .response.txt

# 3. Finalize: reads .response.txt files from --work-dir,
#    writes structured message JSON to output_dir (from config.json)
weclaw-cua finalize --work-dir ./weclaw_work

# 4. Get report prompt; reads all *.json from output_dir, call your own LLM
weclaw-cua build-report-prompt
```

**Claude / Cursor agent snippet** — add to your `CLAUDE.md` or `.cursor/rules/`:

```markdown
## WeClaw-CUA

Use `weclaw-cua` (alias: `weclaw`) to capture and query WeChat messages.

Stepwise workflow (you handle LLM calls):
1. `weclaw-cua capture --no-llm` — screenshots + stitched images, no LLM
2. Process each task in manifest.json with your vision model
3. `weclaw-cua finalize --work-dir <dir>` — produce messages.json
4. `weclaw-cua build-report-prompt` — get report prompt, call your LLM

Query commands (no LLM needed):
- `weclaw-cua sessions` — list captured chats
- `weclaw-cua history "NAME" --limit 20 --format text`
- `weclaw-cua search "KEYWORD" --chat "CHAT_NAME"`
- `weclaw-cua stats "CHAT" --format text`
- `weclaw-cua export "CHAT" --format markdown`
- `weclaw-cua new-messages`
```

---

## Command Reference

| Command | Description |
|---|---|
| `init` | First-time setup: create config file and verify platform permissions |
| `run` | Full pipeline: capture unread messages and generate a report |
| `capture` | Vision-capture unread messages only (no report) |
| `report` | Generate an LLM report from existing captured JSON files |
| `build-report-prompt` | Output the report prompt for your own LLM to process |
| `finalize` | Process agent `.response.txt` files into final `messages.json` (`--work-dir` required) |
| `sessions` | List all captured chat sessions |
| `history` | View messages in a specific chat |
| `search` | Search captured messages by keyword |
| `export` | Export a chat session to Markdown or plain text |
| `stats` | Message statistics for a chat |
| `unread` | Scan the WeChat sidebar for unread chats via vision AI |
| `new-messages` | Incremental fetch — only messages new since the last check |

All commands output JSON by default. Pass `--format text` for human-readable output.

**Common options**

```bash
weclaw-cua history "Group A" --limit 100 --offset 50 --format text
weclaw-cua search "deadline" --chat "Team A" --chat "Team B" --type text
weclaw-cua export "Alice" --format markdown --output alice.md
weclaw-cua sessions --limit 10 --format text
```

---

## Desktop App

> **Coming soon.** A native desktop application for macOS and Windows is in development. It will provide a graphical interface for all WeClaw-CUA features with no command-line setup required.

---

## License & Disclaimer

Released under the [Apache License 2.0](../LICENSE).

- **Read-only** — captures what is visible on screen; does not modify any WeChat data
- **No database access** — pure vision approach; no decryption or memory scanning
- **Local execution** — all UI automation runs on your machine; only LLM API calls leave your device (to your configured provider)
- **Personal use** — intended for personal learning and research purposes only
