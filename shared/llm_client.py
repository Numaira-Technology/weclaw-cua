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
    - provider: "openrouter" or "openai".

Output spec:
    - Returns the LLM response text as a string.
"""

import json
import ssl
import urllib.request

import certifi


def _chat_completions_url(provider: str) -> str:
    assert provider in ("openrouter", "openai"), "provider must be 'openrouter' or 'openai'"
    if provider == "openai":
        return "https://api.openai.com/v1/chat/completions"
    return "https://openrouter.ai/api/v1/chat/completions"


def call_llm(prompt: str, model: str, api_key: str, provider: str = "openrouter") -> str:
    assert prompt
    assert model
    assert api_key

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        _chat_completions_url(provider),
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
