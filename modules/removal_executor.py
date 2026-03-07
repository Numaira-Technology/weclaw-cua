"""
Build removal instructions for the agent.

Usage:
  prompt = removal_prompt(plan)
  prompt = removal_prompt_single(suspect)
  prompt = removal_with_verify_prompt(suspect, is_first=True)
  prompt = verify_panel_opened_prompt(os_type)
  prompt = find_minus_button_prompt(os_type)
  prompt = verify_panel_and_find_minus_prompt(os_type)
  prompt = verify_member_dialog_opened_prompt(os_type)
  prompt = select_user_for_removal_prompt(user_name, is_first, os_type)
  prompt = verify_removal_prompt(user_name, os_type)
  result = parse_user_selection_response(text)
  result = parse_minus_button_response(text)
  result = parse_dialog_opened_response(text)
  result = parse_panel_and_minus_response(text)

Input:
  - plan: RemovalPlan with confirmed flag and suspects list.
  - suspect: Single Suspect to remove.
  - text: AI response text to parse.
  - os_type: "windows" or "macos" — controls prompt wording and coordinate system.

Output:
  - Prompt strings for various removal steps.
  - parse_user_selection_response: dict with user_found, click_x, click_y (0-1000 normalized).
  - parse_minus_button_response: dict with button_found, click_x, click_y (0-1000 normalized).
  - parse_dialog_opened_response: dict with dialog_opened bool.
  - parse_panel_and_minus_response: dict with panel_opened, button_found, click_x, click_y.

Coordinate systems:
  Windows prompts: AI sees a cropped region; coordinates are 0-1000 normalized
  relative to that crop, then converted via:
    get_regions("windows").member_panel.normalized_to_screen_coords(click_x, click_y)
    get_regions("windows").member_select.normalized_to_screen_coords(click_x, click_y)

  macOS prompts: AI sees the full screenshot; coordinates are 0-1000 normalized
  relative to the full screen (physical pixels), then converted via:
    screen_x = click_x / 1000 * img_w
    screen_y = click_y / 1000 * img_h

Cropped regions (Windows only, 2560×1440):
  - verify_panel_opened_prompt:         member_panel  (260×1440)
  - find_minus_button_prompt:           member_panel  (260×1440)
  - verify_panel_and_find_minus_prompt: member_panel  (260×1440)
  - verify_member_dialog_opened_prompt: member_select (705×545)
  - select_user_for_removal_prompt:     member_select (705×545)
  - verify_removal_prompt:              member_panel  (260×1440)

Skills:
  Prompts optionally load skills/wechat_removal.md via load_skill(). The skill
  text is injected as a reference section at the end of action prompts. Missing
  skill files are silently ignored so callers need not manage the path.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from modules.task_types import RemovalPlan, Suspect

# Path to the skill file, relative to the package root (two levels up from here).
_SKILL_PATH = Path(__file__).resolve().parents[1] / "skills" / "wechat_removal.md"


def load_skill(path: Path = _SKILL_PATH) -> str:
    """Load skill markdown content, stripping YAML frontmatter.

    Returns the body text, or an empty string if the file is missing.
    This function is intentionally lenient so prompts degrade gracefully.
    """
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter (--- ... ---)
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].lstrip("\n")
    return text.strip()


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


def verify_panel_opened_prompt(os_type: str = "windows") -> str:
    """Prompt to verify the group info panel is open after clicking three dots."""
    if os_type == "macos":
        return (
            "这是完整的桌面截图。刚才已点击了三个点按钮。\n\n"
            "请查看截图右侧区域：\n"
            "- 群聊信息面板是否已打开？\n"
            "- 能否看到成员头像区域和灰色「-」减号按钮？\n\n"
            "回复JSON：\n"
            '{"panel_opened": true} 如果面板已打开\n'
            '{"panel_opened": false, "reason": "原因"} 如果未打开'
        )
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


def find_minus_button_prompt(os_type: str = "windows") -> str:
    """Prompt to find the minus button position in the member panel.

    On Windows the AI sees a cropped 260x1440 member panel; coordinates are
    normalized (0-1000) relative to that crop.
    On macOS the AI sees the full screenshot; coordinates are normalized
    (0-1000) relative to the full screen.
    """
    if os_type == "macos":
        return (
            "这是完整的桌面截图。\n"
            "任务：在右侧群聊信息面板中找到灰色方形「-」减号按钮的位置\n\n"
            "这个减号按钮用于进入成员移出模式，通常位于成员头像区域的右侧。\n"
            "它是一个小的灰色方形按钮，可能带有减号符号。\n\n"
            "坐标说明：\n"
            "- 使用0-1000归一化坐标系，相对于整个截图\n"
            "- x=0表示截图最左边，x=1000表示最右边\n"
            "- y=0表示截图最上边，y=1000表示最下边\n\n"
            "回复JSON（只输出JSON，不要其他文字）：\n"
            '{"button_found": true, "click_x": 800, "click_y": 150} 如果找到\n'
            '{"button_found": false, "reason": "原因"} 如果未找到'
        )
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


def verify_panel_and_find_minus_prompt(os_type: str = "windows") -> str:
    """Combined: verify panel is open AND find minus button position.

    On Windows: AI sees the cropped 260x1440 member panel region.
    On macOS: AI sees the full screenshot; coordinates are normalized
    (0-1000) relative to the full screen.
    """
    skill = load_skill()
    skill_section = f"\n\n参考操作指南：\n{skill}" if skill else ""
    if os_type == "macos":
        return (
            "这是完整的桌面截图。刚才已点击了三个点按钮。\n\n"
            "请同时回答两个问题：\n"
            "1. 右侧群聊信息面板是否已打开（能看到成员头像区域）？\n"
            "2. 如果已打开，找到灰色方形「-」减号按钮的位置。\n"
            "   减号按钮位于成员头像行的最右侧，是一个小的灰色方形按钮。\n\n"
            "坐标说明（仅在找到按钮时填写，相对于整个截图）：\n"
            "- 使用0-1000归一化坐标系\n"
            "- x=0表示截图最左边，x=1000表示最右边\n"
            "- y=0表示截图最上边，y=1000表示最下边\n\n"
            "回复JSON（只输出JSON，不要其他文字）：\n"
            '{"panel_opened": true, "button_found": true, "click_x": 800, "click_y": 150} 如果面板已开且找到按钮\n'
            '{"panel_opened": true, "button_found": false, "reason": "原因"} 如果面板已开但未找到按钮\n'
            '{"panel_opened": false, "button_found": false, "reason": "原因"} 如果面板未打开'
            + skill_section
        )
    return (
        "这是屏幕右侧群聊信息面板的裁剪截图（宽260像素，高1440像素）。\n"
        "刚才已点击了三个点按钮。\n\n"
        "请同时回答两个问题：\n"
        "1. 群聊信息面板是否已打开（能看到成员头像区域）？\n"
        "2. 如果已打开，找到灰色方形「-」减号按钮的位置。\n"
        "   减号按钮位于成员头像行的最右侧，是一个小的灰色方形按钮。\n\n"
        "坐标说明（仅在找到按钮时填写）：\n"
        "- 使用0-1000归一化坐标系\n"
        "- x=0表示截图最左边，x=1000表示最右边\n"
        "- y=0表示截图最上边，y=1000表示最下边\n\n"
        "回复JSON（只输出JSON，不要其他文字）：\n"
        '{"panel_opened": true, "button_found": true, "click_x": 800, "click_y": 150} 如果面板已开且找到按钮\n'
        '{"panel_opened": true, "button_found": false, "reason": "原因"} 如果面板已开但未找到按钮\n'
        '{"panel_opened": false, "button_found": false, "reason": "原因"} 如果面板未打开'
        + skill_section
    )


def parse_panel_and_minus_response(text: str) -> Dict[str, Any]:
    """Parse response from verify_panel_and_find_minus_prompt.

    Returns:
        dict with keys:
        - panel_opened: bool
        - button_found: bool
        - click_x: int (NORMALIZED 0-1000, only if button_found=True)
        - click_y: int (NORMALIZED 0-1000, only if button_found=True)
        - reason: str (if panel_opened=False or button_found=False)

    Note: click_x/click_y are in NORMALIZED space (0-1000) and must be
    converted to screen coords before clicking.
    Windows: get_regions("windows").member_panel.normalized_to_screen_coords(click_x, click_y)
    Mac:     screen_x = click_x / 1000 * img_w;  screen_y = click_y / 1000 * img_h
    """
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    json_match = re.search(r'\{[^}]*"panel_opened"\s*:\s*(true|false)[^}]*\}', text, re.I)
    if json_match:
        json_str = json_match.group()
        data = json.loads(json_str)
        return {
            "panel_opened": data.get("panel_opened", False),
            "button_found": data.get("button_found", False),
            "click_x": data.get("click_x", 0),
            "click_y": data.get("click_y", 0),
            "reason": data.get("reason", ""),
        }

    return {
        "panel_opened": False,
        "button_found": False,
        "click_x": 0,
        "click_y": 0,
        "reason": "Could not parse response",
    }


def verify_member_dialog_opened_prompt(os_type: str = "windows") -> str:
    """Prompt to verify the member selection dialog is open after clicking minus."""
    if os_type == "macos":
        return (
            "这是完整的桌面截图。刚才已点击了「-」减号按钮。\n\n"
            "请查看截图中央区域：\n"
            "- 成员选择对话框是否已打开？\n"
            "- 能否看到成员列表和灰色圆形选择框？\n\n"
            "回复JSON：\n"
            '{"dialog_opened": true} 如果对话框已打开\n'
            '{"dialog_opened": false, "reason": "原因"} 如果未打开'
        )
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


def select_user_for_removal_prompt(user_name: str, is_first: bool = True, os_type: str = "windows") -> str:
    """Prompt to find user checkbox and return click coordinates.

    On Windows: AI sees the cropped 705x545 member-select region; coordinates
    are normalized (0-1000) relative to that crop.
    On macOS: AI sees the full screenshot; coordinates are normalized (0-1000)
    relative to the full screen.
    """
    skill = load_skill()
    skill_section = f"\n\n参考操作指南：\n{skill}" if skill else ""
    coord_note_mac = (
        "坐标说明：\n"
        "- 使用0-1000归一化坐标系，相对于整个截图\n"
        "- x=0表示截图最左边，x=1000表示最右边\n"
        "- y=0表示截图最上边，y=1000表示最下边\n\n"
    )
    coord_note_win = (
        "坐标说明：\n"
        "- 使用0-1000归一化坐标系\n"
        "- x=0表示截图最左边，x=1000表示最右边\n"
        "- y=0表示截图最上边，y=1000表示最下边\n"
        "- 例如：截图中心点为 x=500, y=500\n\n"
    )
    json_reply = (
        f'{{"user_found": true, "user_name": "{user_name}", "click_x": 100, "click_y": 300}} 如果找到\n'
        f'{{"user_found": false, "user_name": "{user_name}", "reason": "原因"}} 如果未找到'
    )
    if os_type == "macos":
        action = "找到" if is_first else "继续找到"
        return (
            f"这是完整的桌面截图。\n"
            f"任务：{action}成员选择对话框中用户「{user_name}」的灰色圆形选择框位置\n\n"
            "请在截图中央的成员选择对话框中找到该用户名，并确定其旁边选择框的中心位置。\n\n"
            + coord_note_mac
            + "回复JSON（只输出JSON，不要其他文字）：\n"
            + json_reply
            + skill_section
        )
    if is_first:
        return (
            "这是成员选择对话框的裁剪截图（宽705像素，高545像素）。\n"
            f"任务：找到用户「{user_name}」的灰色圆形选择框位置\n\n"
            "请在截图中找到该用户名，并确定其旁边红色选择框的中心位置。\n\n"
            + coord_note_win
            + "回复JSON（只输出JSON，不要其他文字）：\n"
            + json_reply
            + skill_section
        )
    return (
        "这是成员选择对话框的裁剪截图（宽705像素，高545像素）。\n"
        f"继续任务：找到用户「{user_name}」的灰色圆形选择框位置\n\n"
        "请在截图中找到该用户名，并确定其旁边红色选择框的中心位置。\n\n"
        + coord_note_win
        + "回复JSON（只输出JSON，不要其他文字）：\n"
        + json_reply
        + skill_section
    )


def verify_removal_prompt(user_name: str, os_type: str = "windows") -> str:
    """Prompt to verify user was removed from member list after clicking delete."""
    if os_type == "macos":
        return (
            "这是完整的桌面截图。"
            f"刚才已点击了移出按钮。\n\n"
            f"请验证：用户「{user_name}」是否已从右侧群聊信息面板的成员列表中移除？\n\n"
            "仔细检查截图右侧的成员列表区域。\n\n"
            "回复JSON：\n"
            f'{{"user_removed": true, "user_name": "{user_name}"}} 如果已移除\n'
            f'{{"user_removed": false, "user_name": "{user_name}", "reason": "原因"}} 如果仍可见'
        )
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

    Note: click_x/click_y are in NORMALIZED space (0-1000) and must be
    converted to screen coords before clicking.
    Windows: get_regions("windows").member_select.normalized_to_screen_coords(click_x, click_y)
    Mac:     screen_x = click_x / 1000 * img_w;  screen_y = click_y / 1000 * img_h
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

    Note: click_x/click_y are in NORMALIZED space (0-1000) and must be
    converted to screen coords before clicking.
    Windows: get_regions("windows").member_panel.normalized_to_screen_coords(click_x, click_y)
    Mac:     screen_x = click_x / 1000 * img_w;  screen_y = click_y / 1000 * img_h
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


# ---------------------------------------------------------------------------
# macOS-only: vision-based button location prompts
# ---------------------------------------------------------------------------
# WeChat Mac uses a web-based UI (Electron/flue) that exposes no AXButton
# elements in the macOS Accessibility tree.  These prompts ask the AI to
# locate each button visually in the full screenshot and return click coords.
# ---------------------------------------------------------------------------

def mac_find_three_dots_prompt() -> str:
    """Ask AI to locate the three-dots / group-info button in the full screenshot.

    Returns:
        Prompt string. AI should respond with JSON containing button coords.
    """
    return (
        "这是完整的桌面截图。\n"
        "任务：找到微信聊天窗口右上角的「···」三个点按钮（用于打开群聊信息面板）。\n\n"
        "这个按钮通常是一个带有三个点的小图标，位于聊天窗口标题栏的右侧。\n"
        "它可能显示为「···」、「···」或三个点排列的图标。\n\n"
        "坐标说明：\n"
        "- 使用0-1000归一化坐标系，相对于整个截图\n"
        "- x=0表示截图最左边，x=1000表示最右边\n"
        "- y=0表示截图最上边，y=1000表示最下边\n\n"
        "回复JSON（只输出JSON，不要其他文字）：\n"
        '{"button_found": true, "click_x": 850, "click_y": 30} 如果找到\n'
        '{"button_found": false, "reason": "原因"} 如果未找到'
    )


def mac_find_minus_button_prompt() -> str:
    """Ask AI to locate the minus / remove-member button after panel is open.

    Returns:
        Prompt string. AI should respond with JSON containing button coords.
    """
    return (
        "这是完整的桌面截图。群聊信息面板应该已经打开（在右侧）。\n"
        "任务：找到群聊信息面板中的「-」减号按钮的位置。\n\n"
        "这个减号按钮用于进入成员移出模式，通常位于成员头像区域的右下角。\n"
        "它是一个小的灰色虚线轮廓的方形按钮，带有减号「-」符号，方形按钮和成员头像一样大，紧贴成员头像网格的右侧。\n\n"
        "坐标说明：\n"
        "- 使用0-1000归一化坐标系，相对于整个截图\n"
        "- x=0表示截图最左边，x=1000表示最右边\n"
        "- y=0表示截图最上边，y=1000表示最下边\n\n"
        "回复JSON（只输出JSON，不要其他文字）：\n"
        '{"button_found": true, "click_x": 820, "click_y": 200} 如果找到\n'
        '{"button_found": false, "reason": "原因"} 如果未找到'
    )


def mac_find_confirm_removal_prompt(user_name: str = "") -> str:
    """Ask AI to locate the 移出/confirm button after the user has been selected.

    At this point the user's checkbox has already been ticked — the 移出 button
    at the bottom of the member-selection dialog should now be active (blue/red).

    Args:
        user_name: Optional name of the user being removed, used in the prompt.

    Returns:
        Prompt string. AI should respond with JSON containing button coords.
    """
    name_hint = f"「{user_name}」的" if user_name else ""
    return (
        f"这是完整的桌面截图。{name_hint}成员的选择框已经被勾选。\n"
        "任务：找到成员选择对话框底部的「移出」或「确定」按钮位置，点击它来确认移除。\n\n"
        "这个按钮通常出现在成员列表底部，在至少一个成员被勾选后会变为可点击状态（蓝色或红色）。\n"
        "请仔细查找对话框底部区域的确认按钮。\n\n"
        "坐标说明：\n"
        "- 使用0-1000归一化坐标系，相对于整个截图\n"
        "- x=0表示截图最左边，x=1000表示最右边\n"
        "- y=0表示截图最上边，y=1000表示最下边\n\n"
        "回复JSON（只输出JSON，不要其他文字）：\n"
        '{"button_found": true, "click_x": 500, "click_y": 800} 如果找到\n'
        '{"button_found": false, "reason": "原因"} 如果未找到'
    )


def parse_mac_button_response(text: str) -> dict:
    """Parse response from any mac_find_*_prompt function.

    Handles common AI formatting issues:
    - Markdown code fences (```json ... ```)
    - Malformed JSON where click_y value is missing its key name,
      e.g. {"button_found": true, "click_x": 432, 254}

    Returns:
        dict with keys:
        - button_found: bool
        - click_x: int (0-1000 normalized, physical pixel space)
        - click_y: int (0-1000 normalized, physical pixel space)
        - reason: str (if button_found=False)
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    json_match = re.search(r'\{[^}]*"button_found"\s*:\s*(true|false)[^}]*\}', text, re.I | re.S)
    if json_match:
        raw = json_match.group()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Attempt regex extraction for each field individually so that
            # malformed JSON (e.g. missing "click_y": key) still yields coords.
            found_match = re.search(r'"button_found"\s*:\s*(true|false)', raw, re.I)
            x_match = re.search(r'"click_x"\s*:\s*(\d+)', raw)
            # click_y may appear as "click_y": NNN  OR as a bare trailing number
            y_match = re.search(r'"click_y"\s*:\s*(\d+)', raw)
            if y_match is None:
                # Fallback: last standalone integer in the blob that isn't click_x
                x_val = x_match.group(1) if x_match else None
                for m in re.finditer(r'\b(\d+)\b', raw):
                    if m.group(1) != x_val:
                        y_match = m
            if found_match and x_match and y_match:
                button_found = found_match.group(1).lower() == "true"
                return {
                    "button_found": button_found,
                    "click_x": int(x_match.group(1)),
                    "click_y": int(y_match.group(1)),
                    "reason": "",
                }
            return {
                "button_found": False,
                "click_x": 0,
                "click_y": 0,
                "reason": "Could not parse response",
            }

        return {
            "button_found": bool(data.get("button_found", False)),
            "click_x": int(data.get("click_x", 0)),
            "click_y": int(data.get("click_y", 0)),
            "reason": data.get("reason", ""),
        }

    return {
        "button_found": False,
        "click_x": 0,
        "click_y": 0,
        "reason": "Could not parse response",
    }

