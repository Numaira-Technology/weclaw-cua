# WeChat Removal Tool - Architecture Documentation

## Overview

The WeChat Removal Tool is an AI-powered agent that automates the detection and removal of spam/scam users from WeChat groups. It is built on top of the [CUA (Computer Use Agents)](https://github.com/trycua/cua) platform and runs directly on the host desktop.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Execution Flow](#execution-flow)
3. [Agent Vision System](#agent-vision-system)
4. [Find-Click-Verify Workflow](#find-click-verify-workflow)
5. [Coordinate Systems](#coordinate-systems)
6. [Workflow Stages](#workflow-stages)
7. [Configuration](#configuration)
8. [Troubleshooting](#troubleshooting)

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

## Agent Vision System

The agent uses a **hybrid approach** combining fixed-position clicks (scaffolding) with vision-based detection and verification. This provides reliability for known UI elements while maintaining flexibility for dynamic content.

### Vision Query Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VISION QUERY PIPELINE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │  Screenshot  │───▶│    Crop      │───▶│   Vision     │───▶│   Parse   │ │
│  │   (Full)     │    │   Region     │    │    LLM       │    │  Response │ │
│  └──────────────┘    └──────────────┘    └──────────────┘    └───────────┘ │
│        │                    │                   │                   │       │
│        ▼                    ▼                   ▼                   ▼       │
│   2560x1440px          Focused area       Claude/GPT-4o        JSON with   │
│   full screen          for faster         analyzes image       coordinates │
│                        upload                                   (0-1000)   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Crop Regions

The system uses three predefined crop regions to focus vision queries on relevant UI areas:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        2560 x 1440 SCREEN                                    │
│                                                                              │
│  ┌────────┐                                                    ┌──────────┐ │
│  │ CHAT   │                                                    │ MEMBER   │ │
│  │ LIST   │                                                    │ PANEL    │ │
│  │ REGION │              ┌─────────────────────┐               │ REGION   │ │
│  │        │              │   MEMBER_SELECT     │               │          │ │
│  │ 218x   │              │      REGION         │               │  260x    │ │
│  │ 1440   │              │                     │               │  1440    │ │
│  │        │              │     705 x 545       │               │          │ │
│  │ x:58-  │              │                     │               │ x:2300-  │ │
│  │   276  │              │   x:925-1630        │               │    2560  │ │
│  │ y:0-   │              │   y:425-970         │               │ y:0-     │ │
│  │   1440 │              │                     │               │    1440  │ │
│  │        │              └─────────────────────┘               │          │ │
│  │        │                                                    │          │ │
│  │        │                                                    │          │ │
│  └────────┘                                                    └──────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Region Usage:
├── CHAT_LIST_REGION (218x1440)    → Thread classification, clicking chats
├── MEMBER_PANEL_REGION (260x1440) → Panel verification, removal verification
└── MEMBER_SELECT_REGION (705x545) → Finding user checkboxes in removal dialog
```

---

## Find-Click-Verify Workflow

The core automation loop follows a **Find → Click → Verify** pattern for each action:

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FIND-CLICK-VERIFY LOOP                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌─────────┐         ┌─────────┐         ┌─────────┐                      │
│    │  FIND   │────────▶│  CLICK  │────────▶│ VERIFY  │                      │
│    └─────────┘         └─────────┘         └─────────┘                      │
│         │                   │                   │                            │
│         ▼                   ▼                   ▼                            │
│   Vision query to      Execute click      Vision query to                   │
│   locate element       at coordinates     confirm success                   │
│                                                                              │
│         │                   │                   │                            │
│         ▼                   ▼                   ▼                            │
│   ┌───────────┐       ┌───────────┐       ┌───────────┐                     │
│   │ Cropped   │       │ Scaffolding│      │ Cropped   │                     │
│   │ Screenshot│       │ (fixed) or │      │ Screenshot│                     │
│   │ + Prompt  │       │ Vision-    │      │ + Verify  │                     │
│   │           │       │ guided     │      │ Prompt    │                     │
│   └───────────┘       └───────────┘       └───────────┘                     │
│                                                                              │
│                              │                                               │
│                              ▼                                               │
│                    ┌─────────────────┐                                      │
│                    │  Success?       │                                      │
│                    │                 │                                      │
│                    │  Yes ──▶ Next   │                                      │
│                    │  No  ──▶ Retry  │                                      │
│                    └─────────────────┘                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Detailed Removal Workflow

The user removal process demonstrates the full find-click-verify pattern:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      USER REMOVAL WORKFLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  STEP 1: Open Group Info Panel                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [SCAFFOLDING CLICK]              [VISION VERIFY]                   │   │
│  │                                                                      │   │
│  │  Click three dots (...)  ────────▶  Verify panel opened             │   │
│  │  at fixed position                  using MEMBER_PANEL_REGION       │   │
│  │  (2525, 48)                                                         │   │
│  │                                                                      │   │
│  │  Prompt: verify_panel_opened_prompt()                               │   │
│  │  Response: {"panel_opened": true/false}                             │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 2: Enter Removal Mode                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [VISION FIND]                       [VISION VERIFY]                │   │
│  │                                                                      │   │
│  │  Crop MEMBER_PANEL_REGION ──────────▶ AI returns coordinates ─────▶ │   │
│  │  Send to LLM with prompt             in 0-1000 normalized           │   │
│  │  "Find minus button"                 space                          │   │
│  │                                                                      │   │
│  │  Prompt: find_minus_button_prompt()                                 │   │
│  │  Response: {"button_found": true, "click_x": 800, "click_y": 150}   │   │
│  │                                                                      │   │
│  │                    │                                                 │   │
│  │                    ▼                                                 │   │
│  │           Convert coordinates:                                       │   │
│  │           NORMALIZED (0-1000) ──▶ SCREEN (pixels)                   │   │
│  │           Using: MEMBER_PANEL_REGION.normalized_to_screen_coords()  │   │
│  │                                                                      │   │
│  │                    │                                                 │   │
│  │                    ▼                                                 │   │
│  │           Click at calculated screen position                        │   │
│  │                                                                      │   │
│  │                    │                                                 │   │
│  │                    ▼                                                 │   │
│  │           Verify dialog opened using MEMBER_SELECT_REGION           │   │
│  │           Prompt: verify_member_dialog_opened_prompt()              │   │
│  │           Response: {"dialog_opened": true/false}                   │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 3: Find and Select User                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [VISION FIND]                    [VISION-GUIDED CLICK]             │   │
│  │                                                                      │   │
│  │  Crop MEMBER_SELECT_REGION ──────▶ AI returns coordinates ────────▶ │   │
│  │  Send to LLM with prompt          in 0-1000 normalized              │   │
│  │  "Find user checkbox"             space                              │   │
│  │                                                                      │   │
│  │  Prompt: select_user_for_removal_prompt(user_name)                  │   │
│  │  Response: {"user_found": true, "click_x": 100, "click_y": 300}     │   │
│  │                                                                      │   │
│  │                    │                                                 │   │
│  │                    ▼                                                 │   │
│  │           Convert coordinates:                                       │   │
│  │           NORMALIZED (0-1000) ──▶ SCREEN (pixels)                   │   │
│  │           Using: MEMBER_SELECT_REGION.normalized_to_screen_coords() │   │
│  │                                                                      │   │
│  │                    │                                                 │   │
│  │                    ▼                                                 │   │
│  │           Click at calculated screen position                        │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 4: Confirm Removal                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [SCAFFOLDING CLICK]              [VISION VERIFY]                   │   │
│  │                                                                      │   │
│  │  Click delete button  ───────────▶ Verify user removed              │   │
│  │  at fixed position                 using MEMBER_PANEL_REGION        │   │
│  │  (1345, 920)                                                        │   │
│  │                                                                      │   │
│  │  Prompt: verify_removal_prompt(user_name)                           │   │
│  │  Response: {"user_removed": true/false}                             │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│                    ┌─────────────────┐                                     │
│                    │ user_removed?   │                                     │
│                    │                 │                                     │
│                    │ Yes ──▶ Success │                                     │
│                    │ No  ──▶ Retry   │                                     │
│                    └─────────────────┘                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Click Types

The system uses two types of clicks:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLICK TYPES                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────┐    ┌─────────────────────────────────────┐│
│  │    SCAFFOLDING CLICKS       │    │       VISION-GUIDED CLICKS          ││
│  │    (Fixed Positions)        │    │       (Dynamic Positions)           ││
│  ├─────────────────────────────┤    ├─────────────────────────────────────┤│
│  │                             │    │                                      ││
│  │  Used for:                  │    │  Used for:                          ││
│  │  • Three dots button (...)  │    │  • Minus button (-) in member panel ││
│  │  • Delete button (移出)     │    │  • User checkboxes in member list   ││
│  │                             │    │  • Chat threads in sidebar          ││
│  │                             │    │  • Any dynamic UI element           ││
│  │  Coordinates:               │    │                                      ││
│  │  • Hardcoded in config      │    │  Coordinates:                       ││
│  │  • SCREEN space (pixels)    │    │  • AI returns 0-1000 normalized     ││
│  │                             │    │  • Converted to SCREEN pixels       ││
│  │  Reliability:               │    │                                      ││
│  │  • 100% (position fixed)    │    │  Reliability:                       ││
│  │  • Fast (no vision query)   │    │  • Depends on AI accuracy           ││
│  │                             │    │  • Retry logic on failure           ││
│  │  Source:                    │    │                                      ││
│  │  • scaffolding_clicks.py    │    │  Source:                            ││
│  │  • computer_windows.yaml    │    │  • removal_executor.py prompts      ││
│  │                             │    │  • crop_utils.py conversion         ││
│  └─────────────────────────────┘    └─────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Coordinate Systems

The system uses three coordinate systems that must be carefully converted:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COORDINATE SYSTEMS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. SCREEN COORDINATES (Absolute Pixels)                                    │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │  • Used for: Clicking on screen                                    │  │
│     │  • Range: (0,0) to (2560,1440) for 2K display                     │  │
│     │  • Origin: Top-left corner of screen                              │  │
│     │  • Example: Three dots button at (2525, 48)                       │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  2. CROP COORDINATES (Pixels within cropped image)                          │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │  • Used for: Internal coordinate math                              │  │
│     │  • Range: (0,0) to (width, height) of crop region                 │  │
│     │  • Origin: Top-left corner of cropped image                       │  │
│     │  • Example: MEMBER_SELECT_REGION is 705x545 pixels                │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  3. NORMALIZED COORDINATES (0-1000 scale)                                   │
│     ┌───────────────────────────────────────────────────────────────────┐  │
│     │  • Used for: AI vision responses                                   │  │
│     │  • Range: (0,0) to (1000,1000) regardless of image size           │  │
│     │  • Origin: Top-left = (0,0), Bottom-right = (1000,1000)           │  │
│     │  • Example: Center of image = (500, 500)                          │  │
│     └───────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  CONVERSION FLOW:                                                           │
│                                                                              │
│     AI Response          crop_utils.py           Computer Interface         │
│    ┌───────────┐       ┌─────────────────┐       ┌───────────────┐         │
│    │ NORMALIZED│──────▶│ normalized_to_  │──────▶│    SCREEN     │         │
│    │ (0-1000)  │       │ screen_coords() │       │   (pixels)    │         │
│    └───────────┘       └─────────────────┘       └───────────────┘         │
│                                                                              │
│  Example conversion for MEMBER_SELECT_REGION (925-1630, 425-970):          │
│                                                                              │
│    NORMALIZED (500, 500)                                                    │
│         │                                                                   │
│         ▼                                                                   │
│    CROP: x = 500/1000 * 705 = 352                                          │
│          y = 500/1000 * 545 = 272                                          │
│         │                                                                   │
│         ▼                                                                   │
│    SCREEN: x = 352 + 925 = 1277                                            │
│            y = 272 + 425 = 697                                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
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

---

## Complete Workflow Diagram

The following diagram shows the entire workflow from start to finish:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE WORKFLOW DIAGRAM                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         INITIALIZATION                                       │   │
│  │                                                                              │   │
│  │   start.ps1 ──▶ Load .env ──▶ Launch control_panel.py                       │   │
│  │                                     │                                        │   │
│  │                     ┌───────────────┴───────────────┐                       │   │
│  │                     ▼                               ▼                        │   │
│  │            [Start Server]                  [Start Workflow]                  │   │
│  │                     │                               │                        │   │
│  │                     ▼                               ▼                        │   │
│  │         computer-server:8000              workflow backend                   │   │
│  │         (screenshots, clicks)             (step-mode, LLM)                   │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                    STAGE 1: CLASSIFY THREADS                                 │   │
│  │                                                                              │   │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │   │
│  │   │ Crop chat    │───▶│ Send to LLM  │───▶│ Parse JSON   │                  │   │
│  │   │ list region  │    │ with prompt  │    │ response     │                  │   │
│  │   │ (218x1440)   │    │              │    │              │                  │   │
│  │   └──────────────┘    └──────────────┘    └──────────────┘                  │   │
│  │                                                  │                           │   │
│  │   Output: List of threads with:                  ▼                           │   │
│  │   • name, y-coordinate, is_group, unread    [GroupThread]                   │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                    STAGE 2: FILTER UNREAD                                    │   │
│  │                                                                              │   │
│  │   All threads ──▶ Filter(is_group=True, unread=True) ──▶ Unread groups     │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                    PER-GROUP PROCESSING LOOP                                 │   │
│  │                                                                              │   │
│  │   ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │   │  For each unread group:                                             │   │   │
│  │   │                                                                      │   │   │
│  │   │  ┌───────────────────────────────────────────────────────────────┐  │   │   │
│  │   │  │ STAGE 3: READ MESSAGES                                        │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  │  1. Click chat at y-coordinate (scaffolding)                  │  │   │   │
│  │   │  │  2. Take full screenshot                                      │  │   │   │
│  │   │  │  3. Send to LLM: "Read messages, identify spam"               │  │   │   │
│  │   │  │  4. Parse response for suspects                               │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  └───────────────────────────────────────────────────────────────┘  │   │   │
│  │   │                              │                                       │   │   │
│  │   │                              ▼                                       │   │   │
│  │   │  ┌───────────────────────────────────────────────────────────────┐  │   │   │
│  │   │  │ STAGE 4: EXTRACT SUSPECTS                                     │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  │  Parse AI response ──▶ List of Suspect objects                │  │   │   │
│  │   │  │  • sender_name, sender_id, evidence_text                      │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  └───────────────────────────────────────────────────────────────┘  │   │   │
│  │   │                              │                                       │   │   │
│  │   │                              ▼                                       │   │   │
│  │   │  ┌───────────────────────────────────────────────────────────────┐  │   │   │
│  │   │  │ STAGE 5: BUILD PLAN                                           │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  │  Suspects ──▶ RemovalPlan (requires human confirmation)       │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  └───────────────────────────────────────────────────────────────┘  │   │   │
│  │   │                              │                                       │   │   │
│  │   │                              ▼                                       │   │   │
│  │   │  ┌───────────────────────────────────────────────────────────────┐  │   │   │
│  │   │  │ STAGE 6: EXECUTE REMOVAL (Find-Click-Verify Loop)             │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  │  For each suspect in plan:                                    │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  │    ┌─────────────────────────────────────────────────────┐   │  │   │   │
│  │   │  │    │ STEP 1: Open Panel (first suspect only)             │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    │  [CLICK] Three dots at (2525, 48)                   │   │  │   │   │
│  │   │  │    │  [VERIFY] Crop MEMBER_PANEL_REGION                  │   │  │   │   │
│  │   │  │    │           LLM: "Is panel open?"                     │   │  │   │   │
│  │   │  │    │           Response: {"panel_opened": true}          │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    └─────────────────────────────────────────────────────┘   │  │   │   │
│  │   │  │                          │                                    │  │   │   │
│  │   │  │                          ▼                                    │  │   │   │
│  │   │  │    ┌─────────────────────────────────────────────────────┐   │  │   │   │
│  │   │  │    │ STEP 2: Enter Removal Mode (first suspect only)     │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    │  [CLICK] Minus button at (2525, 200)                │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    └─────────────────────────────────────────────────────┘   │  │   │   │
│  │   │  │                          │                                    │  │   │   │
│  │   │  │                          ▼                                    │  │   │   │
│  │   │  │    ┌─────────────────────────────────────────────────────┐   │  │   │   │
│  │   │  │    │ STEP 3: Find User Checkbox                          │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    │  [FIND] Crop MEMBER_SELECT_REGION (705x545)         │   │  │   │   │
│  │   │  │    │         LLM: "Find checkbox for 'username'"         │   │  │   │   │
│  │   │  │    │         Response: {"click_x": 100, "click_y": 300}  │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    │  [CONVERT] Normalized → Screen coordinates          │   │  │   │   │
│  │   │  │    │            (100, 300) → (995, 588)                  │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    │  [CLICK] User checkbox at calculated position       │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    └─────────────────────────────────────────────────────┘   │  │   │   │
│  │   │  │                          │                                    │  │   │   │
│  │   │  │                          ▼                                    │  │   │   │
│  │   │  │    ┌─────────────────────────────────────────────────────┐   │  │   │   │
│  │   │  │    │ STEP 4: Confirm Removal                             │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    │  [CLICK] Delete button at (1345, 920)               │   │  │   │   │
│  │   │  │    │  [VERIFY] Crop MEMBER_PANEL_REGION                  │   │  │   │   │
│  │   │  │    │           LLM: "Is user removed?"                   │   │  │   │   │
│  │   │  │    │           Response: {"user_removed": true}          │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    │  If failed: Retry from STEP 3 (max 2 retries)       │   │  │   │   │
│  │   │  │    │                                                      │   │  │   │   │
│  │   │  │    └─────────────────────────────────────────────────────┘   │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  │  Next suspect ──▶ Loop back to STEP 3                         │  │   │   │
│  │   │  │                                                                │  │   │   │
│  │   │  └───────────────────────────────────────────────────────────────┘  │   │   │
│  │   │                                                                      │   │   │
│  │   │  ──▶ Next group (loop back to STAGE 3)                              │   │   │
│  │   │                                                                      │   │   │
│  │   └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         EXPORT REPORT                                        │   │
│  │                                                                              │   │
│  │   Save to artifacts/logs/report.json:                                       │   │
│  │   • All threads classified                                                   │   │
│  │   • All suspects found                                                       │   │
│  │   • Removal results per suspect                                              │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           MODULE INTERACTIONS                                        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          CONTROL LAYER                                       │   │
│  │                                                                              │   │
│  │  control_panel.py ◄──────────────────────────────────────────────────────┐  │   │
│  │       │                                                                   │  │   │
│  │       │ Step requests (.step_request)                                    │  │   │
│  │       ▼                                                                   │  │   │
│  │  workflow/run_wechat_removal.py                                          │  │   │
│  │       │                                                                   │  │   │
│  │       │ StepModeRunner                                                   │  │   │
│  │       │    ├── handle_classify()                                         │  │   │
│  │       │    ├── handle_read_messages()                                    │  │   │
│  │       │    └── handle_remove()                                           │  │   │
│  │       │                                                                   │  │   │
│  │       │ Step results (.step_result, .step_status)                        │  │   │
│  │       └──────────────────────────────────────────────────────────────────┘  │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          MODULES LAYER                                       │   │
│  │                                                                              │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │   │
│  │  │ group_classifier │  │ message_reader   │  │ removal_executor         │  │   │
│  │  │                  │  │                  │  │                          │  │   │
│  │  │ • Prompt builder │  │ • Prompt builder │  │ • Prompt builders:       │  │   │
│  │  │ • Response parser│  │ • Response parser│  │   - verify_panel_opened  │  │   │
│  │  │                  │  │                  │  │   - select_user_for_     │  │   │
│  │  │                  │  │                  │  │     removal              │  │   │
│  │  │                  │  │                  │  │   - verify_removal       │  │   │
│  │  │                  │  │                  │  │ • Response parsers       │  │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │   │
│  │                                                                              │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │   │
│  │  │ crop_utils       │  │ scaffolding_     │  │ task_types              │  │   │
│  │  │                  │  │ clicks           │  │                          │  │   │
│  │  │ • CropRegion     │  │                  │  │ • GroupThread           │  │   │
│  │  │ • CHAT_LIST_     │  │ • click_three_   │  │ • Suspect               │  │   │
│  │  │   REGION         │  │   dots()         │  │ • RemovalPlan           │  │   │
│  │  │ • MEMBER_PANEL_  │  │ • click_minus_   │  │ • RemovalResult         │  │   │
│  │  │   REGION         │  │   button()       │  │                          │  │   │
│  │  │ • MEMBER_SELECT_ │  │ • click_delete_  │  │                          │  │   │
│  │  │   REGION         │  │   confirm()      │  │                          │  │   │
│  │  │ • normalized_to_ │  │                  │  │                          │  │   │
│  │  │   screen_coords()│  │                  │  │                          │  │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          RUNTIME LAYER                                       │   │
│  │                                                                              │   │
│  │  ┌──────────────────────────┐    ┌──────────────────────────────────────┐  │   │
│  │  │ computer_session.py      │    │ model_session.py                     │  │   │
│  │  │                          │    │                                      │  │   │
│  │  │ • load_computer_settings │    │ • load_model_settings               │  │   │
│  │  │ • build_computer()       │    │ • build_agent()                     │  │   │
│  │  │ • ComputerSettings       │    │ • ModelSettings                     │  │   │
│  │  │   (button positions)     │    │   (LLM config)                      │  │   │
│  │  │                          │    │                                      │  │   │
│  │  └──────────────────────────┘    └──────────────────────────────────────┘  │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          VENDOR LAYER (CUA)                                  │   │
│  │                                                                              │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────────────┐│   │
│  │  │ vendor/agent   │  │ vendor/computer│  │ vendor/computer-server        ││   │
│  │  │                │  │                │  │                                ││   │
│  │  │ ComputerAgent  │  │ Computer       │  │ HTTP API (port 8000)          ││   │
│  │  │ AgentSession   │  │ interface:     │  │ • screenshot()                ││   │
│  │  │                │  │ • screenshot() │  │ • left_click(x, y)            ││   │
│  │  │                │  │ • left_click() │  │ • type()                      ││   │
│  │  │                │  │ • type()       │  │                                ││   │
│  │  └────────────────┘  └────────────────┘  └────────────────────────────────┘│   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          EXTERNAL SERVICES                                   │   │
│  │                                                                              │   │
│  │  ┌────────────────────────────┐    ┌────────────────────────────────────┐  │   │
│  │  │ LLM Provider (OpenRouter)  │    │ WeChat Desktop Application         │  │   │
│  │  │                            │    │                                    │  │   │
│  │  │ • Claude Sonnet 4          │    │ • Running on host machine          │  │   │
│  │  │ • GPT-4o                   │    │ • Logged in with groups            │  │   │
│  │  │ • Gemini                   │    │ • Visible on screen                │  │   │
│  │  │                            │    │                                    │  │   │
│  │  └────────────────────────────┘    └────────────────────────────────────┘  │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Vision Prompt Examples

### Thread Classification Prompt

```
这是微信会话列表的裁剪截图（宽218像素，高1440像素）。
分析截图中可见的每个会话，从上到下依次列出。
使用头像图标区分群聊（多人头像/九宫格）与单聊（单人头像）。

Response format:
{"threads": [{"name": "群名", "y": 73, "is_group": true, "unread": true}, ...]}
```

### User Selection Prompt

```
这是成员选择对话框的裁剪截图（宽705像素，高545像素）。
任务：找到用户「代写论文」的灰色圆形选择框位置

坐标说明：
- 使用0-1000归一化坐标系
- x=0表示截图最左边，x=1000表示最右边
- y=0表示截图最上边，y=1000表示最下边

Response format:
{"user_found": true, "user_name": "代写论文", "click_x": 100, "click_y": 300}
```

### Removal Verification Prompt

```
这是屏幕右侧边缘的裁剪截图（宽260像素，高1440像素）。
刚才已点击了移出按钮。

请验证：用户「代写论文」是否已从成员列表中移除？

Response format:
{"user_removed": true, "user_name": "代写论文"}
```
