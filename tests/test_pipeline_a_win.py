from dataclasses import dataclass

from shared.datatypes import ChatMessage, SidebarRow
from algo_a.pipeline_a_win import _find_first_visible_config_match
from algo_a.pipeline_a_win import _row_allowed_by_initial_sidebar_names
from algo_a.pipeline_a_win import _run_capture_all_fast_path


class FakeSidebarDriver:
    def __init__(self, rows: list[SidebarRow]) -> None:
        self.rows = rows

    def get_sidebar_rows(self, window: object) -> list[SidebarRow]:
        assert window is not None
        return self.rows


@dataclass
class FakeConfig:
    output_dir: str
    chat_max_scrolls: int = 0
    sidebar_max_scrolls: int = 5
    recent_window_hours: int = 0
    chat_max_scrolls: int = 0
    sidebar_max_scrolls: int = 1


class FakeFastCaptureDriver:
    def __init__(self) -> None:
        self.viewports = [
            [
                SidebarRow("Short A", None, None, (0, 0, 100, 40), False),
                SidebarRow("Short B", None, None, (0, 40, 100, 80), False),
            ],
            [
                SidebarRow("Short B", None, None, (0, 0, 100, 40), False),
                SidebarRow("Short C", None, None, (0, 40, 100, 80), False),
            ],
        ]
        self.viewport_idx = 0
        self.clicked: list[str] = []
        self.message_calls: list[tuple[str, bool]] = []
        self.scrolls: list[str] = []

    def get_fast_sidebar_rows(self, window: object) -> list[SidebarRow]:
        assert window is not None
        return self.viewports[self.viewport_idx]

    def capture_sidebar_chat_names(self, window: object, max_scrolls: int) -> list[str]:
        assert window is not None
        assert max_scrolls == 1
        return ["Short A", "Short B", "Short C"]

    def click_row(self, row: SidebarRow, attempt: int = 0) -> None:
        assert attempt == 0
        self.clicked.append(row.name)

    def resolve_current_chat_title(self, fallback: str = "") -> str:
        titles = {
            "Short A": "Full Chat A",
            "Short B": "Full Chat B",
            "Short C": "Full Chat C",
        }
        return titles.get(fallback, fallback)

    def get_chat_messages(
        self,
        chat_name: str,
        max_scrolls: int | None = None,
        recent_window_hours: int = 0,
        skip_navigation_vlm: bool = False,
    ) -> list[ChatMessage]:
        self.message_calls.append((chat_name, skip_navigation_vlm))
        return [ChatMessage(sender="Alice", content=f"hello {chat_name}", time=None, type="text")]

    def scroll_sidebar(self, window: object, direction: str) -> None:
        assert window is not None
        self.scrolls.append(direction)
        if direction == "down":
            self.viewport_idx = min(self.viewport_idx + 1, len(self.viewports) - 1)

    def get_current_chat_name(self) -> str:
        raise AssertionError("fast path must not call VLM current-chat verification")


class FakeMacChatInfo:
    def __init__(self, name: str, row_rect: object, unread_count: int | None = None) -> None:
        self.name = name
        self.row_rect = row_rect
        self.unread_count = unread_count


class FakeRect:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height


def test_fast_capture_all_sweeps_without_current_chat_vlm(tmp_path) -> None:
    driver = FakeFastCaptureDriver()
    config = FakeConfig(output_dir=str(tmp_path))

    paths = _run_capture_all_fast_path(driver, window=object(), config=config, written_paths=[])

    assert len(paths) == 3
    assert driver.clicked == ["Short A", "Short B", "Short C"]
    assert driver.message_calls == [
        ("Full Chat A", True),
        ("Full Chat B", True),
        ("Full Chat C", True),
    ]
    assert driver.scrolls == ["up", "up", "up", "up", "up", "up", "down"]


def test_initial_sidebar_whitelist_rejects_message_summary() -> None:
    name_row = SidebarRow("运营核心群", None, None, (0, 0, 100, 40), False)
    summary_row = SidebarRow("收到，谢谢", None, None, (0, 40, 100, 80), False)
    allowed = ["运营核心群"]

    assert _row_allowed_by_initial_sidebar_names(name_row, allowed)
    assert not _row_allowed_by_initial_sidebar_names(summary_row, allowed)


def test_initial_sidebar_whitelist_allows_truncated_name() -> None:
    row = SidebarRow("运营核心群…", None, None, (0, 0, 100, 40), False)

    assert _row_allowed_by_initial_sidebar_names(row, ["运营核心群后半段被隐藏"])


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
