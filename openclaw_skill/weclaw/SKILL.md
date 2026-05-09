---
name: weclaw
description: Sync selected WeChat desktop chats to JSON on the host, generate an optional LLM report, and answer questions from the captured messages.
metadata:
  {
    "openclaw":
      {
        "emoji": "🦞",
        "os": ["darwin", "win32"],
        "requires": { "anyBins": ["python3"] },
      },
  }
---

# WeClaw (OpenClaw host skill)

WeChat must be the **desktop app** on the **same machine** as OpenClaw Gateway. This skill automates the UI; it does not work from a phone alone.

## One-time setup on the host

1. Clone WeClaw next to your workspace or any fixed path. Set a durable env var (shell profile or OpenClaw `skills.entries.weclaw.env`):

   - `WECLAW_ROOT` = absolute path to the WeClaw git checkout (directory that contains `run.sh`).

2. Python venv (from WeClaw README):

   ```bash
   cd "$WECLAW_ROOT"
   python3 -m venv .venv
   ./.venv/bin/pip install -r requirements.txt
   ```

3. Copy `config/config.json.example` to `config/config.json`. Fill `groups_to_monitor` and either put `openrouter_api_key` in the file or export `OPENROUTER_API_KEY` (env overrides JSON when present per WeClaw config).

4. **macOS:** grant Accessibility to the app running Python (Terminal, iTerm, or the OpenClaw host). **Windows:** match elevation with WeChat if needed.

5. Install this skill into the **active OpenClaw workspace** `skills/weclaw/` (the script uses `openclaw skills list --json` to find `workspaceDir` when `openclaw` is on `PATH`, or set `OPENCLAW_WORKSPACE` to override):

   ```bash
   "$WECLAW_ROOT/scripts/install_openclaw_skill.sh"
   ```

   Or copy `{baseDir}` (this skill’s directory) into your workspace `skills/weclaw/` yourself. OpenClaw discovers `skills/weclaw/SKILL.md`.

Optional `openclaw.json` (JSON5) snippet so the agent always sees `WECLAW_ROOT`:

```text
skills.entries.weclaw.env.WECLAW_ROOT = "/absolute/path/to/weclaw"
```

## Run the capture + report pipeline

From the host shell (or schedule via OpenClaw **cron** / systemd / launchd calling the same command):

```bash
export WECLAW_ROOT="/absolute/path/to/weclaw"
export WECLAW_CONFIG_PATH="$WECLAW_ROOT/config/config.json"
cd "$WECLAW_ROOT"
./run.sh
```

With a non-default config path:

```bash
./run.sh /path/to/other-config.json
```

Stdout is the generated **report text** (or `No matching messages found.`). Structured chat exports are JSON files under `output_dir` from config (default `output/`).

## Machine-readable status

After every run, WeClaw writes **`last_run.json`** inside the configured `output_dir`:

- `ok` — pipeline completed without exception
- `message_json_paths` — list of JSON files produced this run (may be empty)
- `report_generated` — whether algo_b ran
- `error` — set when `ok` is false (run still surfaces the exception afterward)

Use this file in automation to decide whether to notify the user or attach paths in a follow-up agent turn.

## Answering user questions

When the user asks about WeChat content **after** a successful run:

1. Run `weclaw-cua qa-context "<user question>"` from `WECLAW_ROOT`. This reads `last_run.json`, ranks nearby message snippets across the captured JSON files, and returns cited context.
2. Answer only from the returned snippets. Prefer quoting chat facts with chat/sender/time; do not invent messages.
3. If the user explicitly asks about older history, rerun with `--all-history` and optional `--chat "Name"` filters.
4. If ranked snippets are insufficient, say what is missing and use `weclaw-cua search`, `weclaw-cua history`, or direct JSON reads as a follow-up.

If `message_json_paths` is empty, say that there were no captured chats this run and offer to run `./run.sh` again.

## Cron / nightly jobs

Point the scheduler at the host path only (Gateway must be able to execute on the machine where WeChat runs). Example: run `bash -lc 'cd "$WECLAW_ROOT" && ./run.sh'` at the desired time. OpenClaw’s cron tool can invoke the same command when the **main** session has cron enabled; see OpenClaw automation docs.
