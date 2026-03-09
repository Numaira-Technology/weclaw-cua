# WeChat Removal Tool · AI-Powered Group Cleanup

**Clean your WeChat groups—let AI find the spammers, you confirm the removals.**

An AI-powered agent that automates the detection and removal of spam/scam users from WeChat groups. Built on the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform and runs directly on your desktop. No app-specific APIs—if a human can click it, this agent can too.

---

## Table of Contents

- [🖼️ Demos](#️-demos)
- [✨ Key Features](#-key-features)
- [🔄 How It Works](#-how-it-works)
- [🚀 Quick Start](#-quick-start)
- [📁 Project Structure](#-project-structure)
- [⚙️ Configuration](#️-configuration)
- [📖 Documentation](#-documentation)
- [🔧 Extending](#-extending)
- [📦 Upstream](#-upstream)

---

## 🖼️ Demos

> *Add video or GIF demos here once the repo is public. Suggested placeholders:*

### Windows Demo

<!-- TODO: Add demo — Control panel + workflow in action -->
![Control panel workflow](docs/demos/control-panel-workflow.gif)
*Control panel: Start Server → Start Workflow → step through Classify → Filter → Read → Extract → Plan → Remove.*

### OpenClaw Demo

<!-- TODO: Add demo — "Remove spammers from my WeChat groups" via OpenClaw -->
![OpenClaw skill invocation](docs/demos/openclaw-skill.gif)
*Ask OpenClaw to remove spammers—the skill orchestrates the full workflow.*

---

## ✨ Key Features

| Capability | What it means |
|------------|---------------|
| **Automated spam detection** | Vision-based identification of suspicious users in WeChat group chats |
| **Human-in-the-loop** | You confirm before any removal—no surprises |
| **Hybrid automation** | Fixed-position clicks for known UI + vision-guided detection for dynamic content |
| **Dual-model LLM routing** | Heavy model for coordinates; fast model for yes/no checks—speed and accuracy |
| **Skills (markdown playbooks)** | Workflow rules live in `skills/` markdown files, not in code |
| **Multi-provider support** | OpenRouter (Claude, GPT-4o, Gemini, Qwen) or any compatible LLM |
| **Visual control panel** | Step-by-step workflow management—run stages independently or in sequence |
| **OpenClaw integration** | Invoke via [OpenClaw](https://clawhub.ai)—"remove spammers from my WeChat groups" |

---

## 🔄 How It Works

The agent uses a **Find–Click–Verify** pattern:

1. **Scaffolding Clicks** — Fixed-position clicks for known UI elements (menu buttons)
2. **Vision Queries** — Cropped screenshots sent to an LLM for dynamic element detection
3. **Merged Verify+Find** — Panel verification and button location in a single LLM call
4. **Verification** — Vision-based confirmation after each action (fast model)

```
┌──────────────────┐    ┌─────────┐    ┌──────────────────────┐
│  VERIFY + FIND   │───▶│  CLICK  │───▶│       VERIFY         │
│  (single call)   │    │         │    │   (fast model)       │
└──────────────────┘    └─────────┘    └──────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
  Heavy VLM returns     Execute click        Fast VLM confirms
  panel_opened +        at coordinates       success / failure
  button coordinates
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed workflow diagrams.

---

## 🚀 Quick Start

### Prerequisites

- **Windows 10/11** (macOS supported with `config/computer_mac.yaml` and screen coordinates)
- **Python 3.11+** (3.12 recommended)
- **OpenRouter API key** (or other supported LLM provider)

---

### Option A — Run the Installer *(recommended for first-time setup)*

```powershell
# Run once — installs dependencies, prompts for API key, creates desktop shortcut
.\install.ps1
```

Then double-click **"WeChat Removal Tool"** on your desktop.

---

### Option B — Manual Setup

1. **Set your API key** in `.env`:

   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the Control Panel**:

   ```bash
   .\start.ps1
   # or double-click start.bat
   ```

4. **Start the workflow**:
   - Click **Start Server** to launch the computer-server
   - Click **Start Workflow** to launch the workflow backend
   - Ensure WeChat is open and visible on screen
   - Step through: Classify → Filter → Read → Extract → Plan → Remove

---

### Option C — OpenClaw Skill

Use [OpenClaw](https://clawhub.ai) as your AI orchestrator? Install the bundled skill:

```powershell
$SkillsDir = "$env:USERPROFILE\clawd\skills\local"
Copy-Item -Recurse OpenClaw_WeChatRemoval_skill "$SkillsDir\wechat-removal"
```

Then ask OpenClaw: *"Remove spammers from my WeChat groups"*.

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for distribution channels and keeping wrappers in sync.

---

## 📁 Project Structure

```
.
├── config/                      # Configuration
│   ├── computer_windows.yaml   # Desktop settings (screen coords, button positions)
│   └── model.yaml              # AI model settings (model, verify_model, skills_dir)
├── runtime/                     # Session lifecycle
│   ├── computer_session.py
│   ├── model_session.py
│   └── llm_utils.py            # Shared LLM retry utility
├── modules/                     # Workflow components
│   ├── group_classifier.py
│   ├── unread_scanner.py
│   ├── message_reader.py
│   ├── suspicious_detector.py
│   ├── removal_precheck.py
│   ├── human_confirmation.py
│   └── removal_executor.py
├── skills/                      # Markdown playbooks
│   └── wechat_removal.md
├── workflow/
│   └── run_wechat_removal.py    # Entry point
├── artifacts/
│   ├── captures/
│   └── logs/
├── vendor/                      # Vendored CUA packages
├── OpenClaw_WeChatRemoval_skill/
├── install.ps1
├── start.ps1
└── docs/
    ├── ARCHITECTURE.md
    └── DISTRIBUTION.md
```

---

## ⚙️ Configuration

### `config/computer_windows.yaml`

```yaml
use_host_computer_server: true
os_type: windows
api_port: 8000
screen_width: 2560
screen_height: 1440
wechat_three_dots_x: 2525
wechat_three_dots_y: 48
wechat_delete_button_x: 1345
wechat_delete_button_y: 920
```

### `config/model.yaml`

```yaml
model: openrouter/qwen/qwen3-vl-32b-instruct      # Heavy: coordinate prediction
verify_model: openrouter/qwen/qwen2-vl-7b-instruct # Fast: yes/no checks
skills_dir: skills
max_trajectory_budget: 5.0
```

`verify_model` is optional—omitted or empty falls back to `model` for all calls.

### `skills/wechat_removal.md`

Markdown playbook injected into action prompts. Tune the agent's understanding of the WeChat UI without touching Python. Uses YAML frontmatter (`name`, `description`) and plain markdown for instructions.

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Vision system, Find–Click–Verify diagrams, dual-model routing, coordinate conversions, module diagrams |
| [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) | Standalone installer, OpenClaw skill setup, configuration reference, keeping wrappers in sync |

---

## 🔧 Extending

All vision queries use `runtime/llm_utils.llm_call_with_retry()`. To add a new action:

1. Add a prompt builder in the relevant `modules/` file
2. Add a response parser returning a typed dict
3. Call `run_cropped_vision_query()` or `run_vision_query()` from the workflow
4. Add `elif step == "your_step"` in `StepModeRunner.process_request()`
5. Optionally add rules to `skills/wechat_removal.md` or create a new skill

---

## 📦 Upstream

Built on [CUA (Computer Use Agents)](https://github.com/trycua/cua). The `vendor/` directory contains:

- **cua-agent** — AI agent framework
- **cua-computer** — Desktop control SDK
- **cua-computer-server** — HTTP API for UI interactions
- **cua-core** — Shared utilities and telemetry

---

## License

MIT License
