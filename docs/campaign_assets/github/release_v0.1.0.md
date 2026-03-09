# WeClaw v0.1.0 — Initial Release

**WeClaw** is an open-source, AI-powered agent that scans WeChat groups for scam and fraud. This is the first public release.

## What's Included

### Scam & Fraud Detection
- **Classify** — Identifies group vs. individual chats
- **Filter** — Focuses on unread group chats only
- **Read** — AI reads messages and extracts suspicious patterns (phishing, impersonation, spam links)
- **Plan** — Builds removal plan with human confirmation
- **Execute** — Removes suspects with vision-based verification

### Architecture
- **Vision-based automation** — No brittle APIs; works with the WeChat desktop UI
- **Find-Click-Verify** — Dual-model LLM routing (heavy model for coordinates, fast model for verification)
- **Skills system** — Behavior tuned via `skills/wechat_removal.md` without code changes
- **Human-in-the-loop** — You approve every removal before execution

### Platform Support
- **Windows** — Tested on Windows 10/11 (2560×1440 default config)
- **macOS** — Supported via `config/computer_mac.yaml` (AX tree + vision)

### LLM Support
- OpenRouter (Claude, GPT-4o, Gemini, Qwen, others)
- Configurable in `config/model.yaml`

## Quick Start

1. Clone the repo
2. Set `OPENROUTER_API_KEY` in `.env`
3. Run `.\start.ps1` (or `start.bat`)
4. Click **Start Server** → **Start Workflow**
5. Ensure WeChat is open and visible
6. Step through: Classify → Filter → Read → Extract → Plan → Remove

## Requirements

- Python 3.11+ (3.12 recommended)
- OpenRouter API key (or compatible LLM provider)
- WeChat Desktop installed and logged in

## Roadmap

- Reply generation
- Friend request verification
- Community-contributed skills
- More automation tasks (driven by feedback)

## Feedback

We'd love to hear from you. Open an [Issue](URL) or [Discussion](URL). PRs welcome.

---

**Full Changelog**: https://github.com/[org]/weclaw/compare/v0.0.0...v0.1.0
