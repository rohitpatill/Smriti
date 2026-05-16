"""
Time context for the agent.

Computed server-side at every session start (and refreshed on identity.md
reads) so the model never has to do date arithmetic. All times in Asia/Kolkata.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Kolkata")
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _fmt_day(d) -> str:
    return f"{d.strftime('%Y-%m-%d')} ({DAY_NAMES[d.weekday()]})"


def _part_of_day(hour: int) -> str:
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 16:
        return "midday"
    if 16 <= hour < 20:
        return "evening"
    if 20 <= hour < 23:
        return "late evening"
    return "late night"


def build_time_context() -> str:
    now = datetime.now(TIMEZONE)
    today = now.date()

    last_7 = [today - timedelta(days=i) for i in range(7, 0, -1)]
    next_7 = [today + timedelta(days=i) for i in range(1, 8)]
    last_month_start = today - timedelta(days=30)
    next_month_end = today + timedelta(days=30)

    lines = [
        "## Current Time (Asia/Kolkata)",
        "",
        f"- Now: {now.strftime('%Y-%m-%d %H:%M')} ({DAY_NAMES[now.weekday()]} {_part_of_day(now.hour)})",
        f"- Today: {_fmt_day(today)}",
        f"- Yesterday: {_fmt_day(today - timedelta(days=1))}",
        f"- Day before yesterday: {_fmt_day(today - timedelta(days=2))}",
        f"- Tomorrow: {_fmt_day(today + timedelta(days=1))}",
        f"- Day after tomorrow: {_fmt_day(today + timedelta(days=2))}",
        "",
        "### Last 7 days",
    ]
    lines += [f"- {_fmt_day(d)}" for d in last_7]
    lines += ["", "### Next 7 days"]
    lines += [f"- {_fmt_day(d)}" for d in next_7]
    lines += [
        "",
        f"### Last month range: {last_month_start.strftime('%Y-%m-%d')} → {(today - timedelta(days=1)).strftime('%Y-%m-%d')}",
        f"### Next month range: {(today + timedelta(days=1)).strftime('%Y-%m-%d')} → {next_month_end.strftime('%Y-%m-%d')}",
    ]
    return "\n".join(lines)
