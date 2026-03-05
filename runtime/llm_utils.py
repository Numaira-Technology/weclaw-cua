"""
Shared LLM call helpers for vision queries.

Usage:
    from runtime.llm_utils import llm_call_with_retry

    text = await llm_call_with_retry(
        model="openrouter/qwen/qwen3-vl-32b-instruct",
        messages=[{"role": "user", "content": [...]}],
    )

Input:
    - model: LiteLLM model string.
    - messages: List of message dicts in OpenAI chat format.
    - timeout: Request timeout in seconds (default 120).
    - max_retries: Number of retry attempts for transient API errors (default 3).

Output:
    - Response text from the model.

Raises:
    - Exception re-raised after all retries are exhausted, or immediately for
      non-transient errors.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List


_TRANSIENT_INDICATORS = [
    "502",
    "503",
    "504",
    "ServiceUnavailable",
    "server_error",
    "Timeout",
    "Bad Gateway",
]


def _is_transient(error: Exception) -> bool:
    error_str = str(error)
    return any(indicator in error_str for indicator in _TRANSIENT_INDICATORS)


async def llm_call_with_retry(
    model: str,
    messages: List[Dict[str, Any]],
    timeout: float = 120.0,
    max_retries: int = 3,
) -> str:
    """Call an LLM via LiteLLM with exponential-backoff retry on transient errors.

    Returns the response text. Raises on persistent or non-transient failures.

    Future actions that need a vision query should use this function instead of
    re-implementing retry logic. The signature is intentionally model-agnostic so
    any litellm-compatible model string works.
    """
    import litellm

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = await litellm.acompletion(
                model=model, messages=messages, timeout=timeout
            )
            text: str = response.choices[0].message.content or ""  # type: ignore[union-attr]
            return text
        except Exception as exc:
            last_error = exc
            if _is_transient(exc) and attempt < max_retries - 1:
                wait = 2.0 * (attempt + 1)
                await asyncio.sleep(wait)
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("llm_call_with_retry: no attempts made")
