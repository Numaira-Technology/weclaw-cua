"""
Orchestrates the WeChat unread audit and removal workflow on desktop.

Usage:
  python -m workflow.run_wechat_removal [--step-mode]

Input:
  - config/computer_windows.yaml for computer settings.
  - config/model.yaml for model settings.
  - --step-mode: Run in step-by-step mode, waiting for commands from control panel.

Output:
  - Captured screenshots in artifacts/captures.
  - JSON report in artifacts/logs/report.json with threads, suspects, and removal status.
  - In step-mode: .step_result and .step_status files for control panel communication.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from modules.group_classifier import classification_prompt, parse_classification
from modules.human_confirmation import require_confirmation
from modules.message_reader import message_reader_prompt
from modules.removal_executor import removal_prompt
from modules.removal_precheck import build_removal_plan
from modules.suspicious_detector import extract_suspects
from modules.task_types import GroupThread, RemovalPlan, Suspect
from modules.unread_scanner import filter_unread_groups
from runtime.computer_session import build_computer, load_computer_settings
from runtime.model_session import build_agent, load_model_settings


async def targeted_click(
    agent, computer, element_description: str, max_retries: int = 3
) -> Tuple[bool, str]:
    """
    Perform a targeted click on a UI element using the predict_click capability.

    This implements the proper click workflow:
    1. Take a screenshot
    2. Use predict_click to find the element coordinates
    3. Execute the click at those coordinates
    4. Take another screenshot to verify

    Args:
        agent: The ComputerAgent instance
        computer: The computer interface
        element_description: Description of the element to click (e.g., "the minus button", "Catherine's avatar")
        max_retries: Number of retries if click prediction fails

    Returns:
        Tuple of (success: bool, message: str)
    """

    for attempt in range(max_retries):
        try:
            # Step 1: Take a screenshot
            screenshot_b64 = await computer.interface.screenshot()

            # Step 2: Use predict_click to find coordinates
            coords = await agent.predict_click(
                element_description, image_b64=screenshot_b64
            )

            if coords is None:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                return False, f"Could not locate element: {element_description}"

            x, y = coords

            # #region agent log
            import json as _json, time as _time
            from PIL import Image as _Image
            import io as _io, base64 as _b64
            _ss_bytes = _b64.b64decode(screenshot_b64)
            _ss_img = _Image.open(_io.BytesIO(_ss_bytes))
            _ss_w, _ss_h = _ss_img.size
            # Get actual screen size to check for scaling difference
            _screen_size = await computer.interface.get_screen_size()
            _screen_w, _screen_h = _screen_size["width"], _screen_size["height"]
            open(r"d:\Documents\Project Bird\code\cua\.cursor\debug.log", "a").write(_json.dumps({"location": "run_wechat_removal.py:targeted_click:before_transform", "message": "dimensions comparison", "data": {"predicted_x": x, "predicted_y": y, "screenshot_w": _ss_w, "screenshot_h": _ss_h, "screen_w": _screen_w, "screen_h": _screen_h, "element": element_description}, "timestamp": _time.time(), "sessionId": "debug-session", "hypothesisId": "SCREEN_VS_SCREENSHOT"}) + "\n")
            # #endregion

            # Step 3: Convert from screenshot coordinates to screen coordinates
            # The model outputs coordinates based on the screenshot it sees,
            # but clicks need to happen in actual screen space
            screen_x, screen_y = await computer.interface.to_screen_coordinates(x, y)
            screen_x, screen_y = int(round(screen_x)), int(round(screen_y))

            # #region agent log
            open(r"d:\Documents\Project Bird\code\cua\.cursor\debug.log", "a").write(_json.dumps({"location": "run_wechat_removal.py:targeted_click:after_transform", "message": "click after screen transform", "data": {"original_x": x, "original_y": y, "screen_x": screen_x, "screen_y": screen_y, "element": element_description}, "timestamp": _time.time(), "sessionId": "debug-session", "hypothesisId": "SCREEN_VS_SCREENSHOT"}) + "\n")
            # #endregion

            # Step 4: Execute the click in screen coordinates
            await computer.interface.left_click(screen_x, screen_y)

            # Step 4: Wait for UI to respond
            await asyncio.sleep(0.5)

            # Step 5: Take verification screenshot
            await computer.interface.screenshot()

            return True, f"Clicked at ({x}, {y}) for: {element_description}"

        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
                continue
            return False, f"Error clicking {element_description}: {str(e)}"

    return False, f"Failed to click {element_description} after {max_retries} attempts"


def _capture_path(root: Path, task_label: str, index: int) -> Path:
    return root / f"{task_label}_{index}.png"


def _save_screenshot(image_url: str, path: Path) -> None:
    if not image_url.startswith("data:image"):
        return
    _, encoded = image_url.split(",", 1)
    data = base64.b64decode(encoded)
    path.write_bytes(data)


async def run_vision_query(
    computer, model: str, prompt: str, capture_dir: Path, task_label: str
) -> Tuple[str, List[Path]]:
    """
    Simple vision query: take screenshot, send to model, get text response.
    No agent loop, no tool calls - just a single API call.
    """
    import time

    import litellm

    print(f"[run_vision_query] Starting: {task_label}")
    print(f"[run_vision_query] Prompt: {prompt[:100]}...")

    # Step 1: Take screenshot
    print("[run_vision_query] Taking screenshot...")
    start = time.time()
    screenshot_bytes = await computer.interface.screenshot()
    # Convert bytes to base64
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    print(
        f"[run_vision_query] Screenshot captured: {len(screenshot_b64)} chars in {time.time() - start:.1f}s"
    )

    # Save screenshot
    screenshot_path = _capture_path(capture_dir, task_label, 0)
    _save_screenshot(f"data:image/png;base64,{screenshot_b64}", screenshot_path)
    print(f"[run_vision_query] Saved to: {screenshot_path}")

    # Step 2: Send to model with image
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    print(f"[run_vision_query] Calling {model}...")
    start = time.time()
    response = await litellm.acompletion(model=model, messages=messages, timeout=60)
    elapsed = time.time() - start
    print(f"[run_vision_query] Response received in {elapsed:.1f}s")

    # Step 3: Extract text response
    text_output = response.choices[0].message.content or ""
    # Use ASCII-safe encoding for Windows console compatibility
    response_preview = text_output[:200].encode("ascii", "replace").decode("ascii")
    print(f"[run_vision_query] Response: {response_preview}...")

    return text_output, [screenshot_path]


async def run_agent_task(
    agent, prompt: str, capture_dir: Path, task_label: str
) -> Tuple[str, List[Path]]:
    """Run agent task with tool loop (for tasks that need clicking/typing)."""
    import time

    print(f"[run_agent_task] Starting task: {task_label}")
    # Use ASCII-safe encoding for Windows console compatibility
    prompt_preview = prompt[:100].encode("ascii", "replace").decode("ascii")
    print(f"[run_agent_task] Prompt: {prompt_preview}...")
    messages = [{"role": "user", "content": prompt}]
    text_messages: List[str] = []
    screenshot_paths: List[Path] = []
    index = 0
    start_time = time.time()
    print("[run_agent_task] Calling agent.run()...")
    # #region agent log
    _log_path = Path(__file__).resolve().parents[1] / ".cursor" / "debug.log"
    import json as _json

    open(_log_path, "a", encoding="utf-8").write(
        _json.dumps(
            {
                "location": "run_wechat_removal.py:run_agent_task:start",
                "message": "agent.run starting",
                "data": {"task_label": task_label, "prompt_len": len(prompt)},
                "timestamp": time.time(),
                "sessionId": "debug-session",
                "hypothesisId": "A,D",
            }
        )
        + "\n"
    )
    # #endregion
    async for result in agent.run(messages):
        elapsed = time.time() - start_time
        print(
            f"[run_agent_task] Got result after {elapsed:.1f}s with {len(result.get('output', []))} output items"
        )
        # #region agent log
        import json as _json

        open(_log_path, "a", encoding="utf-8").write(
            _json.dumps(
                {
                    "location": "run_wechat_removal.py:run_agent_task:iteration",
                    "message": "agent yielded result",
                    "data": {
                        "elapsed": elapsed,
                        "output_count": len(result.get("output", [])),
                        "output_types": [
                            item.get("type") for item in result.get("output", [])
                        ],
                    },
                    "timestamp": time.time(),
                    "sessionId": "debug-session",
                    "hypothesisId": "A,D",
                }
            )
            + "\n"
        )
        # #endregion
        for item in result["output"]:
            item_type = item.get("type")
            print(f"[run_agent_task] Processing item type: {item_type}")
            if item_type == "message":
                for content_item in item.get("content", []):
                    text = content_item.get("text")
                    if text:
                        # Use ASCII-safe encoding for Windows console compatibility
                        text_preview = (
                            text[:100].encode("ascii", "replace").decode("ascii")
                        )
                        print(f"[run_agent_task] Message text: {text_preview}...")
                        text_messages.append(text)
                        # #region agent log
                        import json as _json

                        open(_log_path, "a", encoding="utf-8").write(
                            _json.dumps(
                                {
                                    "location": "run_wechat_removal.py:run_agent_task:message",
                                    "message": "collected message text",
                                    "data": {
                                        "text_len": len(text),
                                        "text_preview": text[:300],
                                        "total_messages": len(text_messages),
                                    },
                                    "timestamp": time.time(),
                                    "sessionId": "debug-session",
                                    "hypothesisId": "A,B",
                                }
                            )
                            + "\n"
                        )
                        # #endregion
            if item_type == "computer_call_output":
                output = item.get("output", {})
                image_url = output.get("image_url", "")
                path = _capture_path(capture_dir, task_label, index)
                _save_screenshot(image_url, path)
                screenshot_paths.append(path)
                print(f"[run_agent_task] Saved screenshot to: {path}")
                index += 1
            if item_type == "computer_call":
                action = item.get("action", {})
                print(f"[run_agent_task] Computer call action: {action}")
        start_time = time.time()  # Reset for next iteration
    print(
        f"[run_agent_task] Task complete. Messages: {len(text_messages)}, Screenshots: {len(screenshot_paths)}"
    )
    final_text = text_messages[-1] if text_messages else ""
    # #region agent log
    import json as _json

    open(_log_path, "a", encoding="utf-8").write(
        _json.dumps(
            {
                "location": "run_wechat_removal.py:run_agent_task:end",
                "message": "task complete",
                "data": {
                    "total_messages": len(text_messages),
                    "final_text_len": len(final_text),
                    "final_text_preview": final_text[:500],
                    "all_messages": [m[:200] for m in text_messages],
                },
                "timestamp": time.time(),
                "sessionId": "debug-session",
                "hypothesisId": "A,D",
            }
        )
        + "\n"
    )
    # #endregion
    return final_text, screenshot_paths


def _persist_report(
    root: Path, threads: List[GroupThread], suspects: List[Suspect], plan: RemovalPlan
) -> None:
    log_dir = root / "artifacts" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "threads": [thread.__dict__ for thread in threads],
        "suspects": [
            {
                "sender_id": suspect.sender_id,
                "sender_name": suspect.sender_name,
                "avatar_path": str(suspect.avatar_path),
                "evidence_text": suspect.evidence_text,
                "thread_id": suspect.thread_id,
            }
            for suspect in suspects
        ],
        "removal_confirmed": plan.confirmed,
        "note": plan.note,
    }
    report_path = log_dir / "report.json"
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class StepModeRunner:
    def __init__(self, root: Path, agent, computer, model: str, capture_dir: Path):
        self.root = root
        self.agent = agent
        self.computer = computer
        self.model = model
        self.capture_dir = capture_dir
        self.artifacts_dir = root / "artifacts"
        self.request_file = self.artifacts_dir / ".step_request"
        self.result_file = self.artifacts_dir / ".step_result"
        self.status_file = self.artifacts_dir / ".step_status"
        print("[StepModeRunner] Initialized")
        print(f"  Request file: {self.request_file}")
        print(f"  Result file: {self.result_file}")
        print(f"  Status file: {self.status_file}")

    def _write_status(self, status: str) -> None:
        print(f"[StepModeRunner] Writing status: {status}")
        self.status_file.write_text(status, encoding="utf-8")

    def _write_result(self, result: dict) -> None:
        result_json = json.dumps(result, ensure_ascii=False, indent=2)
        print(f"[StepModeRunner] Writing result ({len(result_json)} bytes)")
        self.result_file.write_text(result_json, encoding="utf-8")

    def _write_error(self, error: str) -> None:
        print(f"[StepModeRunner] Writing error: {error}")
        self.result_file.write_text(error, encoding="utf-8")
        self._write_status("error")

    def _clear_request(self) -> None:
        print("[StepModeRunner] Clearing request file")
        self.request_file.unlink(missing_ok=True)

    async def handle_classify(self, params: dict) -> None:
        print("[StepModeRunner] Executing: classify threads (vision query)")
        prompt = classification_prompt()
        print(f"[StepModeRunner] Prompt length: {len(prompt)} chars")
        text_output, screenshots = await run_vision_query(
            self.computer, self.model, prompt, self.capture_dir, "classification"
        )
        print(
            f"[StepModeRunner] Vision query returned: {len(text_output)} chars, {len(screenshots)} screenshots"
        )
        self._write_result(
            {
                "text": text_output,
                "screenshots": [str(p) for p in screenshots],
            }
        )
        self._write_status("complete")

    async def handle_read_messages(self, params: dict) -> None:
        thread_id = params.get("thread_id", "")
        thread_name = params.get("thread_name", "")
        print(
            f"[StepModeRunner] Executing: read messages from {thread_name} (id={thread_id})"
        )
        thread = GroupThread(
            name=thread_name, thread_id=thread_id, unread=True, is_group=True
        )
        prompt = message_reader_prompt(thread)
        print(f"[StepModeRunner] Prompt length: {len(prompt)} chars")
        print("[StepModeRunner] Calling agent.run()...")
        text_output, screenshots = await run_agent_task(
            self.agent, prompt, self.capture_dir, f"reader_{thread_id}"
        )
        print(
            f"[StepModeRunner] Agent returned: {len(text_output)} chars, {len(screenshots)} screenshots"
        )
        self._write_result(
            {
                "text": text_output,
                "screenshots": [str(p) for p in screenshots],
            }
        )
        self._write_status("complete")

    async def handle_remove(self, params: dict) -> None:
        suspects_data = params.get("suspects", [])
        print(f"[StepModeRunner] Executing: remove {len(suspects_data)} suspect(s)")
        # #region agent log
        import time as _time

        _log_path = Path(__file__).resolve().parents[1] / ".cursor" / "debug.log"
        import json as _json

        open(_log_path, "a", encoding="utf-8").write(
            _json.dumps(
                {
                    "location": "run_wechat_removal.py:handle_remove:entry",
                    "message": "handle_remove called",
                    "data": {
                        "suspects_count": len(suspects_data),
                        "suspects_data": suspects_data,
                    },
                    "timestamp": _time.time(),
                    "sessionId": "debug-session",
                    "hypothesisId": "E",
                }
            )
            + "\n"
        )
        # #endregion
        suspects = [
            Suspect(
                sender_id=s["sender_id"],
                sender_name=s["sender_name"],
                avatar_path=Path(),
                evidence_text="",
                thread_id=s.get("thread_id", ""),
            )
            for s in suspects_data
        ]
        plan = RemovalPlan(suspects=suspects, confirmed=True)
        prompt = removal_prompt(plan)
        print(f"[StepModeRunner] Prompt length: {len(prompt)} chars")
        print("[StepModeRunner] Calling agent.run()...")
        # #region agent log
        import json as _json

        open(_log_path, "a", encoding="utf-8").write(
            _json.dumps(
                {
                    "location": "run_wechat_removal.py:handle_remove:before_agent",
                    "message": "about to call run_agent_task",
                    "data": {"prompt_len": len(prompt)},
                    "timestamp": _time.time(),
                    "sessionId": "debug-session",
                    "hypothesisId": "E",
                }
            )
            + "\n"
        )
        # #endregion
        try:
            text_output, screenshots = await run_agent_task(
                self.agent, prompt, self.capture_dir, "removal"
            )
        except Exception as e:
            # #region agent log
            import traceback

            import json as _json

            open(_log_path, "a", encoding="utf-8").write(
                _json.dumps(
                    {
                        "location": "run_wechat_removal.py:handle_remove:exception",
                        "message": "run_agent_task raised exception",
                        "data": {"error": str(e), "traceback": traceback.format_exc()},
                        "timestamp": _time.time(),
                        "sessionId": "debug-session",
                        "hypothesisId": "E",
                    }
                )
                + "\n"
            )
            # #endregion
            raise
        print(
            f"[StepModeRunner] Agent returned: {len(text_output)} chars, {len(screenshots)} screenshots"
        )
        self._write_result(
            {
                "text": text_output,
                "screenshots": [str(p) for p in screenshots],
            }
        )
        self._write_status("complete")

    async def process_request(self, request: dict) -> None:
        step = request.get("step", "")
        params = request.get("params", {})
        print(f"[StepModeRunner] Processing request: step={step}, params={params}")
        self._write_status("running")
        try:
            if step == "classify":
                await self.handle_classify(params)
            elif step == "read_messages":
                await self.handle_read_messages(params)
            elif step == "remove":
                await self.handle_remove(params)
            else:
                print(f"[StepModeRunner] Unknown step: {step}")
                self._write_error(f"Unknown step: {step}")
        except Exception as e:
            import traceback

            print(f"[StepModeRunner] Exception during step: {e}")
            print(f"[StepModeRunner] Traceback:\n{traceback.format_exc()}")
            self._write_error(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")

    async def run_loop(self, poll_interval: float = 0.5) -> None:
        print("\n" + "=" * 60)
        print("STEP MODE ACTIVE")
        print("=" * 60)
        print("Waiting for step requests from control panel...")
        print(f"Request file: {self.request_file}")
        print(f"Artifacts dir: {self.artifacts_dir}")
        print("Press Ctrl+C to exit.\n")

        # Ensure artifacts directory exists
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        print(
            f"[StepModeRunner] Artifacts directory ready: {self.artifacts_dir.exists()}"
        )

        loop_count = 0
        while True:
            loop_count += 1
            if loop_count % 60 == 0:  # Every 30 seconds
                print(f"[StepModeRunner] Still polling... (loop {loop_count})")

            if self.request_file.exists():
                print("[StepModeRunner] Found request file!")
                try:
                    request_text = self.request_file.read_text(encoding="utf-8")
                    # Use ASCII-safe encoding for Windows console compatibility
                    request_preview = request_text.encode("ascii", "replace").decode(
                        "ascii"
                    )
                    print(f"[StepModeRunner] Request content: {request_preview}")
                    request = json.loads(request_text)
                    self._clear_request()
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Received request: {request.get('step')}"
                    )
                    await self.process_request(request)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Step complete.\n")
                except json.JSONDecodeError as e:
                    print(f"[StepModeRunner] JSON decode error: {e}")
                    self._clear_request()
                    self._write_error(f"Invalid request JSON: {e}")
                except Exception as e:
                    import traceback

                    print(f"[StepModeRunner] Unexpected error: {e}")
                    print(f"[StepModeRunner] Traceback:\n{traceback.format_exc()}")
                    self._clear_request()
                    self._write_error(
                        f"Unexpected error: {e}\n\n{traceback.format_exc()}"
                    )
            await asyncio.sleep(poll_interval)


async def orchestrate_step_mode() -> None:
    print("[orchestrate_step_mode] Starting...")
    root = Path(__file__).resolve().parents[1]
    print(f"[orchestrate_step_mode] Root directory: {root}")

    capture_dir = root / "artifacts" / "captures"
    capture_dir.mkdir(parents=True, exist_ok=True)
    print(f"[orchestrate_step_mode] Capture directory: {capture_dir}")

    config_path = root / "config" / "computer_windows.yaml"
    print(f"[orchestrate_step_mode] Loading computer settings from: {config_path}")
    computer_settings = load_computer_settings(config_path)
    print("[orchestrate_step_mode] Computer settings loaded:")
    print(f"  use_host_computer_server: {computer_settings.use_host_computer_server}")
    print(f"  os_type: {computer_settings.os_type}")
    print(f"  api_port: {computer_settings.api_port}")

    model_config_path = root / "config" / "model.yaml"
    print(f"[orchestrate_step_mode] Loading model settings from: {model_config_path}")
    model_settings = load_model_settings(model_config_path)
    print("[orchestrate_step_mode] Model settings loaded:")
    print(f"  model: {model_settings.model}")

    print("[orchestrate_step_mode] Building computer...")
    computer = build_computer(computer_settings)

    print(
        "[orchestrate_step_mode] Connecting to computer server (await computer.run())..."
    )
    try:
        await computer.run()
        print("[orchestrate_step_mode] Computer server connected successfully!")
    except Exception as e:
        print(f"[orchestrate_step_mode] ERROR connecting to computer server: {e}")
        import traceback

        print(f"[orchestrate_step_mode] Traceback:\n{traceback.format_exc()}")
        raise

    print("\n" + "=" * 60)
    print("DESKTOP MODE - STEP MODE ACTIVE")
    print("=" * 60)
    print("\nComputer server connected. Waiting for commands from control panel.")
    print("Launch the Control Panel to begin workflow steps.")
    print("\n" + "-" * 60)

    print("[orchestrate_step_mode] Building agent...")
    agent = build_agent(model_settings, computer)
    print("[orchestrate_step_mode] Agent built successfully!")

    print("[orchestrate_step_mode] Creating StepModeRunner...")
    runner = StepModeRunner(root, agent, computer, model_settings.model, capture_dir)

    print("[orchestrate_step_mode] Starting run_loop...")
    await runner.run_loop()


async def orchestrate() -> None:
    root = Path(__file__).resolve().parents[1]
    capture_dir = root / "artifacts" / "captures"
    capture_dir.mkdir(parents=True, exist_ok=True)
    computer_settings = load_computer_settings(
        root / "config" / "computer_windows.yaml"
    )
    model_settings = load_model_settings(root / "config" / "model.yaml")
    computer = build_computer(computer_settings)
    await computer.run()

    print("\n" + "=" * 60)
    print("DESKTOP MODE - AUTOMATIC WORKFLOW")
    print("=" * 60)
    print("\nComputer server connected.")
    print("Make sure WeChat is open and logged in before continuing.")
    print("\n" + "-" * 60)
    input("Press Enter when WeChat is ready...")
    print("\nStarting workflow...\n")

    agent = build_agent(model_settings, computer)

    # Stage 1-2: Classification and filtering (global)
    classification_output, _ = await run_agent_task(
        agent, classification_prompt(), capture_dir, "classification"
    )
    threads = parse_classification(classification_output)
    unread_groups = filter_unread_groups(threads)

    print(f"\nFound {len(unread_groups)} unread group(s) to process.\n")

    # Accumulated results across all groups
    all_suspects: List[Suspect] = []
    all_plans: List[RemovalPlan] = []

    # Stage 3-6: Per-group processing loop
    for i, thread in enumerate(unread_groups):
        print(f"\n{'=' * 40}")
        print(f"Processing group {i + 1}/{len(unread_groups)}: {thread.name}")
        print(f"{'=' * 40}\n")

        # Stage 3: Read messages (per group)
        reader_prompt = message_reader_prompt(thread)
        reader_output, reader_shots = await run_agent_task(
            agent, reader_prompt, capture_dir, f"reader_{thread.thread_id}"
        )

        # Stage 4: Extract suspects (per group)
        group_suspects = extract_suspects(thread, reader_output, reader_shots)
        print(f"Found {len(group_suspects)} suspect(s) in {thread.name}")

        if not group_suspects:
            print(f"No suspects in {thread.name}, skipping removal.")
            continue

        # Stage 5: Build plan (per group)
        group_plan = build_removal_plan(group_suspects)
        group_plan = require_confirmation(group_plan)

        # Stage 6: Execute removal (per group)
        if group_plan.confirmed:
            removal_output, _ = await run_agent_task(
                agent,
                removal_prompt(group_plan),
                capture_dir,
                f"removal_{thread.thread_id}",
            )
            group_plan.note = removal_output or group_plan.note

        # Accumulate results
        all_suspects.extend(group_suspects)
        all_plans.append(group_plan)

    print(f"\n{'=' * 40}")
    print("Workflow complete!")
    print(f"Total groups processed: {len(unread_groups)}")
    print(f"Total suspects found: {len(all_suspects)}")
    print(f"{'=' * 40}\n")

    # Create a combined plan for the report (backward compatibility)
    combined_plan = RemovalPlan(
        suspects=all_suspects,
        confirmed=any(p.confirmed for p in all_plans),
        note=f"Processed {len(all_plans)} group(s)",
    )
    _persist_report(root, threads, all_suspects, combined_plan)


def main() -> None:
    parser = argparse.ArgumentParser(description="WeChat removal workflow")
    parser.add_argument(
        "--step-mode",
        action="store_true",
        help="Run in step-by-step mode for control panel integration",
    )
    args = parser.parse_args()

    if args.step_mode:
        asyncio.run(orchestrate_step_mode())
    else:
        asyncio.run(orchestrate())


if __name__ == "__main__":
    main()
    main()
