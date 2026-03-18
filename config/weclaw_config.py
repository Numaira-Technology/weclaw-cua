"""WeclawConfig dataclass and config loader.

Usage:
    from config import WeclawConfig, load_config
    config = load_config("config/config.json")

Input spec:
    - config_path: path to a JSON file matching config.json.example schema.

Output spec:
    - Returns a WeclawConfig instance with all fields populated.

config.json schema:
    {
        "wechat_app_name": "WeChat",
        "groups_to_monitor": ["Group A", "Group B"],
        "report_custom_prompt": "Summarize key decisions and action items.",
        "openrouter_api_key": "sk-or-...",
        "llm_model": "google/gemini-3-flash-preview",
        "output_dir": "output"
    }
"""

import json
import os
from dataclasses import dataclass


@dataclass
class WeclawConfig:
    wechat_app_name: str
    groups_to_monitor: list[str]
    report_custom_prompt: str
    openrouter_api_key: str
    llm_model: str
    output_dir: str


def load_config(config_path: str) -> WeclawConfig:
    assert config_path
    assert os.path.isfile(config_path), f"config not found: {config_path}"

    with open(config_path) as f:
        raw = json.load(f)

    assert isinstance(raw, dict)
    return WeclawConfig(
        wechat_app_name=raw["wechat_app_name"],
        groups_to_monitor=raw["groups_to_monitor"],
        report_custom_prompt=raw["report_custom_prompt"],
        openrouter_api_key=raw["openrouter_api_key"],
        llm_model=raw["llm_model"],
        output_dir=raw["output_dir"],
    )
