"""
Build removal instructions for the agent.

Usage:
  prompt = removal_prompt(plan)

Input:
  - plan: RemovalPlan with confirmed flag and suspects list.

Output:
  - Prompt string directing the agent to open group management and remove listed users using IDs and avatars.
"""

from __future__ import annotations

from modules.task_types import RemovalPlan


def removal_prompt(plan: RemovalPlan) -> str:
    suspects = [f"{suspect.sender_name}" for suspect in plan.suspects]
    suspect_list = "、".join(suspects)
    prompt = (
        f"任务：从群聊中移除用户「{suspect_list}」\n\n"
        "操作指南：\n"
        "1. 如果群聊信息面板未打开，点击聊天窗口右上角的三个点(...)\n"
        "2. 在群聊信息面板顶部，成员头像区域的右侧，找到灰色圆形的「-」减号按钮并点击（这个按钮在成员头像的右边，不是在底部）\n"
        "3. 在成员列表中找到并点击用户名「" + suspect_list + "」旁边的红色圆形选择框\n"
        "4. 点击底部的「删除」或「完成」按钮\n\n"
        "重要提示：\n"
        "- 「-」减号按钮是一个小的灰色圆形按钮，位于成员头像行的最右侧\n"
        "- 点击后等待界面更新，观察变化\n"
        "- 每个步骤完成后再进行下一步\n\n"
        '完成后回复: {"removal_status": "done"}\n'
        '失败则回复: {"removal_status": "failed", "reason": "原因"}'
    )
    # #region agent log
    import json as _json
    import time as _time
    from pathlib import Path as _Path

    _log_path = _Path(__file__).resolve().parents[1] / ".cursor" / "debug.log"
    open(_log_path, "a", encoding="utf-8").write(
        _json.dumps(
            {
                "location": "removal_executor.py:removal_prompt",
                "message": "generated removal prompt",
                "data": {
                    "prompt": prompt,
                    "suspect_count": len(plan.suspects),
                    "suspect_list": suspect_list,
                },
                "timestamp": _time.time(),
                "sessionId": "debug-session",
                "hypothesisId": "A",
            }
        )
        + "\n"
    )
    # #endregion
    return prompt
