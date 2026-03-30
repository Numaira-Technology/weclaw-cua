"""litellm 走 OpenRouter 时注入的 HTTP 头（实现见 shared.openrouter_litellm_headers）。"""

from __future__ import annotations

from shared.openrouter_litellm_headers import (
    OPENROUTER_LITELLM_HEADERS,
    ensure_openrouter_ascii_env,
    headers_for_model,
    openrouter_completion_headers,
)

__all__ = [
    "OPENROUTER_LITELLM_HEADERS",
    "ensure_openrouter_ascii_env",
    "headers_for_model",
    "openrouter_completion_headers",
]
