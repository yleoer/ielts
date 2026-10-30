"""Full-deck statistics must never expand the practice queue."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fsrs import Card, State

from anki import FIELD_SEPARATOR, WORD_ATLAS_FIELDS
from app import create_app
from test_app import make_anki_db, make_config


class VocabularyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.collection = root / "collection.anki2"
        make_anki_db(self.collection, word_count=205)
        with closing(sqlite3.connect(self.collection)) as db:
            db.execute("UPDATE cards SET type=0,queue=0 WHERE nid != 101")
            # Both Anki directions and duplicate source notes count as one word.
            db.execute("INSERT INTO cards VALUES(1001,101,1,2,2)")
            raw = db.execute("SELECT flds FROM notes WHERE id=101").fetchone()[0]
            db.execute("INSERT INTO notes VALUES(1000,?)", (raw,))
            db.execute("INSERT INTO cards VALUES(1002,1000,1,0,0)")
            db.commit()
        self.app = create_app(make_config(root, str(self.collection)), start_background_tasks=False)
        self.app.testing = True
        self.state = self.app.extensions["typing_practice_state"]
        self.addCleanup(self.state.close)
        self.client = self.app.test_client()
        self.now = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)
        self.state.memory.now = lambda: self.now

    def progress(self):
        response = self.client.get("/api/stats/vocabulary-progress")
        self.assertEqual(response.status_code, 200)
        return response.json["data"]

    def page(self, **params):
        response = self.client.get("/api/stats/vocabulary-words", query_string={
            "dimension": "cefr", "value": "B2", **params,
        })
        self.assertEqual(response.status_code, 200)
        return response.json["data"]

    def test_full_deck_counts_without_expanding_scheduled_or_free_practice(self):
        changes = self.state.stats.db.total_changes
        data = self.progress()
        self.assertEqual(data["overall"]["total"], 205)
        self.assertEqual(data["overall"]["new"], 205)
        self.assertEqual(data["overall"]["learned"], 0)
        self.assertEqual([level["value"] for level in data["levels"]], ["A1", "A2", "B1", "B2", "C1", "C2"])
        self.assertEqual(data["levels"][3]["total"], 205)
        self.assertEqual(data["topics"][0]["total"], 205)
        self.assertEqual(self.state.stats.db.total_changes, changes)
        for mode in ("scheduled", "free"):
            queue = self.client.get(f"/api/practice/queue?session_id={mode}&mode={mode}").json["data"]
            self.assertEqual(len(queue["items"]), 1)
            self.assertEqual(queue["items"][0]["source_id"], "abandon")
            self.assertEqual(queue["summary"]["total"], 1)

    def test_website_fsrs_statuses_drive_both_groups_and_filters(self):
        question = self.client.get("/api/practice/queue?session_id=test").json["data"]["items"][0]
        self.now += timedelta(seconds=7)
        response = self.client.post("/api/practice/attempts", json={
            "attempt_id": question["attempt_id"], "session_id": "test", "user_input": "abandon",
            "duration_ms": 7000, "reviewed_at": self.now.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        data = self.progress()
        for group in (data["overall"], data["levels"][3], data["topics"][0]):
            self.assertEqual((group["learned"], group["learning"], group["mastered"], group["new"]), (1, 1, 0, 204))
        self.assertEqual(self.page(status="learning")["items"][0]["source_id"], "abandon")
        self.assertEqual(self.page(status="new")["total"], 204)
        row = self.state.stats.db.execute("SELECT * FROM word_memory").fetchone()
        card = Card.from_json(row["card_json"])
        for state, stability, expected in [(State.Review, 20.9, "learning"), (State.Review, 21, "mastered"),
                                           (State.Relearning, 100, "learning")]:
            card.state, card.stability = state, stability
            with self.state.stats.db:
                self.state.stats.db.execute("UPDATE word_memory SET card_json=?,state=?,stability=? WHERE id=?",
                                            (card.to_json(), int(state), stability, row["id"]))
            changes = self.state.stats.db.total_changes
            self.assertEqual(self.progress()["overall"][expected], 1)
            items = self.page(status=expected)["items"]
            self.assertEqual(items[0]["status"], expected)
            self.assertIn("due", items[0])
            topic = self.page(dimension="topic", value="思维", status=expected)
            self.assertEqual(topic["total"], 1)
            self.assertEqual(self.state.stats.db.total_changes, changes)

    def test_detail_lists_prioritize_smoothed_errors_before_paging_and_filtering(self):
        pool = {word["source_id"]: word for word in self.state.vocabulary_pool()}
        # Deliberately put the highest-priority word after lower-priority entries.
        histories = [("abandon", 1, 0), ("word-ab", 1, 1), ("word-ac", 10, 8),
                     ("word-ad", 2, 1), ("word-ae", 4, 2), ("word-af", 4, 2)]
        for source, total, errors in histories:
            word = pool[source]
            for index in range(total):
                question = self.state.memory.queue([word], "sort-test", 1, "free")["items"][0]
                self.now += timedelta(seconds=7)
                self.state.memory.submit({
                    "attempt_id": question["attempt_id"], "session_id": "sort-test",
                    "user_input": "" if index < errors else word["word"],
                    "duration_ms": 7000, "reviewed_at": self.now.isoformat(),
                }, [word])

        changes = self.state.stats.db.total_changes
        expected = ["word-ac", "word-ab", "word-ae", "word-af", "word-ad", "abandon"]
        for group in ({"dimension": "cefr", "value": "B2"}, {"dimension": "topic", "value": "思维"}):
            with self.subTest(**group):
                sources = []
                for offset in (0, 2, 4):
                    data = self.page(**group, offset=offset, limit=2)
                    self.assertEqual(data["total"], 205)
                    self.assertEqual(data["next_offset"], offset + 2)
                    sources.extend(word["source_id"] for word in data["items"])
                self.assertEqual(sources, expected)
                self.assertEqual(self.page(**group, offset=6, limit=1)["items"][0]["source_id"], "word-ag")
                learned = self.page(**group, status="learning")["items"]
                self.assertEqual([word["source_id"] for word in learned], expected)
                self.assertEqual((learned[0]["correct_attempts"], learned[0]["total_attempts"]), (2, 10))
                fresh = self.page(**group, status="new", limit=1)
                self.assertEqual(fresh["total"], 199)
                self.assertEqual((fresh["items"][0]["correct_attempts"], fresh["items"][0]["total_attempts"]), (0, 0))
        self.assertEqual(self.state.stats.db.total_changes, changes)
        self.assertEqual([word["source_id"] for word in self.state.current_pool()], ["abandon"])

    def test_pagination_can_reach_every_word_without_duplicates(self):
        sources, offset = [], 0
        while offset is not None:
            data = self.page(offset=offset)
            self.assertEqual(data["total"], 205)
            sources.extend(word["source_id"] for word in data["items"])
            offset = data["next_offset"]
        self.assertEqual(len(sources), 205)
        self.assertEqual(len(set(sources)), 205)
        self.assertEqual(self.page(offset=1000)["items"], [])

    def test_missing_metadata_and_equal_spellings_keep_stable_source_identity(self):
        with closing(sqlite3.connect(self.collection)) as db:
            raw = db.execute("SELECT flds FROM notes WHERE id=102").fetchone()[0]
            fields = dict(zip(WORD_ATLAS_FIELDS, raw.split(FIELD_SEPARATOR)))
            fields.update(Word="abandon", CEFR=" <b>b1</b> ", Topic="<b>教育</b>")
            db.execute("UPDATE notes SET flds=? WHERE id=102", (FIELD_SEPARATOR.join(fields[name] for name in WORD_ATLAS_FIELDS),))
            fields.update(SourceId="unknown", CEFR="bad", Topic="")
            db.execute("UPDATE notes SET flds=? WHERE id=103", (FIELD_SEPARATOR.join(fields[name] for name in WORD_ATLAS_FIELDS),))
            db.commit()
        data = self.progress()
        self.assertEqual(data["overall"]["total"], 205)
        self.assertEqual(data["levels"][2]["total"], 1)
        self.assertEqual(data["levels"][-1]["value"], "未分级")
        self.assertEqual(self.page(value="未分级")["items"][0]["source_id"], "unknown")
        self.assertEqual(self.page(dimension="topic", value="未分类")["total"], 1)

    def test_invalid_filters_and_paging_are_rejected(self):
        for query in ("", "dimension=bad&value=B2", "dimension=cefr", "dimension=cefr&value=B2&status=bad",
                      "dimension=cefr&value=B2&offset=-1", "dimension=cefr&value=B2&offset=abc",
                      "dimension=cefr&value=B2&limit=0", "dimension=cefr&value=B2&limit=201"):
            self.assertEqual(self.client.get("/api/stats/vocabulary-words?" + query).status_code, 400, query)

    def review(self, answer):
        question = self.client.get("/api/practice/queue?session_id=history&mode=free").json["data"]["items"][0]
        self.now += timedelta(seconds=7)
        payload = {"attempt_id": question["attempt_id"], "session_id": "history", "user_input": answer,
                   "duration_ms": 7000, "reviewed_at": self.now.isoformat()}
        response = self.client.post("/api/practice/attempts", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/api/practice/attempts", json=payload).json, response.json)
        return response.json["data"]

    def test_attempt_counts_and_each_error_share_stable_word_identity(self):
        for answer in ("abndon", "abandon", "", "abando"):
            self.review(answer)
        changes = self.state.stats.db.total_changes
        learned = self.page(status="learning")["items"][0]
        self.assertEqual((learned["correct_attempts"], learned["total_attempts"]), (1, 4))
        fresh = self.page(status="new")["items"][0]
        self.assertEqual((fresh["correct_attempts"], fresh["total_attempts"]), (0, 0))
        scheduled = self.client.get("/api/stats/calendar-words?date=2026-10-29").json["data"]["due"][0]
        self.assertEqual((scheduled["correct_attempts"], scheduled["total_attempts"]), (1, 4))
        first = self.client.get("/api/stats/word-errors?source_id=abandon&limit=2").json["data"]
        self.assertEqual((first["correct_attempts"], first["total_attempts"]), (1, 4))
        self.assertEqual([row["user_input"] for row in first["items"]], ["abando", ""])
        self.assertEqual(set(first["items"][0]), {"id", "word", "user_input", "reviewed_at"})
        second = self.client.get("/api/stats/word-errors", query_string={
            "source_id": "abandon", "limit": 2, "before_id": first["next_before_id"],
        }).json["data"]
        self.assertEqual([row["user_input"] for row in second["items"]], ["abndon"])
        self.assertIsNone(second["next_before_id"])
        self.assertTrue(all(row["word"] == "abandon" and row["reviewed_at"] for row in first["items"] + second["items"]))
        self.assertEqual(self.state.stats.db.total_changes, changes)
        # Equal spellings from another source must not share attempt/error history.
        with closing(sqlite3.connect(self.collection)) as db:
            raw = db.execute("SELECT flds FROM notes WHERE id=102").fetchone()[0]
            fields = dict(zip(WORD_ATLAS_FIELDS, raw.split(FIELD_SEPARATOR)))
            other_source = fields["SourceId"]
            fields["Word"] = "abandon"
            db.execute("UPDATE notes SET flds=? WHERE id=102", (FIELD_SEPARATOR.join(fields[name] for name in WORD_ATLAS_FIELDS),))
            db.commit()
        other = self.client.get("/api/stats/word-errors", query_string={"source_id": other_source}).json["data"]
        self.assertEqual((other["total_attempts"], other["items"]), (0, []))
        other_word = next(item for item in self.page()["items"] if item["source_id"] == other_source)
        self.assertEqual(other_word["total_attempts"], 0)

    def test_correct_only_word_has_counts_but_no_error_records(self):
        self.review("abandon")
        data = self.client.get("/api/stats/word-errors?source_id=abandon").json["data"]
        self.assertEqual((data["correct_attempts"], data["total_attempts"]), (1, 1))
        self.assertEqual(data["items"], [])
        self.assertIsNone(data["next_before_id"])

    def test_error_history_rejects_missing_identity_and_bad_paging(self):
        for query in ("", "source_id=", "source_id=abandon&before_id=-1", "source_id=abandon&before_id=bad",
                      "source_id=abandon&limit=0", "source_id=abandon&limit=201", "source_id=abandon&limit=bad"):
            self.assertEqual(self.client.get("/api/stats/word-errors?" + query).status_code, 400, query)

    def test_empty_deck_and_unavailable_reader_are_distinct(self):
        with closing(sqlite3.connect(self.collection)) as db:
            db.execute("DELETE FROM cards")
            db.commit()
        data = self.progress()
        self.assertEqual(data["overall"]["total"], 0)
        self.assertEqual(len(data["levels"]), 6)
        self.assertEqual(data["topics"], [])
        self.state.reader.close()
        self.state.reader = None
        self.assertEqual(self.client.get("/api/stats/vocabulary-progress").status_code, 503)
        self.assertEqual(self.client.get("/api/stats/overview").status_code, 200)
