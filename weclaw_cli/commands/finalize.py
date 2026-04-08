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

    app = load_app_context(ctx)
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    assert os.path.isdir(work_dir), f"Work directory not found: {work_dir}"
    manifest_path = os.path.join(work_dir, "manifest.json")
    assert os.path.isfile(manifest_path), f"manifest.json not found in {work_dir}"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    tasks = manifest.get("tasks", [])
    if not tasks:
        click.echo("No tasks in manifest.", err=True)
        ctx.exit(1)

    from shared.vision_response_json import parse_json_object_from_model_text
    from shared.datatypes import ChatMessage

    out_dir = app["output_dir"]
    os.makedirs(out_dir, exist_ok=True)

    all_messages: list[dict] = []
    missing = []

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
        except Exception:
            print(f"[WARN] Could not parse JSON from {step_id}.response.txt")
            continue

        messages_data = data.get("messages", [])
        if not messages_data and data.get("threads"):
            continue

        for msg_data in messages_data:
            if "content" not in msg_data:
                continue
            all_messages.append(msg_data)

        task["completed"] = True

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if all_messages:
        output_path = os.path.join(out_dir, "finalized_messages.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_messages, f, ensure_ascii=False, indent=2)

    result = {
        "ok": True,
        "total_tasks": len(tasks),
        "completed": len(tasks) - len(missing),
        "missing_responses": missing,
        "messages_extracted": len(all_messages),
    }
    if all_messages:
        result["output_file"] = os.path.abspath(output_path)

    if fmt == "json":
        output(result, "json")
    else:
        lines = [
            f"Finalized {result['completed']}/{result['total_tasks']} tasks.",
            f"Extracted {len(all_messages)} messages.",
        ]
        if missing:
            lines.append(f"Missing responses: {', '.join(missing)}")
        if all_messages:
            lines.append(f"Output: {output_path}")
        output("\n".join(lines), "text")
