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
8. [Performance Architecture](#performance-architecture)
9. [Skills System](#skills-system)
10. [Adding New Actions](#adding-new-actions)
11. [Troubleshooting](#troubleshooting)

> **Platform differences (Windows vs macOS)** — screenshot strategy, coordinate spaces, click delivery, AX tree vs scaffolding, and per-platform prompt wording are documented separately in [PLATFORM_GUIDE.md](PLATFORM_GUIDE.md).

---

## Project Structure

```
.
├── config/                          # Configuration files
│   ├── computer_windows.yaml        # Desktop mode settings (screen coords, button positions)
│   └── model.yaml                   # AI model settings (model, verify_model, skills_dir)
│
├── runtime/                         # Session lifecycle managers
│   ├── computer_session.py          # Builds Computer from config
│   ├── model_session.py             # Builds ComputerAgent from config (ModelSettings)
│   └── llm_utils.py                 # Shared LLM retry utility (llm_call_with_retry)
│
├── modules/                         # Workflow components (stateless)
│   ├── task_types.py                # Data classes: GroupThread, Suspect, RemovalPlan
│   ├── group_classifier.py          # Classifies chats as group/individual
│   ├── unread_scanner.py            # Filters to unread group chats
│   ├── message_reader.py            # Prompts to read messages
│   ├── suspicious_detector.py       # Extracts suspects from output
│   ├── removal_precheck.py          # Builds removal plan
│   ├── human_confirmation.py        # Requires operator confirmation
│   └── removal_executor.py          # Executes removals (load_skill, merged prompts)
│
├── skills/                          # Skill markdown playbooks
│   └── wechat_removal.md            # WeChat UI rules, injected into action prompts
│
├── workflow/                        # Main orchestration
│   └── run_wechat_removal.py        # Entry point (step-mode backend)
│
├── control_panel_pro.py            # Control panel GUI
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
│  │  2. Launch control_panel_pro.py                                │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  control_panel_pro.py (GUI)                                    │  │
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

The user removal process demonstrates the full find-click-verify pattern. Steps 1 and 2 are merged into a single LLM call (same region, no state change between them):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      USER REMOVAL WORKFLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  STEP 1+2: Open Panel AND Find Minus Button (merged — single LLM call)      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [SCAFFOLDING CLICK]         [COMBINED VISION QUERY]                │   │
│  │                                                                      │   │
│  │  Click three dots (...)  ──▶  Single call to heavy model:           │   │
│  │  at fixed position             Crop MEMBER_PANEL_REGION             │   │
│  │  (2525, 48)                    "Is panel open? Find minus button"   │   │
│  │                                                                      │   │
│  │  Prompt: verify_panel_and_find_minus_prompt()                       │   │
│  │  Response: {"panel_opened": true, "button_found": true,             │   │
│  │             "click_x": 800, "click_y": 150}                         │   │
│  │                                                                      │   │
│  │  → Convert NORMALIZED (800, 150) → SCREEN coords                    │   │
│  │  → Click minus button at calculated position                        │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 3: Verify Dialog Opened  (fast verify_model)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [VISION VERIFY — fast model]                                        │   │
│  │                                                                      │   │
│  │  Crop MEMBER_SELECT_REGION ──▶ "Is member selection dialog open?"   │   │
│  │                                                                      │   │
│  │  Prompt: verify_member_dialog_opened_prompt()                        │   │
│  │  Response: {"dialog_opened": true/false}                             │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 4: Find and Select User  (heavy model)                                │
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
│  │   [PIPELINED] Click user checkbox → immediately click delete button │   │
│  │   (no intermediate sleep; delete is at fixed scaffolding position)  │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 5: Confirm Removal  (fast verify_model)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [VISION VERIFY — fast model]                                        │   │
│  │                                                                      │   │
│  │  Crop MEMBER_PANEL_REGION ──▶ "Is user removed?"                    │   │
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

# WeChat UI fixed button positions (absolute screen pixels for 2560x1440)
wechat_three_dots_x: 2525
wechat_three_dots_y: 48
wechat_delete_button_x: 1345
wechat_delete_button_y: 920
```

### `config/model.yaml`

```yaml
model: openrouter/qwen/qwen3-vl-32b-instruct  # Primary model: coordinate prediction
verify_model: openrouter/qwen/qwen2-vl-7b-instruct  # Fast model: yes/no checks
                                              # Omit or leave empty to use model for all calls
skills_dir: skills                            # Directory with skill .md files
max_trajectory_budget: 5.0                    # Max cost in USD
instructions: |                               # System prompt
  你是一个专门处理微信群违规信息的助手...
use_prompt_caching: false                     # Caching (Anthropic-only)
screenshot_delay: 0.5                         # Delay before screenshots
telemetry_enabled: false                      # Disable telemetry
```

**Model routing logic:**

| Call type | Model used | Why |
|-----------|-----------|-----|
| `verify_panel_and_find_minus_prompt` | `model` | Returns coordinates — needs the heavy model |
| `select_user_for_removal_prompt` | `model` | Returns coordinates — needs the heavy model |
| `verify_member_dialog_opened_prompt` | `verify_model` | Yes/no only — fast model sufficient |
| `verify_removal_prompt` | `verify_model` | Yes/no only — fast model sufficient |
| `classification_prompt` | `model` | Structured list extraction |
| `message_reader_prompt` | `model` | Full message reading |

---

## Performance Architecture

Per-suspect LLM call count before and after optimizations:

```
BEFORE (5-6 calls per suspect, all using heavy 32B model):
  1. verify_panel_opened      → MEMBER_PANEL_REGION  (heavy model)
  2. find_minus_button        → MEMBER_PANEL_REGION  (heavy model)
  3. verify_dialog_opened     → MEMBER_SELECT_REGION (heavy model)
  4. select_user_for_removal  → MEMBER_SELECT_REGION (heavy model)
  5. verify_removal           → MEMBER_PANEL_REGION  (heavy model)
  Total: ~15-30s per suspect

AFTER (4 calls per suspect, mixed models):
  1. verify_panel_and_find_minus → MEMBER_PANEL_REGION  (heavy model, was 2 calls)
  2. verify_dialog_opened        → MEMBER_SELECT_REGION (fast model)
  3. select_user_for_removal     → MEMBER_SELECT_REGION (heavy model)
  4. verify_removal              → MEMBER_PANEL_REGION  (fast model)
  Total: ~8-12s per suspect (estimated)
```

### Shared Retry Utility (`runtime/llm_utils.py`)

All vision queries go through `llm_call_with_retry()`:

```python
async def llm_call_with_retry(
    model: str,
    messages: List[Dict[str, Any]],
    timeout: float = 120.0,
    max_retries: int = 3,
) -> str:
    ...
```

Retries automatically on transient API errors (502, 503, 504, Bad Gateway, Timeout) with 2s × attempt backoff. Non-transient errors propagate immediately. Any new action type should call this function rather than implement its own retry loop.

### Pipelined Click Sequence

After the user checkbox click is confirmed by `select_user_for_removal`, the delete button click is executed immediately with no intermediate sleep. The delete button is at a hardcoded position, so no vision query is needed between the two clicks — verification happens once after both clicks complete.

---

## Skills System

Skills are markdown files in `skills/` that inject workflow rules into prompts at runtime. This separates UI knowledge (how WeChat behaves) from code logic (how to call the LLM).

### File Format

```markdown
---
name: wechat-removal
description: Use when removing users from a WeChat group via the desktop client.
---

# WeChat Member Removal

## UI Flow Overview
1. Click the three-dots (...) button...
...
```

### How Skills Are Loaded

`removal_executor.load_skill(path)` reads the file, strips the YAML frontmatter, and returns the body text. If the file is missing, it returns an empty string (graceful degradation). Prompts that call `load_skill()` append the skill text as a reference section:

```python
skill = load_skill()
skill_section = f"\n\n参考操作指南：\n{skill}" if skill else ""
return "...core prompt..." + skill_section
```

### Currently Skill-Injected Prompts

| Prompt function | Skill content injected? |
|---|---|
| `verify_panel_and_find_minus_prompt()` | Yes |
| `select_user_for_removal_prompt()` | Yes |
| `verify_member_dialog_opened_prompt()` | No (yes/no only) |
| `verify_removal_prompt()` | No (yes/no only) |

---

## Adding New Actions

To add a new action type to the workflow:

1. **Add a prompt builder** in the relevant `modules/` file:
   ```python
   def my_action_prompt(param: str) -> str:
       skill = load_skill()
       skill_section = f"\n\n参考操作指南：\n{skill}" if skill else ""
       return "...prompt text..." + skill_section
   ```

2. **Add a response parser** returning a typed dict:
   ```python
   def parse_my_action_response(text: str) -> Dict[str, Any]:
       ...
   ```

3. **Call the query** from the workflow using the appropriate helper:
   ```python
   text_output, screenshots = await run_cropped_vision_query(
       self.computer, self.model, my_action_prompt(param),
       self.capture_dir, "my_action_label", MY_CROP_REGION,
   )
   ```
   `run_cropped_vision_query` and `run_vision_query` both use `llm_call_with_retry` internally — no retry boilerplate needed.

4. **Register the step** in `StepModeRunner.process_request()`:
   ```python
   elif step == "my_action":
       await self.handle_my_action(params)
   ```

5. **Update the skill** in `skills/wechat_removal.md` if the new action interacts with the same UI, or create a new skill file.

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
1. The Control Panel auto-starts the server and workflow. If it fails, check the terminal for errors.

#### Server fails to start

Check if port 8000 is already in use:
```powershell
netstat -ano | findstr :8000
```

If another process is using the port, either stop it or change `api_port` in config.

#### Agent not responding

1. Make sure both Server and Workflow show "Running" status
2. Check the terminal output for errors
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

The Control Panel (`control_panel_pro.py`) provides:

### Auto-Start
- Launches and automatically starts the computer-server and workflow backend
- Single "启动巡检" button runs the full workflow (all 6 steps) automatically

### Workflow Steps
When "启动巡检" is clicked, steps run in sequence. Steps 1-2 run once globally. Steps 3-6 run **per group** in a loop:

| Step | Description | Scope |
|------|-------------|-------|
| 1. 扫描群组列表 | Agent scans WeChat chat list | Global |
| 2. 筛选未读群组 | Filters to unread groups | Global |
| 3. 读取群消息 | Reads messages in current group | Per Group |
| 4. 识别可疑用户 | Parses suspect info from current group | Per Group |
| 5. 生成处理方案 | Creates removal plan for current group | Per Group |
| 6. 执行移除操作 | Removes suspects from current group | Per Group |

After step 6 completes for a group, the workflow automatically advances to the next unread group and returns to step 3.

### Logging
- Logs are printed to the terminal (stdout) with timestamps
- Workflow backend output is streamed to the terminal

### State Management
- State is persisted to `artifacts/panel_state.json`

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
│  │   start.ps1 ──▶ Load .env ──▶ Launch control_panel_pro.py                   │   │
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
│  │  control_panel_pro.py ◄───────────────────────────────────────────────────┐  │   │
│  │       │                                                                   │  │   │
│  │       │ Step requests (.step_request)                                    │  │   │
│  │       ▼                                                                   │  │   │
│  │  workflow/run_wechat_removal.py                                          │  │   │
│  │       │                                                                   │  │   │
│  │       │ StepModeRunner                                                   │  │   │
│  │       │    ├── handle_classify()                                         │  │   │
│  │       │    ├── handle_read_messages()                                    │  │   │
│  │       │    └── handle_remove()                                           │  │   │
│  │       │         └── _remove_suspect_in_session()                        │  │   │
│  │       │              ├── run_cropped_vision_query(self.model, ...)       │  │   │
│  │       │              └── run_cropped_vision_query(self.verify_model, ...)│  │   │
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
│  │  │ • Prompt builder │  │ • Prompt builder │  │ • load_skill()           │  │   │
│  │  │ • Response parser│  │ • Response parser│  │ • Prompt builders:       │  │   │
│  │  │                  │  │                  │  │   - verify_panel_and_    │  │   │
│  │  │                  │  │                  │  │     find_minus (merged)  │  │   │
│  │  │                  │  │                  │  │   - select_user_for_     │  │   │
│  │  │                  │  │                  │  │     removal              │  │   │
│  │  │                  │  │                  │  │   - verify_dialog_opened │  │   │
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
│  │  │ • MEMBER_PANEL_  │  │ • click_delete_  │  │ • RemovalResult         │  │   │
│  │  │   REGION         │  │   confirm()      │  │                          │  │   │
│  │  │ • MEMBER_SELECT_ │  │                  │  │                          │  │   │
│  │  │   REGION         │  │                  │  │                          │  │   │
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
│  │  │   (button positions)     │    │   (model, verify_model, skills_dir) │  │   │
│  │  │                          │    │                                      │  │   │
│  │  └──────────────────────────┘    └──────────────────────────────────────┘  │   │
│  │                                                                              │   │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │   │
│  │  │ llm_utils.py                                                         │  │   │
│  │  │                                                                      │  │   │
│  │  │ • llm_call_with_retry(model, messages, timeout, max_retries)        │  │   │
│  │  │   Used by run_vision_query and run_cropped_vision_query             │  │   │
│  │  │   Extend by calling directly from any new action handler            │  │   │
│  │  └──────────────────────────────────────────────────────────────────────┘  │   │
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
│  │  │ • qwen3-vl-32b (model)     │    │ • Running on host machine          │  │   │
│  │  │ • qwen2-vl-7b (verify_     │    │ • Logged in with groups            │  │   │
│  │  │   model)                   │    │ • Visible on screen                │  │   │
│  │  │ • Or any litellm-          │    │                                    │  │   │
│  │  │   compatible model         │    │                                    │  │   │
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

### Combined Panel Verify + Minus Button Find (merged, heavy model)

```
这是屏幕右侧群聊信息面板的裁剪截图（宽260像素，高1440像素）。
刚才已点击了三个点按钮。

请同时回答两个问题：
1. 群聊信息面板是否已打开（能看到成员头像区域）？
2. 如果已打开，找到灰色方形「-」减号按钮的位置。

坐标说明：使用0-1000归一化坐标系

Response format (panel open + button found):
{"panel_opened": true, "button_found": true, "click_x": 800, "click_y": 150}

Response format (panel not open):
{"panel_opened": false, "button_found": false, "reason": "原因"}
```

### User Selection Prompt (heavy model)

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

### Removal Verification Prompt (fast verify_model)

```
这是屏幕右侧边缘的裁剪截图（宽260像素，高1440像素）。
刚才已点击了移出按钮。

请验证：用户「代写论文」是否已从成员列表中移除？

Response format:
{"user_removed": true, "user_name": "代写论文"}
```
