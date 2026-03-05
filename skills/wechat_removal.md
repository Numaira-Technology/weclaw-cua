---
name: wechat-removal
description: >
  Use when removing users from a WeChat group via the desktop client.
  Covers opening the member panel, locating the minus button, selecting
  a user checkbox, and confirming the removal.
---

# WeChat Member Removal

## UI Flow Overview

1. Click the three-dots (...) button at the top-right of the chat window to open the group info panel.
2. In the group info panel (right side strip), locate the grey square **minus (−)** button to the right of the member avatar row. Click it to enter removal mode.
3. A member selection dialog appears in the centre of the screen. Find the target user's name and click the grey circular checkbox next to it.
4. Click the **移出** (Remove) / **完成** (Done) button at the bottom of the dialog to confirm.

## Coordinate System

All AI vision responses use **normalised 0–1000 coordinates** relative to the cropped region:

- `x=0` → left edge of crop, `x=1000` → right edge
- `y=0` → top edge of crop, `y=1000` → bottom edge

These must be converted to absolute screen pixels before clicking.

## Key UI Elements

| Element | Region | Notes |
|---|---|---|
| Group info panel | MEMBER_PANEL_REGION (260×1440 px) | Right strip of screen |
| Minus (−) button | MEMBER_PANEL_REGION | Grey square, rightmost in avatar row |
| Member selection dialog | MEMBER_SELECT_REGION (705×545 px) | Centre popup |
| User checkbox | MEMBER_SELECT_REGION | Grey/red circle left of username |
| Delete confirm button | Hardcoded screen position | Fixed position — no vision needed |

## Error Recovery

- If the panel does not open, retry clicking the three-dots button.
- If the minus button is not visible, scroll up in the member panel.
- If the member dialog does not appear after clicking minus, the button click may have missed — re-locate and retry.
- If the user is not visible in the dialog, scroll down inside the member list.
- Never click the same position more than twice in a row without taking a new screenshot.

## Important Constraints

- Only operate inside group chats (群聊), never in individual (单人) conversations.
- After each click, wait for the UI to update before issuing the next action.
- The minus button is a **grey square** — do not confuse it with the plus (+) button which adds members.
