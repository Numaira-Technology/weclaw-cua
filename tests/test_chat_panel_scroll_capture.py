import sys
from types import SimpleNamespace

from PIL import Image

from platform_mac import chat_panel_scroll_capture as scroll_capture


class FakeDriver:
    pid = 123

    def __init__(self) -> None:
        self.scrolls: list[str] = []

    def scroll_chat_panel(self, direction: str = "down") -> None:
        self.scrolls.append(direction)


def _frame(color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (12, 12), color)


def test_scroll_capture_includes_current_bottom_frame_before_scrolling(monkeypatch) -> None:
    driver = FakeDriver()
    frames = [_frame((255, 0, 0)), _frame((0, 255, 0)), _frame((0, 0, 255))]
    calls: list[int] = []

    def fake_capture_window_pid(pid: int):
        assert pid == driver.pid
        calls.append(pid)
        return frames[len(calls) - 1]

    monkeypatch.setitem(
        sys.modules,
        "platform_mac.macos_window",
        SimpleNamespace(capture_window_pid=fake_capture_window_pid),
    )

    out = scroll_capture.scroll_capture_frames_for_extraction(
        driver,
        max_messages=10,
        max_scrolls=2,
    )

    assert out == frames
    assert driver.scrolls == ["up", "up"]


def test_scroll_capture_zero_scrolls_still_captures_current_frame(monkeypatch) -> None:
    driver = FakeDriver()
    current = _frame((255, 0, 0))

    monkeypatch.setitem(
        sys.modules,
        "platform_mac.macos_window",
        SimpleNamespace(capture_window_pid=lambda pid: current),
    )

    out = scroll_capture.scroll_capture_frames_for_extraction(
        driver,
        max_messages=1,
        max_scrolls=0,
    )

    assert out == [current]
    assert driver.scrolls == []
