# WeChat Removal Tool

An AI-powered agent that automates the detection and removal of spam/scam users from WeChat groups. Built on the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform and runs directly on the host desktop.

## Features

- Automated spam/scam user detection in WeChat group chats
- Human-in-the-loop confirmation before removal
- Hybrid automation: fixed-position clicks + vision-guided detection
- Supports multiple LLM providers via OpenRouter (Claude, GPT-4o, Gemini)
- Visual control panel for step-by-step workflow management

## How It Works

The agent uses a **Find-Click-Verify** pattern combining:

1. **Scaffolding Clicks**: Fixed-position clicks for known UI elements (menu buttons)
2. **Vision Queries**: Cropped screenshots sent to LLM for dynamic element detection
3. **Verification**: Vision-based confirmation after each action

```
┌─────────┐         ┌─────────┐         ┌─────────┐
│  FIND   │────────▶│  CLICK  │────────▶│ VERIFY  │
└─────────┘         └─────────┘         └─────────┘
     │                   │                   │
     ▼                   ▼                   ▼
Vision query to     Execute click      Vision query to
locate element      at coordinates     confirm success
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed workflow diagrams.

## Prerequisites

- Windows 10/11 Pro
- Python 3.11+ (3.12 recommended)
- OpenRouter API key (or other supported LLM provider)

## Quick Start

1. **Set your API key** in `.env` file:
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

2. **Install dependencies**:
   ```bash
   pip install httpx aiohttp pydantic litellm pillow
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

## Project Structure

```
.
├── config/                  # Configuration files
│   ├── computer_windows.yaml    # Windows Sandbox settings
│   └── model.yaml               # AI model settings
├── runtime/                 # Session lifecycle managers
│   ├── computer_session.py      # Computer/sandbox setup
│   └── model_session.py         # Agent configuration
├── modules/                 # Workflow components
│   ├── task_types.py            # Data classes
│   ├── group_classifier.py      # Chat classification
│   ├── unread_scanner.py        # Unread filter
│   ├── message_reader.py        # Message reading prompts
│   ├── suspicious_detector.py   # Suspect extraction
│   ├── removal_precheck.py      # Removal planning
│   ├── human_confirmation.py    # User confirmation
│   └── removal_executor.py      # Removal execution
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
└── docs/                    # Documentation
    └── ARCHITECTURE.md          # Architecture details
```

## Configuration

### `config/computer_windows.yaml`

```yaml
provider_type: winsandbox
os_type: windows
display: "1280x720"
memory: "8GB"
cpu: "4"
timeout: 180
```

### `config/model.yaml`

```yaml
model: openrouter/anthropic/claude-sonnet-4
max_trajectory_budget: 5.0
instructions: |
  You are an assistant for managing WeChat group violations...
```

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
  - Coordinate system conversions
  - Module interaction diagrams
  - Vision prompt examples

## Upstream Reference

This project is built on the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform. The `vendor/` directory contains vendored copies of the following CUA packages:

- **cua-agent**: AI agent framework for computer-use tasks
- **cua-computer**: SDK for controlling desktop environments  
- **cua-computer-server**: HTTP API for UI interactions inside sandboxes
- **cua-core**: Shared utilities and telemetry

For the original source code and documentation, visit the [CUA repository](https://github.com/trycua/cua).

## License

MIT License
