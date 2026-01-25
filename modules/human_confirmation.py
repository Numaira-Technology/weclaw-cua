"""
Require human confirmation before executing removals.

Usage:
  plan = require_confirmation(plan)

Input:
  - plan: RemovalPlan with suspects list.

Output:
  - RemovalPlan with confirmed set based on operator input.
"""

from __future__ import annotations

from modules.task_types import RemovalPlan


def require_confirmation(plan: RemovalPlan) -> RemovalPlan:
    if not plan.suspects:
        plan.confirmed = False
        return plan
    decision = input("Confirm removal of listed suspects? (y/N): ").strip().lower()
    plan.confirmed = decision == "y"
    return plan
