"""capture command — vision-based WeChat message capture.

Usage:
    weclaw capture                     # capture with configured built-in LLM
    weclaw capture --no-llm            # stepwise: output images+prompts, no LLM
    weclaw capture --work-dir /tmp/w   # custom work directory for stepwise output

In --no-llm mode, WeClaw uses local OCR to navigate all selected chats and
performs screenshot/scroll/stitch capture without calling an LLM. It writes the
chat images and extraction prompts to a work directory for an external agent,
which then calls `weclaw finalize`.
"""

from importlib import import_module

import click

from ..output.formatter import output


@click.group(invoke_without_command=True)
@click.option("--no-llm", is_flag=True, default=False,
              help="Stepwise mode: output images+prompts, no LLM calls")
@click.option("--work-dir", default=None,
              help="Work directory for stepwise output (default: <output_dir>/work)")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.option("--chat-type", default=None,
              type=click.Choice(["group", "private", "all"]),
              help="Override chat type selection: group, private, or all")
@click.option("--unread-mode", default=None,
              type=click.Choice(["unread", "all"]),
              help="Override unread selection: unread badges only, or all selected chats")
@click.option("--sidebar-max-scrolls", default=None, type=int,
              help="Override max downward sidebar scrolls per scan")
@click.option("--chat-max-scrolls", default=None, type=int,
              help="Override max upward chat-panel scrolls per chat")
@click.option("--recent-window-hours", default=None, type=int,
              help="Keep only messages within this many hours (0 = no limit)")
@click.pass_context
def capture(
    ctx,
    no_llm,
    work_dir,
    fmt,
    chat_type,
    unread_mode,
    sidebar_max_scrolls,
    chat_max_scrolls,
    recent_window_hours,
):
    """Capture selected WeChat messages via vision.

    \b
    Default mode (--no-llm NOT set):
      Uses the configured built-in LLM for vision tasks.
      Produces final message JSON files directly.

    \b
    Stepwise mode (--no-llm):
      1. Uses local OCR to navigate all selected chats
      2. Scroll-captures and stitches each chat's frames
      3. Writes one extraction task per image chunk
      4. Agent processes tasks with its own LLM
      5. Agent calls `weclaw finalize --work-dir <dir>` to produce JSON
    """
    if ctx.invoked_subcommand is not None:
        return

    import os
    import sys

    from ..context import apply_capture_overrides, load_app_context
    from ..progress import progress_to_stderr
    from shared.capture_result import capture_failures, capture_status

    app = load_app_context(ctx)
    config = app["config"]
    config = apply_capture_overrides(
        config,
        chat_type=chat_type,
        unread_mode=unread_mode,
        sidebar_max_scrolls=sidebar_max_scrolls,
        chat_max_scrolls=chat_max_scrolls,
        recent_window_hours=recent_window_hours,
    )

    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    if no_llm:
        from shared.stepwise_backend import StepwiseBackend
        from algo_a.pipeline_a_stepwise import run_pipeline_a_stepwise

        if not work_dir:
            work_dir = os.path.join(app["output_dir"], "work")
        os.makedirs(work_dir, exist_ok=True)
        backend = StepwiseBackend(
            work_dir,
            record_untyped_queries=False,
        )
        backend.set_metadata({"recent_window_hours": config.recent_window_hours})

        with progress_to_stderr():
            capture_result = run_pipeline_a_stepwise(config, backend)

        manifest_path = os.path.join(work_dir, "manifest.json")
        pending = backend.get_pending_tasks()
        failures = capture_failures(capture_result)
        status = capture_status(capture_result)
        result = {
            "mode": "stepwise",
            "ok": not failures,
            "status": status,
            "work_dir": os.path.abspath(work_dir),
            "manifest": manifest_path,
            "run_id": backend.run_id,
            "chats_captured": len(backend.get_message_chat_names()),
            "pending_tasks": len(pending),
            "failures": failures,
            "instructions": (
                "Process each task in manifest.json: send the .png image with "
                "the .prompt.txt content to your vision LLM, then write the "
                "model response to the corresponding .response.txt file. "
                "After all tasks are complete, run: weclaw finalize --work-dir "
                + os.path.abspath(work_dir)
            ),
        }
        if fmt == "json":
            output(result, "json")
        else:
            lines = [
                f"Stepwise capture complete. Work directory: {work_dir}",
                f"Manifest: {manifest_path}",
                f"Pending vision tasks: {len(pending)}",
                "",
                "Next steps for the agent:",
                "  1. Read manifest.json for pending vision tasks",
                "  2. For each task: send .png + .prompt.txt to your vision LLM",
                "  3. Write model response to .response.txt",
                f"  4. Run: weclaw finalize --work-dir {os.path.abspath(work_dir)}",
            ]
            output("\n".join(lines), "text")
        if failures:
            ctx.exit(1)
        return

    from algo_a import run_pipeline_a

    with progress_to_stderr():
        capture_result = run_pipeline_a(config)
    json_paths = list(capture_result)
    failures = capture_failures(capture_result)
    status = capture_status(capture_result)

    result = {
        "mode": "direct",
        "ok": not failures,
        "status": status,
        "chats_captured": len(json_paths),
        "files": json_paths,
        "failures": failures,
    }

    if fmt == "json":
        output(result, "json")
    else:
        if json_paths:
            lines = [f"Captured {len(json_paths)} chat(s):"]
            for p in json_paths:
                lines.append(f"  {p}")
            output("\n".join(lines), "text")
        else:
            output("No matching chats found.", "text")
    if failures:
        ctx.exit(1)


capture.add_command(
    import_module("weclaw_cli.commands.capture_test_img").capture_test_img
)
