"""
Build removal instructions for the agent.

Usage:
  prompt = removal_prompt(plan)
  prompt = removal_prompt_single(suspect)

Input:
  - plan: RemovalPlan with confirmed flag and suspects list.
  - suspect: Single Suspect to remove.

Output:
  - Prompt string directing the agent to open group management and remove listed users.
"""

from __future__ import annotations

from modules.task_types import RemovalPlan, Suspect


def removal_prompt(plan: RemovalPlan) -> str:
    """Build prompt to remove multiple users (legacy batch mode)."""
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
        "错误恢复（如果点错了位置）：\n"
        "- 如果打开了错误的菜单或对话框，找到返回或取消等按键关闭它，回到刚才的界面，然后重新尝试\n"
        "- 如果进入了错误的聊天，点击左侧聊天列表返回正确的群聊\n"
        "- 如果界面状态不确定，先截图观察当前状态，再决定下一步\n"
        "- 不要连续快速点击同一位置，每次点击后等待界面响应\n\n"
        '完成后回复: {"removal_status": "done"}\n'
        '失败则回复: {"removal_status": "failed", "reason": "原因"}'
    )
    return prompt


def removal_prompt_single(suspect: Suspect, is_first: bool = True) -> str:
    """Build prompt to remove a single user.

    Args:
        suspect: The suspect to remove
        is_first: Whether this is the first removal (need to open member management)

    Returns:
        Prompt string for removing this single user
    """
    user_name = suspect.sender_name

    if is_first:
        # First removal: need to open the member management panel
        prompt = (
            f"任务：从群聊中移除用户「{user_name}」\n\n"
            "操作指南：\n"
            "1. 如果群聊信息面板未打开，点击聊天窗口右上角的三个点(...)\n"
            "2. 在群聊信息面板顶部，成员头像区域的右侧，找到灰色圆形的「-」减号按钮并点击\n"
            f"3. 在成员列表中找到用户「{user_name}」，点击其旁边的红色圆形选择框\n"
            "4. 点击底部的「删除」或「完成」按钮确认移除\n\n"
            "重要提示：\n"
            "- 只移除这一个用户，完成后停留在成员列表界面\n"
            "- 「-」减号按钮是一个小的灰色圆形按钮，位于成员头像行的最右侧\n"
            "- 点击后等待界面更新，观察变化\n\n"
            "错误恢复：\n"
            "- 如果打开了错误的菜单，关闭它重新尝试\n"
            "- 如果界面状态不确定，先截图观察\n\n"
            '完成后回复: {"removal_status": "done"}\n'
            '失败则回复: {"removal_status": "failed", "reason": "原因"}'
        )
    else:
        # Subsequent removal: already in member management, just select and remove
        prompt = (
            f"任务：继续移除用户「{user_name}」\n\n"
            "当前应该已经在成员管理界面。\n\n"
            "操作指南：\n"
            "1. 如果不在成员删除模式，点击「-」减号按钮进入删除模式\n"
            f"2. 在成员列表中找到用户「{user_name}」，点击其旁边的红色圆形选择框\n"
            "3. 点击底部的「删除」或「完成」按钮确认移除\n\n"
            "重要提示：\n"
            "- 只移除这一个用户，完成后停留在成员列表界面\n"
            "- 点击后等待界面更新\n\n"
            '完成后回复: {"removal_status": "done"}\n'
            '失败则回复: {"removal_status": "failed", "reason": "原因"}'
        )

    return prompt
