# WeClaw Multi-Platform Social Media Campaign Plan

## Executive Summary

**WeClaw** is an open-source, AI-powered agent that performs WeChat-like messaging app tasks—independently or via OpenClaw command. It currently scans WeChat groups for scam and fraud, with roadmap features including reply generation, friend request verification, and more. This plan outlines a multi-platform campaign to build developer adoption, community trust, and thought leadership in AI automation and messaging security.

**Ready-to-use copy:** All copy-paste ready text lives in [campaign_assets/](campaign_assets/README.md). See [Quick Reference: First 10 Posts](#10-quick-reference-first-10-posts) for direct links.

---

## 1. Product Positioning & Key Messages

### Core Positioning Statement

> *WeClaw: AI-powered WeChat automation that protects your groups, verifies your contacts, and frees you from repetitive messaging tasks—all open source.*

### Key Message Pillars

| Pillar | Message | Audience Hook |
|--------|---------|---------------|
| **Security & Trust** | "Scan groups for scam and fraud—before damage is done." | Group admins, community moderators |
| **Automation Freedom** | "Let AI handle the grunt work: replies, verification, screening." | Power users, small business owners |
| **Open Source** | "Community-driven. Transparent. Extensible." | Developers, privacy advocates |
| **OpenClaw Integration** | "Run WeClaw standalone or as part of your OpenClaw command stack." | CUA/OpenClaw users, automation enthusiasts |
| **AI-Native** | "Vision-based. No brittle APIs. Works with the UI you already use." | Technical audience, automation engineers |

### Taglines (A/B Test)

- *"Your WeChat shield. Your time back."*
- *"AI that watches your groups so you don't have to."*
- *"Open source WeChat automation that actually works."*

---

## 2. Target Audiences

### Primary

| Segment | Pain Points | Platforms | Content Focus |
|---------|-------------|-----------|---------------|
| **WeChat group admins** | Spam, scams, time-consuming moderation | LinkedIn, Twitter, WeChat ecosystem blogs | Fraud detection, case studies, how-to |
| **Open source / CUA developers** | Need for real-world CUA use cases, automation tooling | GitHub, Twitter, Hacker News, Reddit (r/opensource, r/selfhosted) | Technical deep-dives, architecture, contributions |
| **Automation & productivity enthusiasts** | Repetitive messaging tasks | Twitter, Reddit (r/automation), Product Hunt | Demo videos, use cases, "what you can automate" |

### Secondary

| Segment | Interest | Platforms |
|---------|----------|-----------|
| **Privacy & security advocates** | Local-first, no cloud dependency, transparent code | Twitter, Mastodon, security newsletters |
| **Chinese diaspora / international users** | WeChat as primary comms, scam awareness | LinkedIn, WeChat-adjacent communities |
| **Small business / community ops** | Managing large groups, customer touchpoints | LinkedIn |

---

## 3. Platform Strategy

### 3.1 LinkedIn

**Role:** Authority, trust, professional reach.

- **Company/Project Page:** WeClaw (or parent org) with product updates, release notes, and thought leadership.
- **Content mix:**
  - Long-form posts on scam trends in messaging apps, AI in moderation, open source philosophy → [campaign_assets/linkedin/03_scam_artists_wechat.txt](campaign_assets/linkedin/03_scam_artists_wechat.txt)
  - Short-form updates: "WeClaw v0.x shipped: friend request verification is live" → [campaign_assets/linkedin/02_friend_request_verification_shipped.txt](campaign_assets/linkedin/02_friend_request_verification_shipped.txt)
  - Employee/contributor spotlights: maintainer stories, community contributors → [campaign_assets/linkedin/05_contributor_spotlight_template.txt](campaign_assets/linkedin/05_contributor_spotlight_template.txt)
- **LinkedIn Articles (optional):** "Why We Built WeClaw: AI, Messaging Security, and the Open Source Imperative" → [campaign_assets/linkedin/article_why_we_built_weclaw.md](campaign_assets/linkedin/article_why_we_built_weclaw.md)
- **Target metrics:** 3%+ engagement on posts, 8% monthly follower growth.

### 3.2 Twitter / X

**Role:** Real-time engagement, developer community, viral demos.

- **Handles:** @WeClawProject (or aligned handle); coordinate with OpenClaw/CUA accounts.
- **Content mix:**
  - Threads: "Why we built WeClaw" → [campaign_assets/twitter/thread_why_we_built_weclaw.txt](campaign_assets/twitter/thread_why_we_built_weclaw.txt); "How WeClaw detects scams in 5 steps" → [campaign_assets/twitter/thread_how_weclaw_detects_scams.txt](campaign_assets/twitter/thread_how_weclaw_detects_scams.txt)
  - Demo clips: GIF/video of scan → detect → remove workflow → [campaign_assets/twitter/demo_weclaw_30_seconds.txt](campaign_assets/twitter/demo_weclaw_30_seconds.txt)
  - Replies to scam/fraud news: "Tools like WeClaw help group admins..." → [campaign_assets/twitter/reply_scam_news.txt](campaign_assets/twitter/reply_scam_news.txt)
  - Developer tips, CUA integration snippets → [campaign_assets/twitter/developer_tips.txt](campaign_assets/twitter/developer_tips.txt); educational/personal/industry mix → [campaign_assets/twitter/mix_educational_personal_industry.txt](campaign_assets/twitter/mix_educational_personal_industry.txt)
- **Hashtags:** #WeChat #OpenSource #AIAutomation #CUA #WeClaw
- **Target metrics:** 5%+ engagement, quote-tweet amplification from dev influencers.

### 3.3 GitHub

**Role:** Developer home base, contribution funnel.

- **Repo presence:**
  - README with clear value prop, screenshots, quick-start
  - CONTRIBUTING.md → [campaign_assets/github/CONTRIBUTING_template.md](campaign_assets/github/CONTRIBUTING_template.md), CODE_OF_CONDUCT.md → [campaign_assets/github/CODE_OF_CONDUCT_template.md](campaign_assets/github/CODE_OF_CONDUCT_template.md)
  - Issues tagged `good-first-issue` for onboarding
  - Discussions for feature ideas, Q&A → [campaign_assets/github/discussions_features_wanted.txt](campaign_assets/github/discussions_features_wanted.txt), [campaign_assets/github/discussions_feature_brainstorm.txt](campaign_assets/github/discussions_feature_brainstorm.txt)
- **Release cadence:** Semantic versioning, release notes as social assets → [campaign_assets/github/release_v0.1.0.md](campaign_assets/github/release_v0.1.0.md), [campaign_assets/github/release_friend_verification.md](campaign_assets/github/release_friend_verification.md).
- **Target metrics:** Stars, forks, PR velocity, Discussion participation.

### 3.4 Reddit

**Role:** Community building, authentic conversations.

- **Subreddits:** r/opensource, r/selfhosted, r/WeChat, r/automation, r/Python, r/LocalLLaMA (if applicable)
- **Approach:** Help-first, no spam. Answer questions, share when relevant ("We built something for this") → [campaign_assets/reddit/reply_templates.txt](campaign_assets/reddit/reply_templates.txt).
- **Content:** "I built an AI tool to scan WeChat groups for scams—here's how" (story-driven) → [campaign_assets/reddit/r_opensource_story.txt](campaign_assets/reddit/r_opensource_story.txt); r/selfhosted cross-post → [campaign_assets/reddit/r_selfhosted_crosspost.txt](campaign_assets/reddit/r_selfhosted_crosspost.txt).
- **Target metrics:** Positive karma, genuine engagement, not shadowbans.

### 3.5 Hacker News

**Role:** Launch spikes, technical credibility.

- **Strategy:** "Show HN" and "Ask HN" when major releases land or when there's a story worth discussing.
- **Ready copy:** Show HN → [campaign_assets/hacker_news/show_hn_post.txt](campaign_assets/hacker_news/show_hn_post.txt); Ask HN alternative → [campaign_assets/hacker_news/ask_hn_alternative.txt](campaign_assets/hacker_news/ask_hn_alternative.txt).
- **Titles:** Technical, specific—e.g., "Show HN: WeClaw – AI agent that scans WeChat groups for scams (open source)"
- **Target metrics:** Front page reach, thoughtful comments.

### 3.6 WeChat-Adjacent Channels

**Role:** Reach users who live in WeChat.

- **Channels:** Technical blogs, newsletters covering WeChat/Chinese tech, diaspora forums.
- **Content:** Localized value props, case studies in English and (if resources allow) Chinese.

---

## 4. Campaign Phases & Timeline

### Phase 1: Foundation (Weeks 1–2)

| Activity | Owner | Output |
|----------|-------|--------|
| Create social accounts | Ops | LinkedIn, Twitter, GitHub org/repo branding |
| Finalize messaging | Strategy | [One-pager](campaign_assets/foundation/one_pager.md), [FAQ](campaign_assets/foundation/faq.md), [key messages](campaign_assets/foundation/key_messages.txt) |
| Prepare assets | Design | Logo, screenshots, [30s demo video script](campaign_assets/video/script_30s_demo.txt) |
| Seed README & docs | Dev | Polished GitHub presence |

### Phase 2: Soft Launch (Weeks 3–4)

| Activity | Owner | Output |
|----------|-------|--------|
| First LinkedIn post | Strategy | [Introducing WeClaw](campaign_assets/linkedin/01_introducing_weclaw.txt) |
| Twitter thread: "Why we built WeClaw" | Content | [Thread + visuals](campaign_assets/twitter/thread_why_we_built_weclaw.txt) |
| Reddit r/opensource post | Community | [Story-led intro](campaign_assets/reddit/r_opensource_story.txt) |
| GitHub Discussions | Dev | [Feature brainstorm](campaign_assets/github/discussions_feature_brainstorm.txt), [features wanted](campaign_assets/github/discussions_features_wanted.txt) |

### Phase 3: Public Launch (Weeks 5–6)

| Activity | Owner | Output |
|----------|-------|--------|
| Show HN launch | Dev/Strategy | [Hacker News post](campaign_assets/hacker_news/show_hn_post.txt) |
| Cross-post launch content | All | LinkedIn, Twitter, Reddit, [newsletter](campaign_assets/newsletter/launch_announcement.txt) |
| Product Hunt (optional) | Growth | [Listing](campaign_assets/product_hunt/listing.txt) + [community push](campaign_assets/product_hunt/community_push.txt) |
| Outreach to dev/automation influencers | Strategy | [DM/intro templates](campaign_assets/influencer/dm_template.txt) |

### Phase 4: Sustain & Amplify (Ongoing)

| Activity | Owner | Cadence |
|----------|-------|---------|
| Release notes → social | Dev + Ops | Per release → [v0.1.0](campaign_assets/github/release_v0.1.0.md), [friend verification template](campaign_assets/github/release_friend_verification.md) |
| Use case / case study posts | Content | 2x/month → [first 100 users](campaign_assets/linkedin/04_first_100_users.txt) |
| Engage in scam/fraud conversations | Community | Real-time → [reply templates](campaign_assets/twitter/reply_scam_news.txt), [Reddit replies](campaign_assets/reddit/reply_templates.txt) |
| Contributor spotlights | Community | Monthly → [spotlight template](campaign_assets/linkedin/05_contributor_spotlight_template.txt) |

---

## 5. Content Themes & Editorial Calendar

### Content Pillars (Monthly Rhythm)

| Week | Theme | Example Topics |
|------|-------|----------------|
| 1 | **Product** | Release notes, new features, roadmap |
| 2 | **Education** | How scam detection works, AI + moderation |
| 3 | **Community** | Contributor story, use case, integration |
| 4 | **Thought leadership** | Open source, privacy, automation trends |

### Content Types by Platform

| Type | LinkedIn | Twitter | Reddit | GitHub |
|------|----------|---------|--------|--------|
| Release announcements | ✓ | ✓ | ✓ | ✓ |
| Technical deep-dives | ✓ (Articles) | Thread | Post | README/Docs |
| Demo videos | ✓ | ✓✓ | ✓ | ✓ |
| Use case stories | ✓ | ✓ | ✓ | Discussions |
| Developer tips | ✓ | ✓✓ | ✓ | ✓ |
| Scam/fraud commentary | ✓ | ✓ | ✓ | — |

---

## 6. Community Engagement Strategy

### Developer Community

- **GitHub:** Clear CONTRIBUTING.md, `good-first-issue` tags, responsive maintainers
- **Discord/Slack (optional):** Dedicated channel for WeClaw + CUA users
- **Hacktoberfest / open source events:** Highlight WeClaw as a welcoming project

### User Community

- **Feedback loops:** "How are you using WeClaw?" → case studies, testimonials
- **FAQ & docs:** Reduce support burden, improve SEO

### Cross-Platform Coordination

- **Twitter ↔ LinkedIn:** Same themes, adapted format (thread → article → post)
- **GitHub ↔ Social:** Release notes as canonical source, social as amplifier
- **Reddit ↔ Twitter:** Authentic stories on Reddit, distilled for Twitter

---

## 7. Success Metrics

### Awareness

| Metric | Target (6 months) |
|--------|-------------------|
| GitHub stars | 500+ |
| LinkedIn followers | 500+ |
| Twitter followers | 1,000+ |
| Monthly unique visitors (docs/GitHub) | 2,000+ |

### Engagement

| Metric | Target |
|--------|--------|
| LinkedIn post engagement rate | 3%+ |
| Twitter engagement rate | 5%+ |
| Reddit post karma (avg) | Positive, no downvote brigades |
| GitHub Discussions participation | 10+ active threads/month |

### Conversion & Community

| Metric | Target |
|--------|--------|
| First-time contributors | 5+ in 6 months |
| Community-reported use cases | 3+ documented |
| Inbound PR/press mentions | 2+ |

---

## 8. Resource Requirements

### Minimum Viable Team

| Role | Effort | Responsibilities |
|------|--------|------------------|
| **Strategy/Content** | 2–4 hrs/week | Messaging, calendar, key posts |
| **Dev/Technical** | 1–2 hrs/week | Technical posts, release notes, GitHub |
| **Community** | 2–3 hrs/week | Reddit, Twitter replies, Discussions |

### Tools (Low-Cost/Free)

- **Scheduling:** Buffer, Typefully, or native scheduling
- **Analytics:** Native platform analytics; Plausible/Umami for docs
- **Design:** Canva, Figma (existing assets)
- **Video:** OBS, Loom for demos

---

## 9. Risk Mitigation

| Risk | Mitigation |
|------|-------------|
| WeChat ToS concerns | Position as user-side automation, no API abuse; consult legal if needed |
| Low initial traction | Double down on dev communities (GitHub, HN); quality over quantity |
| Scam/fraud topic sensitivity | Stick to educational tone; avoid fear-mongering |
| Open source contributor burnout | Clear scope, celebrate contributions, maintain sustainable pace |

---

## 10. Quick Reference: First 10 Posts

| # | Platform | Description | Ready Copy |
|---|----------|-------------|------------|
| 1 | LinkedIn | Introducing WeClaw: Open source AI for WeChat group protection | [01_introducing_weclaw.txt](campaign_assets/linkedin/01_introducing_weclaw.txt) |
| 2 | Twitter | Thread—5-part "Why we built WeClaw" | [thread_why_we_built_weclaw.txt](campaign_assets/twitter/thread_why_we_built_weclaw.txt) |
| 3 | Reddit r/opensource | I built an AI tool to scan WeChat groups for scams—feedback welcome | [r_opensource_story.txt](campaign_assets/reddit/r_opensource_story.txt) |
| 4 | GitHub | Release v0.1.0 notes | [release_v0.1.0.md](campaign_assets/github/release_v0.1.0.md) |
| 5 | LinkedIn | 3 ways scam artists target WeChat groups (and how to spot them) | [03_scam_artists_wechat.txt](campaign_assets/linkedin/03_scam_artists_wechat.txt) |
| 6 | Twitter | Demo GIF + "WeClaw in 30 seconds" | [demo_weclaw_30_seconds.txt](campaign_assets/twitter/demo_weclaw_30_seconds.txt) |
| 7 | Reddit r/selfhosted | Cross-post if relevant (local-first angle) | [r_selfhosted_crosspost.txt](campaign_assets/reddit/r_selfhosted_crosspost.txt) |
| 8 | Twitter | Reply to a scam news story with WeClaw angle | [reply_scam_news.txt](campaign_assets/twitter/reply_scam_news.txt) |
| 9 | LinkedIn | What we learned from our first 100 users | [04_first_100_users.txt](campaign_assets/linkedin/04_first_100_users.txt) |
| 10 | GitHub Discussions | What features do you want next? | [discussions_features_wanted.txt](campaign_assets/github/discussions_features_wanted.txt) |

**All campaign assets:** [campaign_assets/](campaign_assets/README.md)

---

*Document follows Social Media Strategist Agent framework. Revise quarterly based on analytics and community feedback.*
