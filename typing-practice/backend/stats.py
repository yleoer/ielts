"""SQLite-backed practice statistics and Anki sync history."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from srs import SHANGHAI


SCHEMA = """
CREATE TABLE IF NOT EXISTS anki_sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at DATETIME NOT NULL,
    before_words INTEGER NOT NULL,
    after_words INTEGER NOT NULL,
    added_words INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    message TEXT,
    source_path TEXT,
    target_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS anki_sync_added_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id INTEGER NOT NULL,
    word_id INTEGER,
    word TEXT NOT NULL,
    chinese_meaning TEXT,
    category TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sync_id) REFERENCES anki_sync_history(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_anki_sync_history_synced_at ON anki_sync_history(synced_at);
CREATE INDEX IF NOT EXISTS idx_anki_sync_added_words_sync_id ON anki_sync_added_words(sync_id);
"""


def _parse_time(value: Any, default: datetime | None = None) -> datetime | None:
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return default
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _time_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


class StatsStore:
    def __init__(self, path: str):
        self.path = Path(path or "data/stats.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def heatmap(self, start_date: str = "", end_date: str = "") -> list[dict[str, Any]]:
        today = datetime.now(SHANGHAI).date()
        start = start_date or (today - timedelta(days=365)).isoformat()
        end = end_date or today.isoformat()
        date.fromisoformat(start)
        date.fromisoformat(end)
        with self.lock:
            rows = self.db.execute(
                """SELECT date(reviewed_at,'+8 hours') date,COUNT(*) words,AVG(is_correct)*100 accuracy
                   FROM word_reviews WHERE date(reviewed_at,'+8 hours') BETWEEN ? AND ?
                   GROUP BY date ORDER BY date""", (start, end)
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def accuracy_trend(self, days: int = 30) -> list[dict[str, Any]]:
        since = (datetime.now(SHANGHAI).date() - timedelta(days=max(1, min(days, 366)) - 1)).isoformat()
        return [{"date": row["date"], "accuracy": row["accuracy"], "total_words": row["words"]}
                for row in self.heatmap(since)]

    def streak(self) -> dict[str, Any]:
        with self.lock:
            rows = self.db.execute("SELECT DISTINCT date(reviewed_at,'+8 hours') date FROM word_reviews ORDER BY date").fetchall()
        dates = [row["date"] for row in rows]
        values = {date.fromisoformat(item) for item in dates}
        current = 0
        cursor = datetime.now(SHANGHAI).date()
        if cursor not in values:
            cursor -= timedelta(days=1)
        while cursor in values:
            current += 1
            cursor -= timedelta(days=1)
        longest = run = 0
        previous = None
        for item in sorted(values):
            run = run + 1 if previous and item == previous + timedelta(days=1) else 1
            longest = max(longest, run)
            previous = item
        return {"current_streak": current, "longest_streak": longest, "total_days": len(dates), "practice_dates": dates}

    def word_errors(self, source_id: str, before_id: int = 0, limit: int = 50) -> dict[str, Any]:
        source_id = source_id.strip()
        if not source_id:
            raise ValueError("需要有效的 SourceId")
        key = f"word-atlas:{source_id}"
        with self.lock:
            counts = self.db.execute("""SELECT COUNT(*) total_attempts,
                COALESCE(SUM(is_correct),0) correct_attempts FROM word_reviews WHERE word_key=?""", (key,)).fetchone()
            rows = self.db.execute("""SELECT id,word,user_input,reviewed_at
                FROM word_reviews WHERE word_key=? AND is_correct=0 AND (?=0 OR id<?)
                ORDER BY id DESC LIMIT ?""", (key, before_id, before_id, limit + 1)).fetchall()
        items = [_row_dict(row) for row in rows[:limit]]
        return {"items": items,
                "correct_attempts": counts["correct_attempts"], "total_attempts": counts["total_attempts"],
                "next_before_id": items[-1]["id"] if len(rows) > limit else None}

    def overview(self) -> dict[str, Any]:
        with self.lock:
            row = self.db.execute(
                """SELECT COUNT(DISTINCT session_id) total_sessions,COUNT(*) total_words_practiced,
                   COALESCE(AVG(is_correct)*100,0) overall_accuracy,
                   COALESCE(SUM(duration_ms),0)/60000 total_time_minutes FROM word_reviews"""
            ).fetchone()
        return {**_row_dict(row), "current_streak": self.streak()["current_streak"]}

    def save_sync_history(self, status: dict[str, Any]) -> None:
        words = status.get("added_word_list") or []
        if not words or status.get("added_words", 0) <= 0:
            return
        with self.lock, self.db:
            cursor = self.db.execute(
                """INSERT INTO anki_sync_history(synced_at,before_words,after_words,added_words,success,message,source_path,target_path)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (_time_text(_parse_time(status.get("last_sync_at"), datetime.now(timezone.utc))), status.get("before_words", 0), status.get("after_words", 0), status.get("added_words", 0), int(bool(status.get("success"))), status.get("message", ""), status.get("source_path", ""), status.get("target_path", "")),
            )
            for word in words:
                self.db.execute("INSERT INTO anki_sync_added_words(sync_id,word_id,word,chinese_meaning,category) VALUES(?,?,?,?,?)", (cursor.lastrowid, word.get("id"), word.get("word", ""), word.get("chinese_meaning", ""), word.get("category", "")))

    def list_sync_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT id,synced_at,before_words,after_words,added_words,success,COALESCE(message,'') message FROM anki_sync_history ORDER BY synced_at DESC,id DESC LIMIT ?", (min(max(limit, 1), 50),)).fetchall()
            result = []
            for row in rows:
                words = self.db.execute("SELECT COALESCE(word_id,0) id,word,COALESCE(chinese_meaning,'') chinese_meaning,COALESCE(category,'') category FROM anki_sync_added_words WHERE sync_id=? ORDER BY id", (row["id"],)).fetchall()
                result.append({
                    "synced_at": row["synced_at"], "before_words": row["before_words"], "after_words": row["after_words"], "added_words": row["added_words"],
                    "success": bool(row["success"]), "message": row["message"], "added_word_list": [_row_dict(word) for word in words],
                })
        return result

