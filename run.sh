#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_PATH="${1:-$SCRIPT_DIR/config/config.json}"

cd "$SCRIPT_DIR"

python3 -c "
from config import load_config
from algo_a import run_pipeline_a
from algo_b import run_pipeline_b

config = load_config('$CONFIG_PATH')
json_paths = run_pipeline_a(config)
if json_paths:
    report = run_pipeline_b(config, json_paths)
    print(report)
else:
    print('No unread messages found.')
"
