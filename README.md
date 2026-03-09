# WeChat Removal Tool

An AI-powered agent that automates the detection and removal of spam/scam users from WeChat groups. Built on the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform and runs directly on the host desktop.

## Features

- Automated spam/scam user detection in WeChat group chats
- Human-in-the-loop confirmation before removal
- Hybrid automation: fixed-position clicks + vision-guided detection
- Dual-model LLM routing: heavy model for coordinate prediction, fast model for yes/no checks
- Shared retry utility for all vision queries — extensible for future action types
- Skills system: workflow rules live in `skills/` markdown files, not in code
- Supports multiple LLM providers via OpenRouter (Claude, GPT-4o, Gemini, Qwen)
- Visual control panel for step-by-step workflow management

## How It Works

The agent uses a **Find-Click-Verify** pattern combining:

1. **Scaffolding Clicks**: Fixed-position clicks for known UI elements (menu buttons)
2. **Vision Queries**: Cropped screenshots sent to LLM for dynamic element detection
3. **Merged Verify+Find**: Panel verification and button location resolved in a single LLM call
4. **Verification**: Vision-based confirmation after each action, using a fast model

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

## Prerequisites

- Windows 10/11 (macOS supported — requires a `config/computer_mac.yaml` with screen coordinates)
- Python 3.11+ (3.12 recommended)
- OpenRouter API key (or other supported LLM provider)

## Quick Start

### Option A — Run the Installer (recommended for first-time setup)

```powershell
# Run once — installs dependencies, prompts for API key, creates desktop shortcut
.\install.ps1
```

Then double-click **"WeChat Removal Tool"** on your desktop.

### Option B — Manual Setup

1. **Set your API key** in `.env` file:
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the Control Panel**:
   ```bash
   # Double-click start.bat or run:
   .\start.ps1
   ```

4. **Start the workflow**:
   - Click "Start Server" to launch the computer-server
   - Click "Start Workflow" to launch the workflow backend
   - Make sure WeChat is open and visible on screen
   - Click through workflow steps: Classify → Filter → Read → Extract → Plan → Remove

### Option C — OpenClaw Skill

