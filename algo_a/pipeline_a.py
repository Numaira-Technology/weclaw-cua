"""Orchestrate the full algo_a pipeline: find unread chats, read messages, write JSON.

Usage:
    from algo_a.pipeline_a import run_pipeline_a
    json_paths = run_pipeline_a(config)

Input spec:
    - config: WeclawConfig with wechat_app_name, groups_to_monitor, output_dir.

Output spec:
    - Returns list of JSON file paths written (one per chat with unread messages).

Pipeline steps:
    1. Auto-detect platform, create PlatformDriver
    2. driver.ensure_permissions()
    3. driver.find_wechat_window(config.wechat_app_name)
    4. list_unread_chats(driver) -> filter by groups_to_monitor
    5. For each unread chat:
       a. click_into_chat(driver, window, chat)
       b. scroll_chat_to_bottom(driver, window)
       c. read_messages_from_uitree(driver, window, chat.name)
       d. write_messages_json(chat.name, messages, config.output_dir)
"""

import sys

from algo_a.list_unread_chats import filter_chats_by_groups_to_monitor, list_unread_chats
from config.weclaw_config import WeclawConfig


def _create_driver():
    """Auto-detect the platform and return the appropriate PlatformDriver."""
    if sys.platform == "darwin":
        from platform_mac import create_driver
        return create_driver()
    elif sys.platform == "win32":
        from platform_win import create_driver
        return create_driver()
    else:
        assert False, f"unsupported platform: {sys.platform}"


def run_pipeline_a(config: WeclawConfig) -> list[str]:
    """Run the full message collection pipeline and return written JSON paths."""
    assert config is not None

    from algo_a.click_into_chat import click_into_chat
    from algo_a.scroll_chat_to_bottom import scroll_chat_to_bottom
    from algo_a.read_messages_from_uitree import read_messages_from_uitree
    from algo_a.write_messages_json import write_messages_json

    driver = _create_driver()
    driver.ensure_permissions()
    window = driver.find_wechat_window(config.wechat_app_name)
    unread_chats = list_unread_chats(driver)

    target_chats = filter_chats_by_groups_to_monitor(
        unread_chats, config.groups_to_monitor
    )

    written_paths: list[str] = []
    for chat in target_chats:
        click_into_chat(driver, window, chat)
        scroll_chat_to_bottom(driver, window)
        messages = read_messages_from_uitree(driver, window, chat.name)
        if messages:
            path = write_messages_json(chat.name, messages, config.output_dir)
            written_paths.append(path)

    return written_paths
