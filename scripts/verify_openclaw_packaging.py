#!/usr/bin/env python3
"""Verify WeClaw OpenClaw skill layout, manifest helpers, and install script.

Usage:
  python scripts/verify_openclaw_packaging.py

Input spec:
  - Run from repository root (or any cwd; paths are relative to this file’s parent dir).

Output spec:
  - Exits 0 if all checks pass; raises AssertionError otherwise.
"""

from __future__ import annotations


def main() -> None:
    import json
    import os
    import shutil
    import subprocess
    import tempfile

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, ".."))
    skill_md = os.path.join(root, "openclaw_skill", "weclaw", "SKILL.md")
    assert os.path.isfile(skill_md), skill_md

    text = open(skill_md, encoding="utf-8").read()
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    end = text.index("---\n", 3)
    front = text[4:end]
    assert 'name: weclaw' in front
    assert "description:" in front
    assert "metadata:" in front

    import sys

    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.run_manifest import build_last_run_payload, write_last_run

    tmp = tempfile.mkdtemp(prefix="weclaw_oc_verify_")
    try:
        out_sub = os.path.join(tmp, "out")
        p = build_last_run_payload(
            ok=True,
            config_path=os.path.join(tmp, "c.json"),
            weclaw_root=root,
            output_dir=out_sub,
            message_json_paths=[os.path.join(tmp, "x.json")],
            report_generated=True,
            error=None,
        )
        w = write_last_run(out_sub, p)
        assert w.endswith("last_run.json")
        loaded = json.load(open(w, encoding="utf-8"))
        assert loaded["ok"] is True
        assert loaded["report_generated"] is True
        assert len(loaded["message_json_paths"]) == 1
        assert loaded["error"] is None

        fake_ws = os.path.join(tmp, "ws")
        env = {**os.environ, "OPENCLAW_WORKSPACE": fake_ws}
        subprocess.run(
            ["bash", os.path.join(root, "scripts", "install_openclaw_skill.sh")],
            check=True,
            env=env,
        )
        installed = os.path.join(fake_ws, "skills", "weclaw", "SKILL.md")
        assert os.path.isfile(installed)
        assert open(installed, encoding="utf-8").read() == text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("openclaw packaging verification: OK")


if __name__ == "__main__":
    main()
