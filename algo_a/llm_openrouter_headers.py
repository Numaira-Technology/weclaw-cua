"""litellm 走 OpenRouter 时注入的 HTTP 头（ASCII）。

OpenRouter 使用 X-Title / HTTP-Referer；若环境变量 OR_APP_NAME、OR_SITE_URL
含非 ASCII，httpx 发请求时会报 ascii codec 无法编码。
此处用固定 ASCII 覆盖，避免与中文会话名、中文路径等混用 env 时失败。
"""

from __future__ import annotations

OPENROUTER_LITELLM_HEADERS: dict[str, str] = {
    "HTTP-Referer": "https://github.com/weclaw-main",
    "X-Title": "weclaw",
}


def headers_for_model(model: str) -> dict[str, str] | None:
    if model.startswith("openrouter/"):
        return dict(OPENROUTER_LITELLM_HEADERS)
    return None
