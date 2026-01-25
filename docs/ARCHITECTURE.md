# WeChat Removal Tool - Architecture Documentation

## Overview

The WeChat Removal Tool is an AI-powered agent that automates the detection and removal of spam/scam users from WeChat groups. It is built on top of the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform and runs directly on the host desktop.

---

## Project Structure

```
.
├── config/                          # Configuration files
│   ├── computer_windows.yaml        # Desktop mode settings
│   └── model.yaml                   # AI model settings (OpenRouter)
│
├── runtime/                         # Session lifecycle managers
│   ├── computer_session.py          # Builds Computer from config
│   └── model_session.py             # Builds ComputerAgent from config
│
├── modules/                         # Workflow components (stateless)
│   ├── task_types.py                # Data classes: GroupThread, Suspect, RemovalPlan
│   ├── group_classifier.py          # Classifies chats as group/individual
│   ├── unread_scanner.py            # Filters to unread group chats
│   ├── message_reader.py            # Prompts to read messages
│   ├── suspicious_detector.py       # Extracts suspects from output
│   ├── removal_precheck.py          # Builds removal plan
│   ├── human_confirmation.py        # Requires operator confirmation
│   └── removal_executor.py          # Executes removals
│
├── workflow/                        # Main orchestration
│   └── run_wechat_removal.py        # Entry point (step-mode backend)
│
├── control_panel.py                 # Visual GUI for step-by-step control
├── panel_state.py                   # State persistence for control panel
│
├── artifacts/                       # Output directory
│   ├── captures/                    # Screenshots
│   ├── panel_state.json             # Control panel state
│   └── logs/
│       └── report.json              # Final report
│
├── vendor/                          # Vendored CUA components
│   ├── agent/                       # cua-agent: AI agent framework
│   ├── computer/                    # cua-computer: computer control
│   ├── computer-server/             # cua-computer-server: local API server
│   └── core/                        # cua-core: shared utilities
│
├── docs/
│   └── ARCHITECTURE.md              # This file
│
├── .env                             # API keys (OPENROUTER_API_KEY)
├── start.bat                        # Double-click to launch Control Panel
├── start.ps1                        # PowerShell launcher script
├── pyproject.toml                   # Python project config
└── README.md                        # Project documentation
```

---

