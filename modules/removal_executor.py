"""
Build removal instructions for the agent.

Usage:
  prompt = removal_prompt(plan)
  prompt = removal_prompt_single(suspect)
  prompt = removal_with_verify_prompt(suspect, is_first=True)
  prompt = verify_panel_opened_prompt()
  prompt = select_user_for_removal_prompt(user_name)
  prompt = verify_removal_prompt(user_name)

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


def removal_with_verify_prompt(suspect: Suspect, is_first: bool = True) -> str:
    """
    Build prompt to remove a single user AND verify the removal succeeded.

    This combines the removal action and verification into one agent turn,
    eliminating the need for a separate verification API call.
    """
    user_name = suspect.sender_name

    if is_first:
        return (
            f"任务：从群聊中移除用户「{user_name}」并验证\n\n"
            "操作步骤：\n"
            "1. 点击聊天窗口右上角的三个点(...) 打开群聊信息面板\n"
            "2. 在成员头像区域右侧，找到并点击灰色圆形「-」减号按钮\n"
            f"3. 在成员列表中找到「{user_name}」，点击其旁边的红色圆形选择框\n"
            "4. 点击底部的「删除」按钮确认移除\n"
            f"5. 验证：检查成员列表中是否还能看到「{user_name}」\n\n"
            "重要提示：\n"
            "- 完成后停留在成员列表界面，方便后续操作\n"
            "- 每次点击后等待界面响应\n\n"
            "完成后回复JSON：\n"
            f'{{"user_removed": true, "user_name": "{user_name}"}} 如果已移除\n'
            f'{{"user_removed": false, "user_name": "{user_name}", "reason": "原因"}} 如果失败'
        )
    else:
        return (
            f"继续任务：移除用户「{user_name}」并验证\n\n"
            "当前应在成员管理界面。\n\n"
            "操作步骤：\n"
            "1. 如果不在删除模式，点击「-」减号按钮进入\n"
            f"2. 在成员列表中找到「{user_name}」，点击其旁边的红色选择框\n"
            "3. 点击「删除」按钮确认\n"
            f"4. 验证成员列表中是否还有「{user_name}」\n\n"
            "完成后回复JSON：\n"
            f'{{"user_removed": true, "user_name": "{user_name}"}} 如果已移除\n'
            f'{{"user_removed": false, "user_name": "{user_name}", "reason": "原因"}} 如果失败'
        )


def verify_panel_opened_prompt() -> str:
    """Prompt to verify the group info panel is open after clicking three dots."""
    return (
        "刚才已点击了三个点按钮。\n\n"
        "请查看当前屏幕：\n"
        "- 群聊信息面板是否已打开？\n"
        "- 能否看到成员头像区域？\n\n"
        "回复JSON：\n"
        '{"panel_opened": true} 如果面板已打开\n'
        '{"panel_opened": false, "reason": "原因"} 如果未打开'
    )


def select_user_for_removal_prompt(user_name: str, is_first: bool = True) -> str:
    """Prompt to click minus button and select user checkbox."""
    if is_first:
        return (
            f"任务：选中用户「{user_name}」准备移除\n\n"
            "操作步骤：\n"
            "1. 在成员头像区域右侧，找到并点击灰色圆形「-」减号按钮进入删除模式\n"
            f"2. 在成员列表中找到「{user_name}」，点击其旁边的红色圆形选择框\n\n"
            "重要提示：\n"
            "- 「-」减号按钮是小的灰色圆形按钮，在成员头像行的最右侧\n"
            "- 选中用户后不要点击删除按钮，等待下一步指令\n\n"
            "完成后回复JSON：\n"
            f'{{"user_selected": true, "user_name": "{user_name}"}} 如果已选中\n'
            f'{{"user_selected": false, "user_name": "{user_name}", "reason": "原因"}} 如果失败'
        )
    else:
        return (
            f"继续任务：选中用户「{user_name}」准备移除\n\n"
            "当前应在成员管理界面。\n\n"
            "操作步骤：\n"
            "1. 如果不在删除模式，点击「-」减号按钮进入\n"
            f"2. 在成员列表中找到「{user_name}」，点击其旁边的红色选择框\n\n"
            "重要提示：\n"
            "- 选中用户后不要点击删除按钮，等待下一步指令\n\n"
            "完成后回复JSON：\n"
            f'{{"user_selected": true, "user_name": "{user_name}"}} 如果已选中\n'
            f'{{"user_selected": false, "user_name": "{user_name}", "reason": "原因"}} 如果失败'
        )


def verify_removal_prompt(user_name: str) -> str:
    """Prompt to verify user was removed from member list after clicking delete."""
    return (
        f"刚才已点击了删除按钮。\n\n"
        f"请验证：用户「{user_name}」是否已从成员列表中移除？\n\n"
        "仔细检查当前屏幕上的成员列表。\n\n"
        "回复JSON：\n"
        f'{{"user_removed": true, "user_name": "{user_name}"}} 如果已移除\n'
        f'{{"user_removed": false, "user_name": "{user_name}", "reason": "原因"}} 如果仍可见'
    )
