from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fsrs import Card, Rating, State

from memory import MemoryStore, PracticeConflict
from srs import MemoryConfig, SRS, time_text
from stats import StatsStore


def word(source="apple", note_id=1):
    return {"id": note_id, "source_id": source, "word": source, "chinese_meaning": "释义",
            "category": "测试", "part_of_speech": "n.", "illustration_url": ""}


class RatingTest(unittest.TestCase):
    def test_boundaries_and_error_precedence(self):
        srs = SRS(MemoryConfig(enable_fuzzing=False))
        for elapsed, expected in [(0, Rating.Easy), (5999.9, Rating.Easy), (6000, Rating.Good),
                                  (20000, Rating.Good), (20000.1, Rating.Hard)]:
            with self.subTest(elapsed=elapsed):
                self.assertEqual(srs.grade(True, elapsed), expected)
                self.assertEqual(srs.grade(False, elapsed), Rating.Again)

    def test_invalid_duration_and_config(self):
        srs = SRS(MemoryConfig())
        for value in (None, "6", True, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                srs.grade(True, value)
        for config in (MemoryConfig(easy_seconds=20), MemoryConfig(desired_retention=1)):
            with self.assertRaises(ValueError):
                SRS(config)


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "stats.db"
        self.stats = StatsStore(str(self.path))
        self.addCleanup(self.stats.close)
        self.now = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)
        self.memory = MemoryStore(self.stats, MemoryConfig(enable_fuzzing=False), lambda: self.now)
        self.pool = [word()]

    def question(self, session="test", pool=None):
        return self.memory.queue(pool or self.pool, session)["items"][0]

    def payload(self, question, value="apple", elapsed=7000, session="test"):
        self.now += timedelta(milliseconds=elapsed)
        return {"attempt_id": question["attempt_id"], "session_id": session, "user_input": value,
                "duration_ms": elapsed, "first_input_ms": min(200, elapsed), "reviewed_at": time_text(self.now)}

    def test_actual_fsrs_learning_relearning_and_mastery(self):
        answer = self.memory.submit(self.payload(self.question()), self.pool)
        self.assertEqual(answer["rating"], 3)
        self.assertEqual(parse_due(answer) - self.now, timedelta(minutes=10))
        self.assertEqual(self.memory.summary(self.pool)["due_count"], 0)
        self.now = parse_due(answer)
        answer = self.memory.submit(self.payload(self.question()), self.pool)
        self.assertEqual(answer["memory"]["state"], int(State.Review))
        for _ in range(12):
            if answer["memory"]["status"] == "mastered":
                break
            self.now = parse_due(answer)
            answer = self.memory.submit(self.payload(self.question()), self.pool)
        self.assertEqual(answer["memory"]["status"], "mastered")
        self.now = parse_due(answer)
        answer = self.memory.submit(self.payload(self.question(), "wrong"), self.pool)
        self.assertEqual(answer["memory"]["state"], int(State.Relearning))
        self.assertEqual(answer["memory"]["status"], "learning")
        self.assertEqual(parse_due(answer) - self.now, timedelta(minutes=10))

    def test_again_repeats_in_same_session_only_when_due(self):
        response = self.memory.submit(self.payload(self.question(), ""), self.pool)
        self.assertEqual(response["rating"], 1)
        self.assertEqual(response["error_type"], "skipped")
        self.now = parse_due(response) - timedelta(microseconds=1)
        self.assertEqual(self.memory.queue(self.pool, "test")["items"], [])
        self.now += timedelta(microseconds=1)
        next_question = self.question()
        self.assertNotEqual(next_question["attempt_id"], response["attempt_id"])
        self.memory.submit(self.payload(next_question), self.pool)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 2)

    def test_retry_exactly_once_even_after_word_disappears(self):
        payload = self.payload(self.question())
        original = self.memory.submit(payload, self.pool)
        self.assertEqual(self.memory.submit(payload, None), original)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 1)
        self.assertEqual(self.stats.overview()["total_time_minutes"], 7000 / 60000)
        with self.assertRaises(PracticeConflict):
            self.memory.submit({**payload, "user_input": "wrong"}, self.pool)

    def test_two_tabs_conflict(self):
        first, second = self.question(), self.question(session="other")
        self.memory.submit(self.payload(first), self.pool)
        with self.assertRaises(PracticeConflict):
            self.memory.submit(self.payload(second, session="other"), self.pool)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 1)

    def test_separate_connections_serialize_racing_submissions(self):
        q1, q2 = self.question(), self.question(session="other")
        p1, p2 = self.payload(q1), self.payload(q2, session="other")
        second_stats = StatsStore(str(self.path))
        self.addCleanup(second_stats.close)
        second_memory = MemoryStore(second_stats, MemoryConfig(enable_fuzzing=False), lambda: self.now)
        def submit(store, payload):
            try:
                store.submit(payload, self.pool)
                return "saved"
            except PracticeConflict:
                return "conflict"
        with ThreadPoolExecutor(2) as executor:
            futures = [executor.submit(submit, self.memory, p1), executor.submit(submit, second_memory, p2)]
            self.assertCountEqual([future.result() for future in futures], ["saved", "conflict"])

    def test_transaction_rolls_back_card_when_ledger_write_fails(self):
        payload = self.payload(self.question())
        self.stats.db.execute("CREATE TRIGGER fail_review BEFORE INSERT ON word_reviews BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.memory.submit(payload, self.pool)
        self.assertEqual(self.stats.db.execute("SELECT COUNT(*) FROM word_memory").fetchone()[0], 0)
        self.stats.db.execute("DROP TRIGGER fail_review")
        self.memory.submit(payload, self.pool)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 1)

    def test_free_practice_creates_a_ticket_and_records_memory_and_history(self):
        response = self.memory.queue(self.pool, "free", mode="free")
        question = response["items"][0]
        self.assertIn("attempt_id", question)
        self.assertEqual(self.stats.db.execute("SELECT mode FROM practice_items").fetchone()[0], "free")
        self.assertEqual(self.memory.summary(self.pool)["new_today"], 0)
        payload = self.payload(question, session="free")
        result = self.memory.submit(payload, self.pool)
        self.assertEqual(result["rating"], 3)
        self.assertEqual(self.memory.submit(payload, self.pool), result)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 1)
        self.assertEqual(self.memory.summary(self.pool)["new_today"], 1)

    def test_free_practice_reviews_a_card_before_due(self):
        original = self.memory.submit(self.payload(self.question()), self.pool)
        question = self.memory.queue(self.pool, "free", mode="free")["items"][0]
        self.assertFalse(question["memory"]["is_due"])
        result = self.memory.submit(self.payload(question, "wrong", session="free"), self.pool)
        self.assertLess(self.now, parse_due(original))
        self.assertEqual(result["rating"], 1)
        self.assertEqual(result["card_version"], 2)
        self.assertEqual(parse_due(result), self.now + timedelta(minutes=1))
        self.assertEqual(self.stats.overview()["total_words_practiced"], 2)

    def test_submitted_mode_cannot_override_the_ticket_due_check(self):
        self.memory.submit(self.payload(self.question()), self.pool)
        question = self.memory.queue(self.pool, "early", mode="free")["items"][0]
        with self.stats.db:
            self.stats.db.execute("UPDATE practice_items SET mode='scheduled' WHERE attempt_id=?", (question["attempt_id"],))
        payload = {**self.payload(question, session="early"), "mode": "free"}
        with self.assertRaises(PracticeConflict):
            self.memory.submit(payload, self.pool)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 1)

    def test_free_practice_still_checks_competing_card_versions(self):
        first = self.memory.queue(self.pool, "first", mode="free")["items"][0]
        second = self.memory.queue(self.pool, "second", mode="free")["items"][0]
        self.memory.submit(self.payload(first, session="first"), self.pool)
        with self.assertRaises(PracticeConflict):
            self.memory.submit(self.payload(second, session="second"), self.pool)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 1)

    def test_free_practice_caps_the_sample_and_uses_all_of_a_small_pool(self):
        self.pool = [word(f"word-{index}", index) for index in range(25)]
        for limit, expected in ((None, 20), (1000, 20), (3, 3)):
            with self.subTest(limit=limit):
                items = self.memory.queue(self.pool, "sample", limit=limit, mode="free")["items"]
                self.assertEqual(len(items), expected)
                self.assertEqual(len({item["source_id"] for item in items}), expected)
        self.assertEqual(len(self.memory.queue(self.pool[:3], "small", mode="free")["items"]), 3)

    def test_legacy_tickets_keep_their_scheduled_mode_after_migration(self):
        question = self.question()
        with self.stats.db:
            self.stats.db.execute("ALTER TABLE practice_items DROP COLUMN mode")
        migrated = MemoryStore(self.stats, MemoryConfig(enable_fuzzing=False), lambda: self.now)
        self.assertEqual(self.stats.db.execute("SELECT mode FROM practice_items").fetchone()[0], "scheduled")
        migrated.submit(self.payload(question), self.pool)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 1)

    def test_source_id_survives_reimport_and_missing_source_is_rejected(self):
        payload = self.payload(self.question())
        self.pool[0]["id"] = 987
        self.memory.submit(payload, self.pool)
        self.assertEqual(self.memory.summary(self.pool)["new"], 0)
        with self.assertRaises(ValueError):
            self.memory.summary([word(), word(note_id=20)])
        with self.assertRaises(ValueError):
            self.memory.summary([{**word(), "source_id": ""}])
        self.assertEqual(self.memory.summary([])["total"], 0)
        self.assertEqual(self.memory.summary(self.pool)["learning"], 1)

    def test_daily_new_count_and_shanghai_midnight(self):
        self.pool += [word("book", 2)]
        self.now = datetime(2026, 10, 29, 15, 59, 40, tzinfo=timezone.utc)
        self.memory.submit(self.payload(self.question(), elapsed=1000), self.pool)
        self.assertEqual(self.memory.summary(self.pool)["new_today"], 1)
        self.assertEqual(self.memory.summary(self.pool)["new_available"], 1)
        self.now = datetime(2026, 10, 29, 16, tzinfo=timezone.utc)
        self.assertEqual(self.memory.summary(self.pool)["new_today"], 0)
        self.assertEqual(self.memory.summary(self.pool)["new_available"], 1)
        self.memory.submit(self.payload(self.question(), "book", 1000), self.pool)
        rows = self.stats.heatmap("2026-10-29", "2026-10-30")
        self.assertEqual([(row["date"], row["words"]) for row in rows], [("2026-10-29", 1), ("2026-10-30", 1)])

    def test_outstanding_new_questions_can_both_be_submitted(self):
        a = self.question()
        b = self.question(pool=[word("book", 2)])
        self.pool += [word("book", 2)]
        self.memory.submit(self.payload(a), self.pool)
        self.memory.submit(self.payload(b, "book"), self.pool)
        self.assertEqual(self.memory.summary(self.pool)["new_today"], 2)

    def test_server_checks_answers_variants_and_whitespace(self):
        self.pool[0]["word"] = "colour / color"
        result = self.memory.submit(self.payload(self.question(), " COLOR ", 5999), self.pool)
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["rating"], 4)
        self.assertEqual(result["memory"]["state"], int(State.Review))

    def test_due_learning_precedes_review_then_new(self):
        self.pool = [word("apple"), word("book", 2), word("cat", 3)]
        apple = self.question(pool=[self.pool[0]])
        self.memory.submit(self.payload(apple, "apple", 1000), self.pool)
        book = self.question(pool=[self.pool[1]])
        self.memory.submit(self.payload(book, "wrong", 1000), self.pool)
        self.now += timedelta(days=30)
        items = self.memory.queue(self.pool, "next", limit=3)["items"]
        self.assertEqual([item["source_id"] for item in items], ["book", "apple", "cat"])

    def test_seven_day_forecast_counts_current_pool_at_shanghai_midnight(self):
        self.now = datetime(2026, 10, 29, 15, 59, tzinfo=timezone.utc)
        schedule = [
            ("overdue", datetime(2026, 10, 27, 10, tzinfo=timezone.utc), State.Learning),
            ("today", datetime(2026, 10, 29, 15, 59, 59, 999999, tzinfo=timezone.utc), State.Relearning),
            ("tomorrow", datetime(2026, 10, 29, 16, tzinfo=timezone.utc), State.Review),
            ("last-day", datetime(2026, 11, 4, 15, 59, 59, tzinfo=timezone.utc), State.Review),
            ("outside", datetime(2026, 11, 4, 16, tzinfo=timezone.utc), State.Review),
            ("removed", datetime(2026, 10, 30, 10, tzinfo=timezone.utc), State.Review),
        ]
        self.pool = [word("fresh", 100)]
        with self.stats.db:
            for index, (source, due, state) in enumerate(schedule, 1):
                card = Card(card_id=index, due=due, state=state, stability=25, difficulty=5)
                self.stats.db.execute("""INSERT INTO word_memory
                    (word_key,card_json,due,state,stability,first_review,last_review,version,config_version)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (
                        f"word-atlas:{source}", card.to_json(), time_text(due), int(state), card.stability,
                        time_text(self.now - timedelta(days=30)), time_text(self.now - timedelta(days=1)),
                        1, self.memory.srs.version,
                    ))
                if source != "removed":
                    self.pool.append(word(source, index))
        forecast = self.memory.summary(self.pool)["due_forecast"]
        self.assertEqual([day["date"] for day in forecast], [
            "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01",
            "2026-11-02", "2026-11-03", "2026-11-04",
        ])
        self.assertEqual([day["count"] for day in forecast], [2, 1, 0, 0, 0, 0, 1])
        for day in forecast:
            items = self.memory.forecast_words(self.pool, day["date"])
            self.assertEqual(len(items), day["count"])
        today_words = self.memory.forecast_words(self.pool, "2026-10-29")
        self.assertEqual([item["source_id"] for item in today_words], ["overdue", "today"])
        self.assertTrue(today_words[0]["is_due"])
        self.assertFalse(today_words[1]["is_due"])
        self.assertEqual([item["source_id"] for item in self.memory.forecast_words(self.pool, "2026-10-30")], ["tomorrow"])
        self.now = datetime(2026, 10, 29, 16, tzinfo=timezone.utc)
        forecast = self.memory.summary(self.pool)["due_forecast"]
        self.assertEqual(forecast[0]["date"], "2026-10-30")
        self.assertEqual(forecast[-1]["date"], "2026-11-05")
        self.assertEqual([day["count"] for day in forecast], [3, 0, 0, 0, 0, 1, 1])
        self.assertEqual([item["source_id"] for item in self.memory.forecast_words(self.pool, "2026-10-30")], ["overdue", "today", "tomorrow"])
        self.assertEqual([item["source_id"] for item in self.memory.forecast_words(self.pool, "2026-11-05")], ["outside"])
        self.assertEqual(self.stats.db.execute("SELECT COUNT(*) FROM word_reviews").fetchone()[0], 0)

    def test_empty_forecast_keeps_seven_dates_across_year_boundary(self):
        self.now = datetime(2026, 12, 31, 16, tzinfo=timezone.utc)
        for pool in ([], self.pool):
            with self.subTest(pool=pool):
                forecast = self.memory.summary(pool)["due_forecast"]
                self.assertEqual(len(forecast), 7)
                self.assertEqual(forecast[0], {"date": "2027-01-01", "count": 0})
                self.assertEqual(forecast[-1], {"date": "2027-01-07", "count": 0})
                self.assertEqual(sum(day["count"] for day in forecast), 0)
                self.assertEqual(self.memory.forecast_words(pool, forecast[0]["date"]), [])

    def test_forecast_detail_rejects_invalid_or_expired_dates(self):
        for value in (None, "", "20261029", "2026-02-30", "2026-10-28", "2026-11-05"):
            with self.subTest(date=value), self.assertRaises(ValueError):
                self.memory.forecast_words(self.pool, value)

    def test_parameter_change_keeps_due_and_replays_on_next_review(self):
        result = self.memory.submit(self.payload(self.question()), self.pool)
        before = self.stats.db.execute("SELECT * FROM word_memory").fetchone()
        changed = MemoryStore(self.stats, MemoryConfig(desired_retention=0.85, enable_fuzzing=False), lambda: self.now)
        unchanged = self.stats.db.execute("SELECT * FROM word_memory").fetchone()
        self.assertEqual(unchanged["due"], before["due"])
        self.assertNotEqual(before["config_version"], changed.srs.version)
        self.now = parse_due(result)
        question = changed.queue(self.pool, "test")["items"][0]
        result = changed.submit(self.payload(question), self.pool)
        current = self.stats.db.execute("SELECT * FROM word_memory").fetchone()
        self.assertEqual(current["config_version"], changed.srs.version)
        self.assertEqual(result["card_version"], 2)
        self.assertEqual(self.stats.overview()["total_words_practiced"], 2)

    def test_delay_preserves_original_answer_time_not_retry_time(self):
        payload = self.payload(self.question())
        reviewed = self.now
        self.now += timedelta(hours=2)
        response = self.memory.submit(payload, self.pool)
        self.assertEqual(parse_due(response), reviewed + timedelta(minutes=10))
        row = self.stats.db.execute("SELECT reviewed_at,received_at FROM word_reviews").fetchone()
        self.assertEqual(row["reviewed_at"], time_text(reviewed))
        self.assertEqual(row["received_at"], time_text(self.now))

    def test_invalid_ticket_and_expired_ticket(self):
        payload = self.payload(self.question())
        with self.assertRaises(PracticeConflict):
            self.memory.submit({**payload, "attempt_id": "invented"}, self.pool)
        self.now += timedelta(days=8)
        with self.assertRaises(PracticeConflict):
            self.memory.submit(payload, self.pool)

    def test_unavailable_source_keeps_pending_submission_retryable(self):
        payload = self.payload(self.question())
        with self.assertRaises(RuntimeError):
            self.memory.submit(payload, None)
        self.memory.submit(payload, self.pool)

    def test_invalid_times_and_changed_question_do_not_mutate_memory(self):
        payload = self.payload(self.question())
        with self.assertRaises(PracticeConflict):
            self.memory.submit({**payload, "reviewed_at": time_text(self.now + timedelta(days=1))}, self.pool)
        with self.assertRaises(ValueError):
            self.memory.submit({**payload, "duration_ms": float("nan")}, self.pool)
        with self.assertRaises(PracticeConflict):
            self.memory.submit(payload, [{**word(), "word": "changed"}])
        self.assertEqual(self.stats.overview()["total_words_practiced"], 0)


def parse_due(result):
    return datetime.fromisoformat(result["memory"]["due"].replace("Z", "+00:00"))


class CutoverTest(unittest.TestCase):
    def test_clear_legacy_once_and_preserve_sync_and_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "stats.db"
            secret = Path(folder) / ".access-secret"
            secret.write_bytes(b"private credential")
            stats = StatsStore(str(path))
            try:
                stats.db.executescript("""
                    CREATE TABLE practice_sessions(session_id TEXT PRIMARY KEY,start_time TEXT,
                        total_words INTEGER,correct_words INTEGER,incorrect_words INTEGER,accuracy REAL);
                    CREATE TABLE word_attempts(session_id TEXT REFERENCES practice_sessions(session_id),
                        word TEXT,user_input TEXT,is_correct INTEGER);
                    CREATE TABLE word_mastery(word TEXT PRIMARY KEY);
                """)
                with stats.db:
                    stats.db.execute("INSERT INTO practice_sessions(session_id,start_time,total_words,correct_words,incorrect_words,accuracy) VALUES('legacy','2020-01-01',1,1,0,100)")
                    stats.db.execute("INSERT INTO word_attempts(session_id,word,user_input,is_correct) VALUES('legacy','apple','apple',1)")
                    stats.db.execute("INSERT INTO word_mastery(word) VALUES('apple')")
                stats.save_sync_history({"added_words": 1, "added_word_list": [word()], "success": True})
                memory = MemoryStore(stats, MemoryConfig())
                for table in ("practice_sessions", "word_attempts", "word_mastery"):
                    self.assertIsNone(stats.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())
                self.assertEqual(len(stats.list_sync_history()), 1)
                self.assertEqual(secret.read_bytes(), b"private credential")
                question = memory.queue([word()], "session")["items"][0]
                now = memory.now()
                memory.submit({"attempt_id": question["attempt_id"], "session_id": "session", "duration_ms": 0,
                               "user_input": "apple", "reviewed_at": time_text(now)}, [word()])
            finally:
                stats.close()
            stats = StatsStore(str(path))
            try:
                MemoryStore(stats, MemoryConfig())
                self.assertEqual(stats.overview()["total_words_practiced"], 1)
            finally:
                stats.close()
