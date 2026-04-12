"""Load message JSON files produced by algo_a.

Usage:
    from algo_b.load_messages import load_messages
    all_messages = load_messages(["output/Group A.json", "output/Group B.json"])

Input spec:
    - json_paths: list of file paths to JSON files written by algo_a.

Output spec:
    - Returns a merged list[Message] across all files.
    - Preserves the file order from json_paths and the original order within each file.
"""

import os

from shared.message_schema import Message, messages_from_json


def load_messages(json_paths: list[str]) -> list[Message]:
    """Read and merge messages from multiple JSON files."""
    assert json_paths

    all_messages: list[Message] = []
    for path in json_paths:
        assert os.path.isfile(path), f"message json not found: {path}"
        with open(path, encoding="utf-8") as f:
            messages = messages_from_json(f.read())
        all_messages.extend(messages)

    return all_messages
