import numpy as np
from PIL import Image, ImageDraw

from utils.image_stitcher import CropRegion, scroll_region_from_image_size, stitch_screenshots
from utils.stitch_overlap import estimate_vertical_overlap_match


def _long_chat_image(width: int = 420, height: int = 1500) -> Image.Image:
    img = Image.new("RGB", (width, height), (248, 248, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width - 1, 76), fill=(240, 240, 240))
    draw.text((20, 26), "Catherine", fill=(20, 20, 20))
    for idx, y in enumerate(range(110, height - 80, 95)):
        if idx % 2 == 0:
            draw.rectangle((28, y, 260, y + 44), fill=(230, 230, 230))
            draw.text((40, y + 14), f"LEFT_UNIQUE_{idx:02d}", fill=(0, 0, 0))
        else:
            draw.rectangle((160, y, 392, y + 44), fill=(139, 231, 148))
            draw.text((172, y + 14), f"RIGHT_UNIQUE_{idx:02d}", fill=(0, 0, 0))
        draw.line((0, y + 67, width, y + 67), fill=(238, 238, 238))
    return img


def _frames_from_long_image(long_img: Image.Image) -> list[Image.Image]:
    starts = [0, 260, 520, 780]
    viewport_h = 620
    frames = []
    for start in starts:
        frame = long_img.crop((0, start, long_img.width, start + viewport_h))
        if start:
            draw = ImageDraw.Draw(frame)
            draw.rectangle((0, 0, frame.width - 1, 76), fill=(240, 240, 240))
            draw.text((20, 26), "Catherine", fill=(20, 20, 20))
        frames.append(frame)
    return frames


def _count_color_rows(img: Image.Image, color: tuple[int, int, int]) -> int:
    arr = np.array(img)
    mask = np.all(arr == np.array(color, dtype=np.uint8), axis=2)
    return int(np.count_nonzero(np.any(mask, axis=1)))


def test_default_crop_preserves_chat_title_and_excludes_sidebar() -> None:
    region = scroll_region_from_image_size(1000, 800)
    assert region.y == 0
    assert region.x >= 300
    assert region.x + region.w <= 950
    assert region.h < 800


def test_overlap_match_finds_vertical_translation_with_static_title() -> None:
    frames = _frames_from_long_image(_long_chat_image())
    match = estimate_vertical_overlap_match(
        np.array(frames[0]),
        np.array(frames[1]),
        top_trim=88,
        bottom_trim=40,
    )
    assert match.reliable
    assert abs(match.overlap - 232) <= 12


def test_stitch_preserves_unique_content_without_duplicate_growth() -> None:
    long_img = _long_chat_image()
    frames = _frames_from_long_image(long_img)
    stitched = stitch_screenshots(
        frames,
        scroll_region=CropRegion(0, 0, long_img.width, 620),
        match_bottom_trim=40,
    )
    assert stitched is not None
    assert stitched.height <= 1420
    assert stitched.height >= 1360
    assert _count_color_rows(stitched, (139, 231, 148)) >= 250
    assert _count_color_rows(stitched, (230, 230, 230)) >= 300


def test_near_duplicate_frame_is_skipped() -> None:
    long_img = _long_chat_image()
    frame = _frames_from_long_image(long_img)[0]
    stitched = stitch_screenshots(
        [frame, frame.copy()],
        scroll_region=CropRegion(0, 0, long_img.width, 620),
        match_bottom_trim=40,
    )
    assert stitched is not None
    assert stitched.height == 620
