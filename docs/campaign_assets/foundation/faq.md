# WeClaw — Frequently Asked Questions

## General

### What is WeClaw?

WeClaw is an open-source AI agent that automates WeChat-related tasks on your desktop. It currently scans groups for scam and fraud, with roadmap features for replies, friend request verification, and more. It runs locally on your machine.

### Is it safe to use?

WeClaw runs entirely on your computer. It does not send your messages to third-party servers. It uses vision-based automation (screenshots + LLM) to interact with WeChat’s desktop UI—the same way you would, but automated. You retain full control; human confirmation is required before removing anyone.

### Does it violate WeChat’s terms of service?

WeClaw uses user-side automation—it controls your local WeChat desktop app through the UI, similar to accessibility tools. It does not reverse-engineer APIs or bypass WeChat’s security. We recommend reviewing WeChat’s ToS and using automation in line with your use case. Consult legal counsel for compliance in your jurisdiction.

### Is it free?

Yes. WeClaw is open source (MIT License). You pay for your own LLM usage (e.g. via OpenRouter); there are no WeClaw subscription fees.

---

## Technical

### What do I need to run it?

- Windows 10/11 or macOS
- Python 3.11+
- OpenRouter API key (or another supported LLM provider)
- WeChat Desktop installed and logged in

### How does scam detection work?

The agent classifies chat threads, filters unread groups, reads messages with an LLM, extracts suspicious patterns (e.g. spam links, impersonation, phishing language), and proposes removals. You confirm before any removal. It uses a Find-Click-Verify pattern with vision queries and optional scaffolding clicks for known UI elements.

### Can I run it alongside OpenClaw?

Yes. WeClaw can run standalone or as part of an OpenClaw command stack. See docs for integration details.

### Which LLMs are supported?

OpenRouter is the primary integration—Claude, GPT-4o, Gemini, Qwen, and others. Configuration is in `config/model.yaml`. You can add other providers via the CUA platform.

### Is my data sent to the cloud?

Screenshots and prompts are sent to your configured LLM provider (e.g. OpenRouter). Messages and group data are not stored by WeClaw. Review your LLM provider’s privacy policy.

---

## Community & Contributing

### How can I contribute?

See [CONTRIBUTING.md](URL) for guidelines. We welcome contributions: code, documentation, skills, bug reports, and feature ideas. Tag issues with `good-first-issue` for newcomer-friendly tasks.

### How do I request a feature?

Open a GitHub Discussion or Issue. We prioritize based on community interest and feasibility.

### Where can I get help?

- GitHub Discussions
- GitHub Issues (bugs, feature requests)
- [Documentation](URL)

---

## Roadmap

### What’s next?

Planned features include:
- Reply generation and drafting
- Friend request verification
- Additional automation skills (driven by community feedback)

We ship iteratively; follow releases for updates.
