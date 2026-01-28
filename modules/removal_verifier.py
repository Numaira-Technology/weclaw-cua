"""
Parse removal verification responses from the agent.

Usage:
  result = parse_removal_response(agent_text)

Input:
  - agent_text: Text response from agent after removal_with_verify_prompt

Output:
  - dict with keys: user_removed (bool), user_name (str), reason (str, optional)
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict


def parse_removal_response(text: str) -> Dict[str, Any]:
    """
    Parse agent response from removal_with_verify_prompt.

    Expected JSON format:
      {"user_removed": true, "user_name": "xxx"}
      {"user_removed": false, "user_name": "xxx", "reason": "xxx"}
    """
    text = text.strip()

    json_match = re.search(
        r'\{[^}]*"user_removed"\s*:\s*(true|false)[^}]*\}', text, re.I
    )
    if json_match:
        json_str = json_match.group()
        data = json.loads(json_str)
        return {
            "user_removed": data.get("user_removed", False),
            "user_name": data.get("user_name", ""),
            "reason": data.get("reason", ""),
        }

    user_removed = False
    if "user_removed" in text.lower():
        user_removed = "true" in text.lower().split("user_removed")[1][:20]
    elif "已移除" in text or "成功" in text:
        user_removed = True

    return {
        "user_removed": user_removed,
        "user_name": "",
        "reason": "Could not parse response" if not user_removed else "",
    }
