"""Provider routing for OpenAI-compatible LLM APIs.

Usage:
    from shared.llm_routing import resolve_llm_routing
    base_url, api_key, wire_model = resolve_llm_routing(
        "kimi",
        "kimi/kimi-k2-0905",
        {"kimi": "sk-..."},
    )

Input spec:
    - provider: configured provider name or alias.
    - model: configured model name.
    - api_keys: provider-to-key mapping, usually from config plus env overrides.
    - Provider base URLs are fixed internal values.

Output spec:
    - Returns base URL, API key, and provider wire model for chat completions.
"""

import os


ProviderEntry = tuple[
    str,
    tuple[str, ...],
    tuple[str, ...],
    bool,
]

_PROVIDER_ENTRIES: dict[str, ProviderEntry] = {
    "openrouter": (
        "https://openrouter.ai/api/v1",
        ("openrouter_api_key",),
        ("OPENROUTER_API_KEY", "LITELLM_API_KEY"),
        True,
    ),
    "openai": (
        "https://api.openai.com/v1",
        ("openai_api_key",),
        ("OPENAI_API_KEY",),
        False,
    ),
    "deepseek": (
        "https://api.deepseek.com",
        ("deepseek_api_key",),
        ("DEEPSEEK_API_KEY",),
        False,
    ),
    "kimi": (
        "https://api.moonshot.cn/v1",
        ("kimi_api_key", "moonshot_api_key"),
        ("KIMI_API_KEY", "MOONSHOT_API_KEY"),
        False,
    ),
    "glm": (
        "https://open.bigmodel.cn/api/paas/v4",
        ("glm_api_key", "zhipu_api_key"),
        ("GLM_API_KEY", "ZHIPU_API_KEY"),
        False,
    ),
    "qwen": (
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ("qwen_api_key",),
        ("QWEN_API_KEY",),
        False,
    ),
}

_PROVIDER_ALIASES: dict[str, str] = {
    "openrouter": "openrouter",
    "openai": "openai",
    "deepseek": "deepseek",
    "kimi": "kimi",
    "moonshot": "kimi",
    "glm": "glm",
    "zhipu": "glm",
    "z-ai": "glm",
    "qwen": "qwen",
}


def supported_llm_providers() -> tuple[str, ...]:
    return tuple(_PROVIDER_ALIASES)


def normalize_llm_provider(raw_provider: str | None) -> str:
    provider = str(raw_provider or "openrouter").strip().lower()
    canonical = _PROVIDER_ALIASES.get(provider)
    assert canonical, (
        "llm_provider must be one of: "
        + ", ".join(sorted(supported_llm_providers()))
    )
    return canonical


def _first_config_value(raw: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(raw.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _first_env_value(keys: tuple[str, ...]) -> str:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def collect_provider_api_keys(raw: dict) -> dict[str, str]:
    assert isinstance(raw, dict)
    values: dict[str, str] = {}
    for provider, entry in _PROVIDER_ENTRIES.items():
        values[provider] = (
            _first_env_value(entry[2])
            or _first_config_value(raw, entry[1])
        )
    return values


def default_base_url(provider: str) -> str:
    return _PROVIDER_ENTRIES[normalize_llm_provider(provider)][0]


def _mapping_value(values: dict[str, str], provider: str, keys: tuple[str, ...]) -> str:
    canonical = normalize_llm_provider(provider)
    value = str(values.get(canonical, "") or "").strip()
    if value:
        return value
    return _first_config_value(values, keys)


def _wire_model(provider: str, model: str) -> str:
    entry = _PROVIDER_ENTRIES[normalize_llm_provider(provider)]
    model = model.strip()
    assert model, "llm_model must not be empty"
    if entry[3] or "/" not in model:
        return model
    wire_model = model.split("/", 1)[1].strip()
    assert wire_model, "llm_model prefix must be followed by a model name"
    return wire_model


def resolve_llm_routing(
    provider: str,
    model: str,
    api_keys: dict[str, str],
) -> tuple[str, str, str]:
    canonical = normalize_llm_provider(provider)
    entry = _PROVIDER_ENTRIES[canonical]
    api_key = _mapping_value(api_keys, canonical, entry[1])
    return entry[0], api_key, _wire_model(canonical, model)
