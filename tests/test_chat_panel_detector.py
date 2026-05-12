from unittest.mock import patch

from PIL import Image

from platform_mac.chat_panel_detector import (
    extract_chat_header_title,
    sidebar_name_matches_config_group,
)


def test_sidebar_name_matches_truncated_visible_prefix_without_ellipsis() -> None:
    assert sidebar_name_matches_config_group(
        "运营核心群",
        "运营核心群后半段被隐藏",
    )


def test_sidebar_name_matches_truncated_visible_prefix_with_unicode_ellipsis() -> None:
    assert sidebar_name_matches_config_group(
        "运营核心群…",
        "运营核心群后半段被隐藏",
    )


def test_sidebar_name_rejects_short_truncated_prefix() -> None:
    assert not sidebar_name_matches_config_group(
        "运营",
        "运营核心群后半段被隐藏",
    )


def test_sidebar_name_matches_truncated_config_with_emoji_core() -> None:
    assert sidebar_name_matches_config_group(
        "运营核心群",
        "运营核心群💗后半段被隐藏",
    )


def test_header_title_prefers_short_line_when_hint_does_not_match() -> None:
    img = Image.new("RGB", (1000, 800))
    fake_bands = [
        ["有人可以在合日的最后一周女右到7日30皂女右领和一个"],
        ["涛涛弟弟"],
    ]
    with patch(
        "platform_mac.chat_panel_detector._header_ocr_lines_by_band",
        return_value=fake_bands,
    ):
        assert extract_chat_header_title(img, match_hint="22 chapel") == "涛涛弟弟"


def test_header_title_hint_match_wins_over_longer_line() -> None:
    img = Image.new("RGB", (1000, 800))
    fake_bands = [
        ["有人可以在合日的最后一周女右到7日30皂女右领和一个"],
        ["涛涛弟弟"],
    ]
    with patch(
        "platform_mac.chat_panel_detector._header_ocr_lines_by_band",
        return_value=fake_bands,
    ):
        assert extract_chat_header_title(img, match_hint="涛涛") == "涛涛弟弟"


def test_header_title_rejects_short_mixed_script_ocr_noise_uses_empty() -> None:
    img = Image.new("RGB", (1000, 800))
    fake_bands = [
        ["有人可以在合日的最后一周女右到7日30皂女右领和一个"],
        ["咋尺VQLZ"],
    ]
    with patch(
        "platform_mac.chat_panel_detector._header_ocr_lines_by_band",
        return_value=fake_bands,
    ):
        assert (
            extract_chat_header_title(img, match_hint="Laabat,sn 0.npm Pop") == ""
        )

