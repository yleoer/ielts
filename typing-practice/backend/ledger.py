"""Append-only answer log shared by desktop clients.

The server never schedules cards: each client replays the log with FSRS.
Rows are deduplicated by ``attempt_id`` and paged by the server row id, which
serves as the sync cursor.
"""

from __future__ import annotations

import math
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PAGE_SIZE = 500
MAX_UPLOAD = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id TEXT UNIQUE NOT NULL,
    device_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    word_key TEXT NOT NULL,
    word TEXT NOT NULL,
    chinese_meaning TEXT NOT NULL,
    category TEXT NOT NULL,
    user_input TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 4),
    reviewed_at TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    first_input_ms REAL
);
CREATE INDEX IF NOT EXISTS idx_attempts_word ON attempts(word_key, reviewed_at);
CREATE TABLE IF NOT EXISTS ledger_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL, detail TEXT NOT NULL);
"""

# Columns returned to clients, in order.
FIELDS = ("attempt_id", "word_key", "word", "chinese_meaning", "category", "user_input",
          "is_correct", "rating", "reviewed_at", "duration_ms", "first_input_ms")


def time_text(value: datetime) -> str:
    """UTC with microseconds, the format every client stores (`2026-01-01T00:00:00.000000Z`)."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _text(item: dict, name: str, maximum: int, minimum: int = 0) -> str:
    value = item.get(name)
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError(f"需要有效的 {name}")
    return value


def _number(item: dict, name: str, optional: bool = False) -> float | None:
    value = item.get(name)
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} 必须是非负有限数值")
    return float(value)


def validate_attempt(item: Any) -> tuple:
    if not isinstance(item, dict):
        raise ValueError("作答必须是 JSON 对象")
    word_key = _text(item, "word_key", 200, 1)
    if not word_key.startswith("word-atlas:") or word_key == "word-atlas:":
        raise ValueError("需要有效的 word_key")
    if not isinstance(item.get("is_correct"), bool):
        raise ValueError("需要有效的 is_correct")
    rating = item.get("rating")
    if isinstance(rating, bool) or rating not in (1, 2, 3, 4):
        raise ValueError("需要有效的 rating")
    try:
        reviewed = datetime.fromisoformat(_text(item, "reviewed_at", 64, 1).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("需要有效的 reviewed_at") from None
    if reviewed.tzinfo is None:
        raise ValueError("reviewed_at 必须包含时区")
    return (
        _text(item, "attempt_id", 100, 1), word_key, _text(item, "word", 1000),
        _text(item, "chinese_meaning", 1000), _text(item, "category", 1000), _text(item, "user_input", 1000),
        int(item["is_correct"]), rating, time_text(reviewed),
        _number(item, "duration_ms"), _number(item, "first_input_ms", optional=True),
    )


class Ledger:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.import_web_history()

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def import_web_history(self) -> None:
        """Once, copy answers saved by the retired web app (`word_reviews`) into the log."""
        with self.lock, self.db:
            if self.db.execute("SELECT 1 FROM ledger_migrations WHERE name='web-history-v1'").fetchone():
                return
            imported = 0
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='word_reviews'").fetchone():
                imported = self.db.execute("""INSERT OR IGNORE INTO attempts
                    (attempt_id,device_id,received_at,word_key,word,chinese_meaning,category,user_input,
                     is_correct,rating,reviewed_at,duration_ms,first_input_ms)
                    SELECT attempt_id,'web',received_at,word_key,word,chinese_meaning,category,user_input,
                     is_correct,rating,reviewed_at,duration_ms,first_input_ms
                    FROM word_reviews ORDER BY reviewed_at,id""").rowcount
            self.db.execute("INSERT INTO ledger_migrations VALUES('web-history-v1',?,?)",
                            (time_text(datetime.now(timezone.utc)), f"imported {imported} answers"))

    def sync(self, payload: Any) -> dict[str, Any]:
        """Stores uploaded answers, then returns the log after the client's cursor."""
        if not isinstance(payload, dict):
            raise ValueError("请求必须是 JSON 对象")
        device_id = _text(payload, "device_id", 100, 1)
        cursor = payload.get("cursor", 0)
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
            raise ValueError("无效的同步游标")
        uploads = payload.get("attempts", [])
        if not isinstance(uploads, list) or len(uploads) > MAX_UPLOAD:
            raise ValueError(f"每次最多上传 {MAX_UPLOAD} 条作答")
        rows = []
        for index, item in enumerate(uploads):
            try:
                rows.append(validate_attempt(item))
            except ValueError as exc:
                raise ValueError(f"第 {index + 1} 条作答无效：{exc}") from None
        received = time_text(datetime.now(timezone.utc))
        with self.lock, self.db:
            accepted = 0
            for row in rows:
                # The first copy of an attempt wins; replays and retries are ignored.
                accepted += self.db.execute("""INSERT OR IGNORE INTO attempts
                    (attempt_id,word_key,word,chinese_meaning,category,user_input,is_correct,rating,
                     reviewed_at,duration_ms,first_input_ms,device_id,received_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (*row, device_id, received)).rowcount
            page = self.db.execute(f"SELECT id,{','.join(FIELDS)} FROM attempts WHERE id > ? ORDER BY id LIMIT ?",
                                   (cursor, PAGE_SIZE + 1)).fetchall()
        more = len(page) > PAGE_SIZE
        page = page[:PAGE_SIZE]
        attempts = [{**{name: row[name] for name in FIELDS}, "is_correct": bool(row["is_correct"])} for row in page]
        return {"accepted": accepted, "duplicates": len(rows) - accepted, "attempts": attempts,
                "next_cursor": page[-1]["id"] if page else cursor, "more": more}