If you use [OpenClaw](https://clawhub.ai) as your AI orchestrator, install the bundled
skill so OpenClaw can invoke the tool on your behalf:

```powershell
$SkillsDir = "$env:USERPROFILE\clawd\skills\local"
Copy-Item -Recurse OpenClaw_WeChatRemoval_skill "$SkillsDir\wechat-removal"
```

Then ask OpenClaw: *"remove spammers from my WeChat groups"*.

See **[docs/DISTRIBUTION.md](docs/DISTRIBUTION.md)** for a full explanation of both
distribution channels and how to keep them in sync as the tool evolves.

## Project Structure

```
.
├── config/                  # Configuration files
│   ├── computer_windows.yaml    # Desktop settings (screen coords, button positions)
│   └── model.yaml               # AI model settings (model, verify_model, skills_dir)
├── runtime/                 # Session lifecycle managers
│   ├── computer_session.py      # Computer/sandbox setup
│   ├── model_session.py         # Agent configuration (ModelSettings)
│   └── llm_utils.py             # Shared LLM retry utility (llm_call_with_retry)
├── modules/                 # Workflow components
│   ├── task_types.py            # Data classes
│   ├── group_classifier.py      # Chat classification
│   ├── unread_scanner.py        # Unread filter
│   ├── message_reader.py        # Message reading prompts
│   ├── suspicious_detector.py   # Suspect extraction
│   ├── removal_precheck.py      # Removal planning
│   ├── human_confirmation.py    # User confirmation
│   └── removal_executor.py      # Removal execution (load_skill, merged prompts)
├── skills/                  # Skill markdown files
│   └── wechat_removal.md        # WeChat removal workflow rules and UI reference
├── workflow/                # Main orchestration
│   └── run_wechat_removal.py    # Entry point
├── artifacts/               # Output directory
│   ├── captures/                # Screenshots
│   └── logs/                    # Reports
├── vendor/                  # Vendored CUA packages
│   ├── agent/                   # cua-agent
│   ├── computer/                # cua-computer
│   ├── computer-server/         # cua-computer-server
│   └── core/                    # cua-core
├── OpenClaw_WeChatRemoval_skill/   # OpenClaw skill package
│   ├── SKILL.md                    # Skill descriptor (name, description, instructions)
│   ├── README.md                   # Setup guide for OpenClaw users
│   └── scripts/
│       └── run_wechat_removal.ps1  # Launcher called by OpenClaw
├── install.ps1              # One-shot installer (creates .env, desktop shortcut)
├── start.ps1                # Day-to-day launcher
├── start.bat                # Double-click launcher (calls start.ps1)
├── requirements.txt         # Python dependencies
└── docs/                    # Documentation
    ├── ARCHITECTURE.md          # Architecture details
    └── DISTRIBUTION.md          # Distribution channels (standalone app + OpenClaw skill)
```

## Configuration

### `config/computer_windows.yaml`

```yaml
use_host_computer_server: true
os_type: windows
api_port: 8000
screen_width: 2560
screen_height: 1440
# WeChat UI fixed button positions (absolute screen pixels)
wechat_three_dots_x: 2525
wechat_three_dots_y: 48
wechat_delete_button_x: 1345
wechat_delete_button_y: 920
```

### `config/model.yaml`

```yaml
model: openrouter/qwen/qwen3-vl-32b-instruct  # Heavy model: coordinate prediction
verify_model: openrouter/qwen/qwen2-vl-7b-instruct  # Fast model: yes/no checks
skills_dir: skills                             # Directory with skill .md files
max_trajectory_budget: 5.0
instructions: |
  你是一个专门处理微信群违规信息的助手...
```

`verify_model` is optional — if omitted or empty, falls back to `model` for all calls.

### `skills/wechat_removal.md`

Markdown playbook injected into action prompts at runtime. Edit this file to tune the agent's understanding of the WeChat UI without touching Python code. The file uses YAML frontmatter (`name`, `description`) and plain markdown for the instructions body.

## Output

Results are saved to `artifacts/logs/report.json`:

```json
{
  "timestamp": "2026-01-19T12:00:00.000000",
  "threads": [...],
  "suspects": [...],
  "removal_confirmed": true,
  "note": "Successfully removed 1 suspect"
}
```

## Documentation

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Complete architecture documentation including:
  - Agent vision system and crop regions
  - Find-Click-Verify workflow diagrams
  - Dual-model LLM routing
  - Coordinate system conversions
  - Module interaction diagrams
  - Vision prompt examples

- **[docs/DISTRIBUTION.md](docs/DISTRIBUTION.md)** - Distribution channels documentation including:
  - Standalone installer (`install.ps1`) walkthrough
  - OpenClaw skill setup and usage
  - How wrappers relate to the core tool
  - Configuration reference and dependency list
  - Guide for keeping wrappers up to date as the tool evolves

## Adding New Action Types

All vision queries go through `runtime/llm_utils.llm_call_with_retry()`. To add a new action:

1. Add a prompt builder function in the relevant `modules/` file
2. Add a response parser returning a typed dict
3. Call `run_cropped_vision_query()` (or `run_vision_query()`) from the workflow — both use `llm_call_with_retry` internally
4. Add a new `elif step == "your_step"` branch in `StepModeRunner.process_request()`
5. Optionally add rules to `skills/wechat_removal.md` or create a new skill file

## Upstream Reference

This project is built on the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform. The `vendor/` directory contains vendored copies of the following CUA packages:

- **cua-agent**: AI agent framework for computer-use tasks
- **cua-computer**: SDK for controlling desktop environments
- **cua-computer-server**: HTTP API for UI interactions inside sandboxes
- **cua-core**: Shared utilities and telemetry

For the original source code and documentation, visit the [CUA repository](https://github.com/trycua/cua).

## License

MIT License
