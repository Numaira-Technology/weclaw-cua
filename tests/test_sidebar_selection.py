from PIL import Image

from shared.sidebar_selection import row_has_selected_green_background


def test_row_has_selected_green_background_accepts_wechat_green_row() -> None:
    row = Image.new("RGB", (200, 80), (230, 245, 230))
    green_band = Image.new("RGB", (160, 80), (70, 180, 95))
    row.paste(green_band, (36, 0))

    assert row_has_selected_green_background(row)


def test_row_has_selected_green_background_rejects_plain_row() -> None:
    row = Image.new("RGB", (200, 80), (245, 245, 245))

    assert not row_has_selected_green_background(row)
