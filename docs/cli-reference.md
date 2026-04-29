## WeClaw-CUA CLI reference

This document describes command behavior, capture-selection controls, and output schemas.

## Global options

`weclaw-cua` and the `weclaw` alias accept:

- `--config PATH`: load a specific `config.json`. If omitted, the CLI uses `WECLAW_CONFIG_PATH`, then searches for `config/config.json` from the current directory upward.
- `--version`: print the CLI version.

## Capture selection

`run`, `capture`, and `unread` read these fields from `config/config.json`:

- `groups_to_monitor`: `["*"]` or `[]` scans every chat allowed by `chat_type`; otherwise it is a list of exact or sidebar-truncated chat names.
- `chat_type`: `group`, `private`, or `all`.
- `sidebar_unread_only`: `true` processes only rows with unread badges; `false` processes both read and unread rows.
- `sidebar_max_scrolls`: maximum downward sidebar scrolls during each scan.
- `chat_max_scrolls`: maximum upward chat-panel scrolls while collecting one chat.

 `run` and `capture` can override those values for a single invocation:

```bash
weclaw-cua capture --chat-type private --unread-mode unread
weclaw-cua run --chat-type all --unread-mode all
weclaw-cua run --sidebar-max-scrolls 30 --chat-max-scrolls 20
```

 `unread` supports `--chat-type` and `--sidebar-max-scrolls`.

 Sidebar return-to-top scrolling is derived from `sidebar_max_scrolls`: after a scan that can move down `N` times, WeClaw scrolls up `N + 2` times before starting the next locate pass.

## Data files

Captured message files are JSON arrays. Each item has this shape:

```json
{
  "chat_name": "Team Chat",
  "sender": "Alice",
  "time": "10:15",
  "content": "Please review the proposal.",
  "type": "text"
}
```

 `sender` may be an empty string for system messages. `time` may be `null` or empty when the UI does not show a timestamp. `type` is one of `text`, `system`, `link_card`, `image`, `file`, `recalled`, or `unsupported`.

## Commands

### `init`

 Creates `config/config.json` from the example template and checks platform prerequisites.

Options:

- `--config-dir PATH`: write config in a custom directory.
- `--force`: overwrite an existing config.

Text output reports the config path and prerequisite status.

### `capture`

Captures selected WeChat chats and writes message JSON files. Direct mode calls the configured vision LLM. Stepwise mode writes images and prompts for an external agent.

 Options:

- `--no-llm`: stepwise mode.
- `--work-dir PATH`: stepwise output directory.
- `--format json|text`.
- `--chat-type group|private|all`.
- `--unread-mode unread|all`.
- `--sidebar-max-scrolls N`.
- `--chat-max-scrolls N`.

Capture-selection options override only the current command invocation and do not rewrite `config.json`.

JSON output in direct mode:

```json
{
  "mode": "direct",
  "ok": true,
  "chats_captured": 2,
  "files": ["output/Team.json", "output/Alice.json"]
}
```

JSON output in stepwise mode:

```json
{
  "mode": "stepwise",
  "work_dir": "/abs/weclaw_work",
  "manifest": "/abs/weclaw_work/manifest.json",
  "pending_tasks": 4,
  "instructions": "..."
}
```

 ### `run`

 Runs capture, then generates a report when messages were captured. `--no-llm` delegates to stepwise capture and skips report generation. `--openclaw-gateway` uses the local OpenClaw gateway for vision and report calls.

 Options:

 - `--no-llm`.
 - `--openclaw-gateway`.
 - `--work-dir PATH`.
 - `--format json|text`.
 - `--chat-type group|private|all`.
 - `--unread-mode unread|all`.
 - `--sidebar-max-scrolls N`.
 - `--chat-max-scrolls N`.

Capture-selection options override only the current command invocation and do not rewrite `config.json`.

JSON output:

