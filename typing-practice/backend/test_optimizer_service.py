from __future__ import annotations

import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fsrs import Card, State

from memory import MemoryStore, PracticeConflict
from optimize_fsrs import load_logs
from optimizer_service import LEASE_SECONDS, OptimizationConfig, OptimizationService, next_month
from srs import MemoryConfig, SRS, time_text
from stats import StatsStore


def seed_history(stats, memory, cards=100, days=11):
    """Stable synthetic histories; each event after the first is a day apart."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pool = [{"id": card_id, "source_id": f"word-{card_id}", "word": f"word-{card_id}",
             "chinese_meaning": "模拟词", "part_of_speech": "n.", "category": "测试"}
            for card_id in range(1, cards + 1)]
    with stats.db:
        for word in pool:
            card = Card(card_id=word["id"], due=memory.now(), state=State.Review, stability=10,
                        difficulty=5, last_review=start + timedelta(days=days - 1))
            stats.db.execute("""INSERT INTO word_memory
                (id,word_key,card_json,due,state,stability,first_review,last_review,version,config_version)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (card.card_id, f"word-atlas:{word['source_id']}", card.to_json(),
                    time_text(card.due), int(card.state), card.stability, time_text(start),
                    time_text(card.last_review), 1, memory.srs.version))
    for day in range(days):
        append_day(stats, memory, day, cards)
    return pool


