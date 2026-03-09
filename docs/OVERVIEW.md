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
├── control_panel_pro.py            # Control panel GUI
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
| `crop_utils.py` | Defines `get_regions(os_type)`, Windows crop regions, macOS physical-pixel regions |
| `scaffolding_clicks.py` | Fixed-position clicks (Windows) or AX-tree dispatch (macOS) |
| `ax_clicks.py` | macOS Accessibility-tree click implementations (three dots, minus, confirm) |
| `removal_executor.py` | Vision prompts for finding users and verifying removal (branched by os_type) |
| `run_wechat_removal.py` | Main workflow with `_vision_query()` routing full vs cropped screenshot |

## Coordinate Quick Reference

### Windows (2560×1440)

| Region | Screen Coords | Size | Usage |
|--------|---------------|------|-------|
| `chat_list` | (58–276, 0–1440) | 218×1440 | Thread classification, click to open |
| `member_panel` | (2300–2560, 0–1440) | 260×1440 | Panel/removal verification |
| `member_select` | (925–1630, 425–970) | 705×545 | Member-selection dialog |

| Button | Screen Position | Function |
|--------|-----------------|----------|
| Three dots | (2525, 48) | Open group info panel |
| Minus button | (2525, 200) | Enter removal mode |
| Delete button | (1345, 920) | Confirm removal |

### macOS (3024×1964 — 16" MacBook Pro)

AI always sees the **full 3024×1964 screenshot** (no cropping). Clicks use Quartz `CGEventPost` in physical pixels. Buttons are located via the Accessibility Tree — no hardcoded positions.

See [PLATFORM_GUIDE.md](PLATFORM_GUIDE.md) for the complete platform comparison.

## Workflow Steps

1. **Classify** → (Win: crop chat list / Mac: full screen) → LLM identifies threads
2. **Filter** → Keep unread groups only
3. **Read** → Click chat at y-pixel → LLM reads messages → find suspects
4. **Extract** → Parse suspect info from response
5. **Plan** → Build removal plan → Human confirmation
6. **Remove** → (Win: scaffolding clicks + vision / Mac: AX tree + vision) → verify

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams.
