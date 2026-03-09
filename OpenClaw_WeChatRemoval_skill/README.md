# WeChat Removal — OpenClaw Skill Setup

## Installation

1. Copy the `OpenClaw_WeChatRemoval_skill/` folder into your OpenClaw local skills
   directory. By default this is:

   ```
   clawd/skills/local/wechat-removal/
   ```

   Or wherever OpenClaw resolves local skills from its config.

2. Set your API key (one-time):

   ```powershell
   # Option A: .env file in the tool root (recommended)
   echo "OPENROUTER_API_KEY=sk-or-v1-..." > .env

   # Option B: environment variable
   $env:OPENROUTER_API_KEY = "sk-or-v1-..."
   ```

3. Test the setup without touching WeChat:

   ```powershell
   .\scripts\run_wechat_removal.ps1 --dry-run
   ```

## Usage

Ask OpenClaw naturally:

- "Remove spammers from my WeChat groups"
- "Clean up my WeChat group moderations"
- "There's someone advertising in my WeChat group, remove them"

OpenClaw selects the `wechat-removal` skill and dispatches
`scripts/run_wechat_removal.ps1` automatically.

## Requirements

- Windows 10/11
- Python 3.11+ on PATH (or active conda/venv)
- WeChat desktop app installed, open, and logged in
- OpenRouter API key (or any litellm-compatible provider)
