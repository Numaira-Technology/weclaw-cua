#!/usr/bin/env python3
"""查询 OpenRouter 账户 credits（官方 GET /api/v1/credits）。

Usage:
  export OPENROUTER_API_KEY=sk-or-...   # 或在 config/config.json 填写 openrouter_api_key
  python3 scripts/openrouter_credits.py

Input:  与 shared.resolve_openrouter_api_key 相同（环境变量优先，否则 config.json）。
Output: JSON；若返回 200 且含 data，额外打印 total_credits - total_usage。

说明：OpenRouter 文档称该接口需 Management API key；若得 403，到
https://openrouter.ai/docs/guides/overview/auth/management-api-keys 创建管理密钥再 export。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> None:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from shared.openrouter_api_key import resolve_openrouter_api_key

    key = resolve_openrouter_api_key()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/credits",
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(err, file=sys.stderr)
        print(
            "HTTP {0}: 若 message 含 Forbidden，请换用 OpenRouter「Management」密钥。".format(e.code),
            file=sys.stderr,
        )
        raise SystemExit(e.code) from e
    data = json.loads(body)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    d = data.get("data")
    if isinstance(d, dict):
        tc = d.get("total_credits")
        tu = d.get("total_usage")
        if tc is not None and tu is not None:
            rem = float(tc) - float(tu)
            print(f"approx_remaining: {rem}")


if __name__ == "__main__":
    main()
