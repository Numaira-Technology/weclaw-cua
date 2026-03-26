from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List
import cv2
import numpy as np

@dataclass(frozen=True)
class CropRegion:
    x: int
    y: int
    w: int
    h: int

def stitch_screenshots(
    screenshot_paths: List[Path],
    output_path: Path,
    scroll_region: CropRegion,
) -> None:
    """
    Stitches screenshots by cropping them to a specified region and concatenating them vertically.
    This is a simpler, direct concatenation method without overlap detection.
    """
    assert len(screenshot_paths) >= 1, "Need at least 1 screenshot"

    cropped_images = []
    for path in screenshot_paths:
        try:
            img_bytes = path.read_bytes()
            image = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                print(f"[WARN] Failed to decode image, skipping: {path}")
                continue
            
            # Crop the image to the specified scrollable region
            cropped_img = image[scroll_region.y : scroll_region.y + scroll_region.h, 
                                scroll_region.x : scroll_region.x + scroll_region.w]
            cropped_images.append(cropped_img)

        except Exception as e:
            print(f"[WARN] Could not process image {path}, skipping. Error: {e}")

    if not cropped_images:
        print("[ERROR] No images were successfully cropped. Aborting stitch.")
        return

    # Vertically stack the cropped images
    stitched_image = np.vstack(cropped_images)

    # Save the final stitched image
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), stitched_image)
    print(f"[+] Successfully stitched {len(cropped_images)} images into {output_path}")

