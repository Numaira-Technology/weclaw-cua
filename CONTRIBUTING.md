# Contributing to WeClaw-CUA

Thank you for your interest in contributing. WeClaw-CUA is open source and community-driven — every improvement, no matter how small, matters.

## Ways to Contribute

### Code

- Fork the repo, create a feature branch, submit a PR
- Follow the coding standards in `.cursor/rules/coding-standards.mdc` (one class per file, no defensive try/except, top docstring only, etc.)
- Add tests for new behavior when applicable
- Reference any related Issues in your PR description

### Documentation

- Fix typos, clarify unclear sections
- Add examples, screenshots, or use cases
- Improve `README.md`, `README_CN.md`, or module docstrings

### Bug Reports

- Use [GitHub Issues](https://github.com/Numaira-Technology/weclaw-cua/issues/new?template=bug_report.md)
- Include: steps to reproduce, OS, Python version, WeChat version, and terminal output
- The more detail, the faster we can fix it

### Feature Requests

- Use [GitHub Issues](https://github.com/Numaira-Technology/weclaw-cua/issues/new?template=feature_request.md)
- Describe the use case before the solution
- Check existing [Discussions](https://github.com/Numaira-Technology/weclaw-cua/discussions) first

## Good First Issues

New to the codebase? Look for the [`good-first-issue`](https://github.com/Numaira-Technology/weclaw-cua/issues?q=label%3Agood-first-issue) label. These are scoped, well-documented tasks ideal for first-time contributors.

## Pull Request Process

1. Create a branch from `main` (`git checkout -b feat/your-feature`)
2. Make your changes — keep PRs focused on one concern
3. Test locally before submitting
4. Open a PR with a clear description of what and why
5. A maintainer will review and may request changes

## Development Setup

```bash
# Clone and set up
git clone https://github.com/Numaira-Technology/weclaw-cua.git
cd weclaw-cua
python3 -m venv .venv

# macOS
./.venv/bin/pip install -e ".[macos,llm]"

# Windows
./.venv/bin/pip install -e ".[llm]"

# Configure
cp config/config.json.example config/config.json
# Edit config/config.json with your settings
```

Run tests:

```bash
./.venv/bin/python -m pytest tests/
```

## Code of Conduct

This project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

## Questions?

Open a [Discussion](https://github.com/Numaira-Technology/weclaw-cua/discussions) or comment on an Issue. We're happy to help onboard new contributors.

---

Thanks for making WeClaw-CUA better.

## Keep-Alive Service Notes

WeClaw-CUA now includes a local keep-alive service entrypoint for desktop app integration:

```bash
weclaw-cua serve
```

This mode keeps one Python process alive and accepts local HTTP requests for warmup and task execution. It is intended for app shells that want to reuse already-loaded OCR/model state instead of spawning a new `weclaw-cua run` process for every click.

Current local endpoints:

- `GET /health`
- `POST /warmup`
- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{id}`

If you change service behavior, please also update:

- `README.md`
- any CLI help text affected by new flags or commands
- request/response examples when endpoint payloads change

Recommended local validation:

```bash
weclaw-cua serve
curl http://127.0.0.1:8765/health
curl -X POST http://127.0.0.1:8765/warmup -H "Content-Type: application/json" -d "{\"ocr\": true}"
curl -X POST http://127.0.0.1:8765/tasks -H "Content-Type: application/json" -d "{\"no_llm\": false, \"openclaw_gateway\": false}"
```
