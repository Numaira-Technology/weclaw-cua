"""
Model session lifecycle for Cua VLM router.

Usage:
  from pathlib import Path
  from runtime.computer_session import build_computer, load_computer_settings
  settings = load_computer_settings(Path("config/computer_windows.yaml"))
  computer = build_computer(settings)
  model_settings = load_model_settings(Path("config/model.yaml"))
  agent = build_agent(model_settings, computer)

Input:
  - config_path: Path to YAML file with model, max_trajectory_budget, instructions, use_prompt_caching, screenshot_delay, telemetry_enabled.

Output:
  - ModelSettings dataclass populated from config.
  - ComputerAgent configured with injected Computer tool and system instructions.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
AGENT_PKG = VENDOR / "agent"
COMPUTER_PKG = VENDOR / "computer"
CORE_PKG = VENDOR / "core"
for pkg in [AGENT_PKG, COMPUTER_PKG, CORE_PKG]:
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))

from agent import ComputerAgent  # type: ignore  # noqa: E402
from computer import Computer  # type: ignore  # noqa: E402


@dataclass
class ModelSettings:
    model: str
    max_trajectory_budget: float
    instructions: str
    use_prompt_caching: bool
    screenshot_delay: float
    telemetry_enabled: bool
    api_key: Optional[str]


def _parse_simple_yaml(path: Path) -> Dict[str, str]:
    """Lightweight YAML subset parser that understands literal blocks (|/>)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    data: Dict[str, str] = {}
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in raw:
            i += 1
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value in {"|", ">"}:
            i += 1
            block_lines = []
            indent = None
            while i < len(lines):
                candidate = lines[i]
                if not candidate.strip():
                    block_lines.append("")
                    i += 1
                    continue
                leading_spaces = len(candidate) - len(candidate.lstrip(" "))
                if indent is None:
                    indent = leading_spaces
                if leading_spaces < (indent or 0):
                    break
                block_lines.append(candidate[indent:])
                i += 1
            data[key] = "\n".join(block_lines)
            continue
        data[key] = value
        i += 1
    return data


def load_model_settings(path: Path) -> ModelSettings:
    data = _parse_simple_yaml(path)
    return ModelSettings(
        model=data.get("model", "cua/anthropic/claude-sonnet-4.5"),
        max_trajectory_budget=float(data.get("max_trajectory_budget", 5.0)),
        instructions=data.get("instructions", ""),
        use_prompt_caching=str(data.get("use_prompt_caching", "false")).lower() == "true",
        screenshot_delay=float(data.get("screenshot_delay", 0.5)),
        telemetry_enabled=str(data.get("telemetry_enabled", "false")).lower() == "true",
        api_key=data.get("api_key"),
    )


def build_agent(settings: ModelSettings, computer: Computer) -> ComputerAgent:
    return ComputerAgent(
        model=settings.model,
        tools=[computer],
        instructions=settings.instructions,
        max_trajectory_budget=settings.max_trajectory_budget,
        use_prompt_caching=settings.use_prompt_caching,
        screenshot_delay=settings.screenshot_delay,
        telemetry_enabled=settings.telemetry_enabled,
        api_key=settings.api_key,
    )