```json
{
  "ok": true,
  "chats_captured": 2,
  "files": ["output/Team.json", "output/Alice.json"],
  "report_generated": true,
  "report": "..."
}
```

 OpenClaw gateway mode also includes `"backend": "openclaw-gateway"`.

 ### `finalize`

 Reads stepwise `.response.txt` files from a work directory and writes finalized message JSON.

 Options:

 - `--work-dir PATH` is required.
 - `--format json|text`.

JSON output:

```json
{
  "ok": true,
  "total_tasks": 4,
  "completed": 4,
  "missing_responses": [],
  "messages_extracted": 38,
  "output_file": "/abs/output/finalized_messages.json"
}
```

 ### `report`

 Builds a report from captured message JSON files. By default it calls the configured LLM. `--prompt-only` prints the prompt without an LLM call.

 Options:

 - `--input PATH`: repeatable input files; defaults to all message JSON in `output_dir`.
 - `--prompt-only`.
 - `--format json|text`.

JSON output:

```json
{
  "report": "...",
  "source_files": ["output/Team.json"]
}
```

 ### `build-report-prompt`

 Prints the report prompt for external LLM processing.

 Options:

 - `--input PATH`: repeatable input files; defaults to all message JSON in `output_dir`.

 Output is plain text.

 ### `sessions`

 Lists captured chat files.

 Options:

 - `--limit N`.
 - `--format json|text`.

JSON output:

```json
[
  {
    "chat": "Team",
    "file": "Team.json",
    "messages": 38,
    "captured_at": "2026-04-28 18:00"
  }
]
```

 ### `history`

 Shows messages from one captured chat.

 Options:

 - `--limit N`.
 - `--offset N`.
 - `--type text|system|link_card|image|file|recalled|unsupported`.
 - `--format json|text`.

JSON output:

```json
{
  "chat": "Team",
  "count": 20,
  "total": 38,
  "offset": 0,
  "limit": 20,
  "type": null,
  "messages": []
}
```

 ### `search`

 Searches captured messages by keyword.

 Options:

 - `--chat NAME`: repeatable chat filter.
 - `--limit N`.
 - `--offset N`.
 - `--type text|system|link_card|image|file|recalled|unsupported`.
 - `--format json|text`.

JSON output:

```json
{
  "scope": "all chats",
  "keyword": "deadline",
  "count": 1,
  "total": 1,
  "offset": 0,
  "limit": 20,
  "type": null,
  "results": [
    {
      "chat": "Team",
      "sender": "Alice",
      "time": "10:15",
      "content": "deadline is Friday",
      "type": "text"
    }
  ]
}
```

 ### `export`

 Exports one captured chat as Markdown or plain text.

 Options:

 - `--format markdown|txt`.
 - `--output PATH`: write to file; otherwise prints to stdout.
 - `--limit N`.

 Output is Markdown or plain text, not JSON.

 ### `stats`

 Shows message counts for one captured chat.

 Options:

 - `--format json|text`.

JSON output:

```json
{
  "chat": "Team",
  "total": 38,
  "type_breakdown": {"text": 35, "system": 3},
  "top_senders": [{"name": "Alice", "count": 12}]
}
```

 ### `unread`

 Scans the sidebar for chats with unread badges. It does not capture chat messages.

 Options:

 - `--limit N`.
 - `--format json|text`.
 - `--chat-type group|private|all`.
 - `--sidebar-max-scrolls N`.

JSON output:

```json
[
  {
    "chat": "Team",
    "unread": "3"
  }
]
```

 ### `new-messages`

 Compares capture file modification times against `<output_dir>/last_check.json`.

 Options:

 - `--format json|text`.

 First-call JSON output:

```json
{
  "first_call": true,
  "count": 2,
  "chats": [
    {"chat": "Team", "file": "Team.json", "time": "18:00"}
  ]
}
```

 Subsequent JSON output:

```json
{
  "first_call": false,
  "new_count": 1,
  "chats": [
    {"chat": "Team", "file": "Team.json", "time": "18:05:12"}
  ]
}
```
