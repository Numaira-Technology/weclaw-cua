"""Orchestrate the full algo_b pipeline: load messages, build prompt, generate report.

Usage:
    from algo_b.pipeline_b import run_pipeline_b
    report = run_pipeline_b(config, ["output/Group A.json"])

Input spec:
    - config: WeclawConfig with report prompt and resolved LLM routing fields.
    - message_json_paths: list of JSON file paths produced by algo_a.

Output spec:
    - Returns the generated report text as a string.

Pipeline steps:
    1. load_messages(message_json_paths)
    2. build_report_prompt(messages, config.report_custom_prompt)
    3. generate_report using config's resolved provider routing.
"""

from config.weclaw_config import WeclawConfig
from algo_b.load_messages import load_messages
from algo_b.build_report_prompt import build_report_prompt
from algo_b.generate_report import generate_report


def run_pipeline_b(config: WeclawConfig, message_json_paths: list[str]) -> str:
    """Run the full report generation pipeline and return the report text."""
    assert config is not None
    assert message_json_paths

    messages = load_messages(message_json_paths)
    prompt = build_report_prompt(messages, config.report_custom_prompt)
    report = generate_report(
        prompt,
        config.llm_model,
        config.llm_api_key,
        config.llm_provider,
        config.llm_base_url,
        config.llm_wire_model,
    )
    return report
