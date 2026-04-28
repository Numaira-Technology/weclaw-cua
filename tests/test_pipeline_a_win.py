from shared.datatypes import SidebarRow
from algo_a.pipeline_a_win import _find_first_visible_config_match


class FakeSidebarDriver:
    def __init__(self, rows: list[SidebarRow]) -> None:
        self.rows = rows

    def get_sidebar_rows(self, window: object) -> list[SidebarRow]:
        assert window is not None
        return self.rows


def test_configured_name_match_ignores_unread_filter() -> None:
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

    assert match == ("运营核心群", target)
