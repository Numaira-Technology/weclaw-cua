"""
VLM-based verification that a user has been removed from the member list.

Usage:
  is_removed = await verify_user_removed(screenshot_b64, "用户名", model)

Input:
  - screenshot_b64: Base64-encoded screenshot of the member list after removal
  - user_name: Name of the user to check for
  - model: LiteLLM model identifier

Output:
  - bool: True if user is NOT visible in the member list (removal succeeded)
"""

from __future__ import annotations

import json
import re

import litellm


def verification_prompt(user_name: str) -> str:
    """Build prompt to check if a user name is visible in the member list."""
    return (
        f"查看这张截图中的群成员列表。\n\n"
        f"问题：用户「{user_name}」是否还在成员列表中可见？\n\n"
        f"仔细检查所有可见的成员名称，包括部分可见的名称。\n\n"
        f"只回复JSON格式：\n"
        f'{{"user_visible": true}} 如果能看到「{user_name}」\n'
        f'{{"user_visible": false}} 如果看不到「{user_name}」'
    )


def _parse_verification_response(text: str) -> bool:
    """Parse VLM response to determine if user is still visible."""
    text = text.strip()
    try:
        data = json.loads(text)
        return data.get("user_visible", True)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in the response
    match = re.search(r'\{[^}]*"user_visible"\s*:\s*(true|false)[^}]*\}', text, re.I)
    if match:
        return "true" in match.group(1).lower()

    # Fallback: look for keywords
    text_lower = text.lower()
    if "不可见" in text or "看不到" in text or "not visible" in text_lower:
        return False
    if "可见" in text or "能看到" in text or "visible" in text_lower:
        return True

    # Default to assuming user is still visible (conservative)
    return True


async def verify_user_removed(
    screenshot_b64: str, user_name: str, model: str, timeout: int = 30
) -> bool:
    """Check if a user is no longer visible in the member list screenshot.

    Args:
        screenshot_b64: Base64-encoded screenshot of the member list
        user_name: Name of the user to check for
        model: LiteLLM model identifier
        timeout: Request timeout in seconds

    Returns:
        True if user is NOT visible (removal succeeded), False if still visible
    """
    prompt = verification_prompt(user_name)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    try:
        response = await litellm.acompletion(
            model=model, messages=messages, timeout=timeout
        )
        text_output = response.choices[0].message.content or ""
        user_visible = _parse_verification_response(text_output)
        return not user_visible  # Return True if user is NOT visible
    except Exception as e:
        print(f"[verify_user_removed] Error during verification: {e}")
        # On error, assume user is still visible (conservative)
        return False
