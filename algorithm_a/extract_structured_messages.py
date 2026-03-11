"""Extract structured messages from long images with an LLM.

Usage:
    Call this after long-image generation.

Input spec:
    - `long_image_paths`: one or more stitched long-image file paths.

Output spec:
    - Returns message dictionaries with `user`, `time`, and `content`.
"""


def extract_structured_messages(long_image_paths: list[str]) -> list[dict[str, str]]:
    assert long_image_paths
    raise NotImplementedError("Implement structured message extraction.")
