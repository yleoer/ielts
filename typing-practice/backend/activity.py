"""Shared Beijing calendar boundaries for activity and scheduled reviews."""

from datetime import date, timedelta
from sqlite3 import Connection


def month_start(today: date, offset: int = 0) -> date:
    index = today.year * 12 + today.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def calendar_window(today: date) -> tuple[date, date]:
    return month_start(today, -6), month_start(today, 6) - timedelta(days=1)


def calendar_day(value: str, today: date) -> date:
    try:
        selected = date.fromisoformat(value)
        if selected.isoformat() != value:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValueError("需要 YYYY-MM-DD 格式的日期") from exc
    start, end = calendar_window(today)
    if not start <= selected <= end:
        raise ValueError("请选择学习日历范围内的日期，请刷新后重试")
    return selected


def daily_activity(db: Connection, start: date, end: date) -> list[dict]:
    """The shared read-only daily totals for the calendar and monthly chart."""
    return [dict(row) for row in db.execute("""SELECT date(reviewed_at,'+8 hours') date,
        COUNT(DISTINCT word_key) practiced,COUNT(*) attempts,AVG(is_correct)*100 accuracy
        FROM word_reviews WHERE date(reviewed_at,'+8 hours') BETWEEN ? AND ?
        GROUP BY date ORDER BY date""", (start.isoformat(), end.isoformat()))]
