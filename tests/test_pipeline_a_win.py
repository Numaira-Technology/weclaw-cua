from shared.datatypes import SidebarRow
from algo_a.pipeline_a_win import _find_first_visible_config_match


class FakeSidebarDriver:
    def __init__(self, rows: list[SidebarRow]) -> None:
        self.rows = rows

    def get_sidebar_rows(self, window: object) -> list[SidebarRow]:
        assert window is not None
        return self.rows


def test_configured_name_match_requires_unread_when_enabled() -> None:
    target = SidebarRow(
        name="运营核心群",
        last_message=None,
        badge_text=None,
        bbox=(0, 0, 100, 40),
        is_group=True,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["运营核心群"],
        unread_only=True,
    )

    assert match is None


def test_configured_name_match_allows_unread_badge_when_enabled() -> None:
    target = SidebarRow(
        name="运营核心群",
        last_message=None,
        badge_text="3",
        bbox=(0, 0, 100, 40),
        is_group=True,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["运营核心群"],
        unread_only=True,
    )

    assert match == ("运营核心群", target)


def test_configured_name_matches_truncated_visible_prefix_without_ellipsis() -> None:
    target = SidebarRow(
        name="运营核心群",
        last_message=None,
        badge_text=None,
        bbox=(0, 0, 100, 40),
        is_group=True,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["运营核心群后半段被隐藏"],
        unread_only=False,
    )

    assert match == ("运营核心群后半段被隐藏", target)


def test_configured_name_matches_truncated_visible_prefix_with_ellipsis() -> None:
    target = SidebarRow(
        name="运营核心群…",
        last_message=None,
        badge_text=None,
        bbox=(0, 0, 100, 40),
        is_group=True,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["运营核心群后半段被隐藏"],
        unread_only=False,
    )

    assert match == ("运营核心群后半段被隐藏", target)


def test_configured_name_rejects_short_truncated_prefix() -> None:
    target = SidebarRow(
        name="运营",
        last_message=None,
        badge_text=None,
        bbox=(0, 0, 100, 40),
        is_group=True,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["运营核心群后半段被隐藏"],
        unread_only=False,
    )

    assert match is None


def test_configured_name_match_can_select_private_chat() -> None:
    target = SidebarRow(
        name="Alice",
        last_message=None,
        badge_text="1",
        bbox=(0, 0, 100, 40),
        is_group=False,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["Alice"],
        unread_only=True,
        chat_type="private",
    )

    assert match == ("Alice", target)


def test_configured_name_match_rejects_private_when_group_only() -> None:
    target = SidebarRow(
        name="Alice",
        last_message=None,
        badge_text="1",
        bbox=(0, 0, 100, 40),
        is_group=False,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["Alice"],
        unread_only=True,
        chat_type="group",
    )

    assert match is None
