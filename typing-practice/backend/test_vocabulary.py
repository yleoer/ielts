from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from vocabulary import VocabularyStore


def word(source: str, note_id: int = 1, learned: bool = True) -> dict:
    return {"id": note_id, "source_id": source, "word": source, "learned": learned,
            "chinese_meaning": "释义", "category": "测试"}


class VocabularyHistoryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = str(Path(temporary.name) / "stats.db")
        self.store = VocabularyStore(self.path)
        self.addCleanup(self.store.close)

    def test_initial_pool_is_a_baseline_and_history_survives_restart(self):
        with self.assertRaises(RuntimeError):
            self.store.snapshot()
        self.store.refresh([word("apple"), word("banana", 2, False)])
        self.assertEqual(self.store.snapshot()["sync_history"], [])
        self.store.refresh([word("apple"), word("banana", 2)])
        batch = self.store.snapshot()["sync_history"][0]
        self.assertEqual((batch["before_words"], batch["after_words"], batch["added_words"]), (1, 2, 1))
        self.assertEqual(batch["added_word_list"], [{k: v for k, v in word("banana", 2).items() if k != "learned"}])
        self.store.close()
        restarted = VocabularyStore(self.path)
        self.addCleanup(restarted.close)
        restarted.refresh([word("apple", 99), word("banana", 100)])
        self.assertEqual(restarted.snapshot()["sync_history"], [batch])

    def test_empty_baseline_still_records_the_first_learned_word(self):
        self.store.refresh([])
        self.store.refresh([word("apple")])
        self.assertEqual(self.store.snapshot()["sync_history"][0]["added_words"], 1)

    def test_removal_reset_and_renaming_do_not_recount_seen_sources(self):
        self.store.refresh([word("apple")])
        self.store.refresh([word("apple"), word("banana", 2)])
        original = self.store.snapshot()["sync_history"]
        self.store.refresh([word("banana", 2, False)])
        renamed = {**word("banana", 200), "word": "new spelling"}
        self.store.refresh([word("apple", 100), renamed])
        self.assertEqual(self.store.snapshot()["sync_history"], original)
        self.assertEqual(original[0]["added_word_list"][0]["word"], "banana")

    def test_history_returns_latest_50_batches_in_server_order(self):
        self.store.refresh([])
        for index in range(55):
            self.store.refresh([word(f"word-{index}", index)])
        history = self.store.snapshot()["sync_history"]
        self.assertEqual([batch["id"] for batch in history], list(range(55, 5, -1)))
        self.assertEqual(history[0]["added_word_list"][0]["source_id"], "word-54")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM vocabulary_sync_history").fetchone()[0], 55)

    def test_failed_publish_rolls_back_seen_words_and_history(self):
        self.store.refresh([word("apple")])
        before = self.store.snapshot()
        self.store.db.execute("""CREATE TRIGGER reject_snapshot BEFORE INSERT ON vocabulary_snapshot
                              BEGIN SELECT RAISE(ABORT,'test disk failure'); END""")
        with self.assertRaises(sqlite3.Error):
            self.store.refresh([word("apple"), word("banana", 2)])
        self.assertEqual(self.store.snapshot(), before)
        self.store.db.execute("DROP TRIGGER reject_snapshot")
        self.store.refresh([word("apple"), word("banana", 2)])
        self.assertEqual(self.store.snapshot()["sync_history"][0]["added_words"], 1)


if __name__ == "__main__":
    unittest.main()
