"""Recent-message time window helpers for chat extraction.

Usage:
    from shared.message_time_window import (
        RECENT_WINDOW_HOURS,
        chunk_reaches_recent_cutoff,
        filter_messages_to_recent_window,
    )

Input spec:
    - Message times are free-form strings from vision extraction, such as:
      "23:15", "昨天 21:05", "星期四 09:10", "2026年4月9日 18:30".
    - Messages are expected in visible chat order from older to newer.

Output spec:
    - `filter_messages_to_recent_window` keeps only messages within the recent window when hours > 0.
    - `hours <= 0` disables filtering and cutoff (keeps all messages; never treats a chunk as "reached cutoff").
    - `chunk_reaches_recent_cutoff` returns True when a chunk already reaches the cutoff (hours > 0 only).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from shared.datatypes import ChatMessage

RECENT_WINDOW_HOURS = 0
_FUTURE_TOLERANCE = timedelta(minutes=5)
_WEEKDAY_INDEX = {
    "星期一": 0,
    "周一": 0,
    "monday": 0,
    "mon": 0,
    "星期二": 1,
    "周二": 1,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "星期三": 2,
    "周三": 2,
    "wednesday": 2,
    "wed": 2,
    "星期四": 3,
    "周四": 3,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "星期五": 4,
    "周五": 4,
    "friday": 4,
    "fri": 4,
    "星期六": 5,
    "周六": 5,
    "saturday": 5,
    "sat": 5,
    "星期日": 6,
    "星期天": 6,
    "周日": 6,
    "周天": 6,
    "sunday": 6,
    "sun": 6,
}


def _normalize_time_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = str(raw).strip()
    text = text.replace("：", ":").replace("/", "-").replace(".", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def _parse_clock(text: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    lower = text.lower()
    is_pm = any(token in lower for token in ("pm", "下午", "晚上", "晚", "中午"))
    is_am = any(token in lower for token in ("am", "上午", "早上", "凌晨", "清晨"))
    if is_pm and hour < 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _resolve_same_day_or_yesterday(hour: int, minute: int, now: datetime) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate > now + _FUTURE_TOLERANCE:
        candidate -= timedelta(days=1)
    return candidate


def _resolve_weekday(target_weekday: int, hour: int, minute: int, now: datetime) -> datetime:
    days_back = (now.weekday() - target_weekday) % 7
    candidate_date = (now - timedelta(days=days_back)).date()
    candidate = datetime.combine(candidate_date, datetime.min.time()).replace(
        hour=hour, minute=minute
    )
    if candidate > now + _FUTURE_TOLERANCE:
        candidate -= timedelta(days=7)
    return candidate


def parse_message_time(raw: str | None, now: datetime | None = None) -> datetime | None:
    text = _normalize_time_text(raw)
    if not text:
        return None
    if now is None:
        now = datetime.now().astimezone().replace(tzinfo=None)
    clock = _parse_clock(text)
    if clock is None:
        return None
    hour, minute = clock

    match = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})日?", text)
    if match:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            hour,
            minute,
        )

    match = re.search(r"(?<!\d)(\d{1,2})[-月](\d{1,2})日?", text)
    if match:
        candidate = datetime(
            now.year,
            int(match.group(1)),
            int(match.group(2)),
            hour,
            minute,
        )
        if candidate > now + timedelta(days=1):
            candidate = candidate.replace(year=now.year - 1)
        return candidate

    if "昨天" in text or "yesterday" in text.lower():
        base = now - timedelta(days=1)
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if "今天" in text or "today" in text.lower():
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    lower = text.lower()
    for token, weekday in _WEEKDAY_INDEX.items():
        if token in lower or token in text:
            return _resolve_weekday(weekday, hour, minute, now)

    return _resolve_same_day_or_yesterday(hour, minute, now)


def _message_effective_time(
    message: ChatMessage,
    anchor: datetime | None,
    now: datetime,
) -> tuple[datetime | None, datetime | None]:
    parsed = parse_message_time(message.time, now=now)
    if parsed is not None:
        return parsed, parsed
    return anchor, anchor


def filter_messages_to_recent_window(
    messages: list[ChatMessage],
    *,
    hours: int = RECENT_WINDOW_HOURS,
    now: datetime | None = None,
) -> list[ChatMessage]:
    if hours <= 0:
        return list(messages)
    if now is None:
        now = datetime.now().astimezone().replace(tzinfo=None)
    cutoff = now - timedelta(hours=hours)
    out: list[ChatMessage] = []
    anchor: datetime | None = None
    for message in messages:
        effective, anchor = _message_effective_time(message, anchor, now)
        if effective is None or effective >= cutoff:
            out.append(message)
    return out


def chunk_reaches_recent_cutoff(
    messages: list[ChatMessage],
    *,
    hours: int = RECENT_WINDOW_HOURS,
    now: datetime | None = None,
) -> bool:
    if hours <= 0:
        return False
    if now is None:
        now = datetime.now().astimezone().replace(tzinfo=None)
    cutoff = now - timedelta(hours=hours)
    anchor: datetime | None = None
    for message in messages:
        effective, anchor = _message_effective_time(message, anchor, now)
        if effective is not None and effective < cutoff:
            return True
    return False
