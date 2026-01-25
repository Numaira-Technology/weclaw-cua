"""
State management for the control panel workflow steps.

Usage:
  from panel_state import PanelState, save_state, load_state

Input:
  - state_path: Path to JSON file for persistence.

Output:
  - PanelState dataclass with intermediate results between steps.
  - Serialization helpers for JSON persistence.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.task_types import GroupThread, RemovalPlan, Suspect


@dataclass
class PanelState:
    threads: List[GroupThread] = field(default_factory=list)
    unread_groups: List[GroupThread] = field(default_factory=list)
    current_thread_index: int = 0
    # Per-group state (reset when moving to next group)
    current_group_suspects: List[Suspect] = field(default_factory=list)
    current_group_plan: Optional[RemovalPlan] = None
    # Accumulated results across all groups
    all_suspects: List[Suspect] = field(default_factory=list)
    all_plans: List[RemovalPlan] = field(default_factory=list)
    # Legacy fields (kept for backward compatibility)
    suspects: List[Suspect] = field(default_factory=list)
    plan: Optional[RemovalPlan] = None
    step_logs: Dict[str, str] = field(default_factory=dict)


def _serialize_suspect(s: Suspect) -> dict:
    return {
        "sender_id": s.sender_id,
        "sender_name": s.sender_name,
        "avatar_path": str(s.avatar_path),
        "evidence_text": s.evidence_text,
        "thread_id": s.thread_id,
    }


def _serialize_plan(plan: RemovalPlan) -> dict:
    return {
        "suspects": [_serialize_suspect(s) for s in plan.suspects],
        "confirmed": plan.confirmed,
        "note": plan.note,
    }


def _serialize_state(state: PanelState) -> dict:
    return {
        "threads": [asdict(t) for t in state.threads],
        "unread_groups": [asdict(g) for g in state.unread_groups],
        "current_thread_index": state.current_thread_index,
        "current_group_suspects": [_serialize_suspect(s) for s in state.current_group_suspects],
        "current_group_plan": _serialize_plan(state.current_group_plan) if state.current_group_plan else None,
        "all_suspects": [_serialize_suspect(s) for s in state.all_suspects],
        "all_plans": [_serialize_plan(p) for p in state.all_plans],
        "suspects": [_serialize_suspect(s) for s in state.suspects],
        "plan": _serialize_plan(state.plan) if state.plan else None,
        "step_logs": state.step_logs,
    }


def _deserialize_suspect(s: dict) -> Suspect:
    return Suspect(
        sender_id=s["sender_id"],
        sender_name=s["sender_name"],
        avatar_path=Path(s.get("avatar_path", "")),
        evidence_text=s.get("evidence_text", ""),
        thread_id=s.get("thread_id", ""),
    )


def _deserialize_plan(plan_data: dict) -> RemovalPlan:
    return RemovalPlan(
        suspects=[_deserialize_suspect(s) for s in plan_data.get("suspects", [])],
        confirmed=plan_data.get("confirmed", False),
        note=plan_data.get("note"),
    )


def _deserialize_state(data: dict) -> PanelState:
    threads = [
        GroupThread(
            name=t["name"],
            thread_id=t["thread_id"],
            unread=t["unread"],
            is_group=t.get("is_group", True),
        )
        for t in data.get("threads", [])
    ]
    unread_groups = [
        GroupThread(
            name=g["name"],
            thread_id=g["thread_id"],
            unread=g["unread"],
            is_group=g.get("is_group", True),
        )
        for g in data.get("unread_groups", [])
    ]
    # Per-group state
    current_group_suspects = [_deserialize_suspect(s) for s in data.get("current_group_suspects", [])]
    current_group_plan_data = data.get("current_group_plan")
    current_group_plan = _deserialize_plan(current_group_plan_data) if current_group_plan_data else None
    # Accumulated results
    all_suspects = [_deserialize_suspect(s) for s in data.get("all_suspects", [])]
    all_plans = [_deserialize_plan(p) for p in data.get("all_plans", [])]
    # Legacy fields
    suspects = [_deserialize_suspect(s) for s in data.get("suspects", [])]
    plan_data = data.get("plan")
    plan = _deserialize_plan(plan_data) if plan_data else None
    return PanelState(
        threads=threads,
        unread_groups=unread_groups,
        current_thread_index=data.get("current_thread_index", 0),
        current_group_suspects=current_group_suspects,
        current_group_plan=current_group_plan,
        all_suspects=all_suspects,
        all_plans=all_plans,
        suspects=suspects,
        plan=plan,
        step_logs=data.get("step_logs", {}),
    )


def save_state(state: PanelState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_serialize_state(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_state(path: Path) -> PanelState:
    if not path.exists():
        return PanelState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return _deserialize_state(data)
