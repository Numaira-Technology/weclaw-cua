"""
Assemble a removal plan from detected suspects.

Usage:
  plan = build_removal_plan(suspects, note)

Input:
  - suspects: list of Suspect objects.
  - note: optional operator note.

Output:
  - RemovalPlan with confirmed flag defaulting to False.
"""

from __future__ import annotations

from typing import List, Optional

from modules.task_types import RemovalPlan, Suspect


def build_removal_plan(suspects: List[Suspect], note: Optional[str] = None) -> RemovalPlan:
    return RemovalPlan(suspects=suspects, confirmed=False, note=note)
