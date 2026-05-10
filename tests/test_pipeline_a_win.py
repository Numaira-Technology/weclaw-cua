from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

from shared.datatypes import ChatMessage, SidebarRow
import algo_a.pipeline_a_win as pipeline_a_win
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
        self.capture_calls: list[tuple[str, bool]] = []
        self.extract_calls: list[str] = []
        self.scrolls: list[str] = []

    def get_fast_sidebar_rows(self, window: object) -> list[SidebarRow]:
        assert window is not None
        return self.viewports[self.viewport_idx]

    def capture_sidebar_chat_names(self, window: object, max_scrolls: int) -> list[str]:
        assert window is not None
        assert max_scrolls == 1
        return ["Short A", "Short B", "Short C"]

    def click_row(self, row: SidebarRow, attempt: int = 0) -> None:
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
        skip_navigation_vlm: bool = False,
    ) -> list[ChatMessage]:
        self.message_calls.append((chat_name, skip_navigation_vlm))
        return [ChatMessage(sender="Alice", content=f"hello {chat_name}", time=None, type="text")]

    def capture_chat_messages(
        self,
        chat_name: str,
        max_messages: int | None = None,
        max_scrolls: int | None = None,
        skip_navigation_vlm: bool = False,
    ) -> object:
        assert max_messages is None
        self.capture_calls.append((chat_name, skip_navigation_vlm))
        return SimpleNamespace(chat_name=chat_name)

    def extract_chat_messages_from_capture(self, captured: object) -> list[ChatMessage]:
        chat_name = str(getattr(captured, "chat_name"))
        self.extract_calls.append(chat_name)
        return [ChatMessage(sender="Alice", content=f"hello {chat_name}", time=None, type="text")]

    def scroll_sidebar(self, window: object, direction: str) -> None:
        assert window is not None
        self.scrolls.append(direction)
        if direction == "down":
            self.viewport_idx = min(self.viewport_idx + 1, len(self.viewports) - 1)

    def get_current_chat_name(self) -> str:
        raise AssertionError("fast path must not call VLM current-chat verification")


class FakeNamedFastDriver(FakeFastCaptureDriver):
    def __init__(self) -> None:
        super().__init__()
        self.viewports = [
            [
                SidebarRow("运营核心群", None, None, (0, 0, 100, 40), False),
                SidebarRow("无关群", None, None, (0, 40, 100, 80), False),
            ],
            [
                SidebarRow("NY Cua...", None, None, (0, 0, 100, 40), False),
                SidebarRow("其他群", None, None, (0, 40, 100, 80), False),
            ],
        ]

    def find_wechat_window(self, app_name: str) -> object:
        assert app_name == "微信"
        return object()

    def get_sidebar_rows(self, window: object) -> list[SidebarRow]:
        raise AssertionError("named fast path must not call sidebar VLM")

    def resolve_current_chat_title(self, fallback: str = "") -> str:
        titles = {
            "运营核心群": "运营核心群",
            "NY Cua...": "NY Cua Full Name",
        }
        return titles.get(fallback, fallback)


class FakeFilteredNamedFastDriver(FakeNamedFastDriver):
    def __init__(self) -> None:
        super().__init__()
        self.viewports = [
            [
                SidebarRow("Read Group", None, None, (0, 0, 100, 40), True),
                SidebarRow("Unread Private", None, "1", (0, 40, 100, 80), False),
                SidebarRow("Unread Group", None, "2", (0, 80, 100, 120), True),
            ],
        ]

    def resolve_current_chat_title(self, fallback: str = "") -> str:
        return fallback

    def get_sidebar_rows(self, window: object) -> list[SidebarRow]:
        assert window is not None
        return self.viewports[self.viewport_idx]

    def get_fast_sidebar_rows(self, window: object) -> list[SidebarRow]:
        raise AssertionError("semantic named filters must not use OCR-only rows")


