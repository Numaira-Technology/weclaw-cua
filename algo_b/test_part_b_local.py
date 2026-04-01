"""Run a local smoke test for algo_b with existing message JSON files.

Usage:
    python3 -m algo_b.test_part_b_local
    python3 -m algo_b.test_part_b_local --prompt-only
    python3 -m algo_b.test_part_b_local --json-path "sample_data/Group A.json"
    python3 -m algo_b.test_part_b_local --save-path report.md

Input spec:
    - config_path: path to a config JSON file compatible with load_config().
    - json_path: optional one or more message JSON files produced by algo_a.
      If omitted, the script loads all JSON files inside sample_data/ first,
      and falls back to config.output_dir if no sample data exists.
    - prompt_only: if set, build and print the prompt without calling the LLM.
    - save_path: output file path for the resulting prompt or report text.
      Defaults to report.md in the repo root.

Output spec:
    - Prints either the generated prompt or the final report to stdout.
    - Writes the same text to save_path.
"""

import argparse
import glob
import os
from pathlib import Path

from algo_b.build_report_prompt import build_report_prompt
from algo_b.load_messages import load_messages
from algo_b.pipeline_b import run_pipeline_b
from config import load_config


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLE_DIR = REPO_ROOT / "sample_data"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.json"
DEFAULT_SAVE_PATH = REPO_ROOT / "report.md"


def _resolve_repo_path(path_str: str) -> str:
    path = Path(path_str)
    if path.is_absolute():
        return str(path)
    return str((REPO_ROOT / path).resolve())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local smoke test for algo_b.")
    parser.add_argument(
        "--config-path",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the config JSON file.",
    )
    parser.add_argument(
        "--json-path",
        action="append",
        default=[],
        help="Path to a message JSON file. Can be passed multiple times.",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Build and print the prompt without calling the LLM.",
    )
    parser.add_argument(
        "--save-path",
        default=str(DEFAULT_SAVE_PATH),
        help="Optional file path to save the output text.",
    )
    return parser.parse_args()


def resolve_json_paths(config_output_dir: str, json_paths: list[str]) -> list[str]:
    if json_paths:
        return [_resolve_repo_path(path) for path in json_paths]

    if DEFAULT_SAMPLE_DIR.is_dir():
        discovered_paths = sorted(glob.glob(str(DEFAULT_SAMPLE_DIR / "*.json")))
        if discovered_paths:
            return discovered_paths

    output_dir = _resolve_repo_path(config_output_dir)
    discovered_paths = sorted(glob.glob(f"{output_dir}/*.json"))
    assert discovered_paths, (
        f"no message JSON files found in: {DEFAULT_SAMPLE_DIR} or {output_dir}"
    )
    return discovered_paths


def build_output_text(config_path: str, json_paths: list[str], prompt_only: bool) -> str:
    config = load_config(_resolve_repo_path(config_path))
    resolved_json_paths = resolve_json_paths(config.output_dir, json_paths)

    if prompt_only:
        messages = load_messages(resolved_json_paths)
        return build_report_prompt(messages, config.report_custom_prompt)

    return run_pipeline_b(config, resolved_json_paths)


def main() -> None:
    args = parse_args()
    output_text = build_output_text(args.config_path, args.json_path, args.prompt_only)
    save_path = _resolve_repo_path(args.save_path)

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(output_text)

    print(output_text)


if __name__ == "__main__":
    main()
