"""
Build removal instructions for the agent.

Usage:
  prompt = removal_prompt(plan)
  prompt = removal_prompt_single(suspect)
  prompt = removal_with_verify_prompt(suspect, is_first=True)
  prompt = verify_panel_opened_prompt()
  prompt = find_minus_button_prompt()
  prompt = verify_member_dialog_opened_prompt()
  prompt = select_user_for_removal_prompt(user_name)
  prompt = verify_removal_prompt(user_name)
  result = parse_user_selection_response(text)
  result = parse_minus_button_response(text)
  result = parse_dialog_opened_response(text)

Input:
  - plan: RemovalPlan with confirmed flag and suspects list.
  - suspect: Single Suspect to remove.
  - text: AI response text to parse.

Output:
  - Prompt strings for various removal steps.
  - parse_user_selection_response: dict with user_found, click_x, click_y (0-1000 normalized).
  - parse_minus_button_response: dict with button_found, click_x, click_y (0-1000 normalized).
  - parse_dialog_opened_response: dict with dialog_opened bool.

Cropped regions used:
  - verify_panel_opened_prompt: MEMBER_PANEL_REGION (260x1440)
  - find_minus_button_prompt: MEMBER_PANEL_REGION (260x1440)
  - verify_member_dialog_opened_prompt: MEMBER_SELECT_REGION (705x545)
  - select_user_for_removal_prompt: MEMBER_SELECT_REGION (705x545)
  - verify_removal_prompt: MEMBER_PANEL_REGION (260x1440)
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from modules.task_types import RemovalPlan, Suspect


def removal_prompt(plan: RemovalPlan) -> str:
    """Build prompt to remove multiple users (legacy batch mode)."""
    suspects = [f"{suspect.sender_name}" for suspect in plan.suspects]
    suspect_list = "、".join(suspects)
    prompt = (
        f"任务：从群聊中移除用户「{suspect_list}」\n\n"
        "操作指南：\n"
        "1. 如果群聊信息面板未打开，点击聊天窗口右上角的三个点(...)\n"
        "2. 在群聊信息面板顶部，成员头像区域的右侧，找到灰色方形的「-」减号按钮并点击（这个按钮在成员头像的最后面）\n"
        "3. 在成员列表中找到并点击用户名「" + suspect_list + "」旁边的灰色圆形选择框\n"
        "4. 点击底部的「移出」或「完成」按钮\n\n"
        "重要提示：\n"
        "- 「-」减号按钮是一个小的灰色方形按钮，位于成员头像行的最右侧\n"
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
            "2. 在群聊信息面板顶部，成员头像区域的右侧，找到灰色方形的「-」减号按钮并点击\n"
            f"3. 在成员列表中找到用户「{user_name}」，点击其旁边的灰色圆形选择框\n"
            "4. 点击底部的「移出」或「完成」按钮确认移除\n\n"
            "重要提示：\n"
            "- 只移除这一个用户，完成后停留在成员列表界面\n"
            "- 「-」减号按钮是一个小的灰色方形按钮，位于所有成员头像的最后\n"
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
            "1. 如果不在成员移出模式，点击「-」减号按钮进入移出模式\n"
            f"2. 在成员列表中找到用户「{user_name}」，点击其旁边的灰色圆形选择框\n"
            "3. 点击底部的「移出」或「完成」按钮确认移除\n\n"
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
            f"3. 在成员列表中找到「{user_name}」，点击其旁边的灰色圆形选择框\n"
            "4. 点击底部的「移出」按钮确认移除\n"
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
            "1. 如果不在移出模式，点击「-」减号按钮进入\n"
            f"2. 在成员列表中找到「{user_name}」，点击其旁边的红色选择框\n"
            "3. 点击「移出」按钮确认\n"
            f"4. 验证成员列表中是否还有「{user_name}」\n\n"
            "完成后回复JSON：\n"
            f'{{"user_removed": true, "user_name": "{user_name}"}} 如果已移除\n'
            f'{{"user_removed": false, "user_name": "{user_name}", "reason": "原因"}} 如果失败'
        )


def verify_panel_opened_prompt() -> str:
    """Prompt to verify the group info panel is open after clicking three dots.

    This prompt is used with MEMBER_PANEL_REGION (260x1440 cropped image).
    """
    return (
        "这是屏幕右侧边缘的裁剪截图（宽260像素，高1440像素）。\n"
        "刚才已点击了三个点按钮。\n\n"
        "请查看截图：\n"
        "- 群聊信息面板是否已打开？\n"
        "- 能否看到成员头像区域和灰色「-」减号按钮？\n\n"
        "回复JSON：\n"
        '{"panel_opened": true} 如果面板已打开\n'
        '{"panel_opened": false, "reason": "原因"} 如果未打开'
    )


def find_minus_button_prompt() -> str:
    """Prompt to find the minus button position in the member panel.

    This prompt is used with MEMBER_PANEL_REGION (260x1440 cropped image).
    The AI should return coordinates in NORMALIZED space (0-1000).

    Coordinate system:
    - AI returns coordinates in NORMALIZED space (0-1000)
    - These must be converted to SCREEN coords using:
      MEMBER_PANEL_REGION.normalized_to_screen_coords(click_x, click_y)
    """
    return (
        "这是屏幕右侧群聊信息面板的裁剪截图（宽260像素，高1440像素）。\n"
        "任务：找到灰色方形「-」减号按钮的位置\n\n"
        "这个减号按钮用于进入成员移出模式，通常位于成员头像区域的右侧。\n"
        "它是一个小的灰色方形按钮，可能带有减号符号。\n\n"
        "坐标说明：\n"
        "- 使用0-1000归一化坐标系\n"
        "- x=0表示截图最左边，x=1000表示最右边\n"
        "- y=0表示截图最上边，y=1000表示最下边\n"
        "- 例如：截图中心点为 x=500, y=500\n\n"
        "回复JSON（只输出JSON，不要其他文字）：\n"
        '{"button_found": true, "click_x": 800, "click_y": 150} 如果找到\n'
        '{"button_found": false, "reason": "原因"} 如果未找到'
    )


def verify_member_dialog_opened_prompt() -> str:
    """Prompt to verify the member selection dialog is open after clicking minus button.

    This prompt is used with MEMBER_SELECT_REGION (705x545 cropped image).
    """
    return (
        "这是屏幕中央区域的裁剪截图（宽705像素，高545像素）。\n"
        "刚才已点击了「-」减号按钮。\n\n"
        "请查看截图：\n"
        "- 成员选择对话框是否已打开？\n"
        "- 能否看到成员列表和灰色圆形选择框？\n\n"
        "回复JSON：\n"
        '{"dialog_opened": true} 如果对话框已打开\n'
        '{"dialog_opened": false, "reason": "原因"} 如果未打开'
    )


def select_user_for_removal_prompt(user_name: str, is_first: bool = True) -> str:
    """Prompt to find user checkbox and return click coordinates.

    This prompt is used with MEMBER_SELECT_REGION (705x545 cropped image).

    Coordinate system:
    - AI returns coordinates in NORMALIZED space (0-1000)
    - These must be converted to SCREEN coords using:
      MEMBER_SELECT_REGION.normalized_to_screen_coords(click_x, click_y)
    """
    if is_first:
        return (
            "这是成员选择对话框的裁剪截图（宽705像素，高545像素）。\n"
            f"任务：找到用户「{user_name}」的灰色圆形选择框位置\n\n"
            "请在截图中找到该用户名，并确定其旁边红色选择框的中心位置。\n\n"
            "坐标说明：\n"
            "- 使用0-1000归一化坐标系\n"
            "- x=0表示截图最左边，x=1000表示最右边\n"
            "- y=0表示截图最上边，y=1000表示最下边\n"
            "- 例如：截图中心点为 x=500, y=500\n\n"
            "回复JSON（只输出JSON，不要其他文字）：\n"
            f'{{"user_found": true, "user_name": "{user_name}", "click_x": 100, "click_y": 300}} 如果找到\n'
            f'{{"user_found": false, "user_name": "{user_name}", "reason": "原因"}} 如果未找到'
        )
    else:
        return (
            "这是成员选择对话框的裁剪截图（宽705像素，高545像素）。\n"
            f"继续任务：找到用户「{user_name}」的灰色圆形选择框位置\n\n"
            "请在截图中找到该用户名，并确定其旁边红色选择框的中心位置。\n\n"
            "坐标说明：\n"
            "- 使用0-1000归一化坐标系\n"
            "- x=0表示截图最左边，x=1000表示最右边\n"
            "- y=0表示截图最上边，y=1000表示最下边\n\n"
            "回复JSON（只输出JSON，不要其他文字）：\n"
            f'{{"user_found": true, "user_name": "{user_name}", "click_x": 100, "click_y": 300}} 如果找到\n'
            f'{{"user_found": false, "user_name": "{user_name}", "reason": "原因"}} 如果未找到'
        )


def verify_removal_prompt(user_name: str) -> str:
    """Prompt to verify user was removed from member list after clicking delete.

    This prompt is used with MEMBER_PANEL_REGION (260x1440 cropped image).
    """
    return (
        "这是屏幕右侧边缘的裁剪截图（宽260像素，高1440像素）。\n"
        f"刚才已点击了移出按钮。\n\n"
        f"请验证：用户「{user_name}」是否已从成员列表中移除？\n\n"
        "仔细检查截图中的成员列表区域。\n\n"
        "回复JSON：\n"
        f'{{"user_removed": true, "user_name": "{user_name}"}} 如果已移除\n'
        f'{{"user_removed": false, "user_name": "{user_name}", "reason": "原因"}} 如果仍可见'
    )


def parse_user_selection_response(text: str) -> Dict[str, Any]:
    """Parse response from select_user_for_removal_prompt.

    Returns:
        dict with keys:
        - user_found: bool
        - user_name: str
        - click_x: int (NORMALIZED 0-1000, only if user_found=True)
        - click_y: int (NORMALIZED 0-1000, only if user_found=True)
        - reason: str (only if user_found=False)

    Note: click_x/click_y are in NORMALIZED space and must be converted
    to SCREEN coords before clicking using:
        MEMBER_SELECT_REGION.normalized_to_screen_coords(click_x, click_y)
    """
    text = text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try to find JSON with user_found field
    json_match = re.search(r'\{[^}]*"user_found"\s*:\s*(true|false)[^}]*\}', text, re.I)
    if json_match:
        json_str = json_match.group()
        data = json.loads(json_str)
        return {
            "user_found": data.get("user_found", False),
            "user_name": data.get("user_name", ""),
            "click_x": data.get("click_x", 0),
            "click_y": data.get("click_y", 0),
            "reason": data.get("reason", ""),
        }

    # Fallback: could not parse
    return {
        "user_found": False,
        "user_name": "",
        "click_x": 0,
        "click_y": 0,
        "reason": "Could not parse response",
    }


def parse_minus_button_response(text: str) -> Dict[str, Any]:
    """Parse response from find_minus_button_prompt.

    Returns:
        dict with keys:
        - button_found: bool
        - click_x: int (NORMALIZED 0-1000, only if button_found=True)
        - click_y: int (NORMALIZED 0-1000, only if button_found=True)
        - reason: str (only if button_found=False)

    Note: click_x/click_y are in NORMALIZED space and must be converted
    to SCREEN coords before clicking using:
        MEMBER_PANEL_REGION.normalized_to_screen_coords(click_x, click_y)
    """
    text = text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try to find JSON with button_found field
    json_match = re.search(r'\{[^}]*"button_found"\s*:\s*(true|false)[^}]*\}', text, re.I)
    if json_match:
        json_str = json_match.group()
        data = json.loads(json_str)
        return {
            "button_found": data.get("button_found", False),
            "click_x": data.get("click_x", 0),
            "click_y": data.get("click_y", 0),
            "reason": data.get("reason", ""),
        }

    # Fallback: could not parse
    return {
        "button_found": False,
        "click_x": 0,
        "click_y": 0,
        "reason": "Could not parse response",
    }


def parse_dialog_opened_response(text: str) -> Dict[str, Any]:
    """Parse response from verify_member_dialog_opened_prompt.

    Returns:
        dict with keys:
        - dialog_opened: bool
        - reason: str (only if dialog_opened=False)
    """
    text = text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try to find JSON with dialog_opened field
    json_match = re.search(
        r'\{[^}]*"dialog_opened"\s*:\s*(true|false)[^}]*\}', text, re.I
    )
    if json_match:
        json_str = json_match.group()
        data = json.loads(json_str)
        return {
            "dialog_opened": data.get("dialog_opened", False),
            "reason": data.get("reason", ""),
        }

    # Fallback: could not parse
    return {
        "dialog_opened": False,
        "reason": "Could not parse response",
    }
