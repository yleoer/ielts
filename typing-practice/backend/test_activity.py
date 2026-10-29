from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fsrs import Card, State

from activity import calendar_window
from app import create_app
from srs import time_text
from test_app import make_anki_db, make_config


class ActivityTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.collection = root / "collection.anki2"
        make_anki_db(self.collection, word_count=4)
        self.app = create_app(make_config(root, str(self.collection)), start_background_tasks=False)
        self.addCleanup(self.app.extensions["typing_practice_state"].close)
        self.state = self.app.extensions["typing_practice_state"]
        self.client = self.app.test_client()
        self.now = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)
        self.state.memory.now = lambda: self.now

    def get(self, route):
        response = self.client.get(route)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["data"]

    def review(self, answer="abandon"):
        pool = self.state.current_pool()
        question = self.state.memory.queue([pool[0]], "calendar-test", 1, "free")["items"][0]
        self.now += timedelta(seconds=1)
        payload = {"attempt_id": question["attempt_id"], "session_id": "calendar-test", "user_input": answer,
                   "duration_ms": 1000, "reviewed_at": time_text(self.now)}
        result = self.client.post("/api/practice/attempts", json=payload)
        self.assertEqual(result.status_code, 200, result.json)

    def test_window_contains_current_month_and_six_previous_five_next_months(self):
        self.assertEqual(calendar_window(date(2026, 10, 29)), (date(2026, 4, 1), date(2027, 3, 31)))
        self.assertEqual(calendar_window(date(2024, 2, 29)), (date(2023, 8, 1), date(2024, 7, 31)))
        self.now = datetime(2024, 2, 29, 8, tzinfo=timezone.utc)
        data = self.get("/api/stats/calendar")
        self.assertEqual(len(data["days"]), 366)
        self.assertEqual(data["days"][0]["date"], "2023-08-01")
        self.assertEqual(data["days"][-1]["date"], "2024-07-31")
        self.assertTrue(all(day["practiced"] == day["due_count"] == 0 for day in data["days"]))

    def test_calendar_merges_unique_history_with_current_due_schedule_without_writes(self):
        self.now = datetime(2026, 10, 27, 8, tzinfo=timezone.utc)
        self.review()
        self.review("wrong")
        self.now = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)
        pool = self.state.current_pool()
        schedule = [self.now - timedelta(days=10), datetime(2027, 3, 31, 15, 59, tzinfo=timezone.utc),
                    datetime(2027, 3, 31, 16, tzinfo=timezone.utc)]
        with self.state.stats.db:
            for index, due in enumerate(schedule, 1):
                card = Card(card_id=index, due=due, state=State.Review, stability=25, difficulty=5,
                            last_review=self.now - timedelta(days=1))
                self.state.stats.db.execute("""INSERT OR REPLACE INTO word_memory
                    (id,word_key,card_json,due,state,stability,first_review,last_review,version,config_version)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""", (index, f"word-atlas:{pool[index-1]['source_id']}",
                    card.to_json(), time_text(due), int(card.state), card.stability, time_text(self.now),
                    time_text(card.last_review), 1, self.state.memory.srs.version))
        changes = self.state.stats.db.total_changes
        before = [tuple(row) for row in self.state.stats.db.execute("SELECT * FROM word_memory")]
        data = self.get("/api/stats/calendar")
        days = {day["date"]: day for day in data["days"]}
        self.assertEqual((days["2026-10-27"]["practiced"], days["2026-10-27"]["attempts"]), (1, 2))
        self.assertEqual(days["2026-10-27"]["accuracy"], 50)
        self.assertEqual(days["2026-10-29"]["due_count"], 1)
        self.assertEqual(days["2027-03-31"]["due_count"], 1)
        self.assertEqual(sum(day["due_count"] for day in data["days"]), 2)
        history = self.get("/api/stats/calendar-words?date=2026-10-27")
        self.assertEqual(len(history["practiced"]), 1)
        self.assertEqual(history["practiced"][0]["total_attempts"], 2)
        self.assertEqual(history["due"], [])
        for selected in ("2026-10-29", "2027-03-31"):
            self.assertEqual(len(self.get("/api/stats/calendar-words?date=" + selected)["due"]), days[selected]["due_count"])
        self.assertEqual(self.state.stats.db.total_changes, changes)
        self.assertEqual([tuple(row) for row in self.state.stats.db.execute("SELECT * FROM word_memory")], before)

    def test_beijing_midnight_and_removed_words_preserve_historical_detail(self):
        self.now = datetime(2026, 10, 28, 15, 59, 58, tzinfo=timezone.utc)
        self.review()
        self.review()
        self.review()
        days = {day["date"]: day for day in self.get("/api/stats/calendar")["days"]}
        self.assertEqual((days["2026-10-28"]["practiced"], days["2026-10-28"]["attempts"]), (1, 1))
        self.assertEqual((days["2026-10-29"]["practiced"], days["2026-10-29"]["attempts"]), (1, 2))
        with closing(sqlite3.connect(self.collection)) as db:
            db.execute("DELETE FROM cards WHERE nid=101")
            db.commit()
        data = self.get("/api/stats/calendar-words?date=2026-10-29")
        self.assertEqual(data["practiced"][0]["source_id"], "abandon")
        self.assertEqual(data["practiced"][0]["total_attempts"], 3)
        self.assertEqual(data["due"], [])

    def test_monthly_activity_uses_natural_month_and_includes_zero_days(self):
        self.now = datetime(2026, 9, 30, 15, 59, 58, tzinfo=timezone.utc)
        self.review()
        self.review()
        data = self.get("/api/stats/monthly-activity")
        self.assertEqual(data["month"], "2026-10")
        self.assertEqual(len(data["days"]), 31)
        self.assertEqual(data["days"][0]["words"], 1)
        self.assertEqual(sum(day["words"] for day in data["days"]), 1)
        self.now = datetime(2024, 2, 15, 8, tzinfo=timezone.utc)
        leap = self.get("/api/stats/monthly-activity")
        self.assertEqual(len(leap["days"]), 29)
        self.assertTrue(all(day["accuracy"] is None for day in leap["days"]))

    def test_streak_uses_the_same_beijing_day_as_the_calendar(self):
        self.now = datetime(2026, 10, 28, 15, 59, 58, tzinfo=timezone.utc)
        self.review()
        self.assertEqual(self.get("/api/stats/overview")["current_streak"], 1)
        self.now = datetime(2026, 10, 29, 15, 59, 58, tzinfo=timezone.utc)
        self.review()
        self.assertEqual(self.get("/api/stats/overview")["current_streak"], 2)
        self.now = datetime(2026, 10, 29, 16, tzinfo=timezone.utc)
        self.assertEqual(self.get("/api/stats/overview")["current_streak"], 2)
        self.now = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)
        self.assertEqual(self.get("/api/stats/overview")["current_streak"], 0)

    def test_calendar_detail_returns_more_than_five_hundred_historical_words(self):
        from test_optimizer_service import seed_history
        self.now = datetime(2026, 7, 1, 8, tzinfo=timezone.utc)
        seed_history(self.state.stats, self.state.memory, cards=501, days=1)
        data = self.get("/api/stats/calendar-words?date=2026-01-01")
        self.assertEqual(len(data["practiced"]), 501)
        self.assertEqual(len({word["source_id"] for word in data["practiced"]}), 501)
        self.assertEqual(data["due"], [])

    def test_calendar_rejects_invalid_dates_and_dates_outside_displayed_year(self):
        for day in ("", "20261029", "2026-02-30", "2026-03-31", "2027-04-01"):
            self.assertEqual(self.client.get("/api/stats/calendar-words", query_string={"date": day}).status_code, 400, day)
