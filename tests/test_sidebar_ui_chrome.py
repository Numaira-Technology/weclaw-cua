"""Unit tests for shared.sidebar_ui_chrome.is_sidebar_ui_chrome_label."""

import unittest

from shared.sidebar_ui_chrome import is_sidebar_ui_chrome_label


class TestSidebarUiChrome(unittest.TestCase):
    def test_search_box(self):
        self.assertTrue(is_sidebar_ui_chrome_label("搜索"))

    def test_fold_pinned_header(self):
        self.assertTrue(is_sidebar_ui_chrome_label("折叠置顶聊天"))

    def test_unfold_variant(self):
        self.assertTrue(is_sidebar_ui_chrome_label("展开置顶聊天"))

    def test_whitespace_tolerant(self):
        self.assertTrue(is_sidebar_ui_chrome_label(" 折 叠\u3000置 顶聊天 "))

    def test_real_chat_not_chrome(self):
        self.assertFalse(is_sidebar_ui_chrome_label("家庭群"))
        self.assertFalse(is_sidebar_ui_chrome_label(""))
        self.assertFalse(is_sidebar_ui_chrome_label("置顶设计讨论"))
        self.assertFalse(is_sidebar_ui_chrome_label("搜索助手"))


if __name__ == "__main__":
    unittest.main()
