"""Merge overlapping screenshots into long images.

Usage:
    Call this after screenshot capture and before LLM extraction.

Input spec:
    - `screenshot_paths`: screenshot file paths in capture order.

Output spec:
    - Returns long-image file paths after overlap removal.
"""


def stitch_screenshots(screenshot_paths: list[str]) -> list[str]:
    assert screenshot_paths
    raise NotImplementedError("Implement screenshot stitching.")
