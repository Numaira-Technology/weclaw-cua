from __future__ import annotations
from dataclasses import dataclass
from typing import List
import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class CropRegion:
    x: int
    y: int
    w: int
    h: int


def stitch_screenshots(
    images: List[Image.Image],
    scroll_region: CropRegion,
) -> Image.Image | None:
    """
    Stitches screenshots by cropping them and concatenating them vertically.
    """
    if not images:
        print("[WARN] No images provided to stitch.")
        return None

    cropped_images = []
    for image in images:
        try:
            # Convert PIL Image to numpy array for cv2
            np_image = np.array(image.convert('RGB'))
            # cv2 uses BGR, so convert RGB to BGR
            np_image = np_image[:, :, ::-1].copy()

            # Crop the image
            cropped_img = np_image[scroll_region.y : scroll_region.y + scroll_region.h,
                                 scroll_region.x : scroll_region.x + scroll_region.w]
            cropped_images.append(cropped_img)

        except Exception as e:
            print(f"[WARN] Could not process an image, skipping. Error: {e}")

    if not cropped_images:
        print("[ERROR] No images were successfully cropped. Aborting stitch.")
        return None

    # Vertically stack the cropped images
    stitched_np_image = np.vstack(cropped_images)

    # Convert back to PIL Image
    # cv2 uses BGR, so convert BGR back to RGB
    stitched_pil_image = Image.fromarray(stitched_np_image[:, :, ::-1])

    print(f"[+] Successfully stitched {len(cropped_images)} images in-memory.")
    return stitched_pil_image

