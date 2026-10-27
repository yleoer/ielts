"""SQLite-backed practice statistics and Anki sync history."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS practice_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    user_id TEXT DEFAULT 'default',
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    total_words INTEGER NOT NULL,
    correct_words INTEGER NOT NULL,
    incorrect_words INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    duration_seconds INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS word_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    word TEXT NOT NULL,
    chinese_meaning TEXT,
    category TEXT,
    user_input TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    time_spent REAL,
    error_type TEXT,
    attempt_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES practice_sessions(session_id)
);
CREATE TABLE IF NOT EXISTS word_mastery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE NOT NULL,
    total_attempts INTEGER DEFAULT 0,
    correct_attempts INTEGER DEFAULT 0,
    incorrect_attempts INTEGER DEFAULT 0,
    mastery_level TEXT DEFAULT 'new',
    last_attempt_time DATETIME,
    average_time REAL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
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
CREATE INDEX IF NOT EXISTS idx_session_start_time ON practice_sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_session_id ON word_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_word ON word_attempts(word);
CREATE INDEX IF NOT EXISTS idx_attempt_time ON word_attempts(attempt_time);
CREATE INDEX IF NOT EXISTS idx_word_category ON word_attempts(category);
CREATE INDEX IF NOT EXISTS idx_mastery_level ON word_mastery(mastery_level);
CREATE INDEX IF NOT EXISTS idx_mastery_word ON word_mastery(word);
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


def analyze_error_type(expected: str, user_input: str) -> str:
    input_value = (user_input or "").strip().lower()
    if not input_value:
        return "skipped"
    expected_value = (expected or "").strip().lower()
    if expected_value == input_value:
        return ""
    distance = levenshtein_distance(expected_value, input_value)
    if distance == 1:
        if len(input_value) < len(expected_value):
            return "missing_letter"
        if len(input_value) > len(expected_value):
            return "extra_letter"
        return "spelling"
    return "spelling" if distance <= 3 else "completely_wrong"


def levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, 1):
        current = [index]
        for right_index, right_char in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[right_index] + 1, previous[right_index - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def calculate_mastery_level(total: int, correct: int, incorrect: int) -> str:
    if total == 0:
        return "new"
    if incorrect > correct:
        return "weak"
    if correct >= 6:
        return "mastered"
    if correct >= 3:
        return "familiar"
    if correct >= 1:
        return "learning"
    return "weak"


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

    def save_session(self, payload: dict[str, Any]) -> None:
        session_id = str(payload.get("session_id", "")).strip()
        total = int(payload.get("total_words", 0) or 0)
        correct = int(payload.get("correct_words", 0) or 0)
        incorrect = int(payload.get("incorrect_words", 0) or 0)
        start = _parse_time(payload.get("start_time"))
        end = _parse_time(payload.get("end_time"))
        accuracy = float(payload.get("accuracy", 0) or 0)
        duration = int(payload.get("duration_seconds", 0) or 0)
        if not session_id:
            raise ValueError("session_id is required")
        if total <= 0:
            raise ValueError("total_words must be positive")
        if correct < 0 or incorrect < 0 or correct + incorrect != total:
            raise ValueError("correct_words + incorrect_words must equal total_words")
        if start is None:
            raise ValueError("start_time is required")
        if end and end < start:
            raise ValueError("end_time must be after start_time")
        if not 0 <= accuracy <= 100:
            raise ValueError("accuracy must be between 0 and 100")
        if duration < 0:
            raise ValueError("duration_seconds must be non-negative")
        if accuracy == 0 and total:
            accuracy = correct * 100 / total

        attempts = payload.get("word_attempts") or []
        start_text = _time_text(start)
        end_text = _time_text(end)
        with self.lock, self.db:
            self.db.execute(
                """
                INSERT INTO practice_sessions(session_id,user_id,start_time,end_time,total_words,correct_words,incorrect_words,accuracy,duration_seconds)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                  user_id=excluded.user_id,start_time=excluded.start_time,end_time=excluded.end_time,
                  total_words=excluded.total_words,correct_words=excluded.correct_words,
                  incorrect_words=excluded.incorrect_words,accuracy=excluded.accuracy,
                  duration_seconds=excluded.duration_seconds
                """,
                (session_id, str(payload.get("user_id") or "default"), start_text, end_text, total, correct, incorrect, accuracy, duration),
            )
            self.db.execute("DELETE FROM word_attempts WHERE session_id = ?", (session_id,))
            for attempt in attempts:
                word = str(attempt.get("word", "")).strip()
                if not word:
                    continue
                is_correct = bool(attempt.get("is_correct", False))
                error_type = str(attempt.get("error_type") or "").strip()
                if not is_correct and not error_type:
                    error_type = analyze_error_type(word, str(attempt.get("user_input") or ""))
                self.db.execute(
                    """
                    INSERT INTO word_attempts(session_id,word,chinese_meaning,category,user_input,is_correct,time_spent,error_type,attempt_time)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        session_id, word, str(attempt.get("chinese_meaning") or "").strip(), str(attempt.get("category") or "").strip(),
                        str(attempt.get("user_input") or ""), int(is_correct), attempt.get("time_spent"), error_type, start_text,
                    ),
                )
            self._rebuild_mastery()

    def _rebuild_mastery(self) -> None:
        self.db.execute("DELETE FROM word_mastery")
        rows = self.db.execute(
            """
            SELECT word,COUNT(*) total_attempts,
                   SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) correct_attempts,
                   SUM(CASE WHEN is_correct=0 THEN 1 ELSE 0 END) incorrect_attempts,
                   COALESCE(AVG(time_spent),0) average_time,MAX(attempt_time) last_attempt_time
            FROM word_attempts GROUP BY word
            """
        ).fetchall()
        for row in rows:
            self.db.execute(
                """INSERT INTO word_mastery(word,total_attempts,correct_attempts,incorrect_attempts,mastery_level,last_attempt_time,average_time)
                   VALUES(?,?,?,?,?,?,?)""",
                (row["word"], row["total_attempts"], row["correct_attempts"], row["incorrect_attempts"], calculate_mastery_level(row["total_attempts"], row["correct_attempts"], row["incorrect_attempts"]), row["last_attempt_time"], row["average_time"]),
            )

    def selection_stats(self) -> dict[str, dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                """
                WITH latest AS (
                  SELECT word,is_correct,attempt_time,ROW_NUMBER() OVER(PARTITION BY word ORDER BY attempt_time DESC,id DESC) row_number
                  FROM word_attempts
                )
                SELECT wm.word,wm.total_attempts,wm.correct_attempts,wm.incorrect_attempts,wm.mastery_level,
                       COALESCE(wm.average_time,0) average_time,COALESCE(wm.last_attempt_time,'') last_attempt_time,
                       COALESCE(latest.is_correct,1) last_attempt_correct
                FROM word_mastery wm LEFT JOIN latest ON latest.word=wm.word AND latest.row_number=1
                """
            ).fetchall()
        return {
            row["word"]: {
                "word": row["word"], "total_attempts": row["total_attempts"], "correct_attempts": row["correct_attempts"],
                "incorrect_attempts": row["incorrect_attempts"], "mastery_level": row["mastery_level"], "average_time": row["average_time"],
                "last_attempt_time": row["last_attempt_time"], "last_attempt_correct": bool(row["last_attempt_correct"]),
            }
            for row in rows
        }

    def heatmap(self, start_date: str = "", end_date: str = "") -> list[dict[str, Any]]:
        today = date.today()
        start_date = start_date or (today - timedelta(days=365)).isoformat()
        end_date = end_date or today.isoformat()
        with self.lock:
            rows = self.db.execute(
                """SELECT date(start_time,'localtime') date,
                          COALESCE(SUM(total_words),0) words,
                          COALESCE(SUM(correct_words)*100.0/NULLIF(SUM(total_words),0),0) accuracy
                   FROM practice_sessions WHERE date(start_time,'localtime') BETWEEN ? AND ?
                   GROUP BY date(start_time,'localtime') ORDER BY date""", (start_date, end_date)
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def accuracy_trend(self, days: int = 30) -> list[dict[str, Any]]:
        since = (date.today() - timedelta(days=max(days, 1))).isoformat()
        with self.lock:
            rows = self.db.execute(
                """SELECT date(start_time,'localtime') date,COALESCE(SUM(correct_words)*100.0/NULLIF(SUM(total_words),0),0) accuracy,COALESCE(SUM(total_words),0) total_words
                   FROM practice_sessions WHERE date(start_time,'localtime') >= date(?) GROUP BY date ORDER BY date""", (since,)
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def mastery_distribution(self) -> dict[str, int]:
        data = {"mastered": 0, "familiar": 0, "learning": 0, "weak": 0, "new": 0}
        with self.lock:
            rows = self.db.execute("SELECT mastery_level,COUNT(*) count FROM word_mastery GROUP BY mastery_level").fetchall()
        for row in rows:
            data[row["mastery_level"]] = row["count"]
        return data

    def mastery_words(self, level: str, limit: int = 200) -> list[dict[str, Any]]:
        limit = min(max(limit or 200, 1), 1000)
        with self.lock:
            rows = self.db.execute(
                """
                WITH latest_meaning AS (
                  SELECT word,chinese_meaning,ROW_NUMBER() OVER(PARTITION BY word ORDER BY attempt_time DESC,id DESC) row_number
                  FROM word_attempts WHERE COALESCE(chinese_meaning,'') <> ''
                )
                SELECT wm.word,COALESCE(lm.chinese_meaning,'') chinese_meaning,wm.total_attempts,wm.correct_attempts,
                       wm.incorrect_attempts,COALESCE(wm.correct_attempts*100.0/NULLIF(wm.total_attempts,0),0) accuracy,
                       COALESCE(wm.average_time,0) average_time
                FROM word_mastery wm LEFT JOIN latest_meaning lm ON lm.word=wm.word AND lm.row_number=1
                WHERE wm.mastery_level=? ORDER BY wm.incorrect_attempts DESC,wm.total_attempts DESC,wm.word ASC LIMIT ?
                """, (level, limit)
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def streak(self) -> dict[str, Any]:
        with self.lock:
            rows = self.db.execute("SELECT DISTINCT date(start_time,'localtime') date FROM practice_sessions ORDER BY date").fetchall()
        dates = [row["date"] for row in rows]
        values = {date.fromisoformat(item) for item in dates}
        current = 0
        cursor = date.today()
        while cursor in values:
            current += 1
            cursor -= timedelta(days=1)
        longest = 0
        run = 0
        previous = None
        for item in sorted(values):
            run = run + 1 if previous and item == previous + timedelta(days=1) else 1
            longest = max(longest, run)
            previous = item
        return {"current_streak": current, "longest_streak": longest, "total_days": len(dates), "practice_dates": dates}

    def error_types(self) -> dict[str, int]:
        data = {"spelling": 0, "missing_letter": 0, "extra_letter": 0, "completely_wrong": 0, "skipped": 0}
        with self.lock:
            rows = self.db.execute("SELECT COALESCE(NULLIF(error_type,''),'spelling') type_name,COUNT(*) count FROM word_attempts WHERE is_correct=0 GROUP BY type_name").fetchall()
        for row in rows:
            data[row["type_name"]] = row["count"]
        return data

    def error_type_words(self, error_type: str, limit: int = 200) -> list[dict[str, Any]]:
        limit = min(max(limit or 200, 1), 1000)
        with self.lock:
            rows = self.db.execute(
                """
                WITH filtered AS (
                  SELECT id,word,chinese_meaning,category,user_input,attempt_time FROM word_attempts
                  WHERE is_correct=0 AND COALESCE(NULLIF(error_type,''),'spelling')=?
                ), ranked AS (
                  SELECT word,chinese_meaning,category,user_input,attempt_time,COUNT(*) OVER(PARTITION BY word) error_count,
                         ROW_NUMBER() OVER(PARTITION BY word ORDER BY attempt_time DESC,id DESC) row_number FROM filtered
                )
                SELECT word,COALESCE(chinese_meaning,'') chinese_meaning,COALESCE(category,'') category,
                       COALESCE(user_input,'') user_input,error_count,COALESCE(attempt_time,'') last_attempt_at
                FROM ranked WHERE row_number=1 ORDER BY error_count DESC,last_attempt_at DESC,word ASC LIMIT ?
                """, (error_type, limit)
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def overview(self) -> dict[str, Any]:
        with self.lock:
            row = self.db.execute(
                """SELECT COUNT(*) total_sessions,COALESCE(SUM(total_words),0) total_words_practiced,
                          COALESCE(SUM(correct_words)*100.0/NULLIF(SUM(total_words),0),0) overall_accuracy,
                          COALESCE(SUM(duration_seconds),0)/60.0 total_time_minutes FROM practice_sessions"""
            ).fetchone()
            mastered = self.db.execute("SELECT COUNT(*) FROM word_mastery WHERE mastery_level='mastered'").fetchone()[0]
            weak = self.db.execute("SELECT COUNT(*) FROM word_mastery WHERE mastery_level='weak'").fetchone()[0]
        return {
            "total_sessions": row["total_sessions"], "total_words_practiced": row["total_words_practiced"],
            "overall_accuracy": row["overall_accuracy"], "total_time_minutes": row["total_time_minutes"],
            "current_streak": self.streak()["current_streak"], "mastered_words": mastered, "weak_words": weak,
        }

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

