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
        "groups_to_monitor": ["Group A", "Group B", "..."],
        "report_custom_prompt": "Summarize key decisions and action items.",
        "openrouter_api_key": "sk-or-...",
        "llm_model": "google/gemini-3-flash-preview",
        "output_dir": "output"
    }

    groups_to_monitor 可为任意长度列表；程序未写死条数。项可含 emoji（侧栏 OCR 通常无 emoji），
    匹配规则为「OCR 名与该项全文一致，或与去掉 emoji/绘文字后的文本核严格一致」。

    resolve_openrouter_api_key() 优先使用环境变量 OPENROUTER_API_KEY（或 LITELLM_API_KEY），
    未设置时再读取上述 JSON 中的 openrouter_api_key（路径为仓库 config/config.json）。
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

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    assert isinstance(raw, dict)
    gtm = raw["groups_to_monitor"]
    assert isinstance(gtm, list), "groups_to_monitor 必须是 JSON 数组"
    assert all(isinstance(x, str) for x in gtm), "groups_to_monitor 每项须为字符串"
    return WeclawConfig(
        wechat_app_name=raw["wechat_app_name"],
        groups_to_monitor=list(gtm),
        report_custom_prompt=raw["report_custom_prompt"],
        openrouter_api_key=raw["openrouter_api_key"],
        llm_model=raw["llm_model"],
        output_dir=raw["output_dir"],
    )
