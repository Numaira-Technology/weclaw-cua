from platform_mac.chat_panel_detector import sidebar_name_matches_config_group


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

