# WeChat Removal Tool

An AI-powered agent that automates the detection and removal of spam/scam users from WeChat groups. Built on the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform and runs inside a Windows Sandbox for isolation.

## Features

- Automated spam/scam user detection in WeChat group chats
- Human-in-the-loop confirmation before removal
- Runs in isolated Windows Sandbox environment
- Supports multiple LLM providers via OpenRouter

## Prerequisites

- Windows 10/11 Pro (with Windows Sandbox enabled)
- Python 3.12+
- OpenRouter API key (or other supported LLM provider)

## Quick Start

1. **Enable Windows Sandbox** (if not already enabled):
   ```powershell
   Enable-WindowsOptionalFeature -FeatureName "Containers-DisposableClientVM" -All -Online
   ```

2. **Set your API key**:
   ```powershell
   $env:OPENROUTER_API_KEY = "sk-or-v1-..."
   ```

3. **Install dependencies**:
   ```bash
   pip install httpx aiohttp pydantic litellm pywinsandbox pillow rich
   ```

4. **Run the workflow**:
   ```bash
   python -m workflow.run_wechat_removal
   ```

5. **Follow the prompts**:
   - Wait for the sandbox to start
   - Install WeChat from the shared folder (`Desktop/cua/WeChatWin_4.1.6.exe`)
   - Log in and wait for messages to sync
   - Type `ready` to start the automated workflow

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

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## Upstream Reference

This project is built on the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform. The `vendor/` directory contains vendored copies of the following CUA packages:

- **cua-agent**: AI agent framework for computer-use tasks
- **cua-computer**: SDK for controlling desktop environments  
- **cua-computer-server**: HTTP API for UI interactions inside sandboxes
- **cua-core**: Shared utilities and telemetry

For the original source code and documentation, visit the [CUA repository](https://github.com/trycua/cua).

## License

MIT License
