# WeChat Removal Tool - Quick Reference

## Directory Structure

```
cua/
├── config/                          # Configuration
│   ├── computer_windows.yaml        # Screen coords, button positions
│   └── model.yaml                   # LLM settings (model, budget)
│
├── runtime/                         # Session managers
│   ├── computer_session.py          # Computer + settings loader
│   ├── model_session.py             # Agent builder
│   └── agent_session.py             # Stateful agent wrapper
│
├── modules/                         # Workflow components
│   ├── task_types.py                # Data classes (GroupThread, Suspect, etc.)
│   ├── crop_utils.py                # Screen regions + coordinate conversion
│   ├── scaffolding_clicks.py        # Fixed-position click functions
│   ├── group_classifier.py          # Thread classification prompts
│   ├── message_reader.py            # Message reading prompts
│   ├── removal_executor.py          # Removal prompts + parsers
│   ├── removal_verifier.py          # Verification response parser
│   ├── suspicious_detector.py       # Suspect extraction
│   ├── removal_precheck.py          # Plan builder
│   ├── human_confirmation.py        # Confirmation dialog
│   └── unread_scanner.py            # Unread filter
│
├── workflow/                        # Main orchestration
│   └── run_wechat_removal.py        # Entry point (step-mode backend)
│
├── control_panel.py                 # Visual GUI
├── panel_state.py                   # State persistence
│
├── artifacts/                       # Output
│   ├── captures/                    # Screenshots
│   ├── panel_state.json             # Control panel state
│   └── logs/report.json             # Final report
│
└── vendor/                          # Vendored CUA packages
    ├── agent/                       # AI agent framework
    ├── computer/                    # Computer control SDK
    ├── computer-server/             # HTTP API server
    └── core/                        # Shared utilities
```

## Key Files

| File | Purpose |
|------|---------|
| `crop_utils.py` | Defines CHAT_LIST_REGION, MEMBER_PANEL_REGION, MEMBER_SELECT_REGION |
| `scaffolding_clicks.py` | Fixed-position clicks for three dots, minus, delete buttons |
| `removal_executor.py` | Vision prompts for finding users and verifying removal |
| `run_wechat_removal.py` | Main workflow with `run_cropped_vision_query()` |

## Coordinate Quick Reference

| Region | Screen Coords | Size | Usage |
|--------|---------------|------|-------|
| CHAT_LIST_REGION | (58-276, 0-1440) | 218x1440 | Thread classification |
| MEMBER_PANEL_REGION | (2300-2560, 0-1440) | 260x1440 | Panel/removal verification |
| MEMBER_SELECT_REGION | (925-1630, 425-970) | 705x545 | User checkbox selection |

| Button | Screen Position | Function |
|--------|-----------------|----------|
| Three dots | (2525, 48) | Open group info panel |
| Minus button | (2525, 200) | Enter removal mode |
| Delete button | (1345, 920) | Confirm removal |

## Workflow Steps

1. **Classify** → Crop chat list → LLM identifies threads
2. **Filter** → Keep unread groups only
3. **Read** → Click chat → LLM reads messages → Find suspects
4. **Extract** → Parse suspect info from response
5. **Plan** → Build removal plan → Human confirmation
6. **Remove** → For each suspect: Find checkbox → Click → Verify

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams.
