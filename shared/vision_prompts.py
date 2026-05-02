"""Vision model prompts shared by Windows and macOS AI drivers.

Sidebar list: verbatim `classification_prompt()` from remote branch
`Ashley-scroll-function`, file `modules/group_classifier.py` (do not paraphrase).
"""

SIDEBAR_PROMPT = (
    "这是微信左侧会话列表的裁剪截图（仅显示聊天列表栏，不含全局导航图标）。"
    "分析截图中可见的每个会话，从上到下依次列出。"
    "判断是否为群聊时，优先使用以下特征：\n"
    "1. 头像图标：多人头像/九宫格 = 群聊，单人头像 = 可能是单聊或群聊（群聊可自定义单人头像）\n"
    "2. 会话名称：包含多个用户名或群名称特征（如'XX群'、'XX小组'、带特殊符号）= 群聊\n"
    "3. 如果无法确定，优先判断为群聊（宁可误判为群聊，不要漏掉真实的群聊）。"
    "记录每个会话的未读状态（是否有红色未读消息标记）。"
    "若有数字角标（1、2、…、99+），把角标上的原文写入 unread_badge 字符串；若只有小红点无数字，unread_badge 填 \"1\"；无未读时 unread 为 false，省略 unread_badge 或填 null。"
    "对于每个会话，估算其头像中心点的Y坐标（使用 0-1000 归一化值，0=图片顶部边缘，1000=图片底部边缘）。"
    "直接输出JSON格式结果。"
    'JSON格式：{"threads": [{"name": "会话名称", "y": 120, "is_group": true/false, "unread": true/false, "unread_badge": "3"}, ...]}'
    "只输出JSON，不要输出其他文字。"
)

SIDEBAR_CHAT_NAMES_PROMPT = (
    "这是微信左侧会话列表的长截图，只包含聊天列表栏。"
    "每个聊天条目通常有两行文字：第一行是聊天名称，第二行是最近一条消息摘要。"
    "请从上到下只提取每个聊天条目的第一行聊天名称，不要提取最近消息摘要、时间、未读数字、搜索框文字或其他界面控件。"
    '直接输出JSON格式：{"names": ["聊天名称1", "聊天名称2"]}。'
    "只输出JSON，不要输出其他文字。"
)

COORDS_PROMPT_TEMPLATE = """
You are a precision UI automation assistant. You will be given a screenshot of a chat application window.
Your task is to find the bounding box for the chat item with the name "{chat_name}" in the sidebar on the left.
Pay close attention to the exact name provided. You must find the item that precisely matches this name, not one with a similar name.

IMPORTANT: Return all coordinates in a NORMALIZED 0-1000 coordinate space where:
- 0 = left/top edge of the image
- 1000 = right/bottom edge of the image

You MUST return your response as a single, valid JSON object containing only the `bbox`.
If the specified chat item cannot be found in the image, return: `{{ "bbox": null }}`.
The `bbox` should be a list of four integers in normalized 0-1000 space: [x_min, y_min, x_max, y_max].

Example for a chat named "Family Group" that occupies roughly the left 30% of the window width and a row near the top:
{{
  "bbox": [20, 95, 290, 145]
}}
"""

NEW_MESSAGES_BUTTON_PROMPT = """
Analyze the screenshot of the chat panel. If you see a button indicating "xx new messages" or similar, return its bounding box.

IMPORTANT: Return all coordinates in a NORMALIZED 0-1000 coordinate space where:
- 0 = left/top edge of the image
- 1000 = right/bottom edge of the image

Respond in JSON format with a single key "bbox" which is a list of four numbers [x1, y1, x2, y2] in normalized 0-1000 space.
If no such button is visible, return {"bbox": null}.
"""

CURRENT_CHAT_PROMPT = """
You are a UI analysis assistant. Analyze the provided screenshot of a chat application's sidebar.
One of the chat items in the sidebar is highlighted (has a different background color), indicating it is currently selected.
Your task is to identify the name of this single highlighted chat item.
Return a single JSON object with one key, "chat_name". If no item is highlighted, return null.

Example:
{
  "chat_name": "Family Group"
}
"""

