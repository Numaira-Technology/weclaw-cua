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
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# Add vendor packages to sys.path before importing from them
_ROOT = Path(__file__).resolve().parents[1]
_VENDOR = _ROOT / "vendor"
for _pkg in [_VENDOR / "agent", _VENDOR / "computer", _VENDOR / "core"]:
    if str(_pkg) not in sys.path:
        sys.path.insert(0, str(_pkg))

from agent import ClickCorrector  # type: ignore[import-not-found]

from modules.group_classifier import classification_prompt, parse_classification
from modules.human_confirmation import require_confirmation
from modules.message_reader import message_reader_prompt
from modules.removal_executor import removal_prompt, removal_prompt_single
from modules.removal_precheck import build_removal_plan
from modules.removal_verifier import verify_user_removed
from modules.suspicious_detector import extract_suspects
from modules.task_types import GroupThread, RemovalPlan, RemovalResult, Suspect
from modules.unread_scanner import filter_unread_groups
from runtime.computer_session import build_computer, load_computer_settings
from runtime.model_session import build_agent, load_model_settings

# Fix Windows console encoding for emoji/unicode characters
if sys.platform == "win32" and sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _sanitize_surrogates(text: str) -> str:
    """Remove surrogate characters that cause UTF-8 encoding errors."""
    return text.encode("utf-8", errors="surrogatepass").decode(
        "utf-8", errors="replace"
    )


# Module-level click corrector instance
_click_corrector: Optional[ClickCorrector] = None


async def targeted_click(
    agent,
    computer,
    element_description: str,
    max_retries: int = 3,
    enable_correction: bool = True,
) -> Tuple[bool, str]:
    """
    Perform a targeted click on a UI element using the predict_click capability.

    This implements the proper click workflow with automatic correction:
    1. Take a screenshot
    2. Use predict_click to find the element coordinates
    3. Apply click correction offset if enabled
    4. Execute the click at those coordinates
    5. Take another screenshot to verify
    6. Update click correction based on cursor position

    Args:
        agent: The ComputerAgent instance
        computer: The computer interface
        element_description: Description of the element to click (e.g., "the minus button", "Catherine's avatar")
        max_retries: Number of retries if click prediction fails
        enable_correction: Whether to use click correction mechanism

    Returns:
        Tuple of (success: bool, message: str)
    """
    global _click_corrector

    # Initialize corrector if needed
    corrector = None
    if enable_correction:
        if _click_corrector is None:
            _click_corrector = ClickCorrector()
        corrector = _click_corrector

    for attempt in range(max_retries):
        try:
            # Step 1: Take a screenshot (before click)
            screenshot_before = await computer.interface.screenshot()
            screenshot_b64 = base64.b64encode(screenshot_before).decode("utf-8")

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
            original_x, original_y = x, y

            # Step 3: Apply click correction if enabled
            if corrector:
                x, y = corrector.apply_correction(x, y)
                corrector.record_intended_click(x, y)

            # Step 4: Convert from screenshot coordinates to screen coordinates
            # The model outputs coordinates based on the screenshot it sees,
            # but clicks need to happen in actual screen space
            screen_x, screen_y = await computer.interface.to_screen_coordinates(x, y)
            screen_x, screen_y = int(round(screen_x)), int(round(screen_y))

            # Step 5: Execute the click in screen coordinates
            await computer.interface.left_click(screen_x, screen_y)

            # Step 6: Wait for UI to respond
            await asyncio.sleep(0.5)

            # Step 7: Take verification screenshot
            screenshot_after = await computer.interface.screenshot()
            screenshot_after_b64 = base64.b64encode(screenshot_after).decode("utf-8")

            # Step 8: Update click correction based on cursor position
            if corrector:
                offset = await corrector.detect_and_update_offset(
                    x, y, screenshot_after_b64
                )
                if offset and (abs(offset[0]) > 5 or abs(offset[1]) > 5):
                    stats = corrector.get_correction_stats()
                    print(
                        f"[targeted_click] Click correction updated: offset=({stats['current_offset']['x']:.1f}, {stats['current_offset']['y']:.1f})"
                    )

            correction_info = ""
            if corrector and (original_x != x or original_y != y):
                correction_info = f" (corrected from ({original_x}, {original_y}))"

            return (
                True,
                f"Clicked at ({x}, {y}){correction_info} for: {element_description}",
            )

        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
                continue
            return False, f"Error clicking {element_description}: {str(e)}"

    return False, f"Failed to click {element_description} after {max_retries} attempts"


def reset_click_correction():
    """Reset the click correction state."""
    global _click_corrector
    if _click_corrector:
        _click_corrector.reset()
        print("[reset_click_correction] Click correction reset")


