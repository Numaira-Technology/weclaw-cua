"""Load message JSON files produced by algo_a.

Usage:
    from algo_b.load_messages import load_messages
    all_messages = load_messages(["output/Group A.json", "output/Group B.json"])

Input spec:
    - json_paths: list of file paths to JSON files written by algo_a.

Output spec:
    - Returns a merged list[dict] of all messages across all files.
    - Each dict has keys: chat_name, sender, time, content, type.
"""

import json


def load_messages(json_paths: list[str]) -> list[dict]:
    """Read and merge messages from multiple JSON files."""
    assert json_paths

    all_messages: list[dict] = []
    for path in json_paths:
        with open(path, encoding="utf-8") as f:
            messages = json.load(f)
        assert isinstance(messages, list)
        all_messages.extend(messages)

    return all_messages