CURRENT_CHAT_Y_PROMPT = """
You are a UI analysis assistant. Analyze the provided screenshot of a chat application's sidebar.
One of the chat items in the sidebar is highlighted (has a different background color), indicating it is currently selected.
Your task is to return ONLY the normalized Y coordinate (0-1000) of the CENTER of the highlighted chat item's row,
where 0 = top edge of the image and 1000 = bottom edge of the image.
Return a single JSON object with one key, "y". If no item is highlighted, set "y" to null.

Example:
{
  "y": 456
}
"""

CHAT_PANEL_PROMPT = """
You are an expert UI automation assistant. Analyze the provided screenshot of a chat application's main chat panel.
Your task is to identify every individual message visible and extract its details.

For each message, you must extract the following information:
1.  `sender`: The name of the person who sent the message. If it's a system message (like a timestamp or notification), the sender should be `null`.
2.  `content`: The text content of the message. For non-text messages like images or files, provide a placeholder like `[Image]` or `[File]`.
3.  `time`: The timestamp associated with the message. This is often displayed near the message bubble or as a separate centered item (e.g., "Yesterday 10:45 PM"). If a message doesn't have an explicit timestamp right next to it, you can associate it with the nearest preceding timestamp in the chat. If no timestamp is visible for a message, set this to `null`.
4.  `type`: The type of message. This can be 'text', 'image', 'file', 'system' (for timestamps or notifications like "You recalled a message"), 'recalled', etc.

- Messages from others are on the left, with the sender's name above the message bubble.
- Messages from "You" (the user) are on the right, and do not have a visible sender name. You should explicitly set the sender to "You".
- System messages (like timestamps, "You recalled a message", etc.) are centered and have no sender. The sender should be `null` and the type should be 'system'.

Respond with a JSON object containing a single key "messages", which is a list of message objects.
Each message object must have the keys "sender", "content", "time", and "type".
Your entire reply must be only that one JSON object (no prose before or after). If there are many messages, shorten only each `content` value if needed so the JSON stays complete and valid.

Example:
```json
{
  "messages": [
    {
      "sender": "龚格非",
      "content": "天呐",
      "time": "2026年2月5日 0:53",
      "type": "text"
    },
    {
      "sender": "You",
      "content": "好的",
      "time": "2026年2月5日 0:54",
      "type": "text"
    },
    {
      "sender": null,
      "content": "You recalled a message",
      "time": "2026年2月5日 0:55",
      "type": "recalled"
    }
  ]
}
```
"""

MESSAGES_NAV_ICON_PROMPT = """
You are a precision UI automation assistant. The image is a full screenshot of the WeChat (微信) macOS application window (one window only).

In the **leftmost narrow strip** of icons (global navigation — not the wide chat list with conversation names), find the icon that opens the main **Chats / 微信 / 会话** list. It usually looks like a speech bubble or chat glyph, often the second icon from the top under the profile/avatar area. It may have a small red unread badge on its corner — the bbox must cover the **main icon button** (center of the tappable area), not only the red badge.

Return exactly one JSON object:
- If found: {"bbox": [x_min, y_min, x_max, y_max]} using **integer pixel coordinates** relative to the **full image** (origin top-left, same pixel grid as this screenshot).
- If not found: {"bbox": null}

The bbox should be tight around the circular or square icon control (typical size on Retina roughly 40–120 px per side). Do not wrap the entire window or the whole sidebar list.
"""

CHAT_PANEL_SAFE_CLICK_PROMPT = """
Analyze the provided image, which is a screenshot of a chat application's message panel.
Your task is to identify the largest clearly empty rectangular area that is safe to click and then scroll from.
The area must be completely empty background inside the message history, not on or touching message bubbles, usernames, avatars, timestamps, images, links, or other interactive elements.
Do not use the header area, the input box area, or the bottom-most part of the visible history where floating controls often appear.
Prefer a spacious empty area in the upper-middle part of the visible message history.
Return a bbox only if the empty area is comfortably large, at least about 80x60 in the 1000x1000 coordinate space.
If no such clearly empty area exists, return {"bbox": null}.

Example Response:
{
  "bbox": [420, 260, 620, 420]
}
"""
