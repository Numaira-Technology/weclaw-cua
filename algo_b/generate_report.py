"""Call the LLM to generate a report from a prepared prompt.

Usage:
    from algo_b.generate_report import generate_report
    report = generate_report(prompt, "google/gemini-3-flash-preview", "sk-or-...")

Input spec:
    - prompt: the full prompt string from build_report_prompt.
    - model: provider model identifier.
    - api_key: provider API key.
    - provider: "openrouter" or "openai".

Output spec:
    - Returns the generated report as a plain text string.
"""

from shared.llm_client import call_llm


def generate_report(prompt: str, model: str, api_key: str, provider: str = "openrouter") -> str:
    """Send the prompt to the LLM and return the report text."""
    assert prompt
    assert model
    assert api_key
    return call_llm(prompt=prompt, model=model, api_key=api_key, provider=provider)
