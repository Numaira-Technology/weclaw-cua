"""将处理后的消息列表写入 JSON 文件。

输出格式：
  {
    "chat_name": "群聊名",
    "message_count": 42,
    "timestamp": "2026-03-18T15:30:00",
    "messages": [ { "chat_name", "sender", "time", "content", "type" }, ... ]
  }
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def write_messages_json(
    chat_name: str,
    messages: List[Dict[str, Any]],
    output_dir: str,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> str:
    """写入消息 JSON 并返回绝对路径。

    extra_meta 中的字段会合并到顶层输出中（不覆盖核心字段）。
    """
    assert chat_name, "chat_name 不能为空"
    assert isinstance(messages, list)
    assert output_dir, "output_dir 不能为空"

    os.makedirs(output_dir, exist_ok=True)
    safe_name = chat_name.replace("/", "_").replace("\\", "_").replace(":", "_")
    path = os.path.join(output_dir, f"{safe_name}.json")

    payload: Dict[str, Any] = {
        "chat_name": chat_name,
        "message_count": len(messages),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "messages": messages,
    }
    if extra_meta:
        for k, v in extra_meta.items():
            if k not in payload:
                payload[k] = v

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return os.path.abspath(path)