def get_click_correction_stats() -> dict:
    """Get current click correction statistics."""
    if _click_corrector:
        return _click_corrector.get_correction_stats()
    return {"error": "No corrector initialized"}


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

    # Retry logic for transient API errors (502, 503, etc.)
    import asyncio

    max_retries = 3
    retry_delay = 2.0
    last_error = None
    for attempt in range(max_retries):
        try:
            response = await litellm.acompletion(
                model=model, messages=messages, timeout=60
            )
            break
        except Exception as e:
            last_error = e
            error_str = str(e)
            if any(
                x in error_str
                for x in ["502", "503", "ServiceUnavailable", "server_error"]
            ):
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    print(
                        f"[run_vision_query] API error (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
            raise
    else:
        if last_error:
            raise last_error
        raise RuntimeError("API call failed after all retries")

    elapsed = time.time() - start
    print(f"[run_vision_query] Response received in {elapsed:.1f}s")

    # Step 3: Extract text response
    text_output = response.choices[0].message.content or ""  # type: ignore[union-attr]
    # Sanitize surrogate characters that cause UTF-8 encoding errors
    text_output = _sanitize_surrogates(text_output)
    # Use ASCII-safe encoding for Windows console compatibility
    response_preview = text_output[:200].encode("ascii", "replace").decode("ascii")
    print(f"[run_vision_query] Response: {response_preview}...")

    return text_output, [screenshot_path]


def _is_transient_api_error(error: Exception) -> bool:
    """Check if an error is a transient API error that should be retried."""
    error_str = str(error)
    transient_indicators = [
        "502",
        "503",
        "504",
        "ServiceUnavailable",
        "server_error",
        "Bad Gateway",
    ]
    return any(indicator in error_str for indicator in transient_indicators)


async def run_agent_task(
    agent, prompt: str, capture_dir: Path, task_label: str, max_retries: int = 3
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

    # Retry wrapper for transient API errors
    retry_count = 0
    while True:
        try:
            async for result in agent.run(messages):
                elapsed = time.time() - start_time
                print(
                    f"[run_agent_task] Got result after {elapsed:.1f}s with {len(result.get('output', []))} output items"
                )
                for item in result["output"]:
                    item_type = item.get("type")
                    print(f"[run_agent_task] Processing item type: {item_type}")
                    if item_type == "message":
                        for content_item in item.get("content", []):
                            text = content_item.get("text")
                            if text:
                                # Use ASCII-safe encoding for Windows console compatibility
                                text_preview = (
                                    text[:100]
                                    .encode("ascii", "replace")
                                    .decode("ascii")
                                )
                                print(
                                    f"[run_agent_task] Message text: {text_preview}..."
                                )
                                text_messages.append(_sanitize_surrogates(text))
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
            # Successfully completed - break out of retry loop
            break
        except Exception as e:
            if _is_transient_api_error(e) and retry_count < max_retries:
                retry_count += 1
                wait_time = 2.0 * retry_count
                print(
                    f"[run_agent_task] Transient API error (attempt {retry_count}/{max_retries}), retrying in {wait_time}s: {e}"
                )
                await asyncio.sleep(wait_time)
                continue
            raise

    print(
        f"[run_agent_task] Task complete. Messages: {len(text_messages)}, Screenshots: {len(screenshot_paths)}"
    )
    final_text = text_messages[-1] if text_messages else ""
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
        # Sanitize to avoid encoding issues on Windows
        result_json = _sanitize_surrogates(result_json)
        print(f"[StepModeRunner] Writing result ({len(result_json)} bytes)")
        self.result_file.write_text(result_json, encoding="utf-8")

    def _write_error(self, error: str) -> None:
        print(f"[StepModeRunner] Writing error: {error}")
        # Sanitize error message to avoid encoding issues on Windows
        sanitized = _sanitize_surrogates(error)
        self.result_file.write_text(sanitized, encoding="utf-8")
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
        """Remove suspects one by one with verification after each removal."""
        suspects_data = params.get("suspects", [])
        max_retries = params.get("max_retries", 2)
        print(f"[StepModeRunner] Executing: remove {len(suspects_data)} suspect(s)")

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

        removal_results: List[RemovalResult] = []
        all_screenshots: List[Path] = []

        for i, suspect in enumerate(suspects):
            is_first = i == 0
            print(
                f"[StepModeRunner] Removing suspect {i + 1}/{len(suspects)}: {suspect.sender_name}"
            )

            result = await self._remove_single_suspect(
                suspect, is_first=is_first, max_retries=max_retries
            )
            removal_results.append(result)

            # Collect screenshots for this removal
            removal_label = f"removal_{suspect.sender_id}_{i}"
            screenshot_path = self.capture_dir / f"{removal_label}_final.png"
            if screenshot_path.exists():
                all_screenshots.append(screenshot_path)

            status = "SUCCESS" if result.success else "FAILED"
            print(
                f"[StepModeRunner] Suspect {suspect.sender_name}: {status} "
                f"(attempts: {result.attempts})"
            )

        # Build result summary
        successful = sum(1 for r in removal_results if r.success)
        failed = len(removal_results) - successful
        all_removed = failed == 0

        summary_text = (
            f"Removal complete: {successful}/{len(removal_results)} succeeded"
        )
        if failed > 0:
            failed_names = [r.sender_name for r in removal_results if not r.success]
            summary_text += f"\nFailed: {', '.join(failed_names)}"

        print(f"[StepModeRunner] {summary_text}")

        self._write_result(
            {
                "text": summary_text,
                "screenshots": [str(p) for p in all_screenshots],
                "removal_results": [
                    {
                        "sender_name": r.sender_name,
                        "sender_id": r.sender_id,
                        "thread_id": r.thread_id,
                        "success": r.success,
                        "attempts": r.attempts,
                        "error": r.error,
                    }
                    for r in removal_results
                ],
                "all_removed": all_removed,
            }
        )
        self._write_status("complete")

    async def _remove_single_suspect(
        self, suspect: Suspect, is_first: bool, max_retries: int
    ) -> RemovalResult:
        """Attempt to remove a single suspect with verification and retries."""
        attempts = 0

        while attempts < max_retries:
            attempts += 1
            print(
                f"[StepModeRunner] Removal attempt {attempts}/{max_retries} "
                f"for {suspect.sender_name}"
            )

            # Generate prompt for this removal
            prompt = removal_prompt_single(
                suspect, is_first=(is_first and attempts == 1)
            )

            # Run the agent to perform the removal
            try:
                text_output, screenshots = await run_agent_task(
                    self.agent,
                    prompt,
                    self.capture_dir,
                    f"removal_{suspect.sender_id}_attempt{attempts}",
                )
            except Exception as e:
                print(f"[StepModeRunner] Agent error during removal: {e}")
                continue

            # Take a verification screenshot
            print("[StepModeRunner] Taking verification screenshot...")
            try:
                screenshot_bytes = await self.computer.interface.screenshot()
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

                # Save verification screenshot
                verify_path = (
                    self.capture_dir
                    / f"removal_{suspect.sender_id}_verify{attempts}.png"
                )
                verify_path.write_bytes(screenshot_bytes)
                print(f"[StepModeRunner] Saved verification screenshot: {verify_path}")
            except Exception as e:
                print(f"[StepModeRunner] Failed to take verification screenshot: {e}")
                continue

            # Verify the user was removed using VLM
            print(f"[StepModeRunner] Verifying removal of {suspect.sender_name}...")
            try:
                is_removed = await verify_user_removed(
                    screenshot_b64, suspect.sender_name, self.model
                )
            except Exception as e:
                print(f"[StepModeRunner] Verification error: {e}")
                is_removed = False

            if is_removed:
                print(
                    f"[StepModeRunner] Verified: {suspect.sender_name} removed successfully"
                )
                return RemovalResult(
                    sender_name=suspect.sender_name,
                    sender_id=suspect.sender_id,
                    thread_id=suspect.thread_id,
                    success=True,
                    attempts=attempts,
                )
            else:
                print(
                    f"[StepModeRunner] Verification failed: {suspect.sender_name} "
                    f"still visible (attempt {attempts})"
                )

        # All retries exhausted
        return RemovalResult(
            sender_name=suspect.sender_name,
            sender_id=suspect.sender_id,
            thread_id=suspect.thread_id,
            success=False,
            attempts=attempts,
            error="User still visible after all attempts",
        )

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

            error_msg = str(e)
            tb = traceback.format_exc()
            # Sanitize for console output
            safe_error = error_msg.encode("ascii", "replace").decode("ascii")
            safe_tb = tb.encode("ascii", "replace").decode("ascii")
            print(f"[StepModeRunner] Exception during step: {safe_error}")
            print(f"[StepModeRunner] Traceback:\n{safe_tb}")
            try:
                self._write_error(f"{type(e).__name__}: {error_msg}\n\n{tb}")
            except Exception as write_err:
                # Fallback: write ASCII-safe version if encoding fails
                print(f"[StepModeRunner] Failed to write error: {write_err}")
                self._write_error(f"{type(e).__name__}: {safe_error}\n\n{safe_tb}")

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

                    error_msg = str(e)
                    tb = traceback.format_exc()
                    # Sanitize for console output
                    safe_error = error_msg.encode("ascii", "replace").decode("ascii")
                    safe_tb = tb.encode("ascii", "replace").decode("ascii")
                    print(f"[StepModeRunner] Unexpected error: {safe_error}")
                    print(f"[StepModeRunner] Traceback:\n{safe_tb}")
                    self._clear_request()
                    try:
                        self._write_error(f"Unexpected error: {error_msg}\n\n{tb}")
                    except Exception as write_err:
                        print(f"[StepModeRunner] Failed to write error: {write_err}")
                        self._write_error(
                            f"Unexpected error: {safe_error}\n\n{safe_tb}"
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
