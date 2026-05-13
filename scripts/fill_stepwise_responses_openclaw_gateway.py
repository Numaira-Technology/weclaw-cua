#!/usr/bin/env python3
"""Fill step_*.response.txt via the configured OpenClaw gateway.

Usage:
  python scripts/fill_stepwise_responses_openclaw_gateway.py output/work
  python scripts/fill_stepwise_responses_openclaw_gateway.py output/work --skip-existing
  python scripts/fill_stepwise_responses_openclaw_gateway.py output/work --workers 4

Input spec:
  - work_dir: directory containing manifest.json, step_*.png, step_*.prompt.txt
  - Gateway config comes from OPENCLAW_* env vars or ~/.openclaw/openclaw.json

Output spec:
  - Writes each task's response_file with raw assistant text for `weclaw finalize`.
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", help="Directory with manifest.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing non-empty responses")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip tasks whose response file already exists and is non-empty",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Concurrent gateway VLM requests (default: WECLAW_ASYNC_VLM_WORKERS or 2)",
    )
    args = parser.parse_args()

    from shared.openclaw_gateway import OpenClawGatewayConfig, fill_stepwise_responses

    cfg = OpenClawGatewayConfig.from_env_or_local()
    result = fill_stepwise_responses(
        work_dir=os.path.abspath(args.work_dir),
        config=cfg,
        skip_existing=args.skip_existing,
        force=args.force,
        workers=args.workers,
    )
    print(result)


if __name__ == "__main__":
    main()
