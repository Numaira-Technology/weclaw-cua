"""Run the Algorithm A pipeline.

Usage:
    Use `run_group_collection()` for one group and `run_collection_loop()` for
    repeated polling across groups.

Input spec:
    - `group_name`: one WeChat group name.
    - `group_names`: ordered group names to scan.
    - `poll_forever`: keep polling when `True`.
    - `poll_interval_seconds`: delay between polling passes.

Output spec:
    - `run_group_collection()` returns the written JSON path or `None`.
    - `run_collection_once()` returns written JSON paths from one pass.
    - `run_collection_loop()` returns written JSON paths from the last pass when
      `poll_forever` is `False`.
"""

from time import sleep

from algorithm_a.capture_scroll_screenshots import capture_scroll_screenshots
from algorithm_a.detect_new_messages import detect_new_messages
from algorithm_a.extract_structured_messages import extract_structured_messages
from algorithm_a.locate_unread_position import locate_unread_position
from algorithm_a.stitch_screenshots import stitch_screenshots
from algorithm_a.write_group_json import write_group_json


def run_group_collection(group_name: str) -> str | None:
    assert group_name

    has_new_messages = detect_new_messages(group_name)
    if not has_new_messages:
        return None

    unread_position = locate_unread_position(group_name)
    screenshot_paths = capture_scroll_screenshots(group_name, unread_position)
    long_image_paths = stitch_screenshots(screenshot_paths)
    structured_messages = extract_structured_messages(long_image_paths) # LLM extraction
    group_json_path = write_group_json(group_name, structured_messages)
    return group_json_path


def run_collection_once(group_names: list[str]) -> list[str]:
    assert group_names

    written_json_paths: list[str] = []

    for group_name in group_names:
        group_json_path = run_group_collection(group_name)
        if group_json_path is not None:
            written_json_paths.append(group_json_path)

    return written_json_paths


def run_collection_loop(
    group_names: list[str],
    poll_forever: bool = False,
    poll_interval_seconds: float = 5.0,
) -> list[str]:
    assert group_names
    assert poll_interval_seconds > 0

    while True:
        written_json_paths = run_collection_once(group_names)

        if not poll_forever:
            return written_json_paths

        sleep(poll_interval_seconds)
