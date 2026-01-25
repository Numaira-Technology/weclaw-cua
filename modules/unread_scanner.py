"""
Filter unread group threads from classification results.

Usage:
  unread_groups = filter_unread_groups(threads)

Input:
  - threads: List[GroupThread] produced by classification parsing.

Output:
  - List[GroupThread] where is_group is True and unread is True.
"""

from __future__ import annotations

from typing import List

from modules.task_types import GroupThread


def filter_unread_groups(threads: List[GroupThread]) -> List[GroupThread]:
    return [thread for thread in threads if thread.is_group and thread.unread]
