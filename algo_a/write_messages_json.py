"""Write extracted messages to a JSON file on disk.

Usage:
    from algo_a.write_messages_json import write_messages_json
    path = write_messages_json("Group A", messages, "output")

Input spec:
    - chat_name: name of the chat (used as filename base).
    - messages: list of message dicts from read_messages_from_uitree.
    - output_dir: directory to write the JSON file into.

Output spec:
    - Writes to {output_dir}/{chat_name}.json.
    - Returns the absolute path of the written file.

JSON output schema:
    [
        {
            "chat_name": "Group A",
            "sender": "Alice",
            "time": "14:32",
            "content": "Hello!",
            "type": "text"
        },
        ...
    ]
"""

import json
import os


def write_messages_json(chat_name: str, messages: list[dict], output_dir: str) -> str:
    """Write messages to a JSON file and return the file path."""
    assert chat_name
    assert isinstance(messages, list)
    assert output_dir

    os.makedirs(output_dir, exist_ok=True)
    safe_name = chat_name.replace("/", "_").replace("\\", "_")
    path = os.path.join(output_dir, f"{safe_name}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    return os.path.abspath(path)
