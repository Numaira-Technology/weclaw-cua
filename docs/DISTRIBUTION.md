# Distribution Guide

This document explains the two distribution channels for the WeChat Removal Tool,
mirroring the pattern used by products like [TuriX CUA](https://github.com/TurixAI/TuriX-CUA):
a **standalone downloaded app** and an **OpenClaw skill** that lets an AI orchestrator
invoke the tool on demand.

---

## Table of Contents

1. [Distribution Channels Overview](#1-distribution-channels-overview)
2. [Channel A — Standalone App (install.ps1)](#2-channel-a--standalone-app)
3. [Channel B — OpenClaw Skill](#3-channel-b--openclaw-skill)
4. [How the Two Channels Relate](#4-how-the-two-channels-relate)
5. [Configuration Reference](#5-configuration-reference)
6. [Dependency Reference](#6-dependency-reference)
7. [Keeping Wrappers Up to Date](#7-keeping-wrappers-up-to-date)

---

## 1. Distribution Channels Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTION ARCHITECTURE                         │
├───────────────────────────────┬─────────────────────────────────────┤
│  Channel A: Standalone App    │  Channel B: OpenClaw Skill           │
│                               │                                      │
│  User downloads / clones      │  OpenClaw agent picks up the skill   │
│  the repo and runs:           │  from clawd/skills/local/ and        │
│                               │  dispatches:                         │
│    install.ps1                │                                      │
│         │                     │    scripts/run_wechat_removal.ps1    │
│         ▼                     │         │                            │
│    start.bat / start.ps1      │         ▼                            │
│         │                     │    control_panel.py                  │
│         ▼                     │                                      │
│    control_panel.py           │  Same core tool, same config.        │
│                               │  The skill is just a thin wrapper.   │
└───────────────────────────────┴─────────────────────────────────────┘
```

Both channels launch the same `control_panel.py` entry point and read from the same
`config/` files. The wrappers are intentionally thin so that changes to the core
tool propagate automatically to both channels.

---

## 2. Channel A — Standalone App

### File: `install.ps1`

A one-shot setup script for users who download or clone the repository directly.

**What it does:**

| Step | Action |
|------|--------|
| 1 | Resolves install directory (defaults to repo root; `--install-dir` to override) |
| 2 | Checks Python 3.11+ is on PATH |
| 3 | Creates a `.venv` and installs dependencies from `requirements.txt` into it |
| 4 | Prompts for `OPENROUTER_API_KEY`, writes `.env` with owner-only file permissions |
| 5 | Creates a desktop shortcut pointing to `start.bat` |

**Usage:**

```powershell
# Standard install (run once after downloading)
.\install.ps1

# Install to a different directory
.\install.ps1 --install-dir "C:\Tools\WeChatRemoval"

# CI / headless — no interactive prompts
.\install.ps1 --no-prompt

# Skip pip install if managing dependencies yourself
.\install.ps1 --skip-deps
```

**After install:**

- Double-click **"WeChat Removal Tool"** on the desktop, or
- Run `.\start.bat` (or `.\start.ps1`) from the install directory.

### File: `start.ps1` / `start.bat`

The day-to-day launcher. Loads `.env`, validates the API key, warns about desktop
control mode, then opens the Control Panel GUI.

```
start.bat ──▶ start.ps1 ──▶ python control_panel.py
```

### File: `requirements.txt`

All Python runtime dependencies in one place. Both the installer and manual setups
use this file. Edit here when adding new dependencies; the installer picks it up
automatically.

---

## 3. Channel B — OpenClaw Skill

### Directory: `OpenClaw_WeChatRemoval_skill/`

```
OpenClaw_WeChatRemoval_skill/
├── SKILL.md                       # Skill descriptor (name, description, instructions)
├── README.md                      # Human-readable setup guide
└── scripts/
    └── run_wechat_removal.ps1     # Launcher called by OpenClaw
```

### Installing the Skill

Copy the skill folder into OpenClaw's local skills directory:

```powershell
# Default OpenClaw skills path (adjust if yours differs)
$SkillsDir = "$env:USERPROFILE\clawd\skills\local"
Copy-Item -Recurse OpenClaw_WeChatRemoval_skill "$SkillsDir\wechat-removal"
```

OpenClaw will discover the skill on next startup.

### How OpenClaw Uses It

1. User asks something like *"remove spammers from my WeChat groups"*.
2. OpenClaw reads skill descriptors and matches `wechat-removal` based on the
   `description` field in `SKILL.md`.
3. OpenClaw calls `scripts/run_wechat_removal.ps1` (with optional parameters).
4. The launcher performs pre-flight checks, then opens the Control Panel.

### `SKILL.md` — Skill Descriptor

The `SKILL.md` file has two sections:

- **YAML frontmatter** (`name`, `alias`, `description`, `requires`) — read by OpenClaw
  to match skills to user intent.
- **Markdown body** — instructions that OpenClaw's planner uses to guide each step.

To change when the skill is triggered, edit the `description` field in the
frontmatter. To change what the agent does after launch, edit the body.

### `scripts/run_wechat_removal.ps1` — Skill Launcher

Accepted parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--tool-root` | string | Two levels up from `scripts/` | Path to the WeChat Removal Tool root |
| `--model` | string | _(from config/model.yaml)_ | Override LLM model for this session |
| `--dry-run` | switch | false | Validate setup only; do not launch |

The launcher:
1. Resolves `--tool-root` (auto-detected from the skill's own location).
2. Loads `.env` from the tool root.
3. Runs pre-flight checks (API key, Python, config files).
4. Exports any model override via `WECHAT_REMOVAL_MODEL_OVERRIDE` env var (**stub** — `model_session.py` must be updated to read this before it takes effect).
5. Calls `python control_panel.py` in the tool root.

---

## 4. How the Two Channels Relate

```
┌────────────────────────────────────────────────────────────────┐
│                      CORE TOOL (unchanged)                      │
│                                                                 │
│  config/              ← shared by both channels                │
│  workflow/            ← business logic                         │
│  modules/             ← workflow components                    │
│  skills/              ← prompt playbooks                       │
│  control_panel.py     ← single entry point                     │
│  vendor/              ← vendored CUA libraries                 │
│                                                                 │
├──────────────────────┬──────────────────────────────────────────┤
│  Channel A wrappers  │  Channel B wrappers                     │
│                      │                                         │
│  install.ps1         │  OpenClaw_WeChatRemoval_skill/          │
│  start.ps1           │    SKILL.md                             │
│  start.bat           │    README.md                            │
│  requirements.txt    │    scripts/run_wechat_removal.ps1       │
└──────────────────────┴──────────────────────────────────────────┘
```

**Key design principle:** wrappers contain only environment setup and invocation
logic. They do not duplicate configuration or business logic. When the core tool
changes (new workflow steps, new config keys, new skills), the wrappers require
no modification unless the invocation interface itself changes.

---

## 5. Configuration Reference

Both channels read from the same config files:

### `config/model.yaml`

```yaml
model: openrouter/qwen/qwen3-vl-32b-instruct      # Heavy VLM: coordinate prediction
verify_model: openrouter/qwen/qwen2-vl-7b-instruct # Fast VLM: yes/no checks
skills_dir: skills
max_trajectory_budget: 5.0                          # USD spend cap per session
instructions: |
  你是一个专门处理微信群违规信息的助手...
```

Omit `verify_model` to use `model` for all calls.

Switch providers by changing the model string — any litellm-compatible prefix works:

| Provider | Example model string |
|----------|----------------------|
| OpenRouter | `openrouter/anthropic/claude-sonnet-4` |
| Anthropic | `anthropic/claude-sonnet-4-20250514` |
| OpenAI | `openai/gpt-4o` |
| Google | `gemini/gemini-2.5-flash-preview` |
| Ollama | `ollama_chat/llava` |

### `config/computer_windows.yaml`

```yaml
use_host_computer_server: true
os_type: windows
api_port: 8000
# WeChat button positions in absolute screen pixels (calibrate for your display)
wechat_three_dots_x: 2525
wechat_three_dots_y: 48
wechat_delete_button_x: 1345
wechat_delete_button_y: 920
```

Recalibrate the `wechat_*` coordinates if your screen resolution or WeChat
window position differs from the defaults (2560×1440, WeChat maximised).

---

## 6. Dependency Reference

### Virtual Environment

`install.ps1` creates `.venv/` in the install directory and installs all dependencies there. `start.ps1` activates `.venv/Scripts/Activate.ps1` automatically at launch, so the system Python is never contaminated.

If you manage dependencies yourself (`--skip-deps`), ensure the correct Python 3.11+ environment is active before running `start.bat`.

### Dependency Table

All runtime dependencies are declared in `requirements.txt`:

| Package | Purpose |
|---------|---------|
| `httpx`, `aiohttp`, `anyio` | Async HTTP for computer-server and LLM calls |
| `pydantic` | Data validation for task types |
| `litellm` | LLM provider abstraction (OpenAI / Anthropic / Google / Ollama / …) |
| `pillow` | Screenshot capture and image crop |
| `uvicorn`, `fastapi` | computer-server HTTP layer |
| `pynput` | Mouse and keyboard control |
| `typing-extensions` | Python 3.11 compatibility shim for vendored CUA code |
| `pyyaml` | Config file parsing |

Minimum Python: **3.11** (3.12 recommended).

---

## 7. Keeping Wrappers Up to Date

The wrappers are designed to be forward-compatible. When the core tool evolves:

| Change | Action needed |
|--------|---------------|
| New workflow steps | None — wrappers launch `control_panel.py` which handles all steps |
| New config keys | Add to `config/model.yaml` or `config/computer_windows.yaml`; wrappers read from disk |
| New Python dependency | Add to `requirements.txt`; `install.ps1` picks it up automatically |
| New invocation flag | Add param to `scripts/run_wechat_removal.ps1` and document in `SKILL.md` |
| New LLM provider | Change model string in `config/model.yaml`; no wrapper changes needed |
| Rename entry point | Update `start.ps1` and `scripts/run_wechat_removal.ps1` (two places) |
| New OS platform | Create `config/computer_mac.yaml` and optionally a `scripts/run_wechat_removal.sh` |
