"""finalize command — process agent-provided LLM responses into final JSON.

Usage:
    weclaw finalize --work-dir /tmp/weclaw_work

After `weclaw capture --no-llm`, the agent processes each vision task
in the work directory's manifest.json and writes .response.txt files.
This command reads those responses and produces final message JSON files.
"""

import json
import os

import click

from ..output.formatter import output


def _recent_window_from_manifest(manifest: dict, fallback_hours: int = 0) -> int:
    metadata = manifest.get("metadata", {})
    raw = metadata.get("recent_window_hours", fallback_hours)
    assert type(raw) is int, "recent_window_hours in manifest metadata must be an integer"
    assert raw >= 0, "recent_window_hours in manifest metadata must be >= 0"
    return raw


def _filter_finalized_messages_to_recent_window(
    messages: list[dict],
    *,
    hours: int,
) -> list[dict]:
    if hours <= 0:
        return list(messages)
    from shared.datatypes import ChatMessage
    from shared.message_time_window import filter_messages_to_recent_window

    typed_messages = [
        ChatMessage(
            sender=msg.get("sender"),
            content=str(msg.get("content", "")),
            time=msg.get("time"),
            type=str(msg.get("type", "unsupported")),
        )
        for msg in messages
    ]
    kept = {id(msg) for msg in filter_messages_to_recent_window(typed_messages, hours=hours)}
    return [raw for raw, typed in zip(messages, typed_messages) if id(typed) in kept]


def finalize_work_dir(work_dir: str, out_dir: str, recent_window_hours: int = 0) -> dict:
    assert os.path.isdir(work_dir), f"Work directory not found: {work_dir}"
    manifest_path = os.path.join(work_dir, "manifest.json")
    assert os.path.isfile(manifest_path), f"manifest.json not found in {work_dir}"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    tasks = manifest.get("tasks", [])
    assert tasks, "No tasks in manifest."
    manifest_run_id = str(manifest.get("run_id", "") or "").strip()
    if manifest_run_id:
        tasks = [
            task
            for task in tasks
            if str(task.get("run_id", manifest_run_id) or "") == manifest_run_id
        ]
    assert tasks, "No tasks for the active manifest run."
    recent_window_hours = _recent_window_from_manifest(
        manifest,
        fallback_hours=recent_window_hours,
    )

    from shared.vision_response_json import parse_json_object_from_model_text
    from shared.message_schema import VALID_MESSAGE_TYPES

    os.makedirs(out_dir, exist_ok=True)

    all_messages: list[dict] = []
    missing = []
    failed = []
    current_chat_name = "Current Chat"

    for task in tasks:
        step_id = task["step_id"]
        response_file = os.path.join(work_dir, task["response_file"])

        if not os.path.isfile(response_file):
            missing.append(step_id)
            continue

        with open(response_file, "r", encoding="utf-8") as f:
            response_text = f.read().strip()

        if not response_text:
            missing.append(step_id)
            continue

        try:
            data = parse_json_object_from_model_text(response_text)
        except Exception as exc:
            print(f"[WARN] Could not parse JSON from {step_id}.response.txt")
            failed.append(
                {
                    "step_id": step_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        task_metadata = task.get("metadata", {})
        task_kind = str(task_metadata.get("kind", "") or "")
        detected_chat_name = data.get("chat_name")
        if isinstance(detected_chat_name, str) and detected_chat_name.strip():
            current_chat_name = detected_chat_name.strip()
        task_chat_name = str(task_metadata.get("chat_name", "") or "").strip()
        effective_chat_name = task_chat_name or current_chat_name

        messages_data = data.get("messages", [])
        if not messages_data and data.get("threads"):
            task["completed"] = True
            continue
        if task_kind and task_kind != "message_extraction":
            task["completed"] = True
            continue
        if not isinstance(messages_data, list):
            failed.append(
                {
                    "step_id": step_id,
                    "error": "messages must be a JSON array",
                }
            )
            continue

        for msg_data in messages_data:
            if not isinstance(msg_data, dict) or "content" not in msg_data:
                continue
            normalized = dict(msg_data)
            if not normalized.get("chat_name"):
                normalized["chat_name"] = effective_chat_name
            if normalized.get("type") not in VALID_MESSAGE_TYPES:
                normalized["type"] = "unsupported"
            all_messages.append(normalized)

        task["completed"] = True

    unfiltered_message_count = len(all_messages)
    all_messages = _filter_finalized_messages_to_recent_window(
        all_messages,
        hours=recent_window_hours,
    )
    deduped_messages: list[dict] = []
    seen_messages: set[tuple] = set()
    for message in all_messages:
        identity = (
            message.get("chat_name"),
            message.get("sender"),
            message.get("time"),
            message.get("content"),
            message.get("type"),
        )
        if identity in seen_messages:
            continue
        seen_messages.add(identity)
        deduped_messages.append(message)
    all_messages = deduped_messages

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    completed_count = sum(bool(task.get("completed")) for task in tasks)
    result = {
        "ok": not missing and not failed,
        "total_tasks": len(tasks),
        "completed": completed_count,
        "missing_responses": missing,
        "failed_responses": failed,
        "messages_extracted": len(all_messages),
        "messages_before_recent_window": unfiltered_message_count,
        "recent_window_hours": recent_window_hours,
    }
    output_path = os.path.join(out_dir, "finalized_messages.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_messages, f, ensure_ascii=False, indent=2)
    result["output_file"] = os.path.abspath(output_path)
    return result


@click.command()
@click.option("--work-dir", required=True,
              help="Path to the stepwise work directory")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def finalize(ctx, work_dir, fmt):
    """Process agent-provided vision responses into final message JSON.

    \b
    After running `weclaw capture --no-llm`:
      1. Agent reads manifest.json from work-dir
      2. For each task: sends .png + .prompt.txt to its own LLM
      3. Writes model response to .response.txt
      4. Agent runs this command to produce final message JSON files

    \b
    This command reads the .response.txt files and extracts messages
    from the vision model responses, producing output/*.json files.
    """
    import sys

    from ..context import load_app_context
    from ..progress import progress_to_stderr

    app = load_app_context(ctx)
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    try:
        with progress_to_stderr():
            result = finalize_work_dir(
                work_dir=work_dir,
                out_dir=app["output_dir"],
                recent_window_hours=app["config"].recent_window_hours,
            )
    except AssertionError as e:
        click.echo(str(e), err=True)
        ctx.exit(1)

    if fmt == "json":
        output(result, "json")
    else:
        missing = result.get("missing_responses", [])
        output_path = result.get("output_file")
        lines = [
            f"Finalized {result['completed']}/{result['total_tasks']} tasks.",
            f"Extracted {result['messages_extracted']} messages.",
        ]
        if missing:
            lines.append(f"Missing responses: {', '.join(missing)}")
        if output_path:
            lines.append(f"Output: {output_path}")
        output("\n".join(lines), "text")
    if not result["ok"]:
        ctx.exit(1)
