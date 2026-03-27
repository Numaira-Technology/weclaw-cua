"""Combine messages and user-customized prompt into a detailed morning-triage prompt.

Usage:
    from algo_b.build_report_prompt import build_report_prompt
    prompt = build_report_prompt(messages, "请重点提醒我今天早上最该先处理什么。")

Input spec:
    - messages: list[Message] loaded from algo_a output.
    - custom_prompt: the user's customization text describing what kind of report they want.

Output spec:
    - Returns a single prompt string ready to send to the LLM.
"""

from shared.message_schema import Message


def _format_message_line(message: Message) -> str:
    time_text = message.time if message.time else "时间未知"
    type_suffix = "" if message.type == "text" else f" [{message.type}]"
    content = message.content.strip() if message.content.strip() else "(空内容)"
    return f"- {time_text} | {message.sender}{type_suffix}: {content}"


def _build_chat_blocks(messages: list[Message]) -> str:
    chat_to_messages: dict[str, list[Message]] = {}
    for message in messages:
        chat_to_messages.setdefault(message.chat_name, []).append(message)

    blocks: list[str] = []
    for chat_name, chat_messages in chat_to_messages.items():
        rendered_messages = "\n".join(_format_message_line(message) for message in chat_messages)
        blocks.append(f"会话：{chat_name}\n{rendered_messages}")
    return "\n\n".join(blocks)


def build_report_prompt(messages: list[Message], custom_prompt: str) -> str:
    """Build the full LLM prompt from messages and user instructions."""
    assert isinstance(messages, list)
    assert messages
    assert custom_prompt.strip()

    messages_block = _build_chat_blocks(messages)

    return (
        "你是一名晨间未读消息处理助手。\n"
        "下面提供的是用户醒来后需要处理的全部未读聊天记录。你的任务不是泛泛总结，而是帮助用户快速判断今天早上先处理什么、先回复谁、哪些事情可以稍后再看。\n"
        "只能依据提供的聊天记录输出，不要编造不存在的事实；如果证据不足，请明确写出“信息不足”或“待确认”。\n"
        "默认使用中文输出。\n\n"
        "请严格遵守以下规则：\n"
        "1. 优先识别以下高优先级信息：有明确截止时间或时间要求、对方正在等待回复或确认、涉及客户/财务/出行/日程/会议、以及不及时处理会造成延误或损失的事项。\n"
        "2. 对生活类消息也要按“是否需要今天尽快处理”来排序。\n"
        "3. 不要按聊天逐条复述，重点输出对用户有行动价值的信息。\n"
        "4. 把聊天中的事实和你的处理建议区分开，不要把推测写成事实。\n"
        "5. 如果某一类信息没有明确证据，请写“无”。\n"
        "6. 如果用户有额外要求，在不违背以上规则的前提下优先满足。\n\n"
        "请按以下 Markdown 结构输出：\n"
        "## 晨间总览\n"
        "用 2 到 4 句话概括今天早上最值得优先关注的事情。\n\n"
        "## 优先处理\n"
        "列出最重要的 3 到 5 项事项。每项说明：事项、为什么重要、涉及会话。\n\n"
        "## 建议立即回复\n"
        "列出建议优先回复的对象或群聊。每项说明：会话或对象、建议回复主题、原因。\n\n"
        "## 重要进展与决定\n"
        "提取聊天中已经明确的新信息、关键决定或确认结果。\n\n"
        "## 待办事项\n"
        "提取聊天中明确提到的待办，尽量标明负责人和时间要求。\n\n"
        "## 风险与待确认问题\n"
        "提取风险、阻塞点和仍未确认的问题。\n\n"
        "## 可稍后处理\n"
        "列出不需要立刻处理、可以延后查看的信息。\n\n"
        f"用户自定义要求：\n{custom_prompt.strip()}\n\n"
        f"以下是全部聊天记录（按会话分组）：\n{messages_block}\n\n"
        "请直接输出最终中文晨间消息处理报告。"
    )
