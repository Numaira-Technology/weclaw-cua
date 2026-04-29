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
        "llm_model": "openai/gpt-4o",
        "output_dir": "output"
    }

    groups_to_monitor: [] or ["*"] means all chats allowed by chat_type.
    sidebar_unread_only: true = only process rows with unread badges.
    chat_type: "group", "private", or "all".
    sidebar_max_scrolls: maximum number of downward sidebar scrolls per scan.
    chat_max_scrolls: maximum number of upward chat-panel scrolls per chat.
    llm_provider: "openrouter" or "openai"; defaults to "openrouter".
    openrouter_api_key: optional. Only needed for built-in OpenRouter mode.
      Env OPENROUTER_API_KEY (or LITELLM_API_KEY) takes precedence.
    openai_api_key: optional. Only needed for built-in OpenAI mode.
      Env OPENAI_API_KEY takes precedence.
      In stepwise mode (agent handles LLM), this can be empty.
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
    chat_type: str = "group"
    sidebar_max_scrolls: int = 16
    chat_max_scrolls: int = 10
    llm_provider: str = "openrouter"
    openai_api_key: str = ""
    llm_api_key: str = ""

    def __post_init__(self) -> None:
        self.llm_provider = _normalize_llm_provider(self.llm_provider)
        self.chat_type = normalize_chat_type(self.chat_type)
        assert self.sidebar_max_scrolls >= 0, "sidebar_max_scrolls must be >= 0"
        assert self.chat_max_scrolls >= 0, "chat_max_scrolls must be >= 0"
        if not self.llm_api_key:
            if self.llm_provider == "openai":
                self.llm_api_key = self.openai_api_key
            else:
                self.llm_api_key = self.openrouter_api_key


def _normalize_llm_provider(raw_provider: str | None) -> str:
    provider = str(raw_provider or "openrouter").strip().lower()
    assert provider in ("openrouter", "openai"), "llm_provider must be 'openrouter' or 'openai'"
    return provider


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


def _resolve_openrouter_api_key(raw: dict) -> str:
    return (
        os.environ.get("OPENROUTER_API_KEY", "").strip()
        or os.environ.get("LITELLM_API_KEY", "").strip()
        or str(raw.get("openrouter_api_key", "") or "").strip()
    )


def _resolve_openai_api_key(raw: dict) -> str:
    return (
        os.environ.get("OPENAI_API_KEY", "").strip()
        or str(raw.get("openai_api_key", "") or "").strip()
    )


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
    assert type(sidebar_max_scrolls) is int, "sidebar_max_scrolls must be an integer"
    assert type(chat_max_scrolls) is int, "chat_max_scrolls must be an integer"
    llm_provider = _normalize_llm_provider(raw.get("llm_provider"))
    openrouter_api_key = _resolve_openrouter_api_key(raw)
    openai_api_key = _resolve_openai_api_key(raw)
    llm_api_key = openai_api_key if llm_provider == "openai" else openrouter_api_key
    return WeclawConfig(
        wechat_app_name=raw["wechat_app_name"],
        groups_to_monitor=list(gtm),
        sidebar_unread_only=ur,
        report_custom_prompt=raw.get("report_custom_prompt", ""),
        openrouter_api_key=openrouter_api_key,
        llm_model=raw.get("llm_model", "openai/gpt-4o"),
        output_dir=raw.get("output_dir", "output"),
        chat_type=normalize_chat_type(raw.get("chat_type", "group")),
        sidebar_max_scrolls=sidebar_max_scrolls,
        chat_max_scrolls=chat_max_scrolls,
        llm_provider=llm_provider,
        openai_api_key=openai_api_key,
        llm_api_key=llm_api_key,
    )