class FakeSemanticFailureNamedDriver(FakeFilteredNamedFastDriver):
    def __init__(self) -> None:
        super().__init__()
        self.viewports = [
            [
                SidebarRow("Failed Group", None, "1", (0, 0, 100, 40), True),
                SidebarRow("Unread Group", None, "2", (0, 40, 100, 80), True),
            ],
        ]

    def capture_chat_messages(
        self,
        chat_name: str,
        max_messages: int | None = None,
        max_scrolls: int | None = None,
        skip_navigation_vlm: bool = False,
    ) -> object:
        assert max_messages is None
        self.capture_calls.append((chat_name, skip_navigation_vlm))
        if chat_name == "Failed Group":
            return SimpleNamespace(chat_name=chat_name, chunks=[])
        return SimpleNamespace(chat_name=chat_name)


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


def test_fast_capture_all_sweeps_without_current_chat_vlm(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WECLAW_ASYNC_VLM_WORKERS", "1")
    monkeypatch.setenv("WECLAW_ASYNC_VLM_MAX_PENDING", "2")
    driver = FakeFastCaptureDriver()
    config = FakeConfig(output_dir=str(tmp_path))

    paths = _run_capture_all_fast_path(
        driver,
        window=object(),
        config=cast(Any, config),
        written_paths=[],
    )

    assert len(paths) == 3
    assert driver.clicked == ["Short A", "Short B", "Short C"]
    assert driver.message_calls == []
    assert driver.capture_calls == [
        ("Full Chat A", True),
        ("Full Chat B", True),
        ("Full Chat C", True),
    ]
    assert driver.extract_calls == ["Full Chat A", "Full Chat B", "Full Chat C"]
    assert driver.scrolls == ["up", "up", "up", "up", "up", "up", "down"]


class FakeFocusedNamedDriver(FakeNamedFastDriver):
    """Simulate WeChat already open on the NY chat before OCR sweep starts."""

    def resolve_current_chat_title(self, fallback: str = "") -> str:
        if not str(fallback or "").strip():
            return "NY Cua Full Name"
        titles = {
            "运营核心群": "运营核心群",
            "NY Cua...": "NY Cua Full Name",
        }
        return titles.get(fallback, fallback)


class FakeFocusedReadDriver(FakeFilteredNamedFastDriver):
    def resolve_current_chat_title(self, fallback: str = "") -> str:  # noqa: ARG002
        return "Read Group"


def test_named_chats_already_focused_captures_without_sidebar_click(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WECLAW_ASYNC_VLM_WORKERS", "1")
    monkeypatch.setenv("WECLAW_ASYNC_VLM_MAX_PENDING", "2")
    driver = FakeFocusedNamedDriver()
    config = SimpleNamespace(
        wechat_app_name="微信",
        groups_to_monitor=["NY Cua Full Name", "运营核心群"],
        sidebar_unread_only=False,
        chat_type="all",
        sidebar_max_scrolls=1,
        chat_max_scrolls=0,
        output_dir=str(tmp_path),
    )
    monkeypatch.setattr(pipeline_a_win, "_create_driver", lambda vision_backend=None: driver)

    paths = pipeline_a_win._run_sidebar_scan_pipeline(config)

    assert len(paths) == 2
    assert "NY Cua..." not in driver.clicked
    assert driver.clicked == ["运营核心群"]


def test_named_chats_focused_but_unread_filter_blocks_read_group_when_unread_only(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WECLAW_ASYNC_VLM_WORKERS", "1")
    monkeypatch.setenv("WECLAW_ASYNC_VLM_MAX_PENDING", "2")
    driver = FakeFocusedReadDriver()
    config = SimpleNamespace(
        wechat_app_name="微信",
        groups_to_monitor=["Read Group"],
        sidebar_unread_only=True,
        chat_type="group",
        sidebar_max_scrolls=0,
        chat_max_scrolls=0,
        output_dir=str(tmp_path),
    )
    monkeypatch.setattr(pipeline_a_win, "_create_driver", lambda vision_backend=None: driver)

    paths = pipeline_a_win._run_sidebar_scan_pipeline(config)

    assert len(paths) == 0
    assert driver.clicked == []


def test_named_chats_use_ocr_fast_path_without_navigation_vlm(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WECLAW_ASYNC_VLM_WORKERS", "1")
    monkeypatch.setenv("WECLAW_ASYNC_VLM_MAX_PENDING", "2")
    driver = FakeNamedFastDriver()
    config = SimpleNamespace(
        wechat_app_name="微信",
        groups_to_monitor=["运营核心群", "NY Cua Full Name"],
        sidebar_unread_only=False,
        chat_type="all",
        sidebar_max_scrolls=1,
        chat_max_scrolls=0,
        output_dir=str(tmp_path),
    )
    monkeypatch.setattr(pipeline_a_win, "_create_driver", lambda vision_backend=None: driver)

    paths = pipeline_a_win._run_sidebar_scan_pipeline(cast(Any, config))

    assert len(paths) == 2
    assert driver.clicked == ["运营核心群", "NY Cua..."]
    assert driver.capture_calls == [
        ("运营核心群", True),
        ("NY Cua Full Name", True),
    ]
    assert driver.extract_calls == ["运营核心群", "NY Cua Full Name"]
    assert driver.scrolls == ["up", "up", "up", "down"]


def test_named_chats_semantic_path_respects_unread_and_chat_type_filters(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WECLAW_ASYNC_VLM_WORKERS", "1")
    monkeypatch.setenv("WECLAW_ASYNC_VLM_MAX_PENDING", "2")
    driver = FakeFilteredNamedFastDriver()
    config = SimpleNamespace(
        wechat_app_name="微信",
        groups_to_monitor=["Read Group", "Unread Private", "Unread Group"],
        sidebar_unread_only=True,
        chat_type="group",
        sidebar_max_scrolls=0,
        chat_max_scrolls=0,
        output_dir=str(tmp_path),
    )
    monkeypatch.setattr(pipeline_a_win, "_create_driver", lambda vision_backend=None: driver)

    paths = pipeline_a_win._run_sidebar_scan_pipeline(cast(Any, config))

    assert len(paths) == 1
    assert driver.clicked == ["Unread Group"]
    assert driver.capture_calls == [("Unread Group", True)]
    assert driver.extract_calls == ["Unread Group"]


def test_named_chats_semantic_path_continues_after_failed_capture(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WECLAW_ASYNC_VLM_WORKERS", "1")
    monkeypatch.setenv("WECLAW_ASYNC_VLM_MAX_PENDING", "2")
    driver = FakeSemanticFailureNamedDriver()
    config = SimpleNamespace(
        wechat_app_name="微信",
        groups_to_monitor=["Failed Group", "Unread Group"],
        sidebar_unread_only=True,
        chat_type="group",
        sidebar_max_scrolls=0,
        chat_max_scrolls=0,
        output_dir=str(tmp_path),
    )
    monkeypatch.setattr(pipeline_a_win, "_create_driver", lambda vision_backend=None: driver)

    paths = pipeline_a_win._run_sidebar_scan_pipeline(cast(Any, config))

    assert len(paths) == 1
    assert driver.clicked == ["Failed Group", "Unread Group"]
    assert driver.capture_calls == [
        ("Failed Group", True),
        ("Unread Group", True),
    ]
    assert driver.extract_calls == ["Unread Group"]


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


def test_configured_name_matches_ocr_single_dot_truncated_prefix() -> None:
    target = SidebarRow(
        name="深圳奇鸟科技.",
        last_message=None,
        badge_text=None,
        bbox=(0, 0, 100, 40),
        is_group=True,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["深圳奇鸟科技有限公司  泓灼财税服务群"],
        unread_only=False,
    )

    assert match == ("深圳奇鸟科技有限公司  泓灼财税服务群", target)


def test_configured_name_matches_visible_prefix_without_truncation_marker() -> None:
    target = SidebarRow(
        name="深圳奇鸟科技",
        last_message=None,
        badge_text=None,
        bbox=(0, 0, 100, 40),
        is_group=True,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["深圳奇鸟科技有限公司  泓灼财税服务群"],
        unread_only=False,
    )

    assert match == ("深圳奇鸟科技有限公司  泓灼财税服务群", target)


def test_configured_name_matches_punctuation_noisy_visible_prefix() -> None:
    target = SidebarRow(
        name="深圳-奇鸟科技",
        last_message=None,
        badge_text=None,
        bbox=(0, 0, 100, 40),
        is_group=True,
    )
    driver = FakeSidebarDriver([target])

    match = _find_first_visible_config_match(
        driver,
        window=object(),
        pending_names=["深圳奇鸟科技有限公司  泓灼财税服务群"],
        unread_only=False,
    )

    assert match == ("深圳奇鸟科技有限公司  泓灼财税服务群", target)


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
