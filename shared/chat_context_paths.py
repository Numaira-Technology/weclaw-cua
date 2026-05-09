"""Discover captured chat-message JSON files for Q&A retrieval.

Usage:
    from shared.chat_context_paths import discover_message_json_paths
    paths = discover_message_json_paths("output", use_last_run=True)

Input spec:
    - output_dir contains captured chat JSON files and optional last_run.json.
    - last_run.json may include message_json_paths from the latest capture.

Output spec:
    - Returns absolute JSON paths from last_run.json or all chat exports.
"""

import json
import os


METADATA_FILES = {"last_run.json", "last_check.json"}


def discover_message_json_paths(output_dir: str, *, use_last_run: bool = True) -> list[str]:
    assert output_dir
    output_dir = os.path.abspath(output_dir)
    manifest_path = os.path.join(output_dir, "last_run.json")
    if use_last_run and os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert isinstance(manifest, dict)
        paths = manifest.get("message_json_paths", [])
        assert isinstance(paths, list)
        return [os.path.abspath(str(path)) for path in paths]

    assert os.path.isdir(output_dir), f"output directory not found: {output_dir}"
    names = [
        name for name in os.listdir(output_dir)
        if name.endswith(".json") and name not in METADATA_FILES and not name.startswith("last_")
    ]
    return [os.path.abspath(os.path.join(output_dir, name)) for name in sorted(names)]
