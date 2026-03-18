"""Combine messages and user-customized prompt into a full LLM prompt for report generation.

Usage:
    from algo_b.build_report_prompt import build_report_prompt
    prompt = build_report_prompt(messages, "Summarize key decisions.")

Input spec:
    - messages: list[dict] of messages loaded from algo_a output.
    - custom_prompt: the user's customization text describing what kind of report they want.

Output spec:
    - Returns a single prompt string ready to send to the LLM.
"""

import json


def build_report_prompt(messages: list[dict], custom_prompt: str) -> str:
    """Build the full LLM prompt from messages and user instructions."""
    assert isinstance(messages, list)
    assert custom_prompt

    messages_block = json.dumps(messages, ensure_ascii=False, indent=2)

    return (
        f"You are a report assistant. The user wants a report based on WeChat messages.\n\n"
        f"User instructions:\n{custom_prompt}\n\n"
        f"Messages:\n{messages_block}\n\n"
        f"Generate the report based on the user's instructions above."
    )