## Execution Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                          HOST MACHINE                                │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  start.ps1 / start.bat                                         │  │
│  │  1. Load .env for API key                                      │  │
│  │  2. Launch control_panel.py                                    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  control_panel.py (Visual GUI)                                 │  │
│  │                                                                │  │
│  │  Server Control:                                               │  │
│  │  ├── [Start Server] → computer-server on port 8000            │  │
│  │  └── [Start Workflow] → workflow backend in step-mode         │  │
│  │                                                                │  │
│  │  Workflow Steps:                                               │  │
│  │  ├── [📂] [1. Classify Threads] → Agent scans WeChat          │  │
│  │  ├── [📂] [2. Filter Unread] → Filters to unread groups       │  │
│  │  │                                                             │  │
│  │  │   ┌─── Per-Group Loop (for each unread group) ───┐         │  │
│  │  │   │                                               │         │  │
│  │  ├── │ [📂] [3. Read Messages] → Reads this group   │         │  │
│  │  ├── │ [📂] [4. Extract Suspects] → Parses suspects │         │  │
│  │  ├── │ [📂] [5. Build Plan] → Creates removal plan  │         │  │
│  │  └── │ [📂] [6. Execute Removal] → Removes suspects │         │  │
│  │      │                                               │         │  │
│  │      └───────────────────────────────────────────────┘         │  │
│  │                                                                │  │
│  │  📂 = Load manual data for independent testing                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│              ┌───────────────┼───────────────┐                      │
│              ▼               ▼               ▼                      │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       │
│  │ computer-server │ │ workflow backend│ │ WeChat Desktop  │       │
│  │ (port 8000)     │ │ (step-mode)     │ │ (user's app)    │       │
│  │                 │ │                 │ │                 │       │
│  │ - Screenshots   │ │ - ComputerAgent │ │ - Already       │       │
│  │ - Mouse/kbd     │ │ - LLM calls     │ │   installed     │       │
│  │ - Automation    │ │ - Task prompts  │ │ - Logged in     │       │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Workflow Stages

### Stage 1: Server Initialization

User clicks "Start Server" in Control Panel:

```python
# Starts computer-server on localhost:8000
python -m computer_server --host 0.0.0.0 --port 8000
```

### Stage 2: Workflow Backend

User clicks "Start Workflow" in Control Panel:

```python
# Starts workflow in step-mode, waiting for commands
python -m workflow.run_wechat_removal --step-mode
```

The backend:
1. Loads configs (computer_windows.yaml, model.yaml)
2. Creates Computer(use_host_computer_server=True)
3. Connects to local computer-server
4. Waits for step requests from Control Panel

### Stage 3: Classification

User clicks "1. Classify Threads" in Control Panel:

```python
classification_output, _ = await run_agent_task(
    agent, classification_prompt(), capture_dir, "classification"
)
threads = parse_classification(classification_output)
```

Agent:
1. Takes screenshot of WeChat
2. LLM identifies all chat threads
3. Classifies each as group/individual, read/unread

### Stage 4: Filter Unread

User clicks "2. Filter Unread" in Control Panel:

```python
unread_groups = filter_unread_groups(threads)
```

Filters threads to only unread group chats. After this step, the workflow enters a **per-group loop**.

---

### Per-Group Processing Loop

**For each unread group**, the following stages (5-8) are executed in sequence before moving to the next group. This ensures each group is fully processed (read → extract → plan → remove) before the workflow advances.

```
┌─────────────────────────────────────────────────────────────┐
│  For each unread_group in unread_groups:                    │
│                                                             │
│    Stage 5: Read Messages (this group)                      │
│         ↓                                                   │
│    Stage 6: Extract Suspects (this group)                   │
│         ↓                                                   │
│    Stage 7: Build Plan (this group)                         │
│         ↓                                                   │
│    Stage 8: Execute Removal (this group, with confirmation) │
│         ↓                                                   │
│    → Move to next group                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Stage 5: Read Messages (Per Group)

User clicks "3. Read Messages" in Control Panel:

```python
reader_output, reader_shots = await run_agent_task(
    agent, message_reader_prompt(current_group), capture_dir, f"reader_{current_group.thread_id}"
)
```

For the **current** unread group:
1. Agent navigates to the chat
2. Reads recent messages
3. Identifies suspicious content (e.g., "代写")
4. Records sender info and evidence

### Stage 6: Extract Suspects (Per Group)

User clicks "4. Extract Suspects" in Control Panel:

```python
suspects = extract_suspects(current_group, reader_output, reader_shots)
```

Parses suspect information from read results **for this group only**.

### Stage 7: Build Plan (Per Group)

User clicks "5. Build Plan" in Control Panel:

```python
plan = build_removal_plan(suspects)
```

Creates removal plan from suspects found **in this group**.

### Stage 8: Execute Removal (Per Group)

User clicks "6. Execute Removal" in Control Panel:

```python
# Confirmation dialog shown first
if plan.confirmed:
    removal_output, _ = await run_agent_task(
        agent, removal_prompt(plan), capture_dir, f"removal_{current_group.thread_id}"
    )
```

Agent removes confirmed suspects **from this group**. After completion, the workflow advances to the next unread group.

---

### Stage 9: Export Report

User clicks "Export Report" in Control Panel:

```python
_persist_report(root, threads, all_suspects, all_plans)
```

Saves JSON report to `artifacts/logs/panel_report.json` with results from all processed groups.

---

## Configuration

### `config/computer_windows.yaml`

```yaml
use_host_computer_server: true      # Desktop mode (connects to local server)
os_type: windows                    # Operating system
api_port: 8000                      # Computer server port
display: "1280x720"                 # Screen resolution
timeout: 180                        # Connection timeout (seconds)
telemetry_enabled: false            # Disable telemetry
screenshot_delay: 0.5               # Delay before screenshots
```

### `config/model.yaml`

```yaml
model: openrouter/anthropic/claude-sonnet-4  # LLM via OpenRouter
max_trajectory_budget: 5.0                    # Max cost in USD
instructions: |                               # System prompt
  你是一个专门处理微信群违规信息的助手...
use_prompt_caching: false                     # Caching (Anthropic-only)
screenshot_delay: 0.5                         # Delay before screenshots
telemetry_enabled: false                      # Disable telemetry
```

---

## Model Support

Via LiteLLM and OpenRouter, supports:

| Provider | Model Examples |
|----------|----------------|
| OpenRouter | `openrouter/anthropic/claude-sonnet-4`, `openrouter/openai/gpt-4o` |
| Anthropic | `anthropic/claude-sonnet-4-20250514` |
| OpenAI | `openai/computer-use-preview` |
| Google | `gemini/gemini-2.5-flash-preview` |
| Azure | `azure/deployment-name` |
| Ollama | `omniparser+ollama_chat/llava` |
| Local | `huggingface-local/ByteDance-Seed/UI-TARS-1.5-7B` |

---

## Output

### `artifacts/logs/report.json`

```json
{
  "timestamp": "2026-01-19T12:00:00.000000",
  "threads": [
    {
      "thread_id": "group_1",
      "name": "留学交流群",
      "type": "group",
      "unread_count": 5
    }
  ],
  "suspects": [
    {
      "sender_id": "wxid_xxx",
      "sender_name": "代写论文",
      "avatar_path": "artifacts/captures/avatar_1.png",
      "evidence_text": "专业代写，联系微信xxx",
      "thread_id": "group_1"
    }
  ],
  "removal_confirmed": true,
  "note": "Successfully removed 1 suspect"
}
```

---

## Troubleshooting

### Desktop Mode Issues

#### "Computer API Server not ready"

The workflow is waiting for computer-server to start.

**Fix:**
1. Click "Start Server" in the Control Panel
2. Wait for status to show "Running"
3. Then click "Start Workflow"

#### Server fails to start

Check if port 8000 is already in use:
```powershell
netstat -ano | findstr :8000
```

If another process is using the port, either stop it or change `api_port` in config.

#### Agent not responding

1. Make sure both Server and Workflow show "Running" status
2. Check the log area in Control Panel for errors
3. Verify WeChat is open and visible on screen

### Model Issues

#### API key errors

Set environment variable:
```powershell
$env:OPENROUTER_API_KEY = "sk-or-v1-..."
```

#### Budget exceeded

Increase `max_trajectory_budget` in model.yaml or reset agent.

### Python Version

CUA requires Python 3.11+ (some features need 3.12).

The vendored code has been patched for Python 3.11 compatibility:
- `typing.override` -> `typing_extensions.override`

---

## Dependencies

### Host Machine

```
# Core
httpx, aiohttp, anyio        # Async HTTP
pydantic                     # Data validation
litellm                      # LLM abstraction
typing-extensions            # Python 3.11 compat

# Computer Server
uvicorn, fastapi             # HTTP server
pynput                       # Mouse/keyboard control
pillow                       # Screenshots

# UI
tkinter                      # Control Panel GUI (built-in)
```

---

## Vendored CUA Packages

The `vendor/` directory contains **copies** of CUA packages from the upstream repository:

| Vendored Package | Upstream Source |
|------------------|-----------------|
| `vendor/agent/` | [cua-agent](https://github.com/trycua/cua/tree/main/libs/python/agent) |
| `vendor/computer/` | [cua-computer](https://github.com/trycua/cua/tree/main/libs/python/computer) |
| `vendor/computer-server/` | [cua-computer-server](https://github.com/trycua/cua/tree/main/libs/python/computer-server) |
| `vendor/core/` | [cua-core](https://github.com/trycua/cua/tree/main/libs/python/core) |

The packages are vendored to:
1. Avoid version conflicts
2. Allow local patches (e.g., Python 3.11 compat)
3. Work without installing CUA globally

To update vendored code, copy from the [upstream CUA repository](https://github.com/trycua/cua) and reapply any local patches.

---

## Control Panel Features

The Control Panel (`control_panel.py`) provides:

### Server Control
- **Start/Stop Server**: Manages the computer-server process
- **Start/Stop Workflow**: Manages the workflow backend process

### Workflow Steps
Steps 1-2 run once globally. Steps 3-6 run **per group** in a loop:

| Step | Description | Scope | Manual Input |
|------|-------------|-------|--------------|
| 1. Classify Threads | Agent scans WeChat chat list | Global | N/A |
| 2. Filter Unread | Filters to unread groups | Global | Load threads JSON |
| 3. Read Messages | Reads messages in current group | Per Group | Load groups JSON |
| 4. Extract Suspects | Parses suspect info from current group | Per Group | Load read results JSON |
| 5. Build Plan | Creates removal plan for current group | Per Group | Load suspects JSON |
| 6. Execute Removal | Removes suspects from current group | Per Group | Load plan JSON |

After step 6 completes for a group, the workflow automatically advances to the next unread group and returns to step 3.

### Manual Input (📂 buttons)
Each step (except Classify) has a load button that allows:
- Loading data from a JSON file
- Pasting JSON directly

This enables independent testing of each step without running previous steps.

### State Management
- State is persisted to `artifacts/panel_state.json`
- "Reset State" clears all workflow state
- "Export Report" saves results to `artifacts/logs/panel_report.json`
