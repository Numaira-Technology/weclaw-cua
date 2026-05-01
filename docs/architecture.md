# Architecture

## Directory Structure

```
weclaw-cua/
├── weclaw_cli/                 # CLI layer (Click commands)
│   ├── main.py                 # Entry point
│   ├── context.py              # Config loading
│   └── commands/               # All CLI commands
│
├── algo_a/                     # Vision-based message capture
│   ├── pipeline_a_win.py       # Main capture pipeline
│   ├── capture_chat.py         # Screenshot scroll-capture engine
│   ├── extract_messages.py     # Vision LLM message extraction
│   └── ...                     # Sidebar scan, stitch, dedup
│
├── algo_b/                     # LLM report generation
│   ├── pipeline_b.py           # Report pipeline
│   ├── build_report_prompt.py  # Prompt construction
│   └── generate_report.py      # LLM call
│
├── platform_mac/               # macOS platform layer
│   ├── driver.py               # Quartz screenshots + CGEvent
│   └── ...                     # Window detection, stitching
│
├── platform_win/               # Windows platform layer
│   ├── driver.py               # Vision AI driver
│   └── ...                     # Window detection, UI Automation
│
├── shared/                     # Cross-cutting utilities
│   ├── platform_api.py         # PlatformDriver protocol
│   ├── vision_backend.py       # VisionBackend protocol
│   ├── stepwise_backend.py     # StepwiseBackend (images+prompts for agent)
│   ├── vision_ai.py            # Built-in OpenAI-compatible vision LLM
│   ├── message_schema.py       # Message dataclass
│   ├── llm_routing.py          # Multi-provider LLM routing
│   └── llm_client.py           # OpenAI-compatible text wrapper
│
├── config/                     # Configuration
├── tests/                      # Test suite
├── scripts/                    # Debug and utility scripts
├── sample_data/                # Sample JSON for local testing
├── npm/                        # npm binary distribution
├── pyproject.toml              # Python package config
└── entry.py                    # PyInstaller entry point
```

---

## Data Flow

```
weclaw-cua run / weclaw-cua capture
  │
  ├─ algo_a (vision capture)
  │   ├─ find WeChat window (OS API)
  │   ├─ scan sidebar for unread (vision AI)
  │   ├─ for each chat:
  │   │   ├─ click into chat
  │   │   ├─ scroll + capture screenshots
  │   │   ├─ stitch into long image
  │   │   ├─ vision LLM → structured JSON
  │   │   └─ post-process + dedup
  │   └─ write JSON files to output/
  │
  └─ algo_b (report generation)
      ├─ load message JSONs
      ├─ build report prompt
      ├─ call LLM
      └─ output report text
```