def append_day(stats, memory, day, cards=100, first_card=1):
    when = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    with stats.db:
        for card_id in range(first_card, first_card + cards):
            stats.db.execute("""INSERT INTO word_reviews
                (attempt_id,request_hash,session_id,memory_id,word_key,word,chinese_meaning,category,
                 user_input,is_correct,error_type,rating,reviewed_at,received_at,duration_ms,answer_length,
                 before_json,after_json,config_version,response_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    f"day-{day}-card-{card_id}", "fixture", f"day-{day}", card_id, f"word-atlas:word-{card_id}",
                    f"word-{card_id}", "模拟词", "测试", "answer", int((day + card_id) % 7 != 0), "",
                    1 if (day + card_id) % 7 == 0 else 3, time_text(when), time_text(when), 7000, 6,
                    None, "{}", memory.srs.version, "{}",
                ))


def candidate(record, _logs, accepted=False):
    parameters = list(record["report"]["baseline_parameters"])
    parameters[0] *= 1.05
    return {"fsrs_version": "6.3.2", "accepted": accepted,
            "outcome": "accepted" if accepted else "not_improved", "parameters": parameters,
            "baseline": {"reviews": 200, "log_loss": 0.5, "brier_score": 0.2},
            "default": {"reviews": 200, "log_loss": 0.5, "brier_score": 0.2},
            "candidate": {"reviews": 200, "log_loss": 0.4 if accepted else 0.6, "brier_score": 0.15},
            "reason": "验证误差改善" if accepted else "验证结果未改善"}


class OptimizationServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "stats.db"
        self.now = datetime(2026, 3, 31, 8, tzinfo=timezone.utc)
        self.stats = StatsStore(str(self.path))
        self.addCleanup(self.stats.close)
        self.memory = MemoryStore(self.stats, MemoryConfig(enable_fuzzing=False), lambda: self.now)

    def service(self, trainer=candidate, stats=None, memory=None, config=None):
        result = OptimizationService(stats or self.stats, memory or self.memory, config,
                                     now=lambda: self.now, trainer=trainer)
        self.addCleanup(result.stop)
        return result

    def test_environment_config_overrides_and_rejects_invalid_values(self):
        from config import load_config
        values = {"FSRS_AUTO_OPTIMIZE": "false", "FSRS_OPTIMIZER_CHECK_SECONDS": "30",
                  "FSRS_OPTIMIZER_MIN_NEW_REVIEWS": "150", "FSRS_OPTIMIZER_TIMEOUT_SECONDS": "120"}
        with patch.dict("os.environ", values):
            configured = load_config().optimization
        self.assertFalse(configured.enabled)
        self.assertEqual((configured.check_interval_seconds, configured.min_new_reviews, configured.timeout_seconds), (30, 150, 120))
        for key, value in (("FSRS_AUTO_OPTIMIZE", "yes"), ("FSRS_OPTIMIZER_CHECK_SECONDS", "0"),
                           ("FSRS_OPTIMIZER_MIN_NEW_REVIEWS", "-1"), ("FSRS_OPTIMIZER_TIMEOUT_SECONDS", "oops")):
            with self.subTest(key=key), patch.dict("os.environ", {**values, key: value}), self.assertRaises(ValueError):
                load_config()

    def test_first_attempt_starts_at_1000_effective_reviews_and_is_not_repeated(self):
        seed_history(self.stats, self.memory, days=10)
        append_day(self.stats, self.memory, 10, cards=99)
        service = self.service()
        self.assertIsNone(service.check_once())
        self.assertEqual(service.status()["effective_reviews"], 999)
        self.assertEqual(service.history()["items"], [])
        append_day(self.stats, self.memory, 10, cards=1, first_card=100)
        result = service.check_once()
        self.assertEqual(result["effective_reviews"], 1000)
        self.assertEqual(result["status"], "rejected")
        self.assertIsNone(service.check_once())
        self.assertEqual(len(service.history()["items"]), 1)
        self.assertEqual(service.status()["next_evaluation_at"], "2026-04-30T08:00:00.000000Z")

    def test_monthly_skip_is_recorded_and_new_data_accumulates(self):
        seed_history(self.stats, self.memory)
        service = self.service()
        service.check_once()
        self.now = next_month(self.now)
        result = service.check_once()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["new_effective_reviews"], 0)
        self.assertIn("新增有效间隔复习不足", result["reason"])
        append_day(self.stats, self.memory, 11)
        self.assertIsNone(service.check_once())
        self.now = next_month(self.now)
        result = service.check_once()
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["new_effective_reviews"], 100)
        self.assertEqual([row["status"] for row in service.history()["items"]], ["rejected", "skipped", "rejected"])
        first_page = service.history(limit=2)
        self.assertEqual(len(first_page["items"]), 2)
        self.assertEqual(len(service.history(first_page["next_before_id"], limit=2)["items"]), 1)

    def test_activation_preserves_due_dates_and_accepts_an_outstanding_question(self):
        pool = seed_history(self.stats, self.memory)
        question = self.memory.queue(pool, "pending")["items"][0]
        before = [tuple(row) for row in self.stats.db.execute("SELECT due,version FROM word_memory ORDER BY id")]
        service = self.service(lambda record, logs: candidate(record, logs, accepted=True))
        result = service.check_once()
        self.assertEqual(result["status"], "accepted")
        self.assertNotEqual(result["baseline_version"], self.memory.srs.version)
        self.assertEqual([tuple(row) for row in self.stats.db.execute("SELECT due,version FROM word_memory ORDER BY id")], before)
        self.assertEqual(service.status()["active_run_id"], result["id"])
        self.now += timedelta(seconds=7)
        answer = self.memory.submit({"session_id": "pending", "attempt_id": question["attempt_id"],
            "user_input": "answer", "duration_ms": 7000, "reviewed_at": time_text(self.now)}, pool)
        self.assertEqual(answer["card_version"], 2)
        row = self.stats.db.execute("SELECT config_version FROM word_memory WHERE word_key=?", (f"word-atlas:{question['source_id']}",)).fetchone()
        self.assertEqual(row[0], self.memory.srs.version)

    def test_restart_restores_the_accepted_version_and_manual_disable_allows_rollback(self):
        seed_history(self.stats, self.memory)
        service = self.service(lambda record, logs: candidate(record, logs, accepted=True))
        accepted = service.check_once()
        second_stats = StatsStore(str(self.path))
        self.addCleanup(second_stats.close)
        second_memory = MemoryStore(second_stats, MemoryConfig(enable_fuzzing=False))
        restored = self.service(stats=second_stats, memory=second_memory)
        self.assertEqual(second_memory.srs.version, accepted["activated_version"])
        self.assertEqual(len(restored.history()["items"]), 1)
        default_memory = MemoryStore(second_stats, MemoryConfig(enable_fuzzing=False))
        disabled = self.service(stats=second_stats, memory=default_memory, config=OptimizationConfig(enabled=False))
        self.assertEqual(default_memory.srs.version, accepted["baseline_version"])
        self.assertIsNone(disabled.check_once())

    def test_failure_is_saved_and_retried_after_a_day_without_activating_parameters(self):
        seed_history(self.stats, self.memory)
        original = self.memory.srs.version
        def fail(_record, _logs):
            raise ImportError("缺少训练依赖")
        service = self.service(fail)
        with self.assertLogs("optimizer_service", level="ERROR"):
            result = service.check_once()
        self.assertEqual(result["status"], "failed")
        self.assertIn("缺少训练依赖", result["report"]["error"])
        self.assertEqual(self.memory.srs.version, original)
        self.assertIsNone(service.check_once())
        self.now += timedelta(days=1)
        with self.assertLogs("optimizer_service", level="ERROR"):
            self.assertEqual(service.check_once()["status"], "failed")
        self.assertEqual(len(service.history()["items"]), 2)

    def test_invalid_or_unimproved_accepted_artifact_is_recorded_as_failure(self):
        seed_history(self.stats, self.memory)
        original = self.memory.srs.version
        def invalid(record, logs):
            report = candidate(record, logs, accepted=True)
            report["candidate"]["log_loss"] = report["baseline"]["log_loss"]
            return report
        service = self.service(invalid)
        with self.assertLogs("optimizer_service", level="ERROR"):
            result = service.check_once()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.memory.srs.version, original)
        self.assertIsNone(service.status()["active_run_id"])

    def test_database_lease_prevents_duplicate_training_and_practice_remains_available(self):
        pool = seed_history(self.stats, self.memory)
        started, release = threading.Event(), threading.Event()
        def blocked(record, logs):
            started.set()
            release.wait(timeout=10)
            return candidate(record, logs)
        service = self.service(blocked)
        second_stats = StatsStore(str(self.path))
        self.addCleanup(second_stats.close)
        second_memory = MemoryStore(second_stats, MemoryConfig(enable_fuzzing=False))
        other = self.service(stats=second_stats, memory=second_memory)
        worker = threading.Thread(target=service.check_once)
        worker.start()
        try:
            self.assertTrue(started.wait(timeout=5))
            self.assertIsNone(other.check_once())
            self.assertEqual(len(self.memory.queue(pool, "while-training")["items"]), 1)
        finally:
            release.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(service.history()["items"]), 1)

    def test_expired_training_is_recorded_and_late_results_cannot_overwrite_it(self):
        seed_history(self.stats, self.memory)
        service = self.service()
        snapshot = self.stats.db.execute("SELECT MAX(id) FROM word_reviews").fetchone()[0]
        run_id, owner, _ = service._claim(snapshot, load_logs(self.path, snapshot))
        self.now += timedelta(seconds=LEASE_SECONDS + 1)
        result = service.check_once()
        self.assertEqual(service.run_record(run_id)["status"], "interrupted")
        self.assertEqual(result["status"], "rejected")
        service._finish(run_id, owner, candidate(service.run_record(run_id), [], accepted=True))
        self.assertEqual(service.run_record(run_id)["status"], "interrupted")
        self.assertIsNone(service.status()["active_run_id"])

    def test_grading_rule_changes_still_reject_old_questions(self):
        pool = seed_history(self.stats, self.memory)
        question = self.memory.queue(pool, "pending")["items"][0]
        changed = SRS(MemoryConfig(easy_seconds=5, enable_fuzzing=False))
        with self.stats.db:
            self.stats.db.execute("INSERT INTO srs_configs VALUES(?,?)", (changed.version, json.dumps(changed.snapshot)))
        self.memory.srs = changed
        self.now += timedelta(seconds=7)
        with self.assertRaises(PracticeConflict):
            self.memory.submit({"session_id": "pending", "attempt_id": question["attempt_id"],
                "user_input": "answer", "duration_ms": 7000, "reviewed_at": time_text(self.now)}, pool)

    def test_calendar_month_handles_leap_year_and_year_boundary(self):
        self.assertEqual(next_month(datetime(2028, 1, 31, tzinfo=timezone.utc)).day, 29)
        self.assertEqual(next_month(datetime(2026, 12, 31, tzinfo=timezone.utc)).year, 2027)
