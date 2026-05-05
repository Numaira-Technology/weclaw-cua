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
        "chat_type": "group",
        "sidebar_max_scrolls": 16,
        "chat_max_scrolls": 10,
        "report_custom_prompt": "Summarize key decisions and action items.",
        "llm_provider": "openrouter",
        "openrouter_api_key": "",
        "openai_api_key": "",
        "deepseek_api_key": "",
        "kimi_api_key": "",
        "glm_api_key": "",
        "qwen_api_key": "",
        "llm_model": "openai/gpt-4o",
        "output_dir": "output"
    }

    groups_to_monitor: [] or ["*"] means all chats allowed by chat_type.
    sidebar_unread_only: true = only process rows with unread badges.
    chat_type: "group", "private", or "all".
    sidebar_max_scrolls: maximum number of downward sidebar scrolls per scan.
    chat_max_scrolls: maximum number of upward chat-panel scrolls per chat.
    recent_window_hours: keep only messages within this many hours (0 = no limit).
    llm_provider: "openrouter", "openai", "deepseek", "kimi", "glm", or "qwen".
      "moonshot" aliases to "kimi"; "zhipu" and "z-ai" alias to "glm".
    openrouter_api_key: optional. Only needed for built-in OpenRouter mode.
      Env OPENROUTER_API_KEY (or LITELLM_API_KEY) takes precedence.
    openai_api_key: optional. Only needed for built-in OpenAI mode.
      Env OPENAI_API_KEY takes precedence.
    deepseek_api_key, kimi_api_key, glm_api_key, qwen_api_key: optional.
      Matching env vars take precedence.
      In stepwise mode (agent handles LLM), this can be empty.
"""

import json
import os
from dataclasses import dataclass

from shared.llm_routing import collect_provider_api_keys
from shared.llm_routing import normalize_llm_provider
from shared.llm_routing import resolve_llm_routing


@dataclass
class WeclawConfig:
    wechat_app_name: str
    groups_to_monitor: list[str]
    sidebar_unread_only: bool
    report_custom_prompt: str
    openrouter_api_key: str
    llm_model: str
    output_dir: str
    chat_type: str = "group"
    sidebar_max_scrolls: int = 16
    chat_max_scrolls: int = 10
    recent_window_hours: int = 0
    llm_provider: str = "openrouter"
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    kimi_api_key: str = ""
    glm_api_key: str = ""
    qwen_api_key: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_wire_model: str = ""

    def __post_init__(self) -> None:
        self.llm_provider = _normalize_llm_provider(self.llm_provider)
        self.chat_type = normalize_chat_type(self.chat_type)
        assert self.sidebar_max_scrolls >= 0, "sidebar_max_scrolls must be >= 0"
        assert self.chat_max_scrolls >= 0, "chat_max_scrolls must be >= 0"
        assert self.recent_window_hours >= 0, "recent_window_hours must be >= 0"
        base_url, api_key, wire_model = resolve_llm_routing(
            self.llm_provider,
            self.llm_model,
            {
                "openrouter": self.openrouter_api_key,
                "openai": self.openai_api_key,
                "deepseek": self.deepseek_api_key,
                "kimi": self.kimi_api_key,
                "glm": self.glm_api_key,
                "qwen": self.qwen_api_key,
            },
        )
        if not self.llm_api_key:
            self.llm_api_key = api_key
        if not self.llm_base_url:
            self.llm_base_url = base_url
        if not self.llm_wire_model:
            self.llm_wire_model = wire_model


def _normalize_llm_provider(raw_provider: str | None) -> str:
    return normalize_llm_provider(raw_provider)


def normalize_chat_type(raw_chat_type: str | None) -> str:
    chat_type = str(raw_chat_type or "group").strip().lower()
    aliases = {
        "groups": "group",
        "private_chat": "private",
        "private_chats": "private",
        "direct": "private",
        "dm": "private",
        "dms": "private",
        "all_chats": "all",
    }
    chat_type = aliases.get(chat_type, chat_type)
    assert chat_type in ("group", "private", "all"), "chat_type must be 'group', 'private', or 'all'"
    return chat_type


def load_config(config_path: str) -> WeclawConfig:
    assert config_path
    assert os.path.isfile(config_path), f"config not found: {config_path}"

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    assert isinstance(raw, dict)
    gtm = raw["groups_to_monitor"]
    assert isinstance(gtm, list), "groups_to_monitor must be a JSON array"
    assert all(isinstance(x, str) for x in gtm), "groups_to_monitor items must be strings"
    ur = raw.get("sidebar_unread_only", False)
    assert isinstance(ur, bool), "sidebar_unread_only must be boolean"
    sidebar_max_scrolls = raw.get("sidebar_max_scrolls", 16)
    chat_max_scrolls = raw.get("chat_max_scrolls", 10)
    recent_window_hours = raw.get("recent_window_hours", 0)
    assert type(sidebar_max_scrolls) is int, "sidebar_max_scrolls must be an integer"
    assert type(chat_max_scrolls) is int, "chat_max_scrolls must be an integer"
    assert type(recent_window_hours) is int, "recent_window_hours must be an integer"
    llm_provider = _normalize_llm_provider(raw.get("llm_provider"))
    api_keys = collect_provider_api_keys(raw)
    llm_model = str(raw.get("llm_model", "openai/gpt-4o") or "").strip()
    llm_base_url, llm_api_key, llm_wire_model = resolve_llm_routing(
        llm_provider,
        llm_model,
        api_keys,
    )
    return WeclawConfig(
        wechat_app_name=raw["wechat_app_name"],
        groups_to_monitor=list(gtm),
        sidebar_unread_only=ur,
        report_custom_prompt=raw.get("report_custom_prompt", ""),
        openrouter_api_key=api_keys["openrouter"],
        llm_model=llm_model,
        output_dir=raw.get("output_dir", "output"),
        chat_type=normalize_chat_type(raw.get("chat_type", "group")),
        sidebar_max_scrolls=sidebar_max_scrolls,
        chat_max_scrolls=chat_max_scrolls,
        recent_window_hours=recent_window_hours,
        llm_provider=llm_provider,
        openai_api_key=api_keys["openai"],
        deepseek_api_key=api_keys["deepseek"],
        kimi_api_key=api_keys["kimi"],
        glm_api_key=api_keys["glm"],
        qwen_api_key=api_keys["qwen"],
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_wire_model=llm_wire_model,
    )
