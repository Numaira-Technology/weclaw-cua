"""Thin OpenRouter API wrapper for LLM calls.

Usage:
    from shared.llm_client import call_llm
    response = call_llm(prompt="Summarize these messages...", model="google/gemini-3-flash-preview", api_key="sk-...")

Input spec:
    - prompt: the full prompt string to send as user message.
    - model: OpenRouter model identifier.
    - api_key: OpenRouter API key.

Output spec:
    - Returns the LLM response text as a string.
"""

import json
import urllib.request


def call_llm(prompt: str, model: str, api_key: str) -> str:
    assert prompt
    assert model
    assert api_key

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode("utf-8"))

    choices = data.get("choices")
    assert choices, "OpenRouter response missing choices"
    message = choices[0].get("message")
    assert message, "OpenRouter response missing message"
    content = message.get("content")
    assert content, "OpenRouter response missing content"
    return content
