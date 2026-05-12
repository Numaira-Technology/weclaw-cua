"""Thin OpenAI-compatible API wrapper for LLM calls.

Usage:
    from shared.llm_client import call_llm
    response = call_llm(
        prompt="Summarize these messages...",
        model="google/gemini-3-flash-preview",
        api_key="sk-...",
    )

Input spec:
    - prompt: the full prompt string to send as user message.
    - model: provider model identifier.
    - api_key: provider API key.
    - provider: configured LLM provider.
    - base_url: resolved OpenAI-compatible API base URL.
    - wire_model: model name sent to the selected provider.

Output spec:
    - Returns the LLM response text as a string.
"""

import json
import ssl
import urllib.request

import certifi

from shared.llm_routing import normalize_llm_provider
from shared.llm_routing import resolve_llm_routing


def _chat_completions_url(base_url: str) -> str:
    assert base_url
    return f"{base_url.rstrip('/')}/chat/completions"


def _resolve_call_args(
    model: str,
    api_key: str,
    provider: str,
    base_url: str,
    wire_model: str,
) -> tuple[str, str]:
    if base_url and wire_model:
        return base_url, wire_model
    canonical = normalize_llm_provider(provider)
    resolved_base_url, _, resolved_model = resolve_llm_routing(
        canonical,
        model,
        {canonical: api_key},
    )
    return base_url or resolved_base_url, wire_model or resolved_model


def call_llm(
    prompt: str,
    model: str,
    api_key: str,
    provider: str = "openrouter",
    base_url: str = "",
    wire_model: str = "",
) -> str:
    assert prompt
    assert model
    assert api_key
    base_url, wire_model = _resolve_call_args(model, api_key, provider, base_url, wire_model)

    body = json.dumps({
        "model": wire_model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        _chat_completions_url(base_url),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    resp = urllib.request.urlopen(req, context=ssl_context)
    data = json.loads(resp.read().decode("utf-8"))

    choices = data.get("choices")
    assert choices, f"{provider} response missing choices"
    message = choices[0].get("message")
    assert message, f"{provider} response missing message"
    content = message.get("content")
    assert content, f"{provider} response missing content"
    return content
