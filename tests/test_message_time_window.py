"""Unit tests for recent-message time window helpers.

Usage:
    python3 -m pytest tests/test_message_time_window.py

Input spec:
    - Uses synthetic ChatMessage rows with representative time strings.

Output spec:
    - Verifies parsing; filtering/cutoff tests use explicit hours=24 (default RECENT_WINDOW_HOURS is 0 / disabled).
"""

from datetime import datetime
import unittest

from shared.datatypes import ChatMessage
from shared.message_time_window import (
    chunk_reaches_recent_cutoff,
    filter_messages_to_recent_window,
    parse_message_time,
)


class TestMessageTimeWindow(unittest.TestCase):
    def test_parse_plain_clock_rolls_back_after_midnight(self) -> None:
        now = datetime(2026, 4, 10, 0, 15)
        parsed = parse_message_time("23:30", now=now)
        self.assertEqual(parsed, datetime(2026, 4, 9, 23, 30))

    def test_parse_relative_chinese_day(self) -> None:
        now = datetime(2026, 4, 10, 10, 0)
        parsed = parse_message_time("昨天 21:10", now=now)
        self.assertEqual(parsed, datetime(2026, 4, 9, 21, 10))

    def test_parse_weekday(self) -> None:
        now = datetime(2026, 4, 10, 10, 0)
        parsed = parse_message_time("星期四 09:10", now=now)
        self.assertEqual(parsed, datetime(2026, 4, 9, 9, 10))

    def test_filter_messages_to_recent_window(self) -> None:
        now = datetime(2026, 4, 10, 12, 0)
        messages = [
            ChatMessage(sender="A", time="昨天 11:30", content="old", type="text"),
            ChatMessage(sender="A", time="昨天 13:30", content="new", type="text"),
            ChatMessage(sender="A", time=None, content="follow", type="text"),
        ]
        out = filter_messages_to_recent_window(messages, hours=24, now=now)
        self.assertEqual([m.content for m in out], ["new", "follow"])

    def test_chunk_reaches_recent_cutoff(self) -> None:
        now = datetime(2026, 4, 10, 12, 0)
        messages = [
            ChatMessage(sender="A", time="昨天 11:30", content="old", type="text"),
            ChatMessage(sender="A", time="昨天 13:30", content="new", type="text"),
        ]
        self.assertTrue(chunk_reaches_recent_cutoff(messages, hours=24, now=now))


if __name__ == "__main__":
    unittest.main()
