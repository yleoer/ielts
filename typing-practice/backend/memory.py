"""Transactional practice queue, review ledger, and FSRS card storage."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from uuid import uuid4

from fsrs import Card, Rating, ReviewLog, State

from srs import SRS, SHANGHAI, answer_candidates, duration, normalize_answer, parse_time, time_text, utc_now
from stats import analyze_error_type

FREE_PRACTICE_LIMIT = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS srs_configs (version TEXT PRIMARY KEY, config_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS word_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_key TEXT UNIQUE NOT NULL,
    card_json TEXT NOT NULL,
    due TEXT NOT NULL,
    state INTEGER NOT NULL,
    stability REAL,
    first_review TEXT NOT NULL,
    last_review TEXT NOT NULL,
    version INTEGER NOT NULL,
    config_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_due ON word_memory(due);
CREATE TABLE IF NOT EXISTS practice_items (
    attempt_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    word_key TEXT NOT NULL,
    word_json TEXT NOT NULL,
    card_version INTEGER NOT NULL,
    issued_at TEXT NOT NULL,
    config_version TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'scheduled'
);
CREATE INDEX IF NOT EXISTS idx_items_issued ON practice_items(issued_at);
CREATE TABLE IF NOT EXISTS word_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id TEXT UNIQUE NOT NULL,
    request_hash TEXT NOT NULL,
    session_id TEXT NOT NULL,
    memory_id INTEGER NOT NULL REFERENCES word_memory(id),
    word_key TEXT NOT NULL,
    word TEXT NOT NULL,
    chinese_meaning TEXT NOT NULL,
    category TEXT NOT NULL,
    user_input TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    error_type TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 4),
    reviewed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    first_input_ms REAL,
    answer_length INTEGER NOT NULL,
    before_json TEXT,
    after_json TEXT NOT NULL,
    config_version TEXT NOT NULL REFERENCES srs_configs(version),
    response_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_time ON word_reviews(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_reviews_word ON word_reviews(word_key, reviewed_at);
CREATE INDEX IF NOT EXISTS idx_reviews_session ON word_reviews(session_id);
"""


class PracticeConflict(ValueError):
    """An expired question or a competing review must not advance this card."""


def pool_by_key(pool: list[dict]) -> dict[str, dict]:
    result = {}
    for word in pool:
        source = word.get("source_id", "").strip()
        if not source:
            raise ValueError(f"词条 {word.get('id')} 缺少 SourceId，请更新 Word Atlas 牌组")
        key = f"word-atlas:{source}"
        if key in result:
            raise ValueError(f"Word Atlas SourceId 重复：{source}")
        result[key] = word
    return result


def forecast_date(card: Card, today: date) -> date:
    return max(today, card.due.astimezone(SHANGHAI).date())


