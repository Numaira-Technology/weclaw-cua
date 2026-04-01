#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -n "${OPENCLAW_WORKSPACE:-}" ]]; then
	DEST_ROOT="${OPENCLAW_WORKSPACE}/skills"
else
	if command -v openclaw >/dev/null 2>&1; then
		WORKSPACE_DIR="$(openclaw skills list --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get(\"workspaceDir\") or \"\")" || true)"
		if [[ -n "$WORKSPACE_DIR" ]]; then
			DEST_ROOT="${WORKSPACE_DIR}/skills"
		else
			DEST_ROOT="${HOME}/.openclaw/workspace/skills"
		fi
	else
		DEST_ROOT="${HOME}/.openclaw/workspace/skills"
	fi
fi

DEST_SKILL="$DEST_ROOT/weclaw"
SRC_SKILL="$REPO_ROOT/openclaw_skill/weclaw"

mkdir -p "$DEST_SKILL"
cp "$SRC_SKILL/SKILL.md" "$DEST_SKILL/SKILL.md"

echo "Installed OpenClaw skill to: $DEST_SKILL"
echo "Set WECLAW_ROOT to your WeClaw repo (this tree): $REPO_ROOT"
