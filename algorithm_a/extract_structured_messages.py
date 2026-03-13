"""Extract structured messages from long images with an LLM via OpenRouter.

Usage:
    Call this after long-image generation. Set OPENROUTER_API_KEY in the environment
    or in a .env file in the project root.

Input spec:
    - `long_image_path`: path to one stitched long-image file.

Output spec:
    - Returns list of message dicts with `sender`, `time`, `content`, `type`.
"""

import base64
import json
import os
import re
import urllib.request


def _load_dotenv() -> None:
    root = os.environ.get("WECLAW_ROOT")
    candidates = [root] if root else []
    candidates.append(os.getcwd())
    candidates.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for path in candidates:
        if not path or not os.path.isdir(path):
            continue
        env_path = os.path.join(path, ".env")
        if not os.path.isfile(env_path):
            continue
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = value
        return


def _extract_prompt() -> str:
    return (
        "Extract visible WeChat messages from this long chat screenshot and return JSON only.\n\n"
        "Rules:\n"
        "1. Follow the JSON schema exactly.\n"
        "2. Keep messages in top-to-bottom order.\n"
        "3. For each message, extract: sender, time, content, type.\n"
        '4. If time is not explicitly visible, use null.\n'
        '5. If sender is unclear, use "UNKNOWN".\n'
        '6. For system notices or date separators, use sender="SYSTEM", type="system".\n'
        '7. For link/job/share/mini-program cards, extract visible title/summary into content, type="link_card".\n'
        "8. Do not invent hidden or cut-off content; only extract what is visible.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "messages": [\n'
        "    {\n"
        '      "sender": "string",\n'
        '      "time": "string|null",\n'
        '      "content": "string",\n'
        '      "type": "text|system|link_card|other"\n'
        "    }\n"
        "  ],\n"
        '  "extraction_confidence": "high|medium|low",\n'
        '  "boundary_stability": "stable|unstable"\n'
        "}"
    )


def _load_image_base64(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    return base64.standard_b64encode(raw).decode("ascii")


def _parse_json_from_response(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def extract_structured_messages(
    long_image_path: str,
    model: str = "google/gemini-3-flash-preview",
) -> list[dict]:
    assert long_image_path
    _load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    assert api_key, "OPENROUTER_API_KEY must be set"

    b64 = _load_image_base64(long_image_path)
    content: list[dict] = [
        {"type": "text", "text": _extract_prompt()},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Referer": "https://github.com/weclaw",
        },
    )

    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {err_body}") from e

    with resp:
        data = json.loads(resp.read().decode("utf-8"))

    choice = data.get("choices")
    assert choice, "OpenRouter response missing choices"
    message = choice[0].get("message")
    assert message, "OpenRouter response missing message"
    raw = message.get("content")
    assert raw, "OpenRouter response missing content"

    parsed = _parse_json_from_response(raw)
    messages = parsed.get("messages")
    assert isinstance(messages, list), "LLM response missing messages array"
    return messages



if __name__ == "__main__":
    import sys
    long_image_path = sys.argv[1] if len(sys.argv) > 1 else "test/test_data_output/stitched_screenshot.png"
    messages = extract_structured_messages(long_image_path)
    print(messages)
    out_dir = os.path.dirname(long_image_path)
    out_path = os.path.join(out_dir, "structured_messages.json") if out_dir else "structured_messages.json"
    os.makedirs(out_dir, exist_ok=True) if out_dir else None
    with open(out_path, "w") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)
    