class MemoryStore:
    def __init__(self, stats, config, now=utc_now):
        self.db = stats.db
        self.lock = stats.lock
        self.srs = SRS(config)
        self.now = now
        self.db.executescript(SCHEMA)
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in self.db.execute("PRAGMA table_info(practice_items)")}
            if "mode" not in columns:
                self.db.execute("ALTER TABLE practice_items ADD COLUMN mode TEXT NOT NULL DEFAULT 'scheduled'")
            # Retired tables are removed on cutover and never recreated.
            self.db.execute("DROP TABLE IF EXISTS word_attempts")
            self.db.execute("DROP TABLE IF EXISTS word_mastery")
            self.db.execute("DROP TABLE IF EXISTS practice_sessions")
            self.db.execute("INSERT OR IGNORE INTO schema_migrations VALUES('fsrs-v1',?)", (time_text(self.now()),))
            self.db.execute("INSERT OR IGNORE INTO srs_configs VALUES(?,?)", (self.srs.version, json.dumps(self.srs.snapshot)))

    def _states(self):
        return {row["word_key"]: row for row in self.db.execute("SELECT * FROM word_memory")}

    def _new_today(self, now):
        day = now.astimezone(SHANGHAI).date().isoformat()
        return self.db.execute("SELECT COUNT(*) FROM word_memory WHERE date(first_review,'+8 hours')=?", (day,)).fetchone()[0]

    def _plan(self, pool, now):
        words = pool_by_key(pool)
        states = self._states()
        learning, review, fresh, future = [], [], [], []
        for key, word in words.items():
            row = states.get(key)
            if not row:
                fresh.append(key)
            elif parse_time(row["due"]) <= now:
                (review if row["state"] == int(State.Review) else learning).append(key)
            else:
                future.append(row["due"])
        learning.sort(key=lambda key: (states[key]["due"], key))
        review.sort(key=lambda key: (states[key]["due"], key))
        fresh.sort()
        new_today = self._new_today(now)
        today = now.astimezone(SHANGHAI).date()
        summary = {
            "total": len(words), "due_count": len(learning) + len(review),
            "new_available": len(fresh), "new_today": new_today,
            "next_due": min(future) if future else None,
            "new": len(fresh), "learning": 0, "mastered": 0,
            "due_forecast": [{"date": (today + timedelta(days=offset)).isoformat(), "count": 0}
                             for offset in range(7)],
        }
        for key in words:
            if key in states:
                card = Card.from_json(states[key]["card_json"])
                summary[self.srs.describe(card, now)["status"]] += 1
                # Outstanding overdue cards belong to today, including later today.
                offset = (forecast_date(card, today) - today).days
                if offset < 7:
                    summary["due_forecast"][offset]["count"] += 1
        return words, states, learning + review + fresh, summary

    def summary(self, pool):
        with self.lock:
            return self._plan(pool, self.now())[3]

    def forecast_words(self, pool, day: str):
        try:
            selected = date.fromisoformat(day)
            if selected.isoformat() != day:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("需要 YYYY-MM-DD 格式的复习日期") from exc
        now = self.now()
        today = now.astimezone(SHANGHAI).date()
        if not 0 <= (selected - today).days < 7:
            raise ValueError("请选择未来 7 天内的复习日期，请刷新后重试")
        with self.lock:
            states = self._states()
            result = []
            for key, word in pool_by_key(pool).items():
                row = states.get(key)
                if not row:
                    continue
                card = Card.from_json(row["card_json"])
                if forecast_date(card, today) == selected:
                    result.append({**word, **self.srs.describe(card, now)})
            result.sort(key=lambda item: (item["due"], item["source_id"]))
            return result

    def queue(self, pool, session_id: str, limit=None, mode="scheduled"):
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 100:
            raise ValueError("需要有效的 session_id")
        if mode not in {"scheduled", "free"}:
            raise ValueError("无效练习模式")
        now = self.now()
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            words, states, keys, summary = self._plan(pool, now)
            self.db.execute("DELETE FROM practice_items WHERE issued_at < ?", (time_text(now - timedelta(days=7)),))
            if mode == "free":
                # Free practice samples the whole pool, including cards not yet due.
                import random
                keys = list(words)
                random.SystemRandom().shuffle(keys)
            data = []
            maximum = FREE_PRACTICE_LIMIT if mode == "free" else 100
            default_limit = FREE_PRACTICE_LIMIT if mode == "free" else 1
            item_limit = min(max(limit if limit is not None else default_limit, 1), maximum)
            for key in keys[:item_limit]:
                word = dict(words[key])
                row = states.get(key)
                word["memory"] = self.srs.describe(Card.from_json(row["card_json"]), now) if row else {"status": "new", "is_due": False}
                word["card_version"] = row["version"] if row else 0
                word["attempt_id"] = str(uuid4())
                word["issued_at"] = time_text(now)
                self.db.execute("""INSERT INTO practice_items
                    (attempt_id,session_id,word_key,word_json,card_version,issued_at,config_version,mode)
                    VALUES(?,?,?,?,?,?,?,?)""", (
                    word["attempt_id"], session_id, key, json.dumps(words[key]),
                    word["card_version"], time_text(now), self.srs.version, mode,
                ))
                data.append(word)
            return {"items": data, "summary": summary, "server_time": time_text(now)}

    def submit(self, payload: dict, pool):
        if not isinstance(payload, dict):
            raise ValueError("请求必须是 JSON 对象")
        for name in ("attempt_id", "session_id"):
            if not isinstance(payload.get(name), str) or not 1 <= len(payload[name]) <= 100:
                raise ValueError(f"需要有效的 {name}")
        elapsed = duration(payload.get("duration_ms"))
        first_input = payload.get("first_input_ms")
        if first_input is not None and duration(first_input, "first_input_ms") > elapsed:
            raise ValueError("首次输入时间不能超过总耗时")
        user_input = payload.get("user_input")
        if not isinstance(user_input, str) or len(user_input) > 1000:
            raise ValueError("无效输入")
        reviewed = parse_time(payload.get("reviewed_at"))
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        now = self.now()
        with self.lock, self.db:
            # SQLite serializes even different processes, not just this Python instance.
            self.db.execute("BEGIN IMMEDIATE")
            previous = self.db.execute("SELECT request_hash,response_json FROM word_reviews WHERE attempt_id=?", (payload.get("attempt_id"),)).fetchone()
            if previous:
                if previous["request_hash"] != request_hash:
                    raise PracticeConflict("这道题已保存，不能更改已提交的答案")
                return json.loads(previous["response_json"])
            if pool is None:
                raise RuntimeError("Anki 词库暂不可用，请稍后重试保存")
            item = self.db.execute("SELECT * FROM practice_items WHERE attempt_id=?", (payload.get("attempt_id"),)).fetchone()
            if not item or item["session_id"] != payload.get("session_id"):
                raise PracticeConflict("题目已过期，请重新获取")
            issued = parse_time(item["issued_at"])
            if now - issued > timedelta(days=7):
                raise PracticeConflict("题目已过期，请重新获取")
            if reviewed < issued or reviewed > now + timedelta(seconds=5):
                raise PracticeConflict("作答时间异常，请重新获取题目校准时间")
            if elapsed > (reviewed - issued).total_seconds() * 1000 + 2000:
                raise ValueError("有效耗时不能超过题目展示后的实际时间")
            if item["config_version"] != self.srs.version:
                previous_config = self.db.execute("SELECT config_json FROM srs_configs WHERE version=?", (item["config_version"],)).fetchone()
                previous_rules = json.loads(previous_config[0]) if previous_config else {}
                if any(previous_rules.get(key) != self.srs.snapshot[key]
                       for key in ("rating_version", "easy_seconds", "hard_seconds")):
                    raise PracticeConflict("评分配置已更新，请重新获取题目")
            words = pool_by_key(pool)
            word = words.get(item["word_key"])
            snapshot = json.loads(item["word_json"])
            if not word or any(word[field] != snapshot[field] for field in ("word", "chinese_meaning", "part_of_speech")):
                raise PracticeConflict("词条已更新或移出练习池，请重新获取")
            row = self.db.execute("SELECT * FROM word_memory WHERE word_key=?", (item["word_key"],)).fetchone()
            if (row["version"] if row else 0) != item["card_version"]:
                raise PracticeConflict("这个词已在其他题目中完成复习，请继续下一题")
            if row:
                card = Card.from_json(row["card_json"])
                if reviewed <= card.last_review:
                    raise PracticeConflict("作答时间必须晚于上次复习，请重新获取题目")
                if item["mode"] != "free" and reviewed < card.due:
                    raise PracticeConflict("这个词尚未到期，请重新获取题目")
                if row["config_version"] != self.srs.version:
                    logs = [ReviewLog(row["id"], Rating(log["rating"]), parse_time(log["reviewed_at"]), round(log["duration_ms"]))
                            for log in self.db.execute("SELECT * FROM word_reviews WHERE memory_id=? ORDER BY reviewed_at,id", (row["id"],))]
                    card = self.srs.scheduler.reschedule_card(card, logs)
                before_json = card.to_json()
            else:
                cursor = self.db.execute("""INSERT INTO word_memory(word_key,card_json,due,state,first_review,last_review,version,config_version)
                    VALUES(?, '', ?, 1, ?, ?, 0, ?)""", (item["word_key"], time_text(reviewed), time_text(reviewed), time_text(reviewed), self.srs.version))
                card = Card(card_id=cursor.lastrowid, due=reviewed)
                before_json = None
            correct = bool(normalize_answer(user_input)) and normalize_answer(user_input) in answer_candidates(word["word"])
            error_type = "" if correct else analyze_error_type(word["word"], user_input)
            updated, log = self.srs.review(card, correct, elapsed, reviewed)
            version = item["card_version"] + 1
            self.db.execute("""UPDATE word_memory SET card_json=?,due=?,state=?,stability=?,last_review=?,version=?,config_version=? WHERE id=?""", (
                updated.to_json(), time_text(updated.due), int(updated.state), updated.stability,
                time_text(reviewed), version, self.srs.version, card.card_id,
            ))
            response = {
                "attempt_id": item["attempt_id"], "is_correct": correct, "rating": int(log.rating),
                "rating_name": log.rating.name, "error_type": error_type, "reviewed_at": time_text(reviewed),
                "duration_ms": elapsed, "memory": self.srs.describe(updated, now), "card_version": version,
            }
            self.db.execute("""INSERT INTO word_reviews(attempt_id,request_hash,session_id,memory_id,word_key,word,chinese_meaning,category,user_input,is_correct,error_type,rating,reviewed_at,received_at,duration_ms,first_input_ms,answer_length,before_json,after_json,config_version,response_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                item["attempt_id"], request_hash, item["session_id"], card.card_id, item["word_key"],
                word["word"], word["chinese_meaning"], word["category"], user_input, int(correct), error_type,
                int(log.rating), time_text(reviewed), time_text(now), elapsed, first_input, len(normalize_answer(user_input)),
                before_json, updated.to_json(), self.srs.version, json.dumps(response),
            ))
            return response

    def mastery_words(self, pool, level, limit=200):
        if level not in {"new", "learning", "mastered", "due"}:
            raise ValueError("无效记忆状态")
        with self.lock:
            words, states, _, _ = self._plan(pool, self.now())
            counts = {row["word_key"]: row for row in self.db.execute("""SELECT word_key,COUNT(*) total_attempts,SUM(is_correct) correct_attempts,
                AVG(duration_ms)/1000 average_time FROM word_reviews GROUP BY word_key""")}
            result = []
            for key, word in words.items():
                row = states.get(key)
                memory = self.srs.describe(Card.from_json(row["card_json"]), self.now()) if row else {"status": "new", "is_due": False}
                if not (memory["is_due"] if level == "due" else memory["status"] == level):
                    continue
                values = dict(counts[key]) if key in counts else {"total_attempts": 0, "correct_attempts": 0, "average_time": 0}
                total, correct = values["total_attempts"], values["correct_attempts"]
                result.append({**word, **values, **memory, "accuracy": correct * 100 / total if total else 0, "incorrect_attempts": total - correct})
            result.sort(key=lambda item: (item.get("due", ""), item["source_id"]))
            return result[:min(max(limit, 1), 1000)]
