---
name: wechat-removal
alias: wechat-removal-win
description: >
  Remove spam/scam users from WeChat groups automatically on Windows.
  The skill detects suspicious messages, builds a removal plan, shows you
  a confirmation dialog, then executes removals one-by-one with vision
  verification. Use when asked to moderate a WeChat group, remove a spammer,
  or clean up advertisement messages.
requires:
  - os: windows
  - app: wechat (must be open and logged in)
  - env: OPENROUTER_API_KEY
---

# WeChat Removal Skill

## Overview

This skill launches the WeChat Removal Tool — an AI agent that monitors
WeChat group chats for spam/scam messages and removes the offending users
with human confirmation.

## When to Use

- User says "remove spammers from my WeChat groups"
- User says "clean up WeChat group chats"
- User says "someone is advertising in my WeChat group, remove them"
- User wants to moderate one or more WeChat groups automatically

## Pre-flight Checklist

Before invoking this skill, verify:

1. WeChat desktop app is open and the user is logged in
2. The group chat(s) to moderate are visible in the sidebar
3. `OPENROUTER_API_KEY` is set in the environment or in a `.env` file in the
   tool root directory
4. Python 3.11+ is available on PATH

If any check fails, tell the user what is missing before proceeding.

## Invocation

Run the skill by executing the bundled launcher script:

```powershell
.\scripts\run_wechat_removal.ps1
```

Or with optional parameters:

```powershell
# Dry-run: validate setup without touching WeChat
.\scripts\run_wechat_removal.ps1 --dry-run

# Point to a custom tool root (if not installed at default path)
.\scripts\run_wechat_removal.ps1 --tool-root "C:\path\to\wechat-removal"

# Override the LLM model for this session
# Note: sets WECHAT_REMOVAL_MODEL_OVERRIDE — requires model_session.py to consume it
.\scripts\run_wechat_removal.ps1 --model "openrouter/anthropic/claude-sonnet-4"
```

## What Happens After Launch

1. The launcher validates the environment and starts the Control Panel GUI.
2. Inside the Control Panel the user clicks **Start Server**, then **Start Workflow**.
3. The workflow proceeds step-by-step:
   - **Classify Threads** — scans the WeChat chat list
   - **Filter Unread** — isolates unread group chats
   - **Read Messages** — reads messages in each group
   - **Extract Suspects** — identifies spam/scam senders
   - **Build Plan** — prepares a removal plan
   - **Execute Removal** — removes suspects after user confirmation
4. A JSON report is saved to `artifacts/logs/report.json`.

## Configuration

All tunable parameters live in `config/`:

| File | Purpose |
|------|---------|
| `config/model.yaml` | LLM models, budget cap, system prompt |
| `config/computer_windows.yaml` | Screen resolution, WeChat button positions |

Edit `config/model.yaml` to change the LLM:

```yaml
model: openrouter/qwen/qwen3-vl-32b-instruct      # coordinate prediction
verify_model: openrouter/qwen/qwen2-vl-7b-instruct # fast yes/no checks
max_trajectory_budget: 5.0                          # USD spend cap
```

Edit `config/computer_windows.yaml` if your WeChat window is positioned
differently (e.g., a different screen resolution):

```yaml
wechat_three_dots_x: 2525
wechat_three_dots_y: 48
wechat_delete_button_x: 1345
wechat_delete_button_y: 920
```

## Output

Results are saved to `artifacts/logs/report.json` after each session.

## Troubleshooting

- **"Computer API Server not ready"** — click Start Server in the Control Panel first
- **"OPENROUTER_API_KEY not set"** — add the key to `.env` in the tool root
- **Agent clicks wrong position** — re-calibrate coordinates in `config/computer_windows.yaml`
- **Python not found** — ensure Python 3.11+ is on PATH or activate the right conda/venv environment

Full architecture documentation: `docs/ARCHITECTURE.md`
