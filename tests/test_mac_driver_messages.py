import pytest

pytest.importorskip("Quartz")

from platform_mac.mac_driver_messages import MacDriverMessages
from shared.datatypes import SidebarRow


class FakeUnreadMacDriver(MacDriverMessages):
    def __init__(self) -> None:
        self.clicked: list[str] = []
        self.rows = [
            SidebarRow(
                "运营核心群",
                None,
                "3",
                (0, 0, 100, 40),
                True,
                selected=True,
            ),
        ]

    def get_fast_sidebar_rows(self, window: object) -> list[SidebarRow]:
        return self.rows

    def click_row(self, row: SidebarRow, attempt: int = 0) -> None:
        self.clicked.append(row.name)


def test_click_first_unread_sidebar_row_skips_selected_row() -> None:
    driver = FakeUnreadMacDriver()

    cap, name = driver.click_first_unread_sidebar_row()

    assert cap == 3
    assert name == "运营核心群"
    assert driver.clicked == []
