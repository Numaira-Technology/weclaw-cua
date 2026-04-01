#!/usr/bin/env python3
"""Host entry for WeClaw: algo_a → algo_b, print report, write `output/last_run.json`.

Usage:
  WECLAW_CONFIG_PATH=config/config.json python scripts/run_full_pipeline.py

  From repo root after `cd` (run.sh sets WECLAW_CONFIG_PATH):

  ./run.sh
  ./run.sh /path/to/config.json

Input spec:
  - WECLAW_CONFIG_PATH: path to JSON config (see config.json.example).

Output spec:
  - Prints report text or `No unread messages found.` to stdout.
  - Writes last_run.json under config.output_dir (always; on failure ok=false and re-raises).
"""

from __future__ import annotations


def _repo_root() -> str:
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, ".."))


def main() -> None:
    import os
    import sys

    root = _repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    from algo_a import run_pipeline_a
    from algo_b import run_pipeline_b
    from config import load_config
    from shared.run_manifest import build_last_run_payload, write_last_run

    config_path = os.environ.get("WECLAW_CONFIG_PATH", "").strip()
    assert config_path, "WECLAW_CONFIG_PATH must be set"
    config = load_config(config_path)
    out_dir = config.output_dir
    if not os.path.isabs(out_dir):
        out_dir = os.path.normpath(os.path.join(root, out_dir))

    err: str | None = None
    json_paths: list[str] = []
    report_generated = False
    try:
        json_paths = run_pipeline_a(config)
        abs_json = [os.path.abspath(p) for p in json_paths]
        if abs_json:
            report = run_pipeline_b(config, abs_json)
            report_generated = True
            print(report)
        else:
            print("No unread messages found.")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        payload = build_last_run_payload(
            ok=False,
            config_path=config_path,
            weclaw_root=root,
            output_dir=out_dir,
            message_json_paths=[],
            report_generated=False,
            error=err,
        )
        write_last_run(out_dir, payload)
        raise

    payload = build_last_run_payload(
        ok=True,
        config_path=config_path,
        weclaw_root=root,
        output_dir=out_dir,
        message_json_paths=json_paths,
        report_generated=report_generated,
        error=None,
    )
    write_last_run(out_dir, payload)


if __name__ == "__main__":
    main()
