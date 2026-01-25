"""
Data structures for the WeChat removal workflow.

Usage:
  from modules.task_types import GroupThread, Suspect, RemovalPlan

Input:
  - None; instantiate dataclasses directly.

Output:
  - Typed containers used across modules and the workflow runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class GroupThread:
    name: str
    thread_id: str
    unread: bool
    is_group: bool = True


@dataclass
class Suspect:
    sender_id: str
    sender_name: str
    avatar_path: Path
    evidence_text: str
    thread_id: str


@dataclass
class RemovalPlan:
    suspects: List[Suspect] = field(default_factory=list)
    confirmed: bool = False
    note: Optional[str] = None


@dataclass
class RemovalResult:
    """Result of attempting to remove a single suspect from a group."""

    sender_name: str
    sender_id: str
    thread_id: str
    success: bool
    attempts: int = 1
    error: Optional[str] = None
