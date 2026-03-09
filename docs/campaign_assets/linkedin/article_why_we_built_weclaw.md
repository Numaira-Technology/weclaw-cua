# Why We Built WeClaw: AI, Messaging Security, and the Open Source Imperative

*LinkedIn Article — long-form. Paste into LinkedIn Article editor or adapt for blog.*

---

## The Problem Nobody Talks About

WeChat groups are everywhere. Family reunions. Business networks. Community hubs. But with scale comes risk: scams, spam, impersonation, and fraud. Group admins—often volunteers—spend hours each week scanning, removing, and blocking. Manual moderation doesn't scale. Most tools either don't exist or lock you into closed, opaque systems.

We wanted something different.

## Why AI, and Why Vision?

Messaging platforms rarely expose moderation APIs. Reverse-engineering them is brittle and often against terms of service. We took another path: vision-based automation. The agent sees the WeChat desktop UI the same way you do—screenshots, structured prompts, and an LLM that understands context. No API keys. No unofficial SDKs. It works with what's already there.

That's why we built on CUA (Computer Use Agents): a platform for AI that operates computers through vision and control, not hardcoded scripts. WeClaw is one agent in a broader ecosystem. The same approach could power automation for other apps—browser workflows, desktop tools, anything with a visual interface.

## Why Human-in-the-Loop?

AI can err. False positives—removing legitimate users—are costly. So we designed WeClaw to propose, not execute. You see the plan. You confirm. The agent clicks. Accountability stays with you. That constraint made adoption possible. Users trust the system because they're always in control.

## Why Open Source?

Three reasons.

**Transparency.** Messaging security is sensitive. Users deserve to know exactly what the agent does, what data flows where, and how decisions are made. Open source is the only way to prove it.

**Extensibility.** Different groups need different rules. Family chats vs. business networks vs. community forums—norms vary. Skills (markdown playbooks) let anyone add or tune behavior without touching core code. The community will outpace us.

**Sustainability.** We're not building a vendor lock-in. We're building infrastructure. Open source ensures the project outlives any single team or company.

## What's Next

We're shipping iteratively. Scam detection first. Reply generation, friend request verification, and more automation tasks—driven by community feedback. WeClaw runs standalone or as part of OpenClaw, so it fits into existing workflows.

If you moderate WeChat groups, care about messaging security, or want to contribute to open source AI—we'd love to hear from you.

**[Call to action: GitHub link, invite to star, fork, contribute]**

---

*WeClaw: Your WeChat shield. Your time back. Open source.*
