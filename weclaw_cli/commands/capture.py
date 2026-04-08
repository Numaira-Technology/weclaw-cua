"""capture command — vision-based WeChat message capture.

Usage:
    weclaw capture                     # capture with built-in LLM (OpenRouter)
    weclaw capture --no-llm            # stepwise: output images+prompts, no LLM
    weclaw capture --work-dir /tmp/w   # custom work directory for stepwise output

In --no-llm mode, WeClaw performs all UI automation (screenshot, scroll, stitch)
but does NOT call any LLM. Instead it writes images and prompts to a work directory.
The calling agent processes them with its own LLM, then calls `weclaw finalize`.
"""

import click

from ..output.formatter import output


@click.command()
@click.option("--no-llm", is_flag=True, default=False,
              help="Stepwise mode: output images+prompts, no LLM calls")
@click.option("--work-dir", default=None,
              help="Work directory for stepwise output (default: <output_dir>/work)")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def capture(ctx, no_llm, work_dir, fmt):
    """Capture unread WeChat messages via vision.

    \b
    Default mode (--no-llm NOT set):
      Uses built-in OpenRouter LLM for vision tasks.
      Produces final message JSON files directly.

    \b
    Stepwise mode (--no-llm):
      1. Performs all UI automation (screenshot, scroll, stitch)
      2. Writes images + prompts to work directory
      3. Outputs a manifest.json listing pending vision tasks
      4. Agent processes tasks with its own LLM
      5. Agent calls `weclaw finalize --work-dir <dir>` to produce JSON
    """
    import os
    import sys

    from ..context import load_app_context

    app = load_app_context(ctx)
    config = app["config"]

    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    vision_backend = None
    if no_llm:
        from shared.stepwise_backend import StepwiseBackend
        if not work_dir:
            work_dir = os.path.join(app["output_dir"], "work")
        os.makedirs(work_dir, exist_ok=True)
        vision_backend = StepwiseBackend(work_dir)

    from algo_a import run_pipeline_a

    json_paths = run_pipeline_a(config, vision_backend=vision_backend)

    if no_llm:
        manifest_path = os.path.join(work_dir, "manifest.json")
        result = {
            "mode": "stepwise",
            "work_dir": os.path.abspath(work_dir),
            "manifest": manifest_path,
            "instructions": (
                "Process each task in manifest.json: send the .png image with "
                "the .prompt.txt content to your vision LLM, then write the "
                "model response to the corresponding .response.txt file. "
                "After all tasks are complete, run: weclaw finalize --work-dir "
                + os.path.abspath(work_dir)
            ),
        }
        if json_paths:
            result["partial_files"] = json_paths
    else:
        result = {
            "mode": "direct",
            "ok": True,
            "chats_captured": len(json_paths),
            "files": json_paths,
        }

    if fmt == "json":
        output(result, "json")
    else:
        if no_llm:
            lines = [
                f"Stepwise capture complete. Work directory: {work_dir}",
                f"Manifest: {os.path.join(work_dir, 'manifest.json')}",
                "",
                "Next steps for the agent:",
                "  1. Read manifest.json for pending vision tasks",
                "  2. For each task: send .png + .prompt.txt to your vision LLM",
                "  3. Write response to .response.txt",
                "  4. Run: weclaw finalize --work-dir " + os.path.abspath(work_dir),
            ]
            output("\n".join(lines), "text")
        else:
            if json_paths:
                lines = [f"Captured {len(json_paths)} chat(s):"]
                for p in json_paths:
                    lines.append(f"  {p}")
                output("\n".join(lines), "text")
            else:
                output("No unread chats found.", "text")
