# Changelog

All notable changes to WeClaw-CUA are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). This project uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Planned

- Windows UI Automation improvements
- Additional message type support
- Community-contributed prompt templates

---

## [0.1.5] — 2026-04-11

### Added

- `new-messages` command — incremental message fetch, returns only messages since last check
- OpenClaw gateway mode (`--openclaw-gateway`) — reuse local OpenClaw gateway without a separate OpenRouter key
- Stepwise backend — `--no-llm` flag on `capture` and `run` lets an external agent handle all LLM calls via `manifest.json`
- `build-report-prompt` command — output the report prompt for an agent to call its own LLM
- `finalize` command — process agent-provided `.response.txt` files into final `messages.json`
- `unread` command — scan WeChat sidebar for unread chats via vision AI

### Improved

- Cross-platform driver abstraction (`PlatformDriver` protocol) covering macOS (Quartz + Accessibility) and Windows (UI Automation)
- Image stitching using OpenCV template matching with grayscale + edge dual-channel detection
- Message deduplication across scroll captures

---

## [0.1.0] — 2026-03-15

Initial public release.

### Added

**Vision Capture Pipeline**

- `capture` command — scroll through unread chats, stitch screenshots into long images, extract structured messages via vision LLM
- `run` command — full pipeline: capture + report generation in one step
- `report` command — generate LLM report from existing captured JSON files
- `init` command — first-time setup: create `config/config.json` from template, verify platform prerequisites

**Query Commands** (operate on captured data, no LLM needed)

- `sessions` — list captured chat sessions
- `history` — paginate through messages in a session
- `search` — full-text search across captured messages
- `export` — export a session to markdown or plain text
- `stats` — message statistics for a session

**Platform Support**

- macOS (Apple Silicon and Intel) via Accessibility API + Quartz screenshots
- Windows 10/11 via UI Automation

**Architecture**

- Pure vision approach — no WeChat database decryption, no version lock-in
- JSON-first output — all commands output structured JSON by default, `--format text` for human-readable output
- OpenRouter integration for vision LLM (message extraction) and text LLM (report generation)
- `config/config.json` for local configuration; `OPENROUTER_API_KEY` env var support

**Distribution**

- `weclaw-cua` PyPI package with `[llm]` and `[macos]` extras
- `weclaw` console script alias
- npm binary distribution scaffold (`npm/`)

---

[Unreleased]: https://github.com/Numaira-Technology/weclaw-cua/compare/v0.1.5...HEAD
[0.1.5]: https://github.com/Numaira-Technology/weclaw-cua/compare/v0.1.0...v0.1.5
[0.1.0]: https://github.com/Numaira-Technology/weclaw-cua/releases/tag/v0.1.0
