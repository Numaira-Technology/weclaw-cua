#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -x "${SCRIPT_DIR}/.venv/bin/python3" ]]; then
	PYTHON="${SCRIPT_DIR}/.venv/bin/python3"
else
	PYTHON="python3"
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
	if ! "$PYTHON" -c "import AppKit, ApplicationServices, Quartz, numpy" 2>/dev/null; then
		echo "WeClaw on macOS requires PyObjC (AppKit, ApplicationServices, Quartz) and numpy. Current interpreter:"
		"$PYTHON" -c "import sys; print(sys.executable)"
		echo ""
		echo "Create a venv and install dependencies:"
		echo "  cd \"${SCRIPT_DIR}\""
		echo "  python3 -m venv .venv"
		echo "  ./.venv/bin/pip install -r requirements.txt"
		echo "  ./run.sh"
		exit 1
	fi
fi

export WECLAW_CONFIG_PATH="${1:-$SCRIPT_DIR/config/config.json}"

"$PYTHON" "$SCRIPT_DIR/scripts/run_full_pipeline.py"
