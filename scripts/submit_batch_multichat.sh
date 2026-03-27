#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${OPENROUTER_API_KEY:?Set OPENROUTER_API_KEY}"
exec python3 -u scripts/debug_mac_multiple_chats.py "$@"
