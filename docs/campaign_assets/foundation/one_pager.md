# WeClaw — One-Pager

## What Is WeClaw?

WeClaw is an open-source, AI-powered agent that performs WeChat-like messaging app tasks—independently or via OpenClaw command. It protects your groups, verifies your contacts, and frees you from repetitive messaging work.

## Current Capabilities

- **Scam & fraud detection** — Scans WeChat groups for suspicious users and activity
- **Human-in-the-loop removal** — AI identifies suspects; you confirm before any action
- **Vision-based automation** — No brittle APIs; works with the WeChat UI you already use
- **Skills system** — Extensible playbooks (e.g. `wechat_removal.md`) without code changes

## Roadmap

- Reply generation and drafting
- Friend request verification
- Additional automation tasks (community-driven)

## Why Open Source?

- **Transparent** — Inspect every line of code
- **Extensible** — Add skills, integrate with OpenClaw, customize for your needs
- **Community-driven** — We build what users ask for
- **Local-first** — Runs on your machine; your data stays yours

## Technical Highlights

- Built on [CUA (Computer Use Agents)](https://github.com/trycua/cua)
- Dual-model LLM routing (heavy + fast models) for speed and accuracy
- Supports OpenRouter: Claude, GPT-4o, Gemini, Qwen
- Windows & macOS (with platform-specific configs)

## Quick Start

1. Clone repo → set `OPENROUTER_API_KEY` in `.env`
2. Run `.\start.ps1` → Control Panel launches
3. Start Server → Start Workflow → run steps with WeChat open

## Links

- GitHub: [URL]
- Docs: [URL]

---

*WeClaw: Your WeChat shield. Your time back.*
