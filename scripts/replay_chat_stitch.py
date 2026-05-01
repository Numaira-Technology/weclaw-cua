"""Replay chat screenshot stitching on saved frame PNGs.

Usage:
    python scripts/replay_chat_stitch.py --frames debug_outputs/chat_frames --output /tmp/stitched.png

Input spec:
    --frames points to a directory containing PNG/JPEG frames in lexical order.
    Frames may be raw full-window captures or already cropped chat-panel frames.

Output spec:
    Writes one stitched PNG and prints the same overlap metrics emitted by
    utils.image_stitcher.stitch_screenshots.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from utils.image_stitcher import stitch_screenshots


def _load_frames(frames_dir: Path) -> list[Image.Image]:
    assert frames_dir.is_dir(), f"frames directory not found: {frames_dir}"
    paths = sorted(
        path
        for path in frames_dir.iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    assert paths, f"no image frames found in {frames_dir}"
    return [Image.open(path).convert("RGB") for path in paths]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--already-cropped", action="store_true")
    args = parser.parse_args()

    frames = _load_frames(Path(args.frames))
    scroll_region = None
    if args.already_cropped:
        from utils.image_stitcher import CropRegion

        width, height = frames[0].size
        scroll_region = CropRegion(0, 0, width, height)
    stitched = stitch_screenshots(frames, scroll_region=scroll_region)
    assert stitched is not None
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stitched.save(output_path)
    print(f"[replay] wrote {output_path}")


if __name__ == "__main__":
    main()
