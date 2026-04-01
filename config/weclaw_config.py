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
        "groups_to_monitor": ["*"],
        "sidebar_unread_only": false,
        "report_custom_prompt": "Summarize key decisions and action items.",
        "openrouter_api_key": "sk-or-...",
        "llm_model": "google/gemini-3-flash-preview",
        "output_dir": "output"
    }

    groups_to_monitor: [] 或 ["*"] 表示侧栏里所有群聊（vision 判定 is_group）。
    sidebar_unread_only: true 时只入队带未读角标的行（依赖 vision `unread`）；false 时不筛未读。
    其它 groups_to_monitor 规则：具名为按名称匹配（可含单聊）。项可含 emoji；匹配规则见 list_target_chats_win。

    openrouter_api_key：优先环境变量 OPENROUTER_API_KEY（或 LITELLM_API_KEY），否则读 JSON 字段。
"""

import json
import os
from dataclasses import dataclass


@dataclass
class WeclawConfig:
    wechat_app_name: str
    groups_to_monitor: list[str]
    sidebar_unread_only: bool
    report_custom_prompt: str
    openrouter_api_key: str
    llm_model: str
    output_dir: str


def load_config(config_path: str) -> WeclawConfig:
    assert config_path
    assert os.path.isfile(config_path), f"config not found: {config_path}"

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    assert isinstance(raw, dict)
    gtm = raw["groups_to_monitor"]
    assert isinstance(gtm, list), "groups_to_monitor 必须是 JSON 数组"
    assert all(isinstance(x, str) for x in gtm), "groups_to_monitor 每项须为字符串"
    ur = raw.get("sidebar_unread_only", False)
    assert isinstance(ur, bool), "sidebar_unread_only 须为布尔"
    api_key = str(raw.get("openrouter_api_key", "") or "").strip()
    if not api_key:
        api_key = (
            os.environ.get("OPENROUTER_API_KEY", "").strip()
            or os.environ.get("LITELLM_API_KEY", "").strip()
        )
    assert api_key, (
        "Set OPENROUTER_API_KEY (or LITELLM_API_KEY) or fill openrouter_api_key in config.json"
    )
    return WeclawConfig(
        wechat_app_name=raw["wechat_app_name"],
        groups_to_monitor=list(gtm),
        sidebar_unread_only=ur,
        report_custom_prompt=raw["report_custom_prompt"],
        openrouter_api_key=api_key,
        llm_model=raw["llm_model"],
        output_dir=raw["output_dir"],
    )
