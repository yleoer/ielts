from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from app import create_app, start_collection_refresh
from anki import FIELD_SEPARATOR, WORD_ATLAS_FIELDS
from config import AnkiConfig, Config, ServerConfig


def make_config(root: Path, anki_path: str = "") -> Config:
    return Config(server=ServerConfig(host="127.0.0.1", port=0),
                  anki=AnkiConfig(db_path=anki_path, deck_name="Word Atlas", deck_id=1),
                  db_path=str(root / "stats.db"))


def make_anki_db(path: Path, word_count: int = 1) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE decks(id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE notes(id INTEGER PRIMARY KEY, flds TEXT, tags TEXT NOT NULL DEFAULT '');
        CREATE TABLE cards(id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER, type INTEGER, queue INTEGER);
        INSERT INTO decks(id,name) VALUES(1,'Word Atlas');
        INSERT INTO cards(id,nid,did,type,queue) VALUES(201,101,1,1,1);
        """
    )
    fields = {name: "" for name in WORD_ATLAS_FIELDS}
    fields.update({"Word": "abandon", "UK": "/əˈbændən/", "US": "/əˈbændən/",
                   "PartOfSpeech": "v.", "MeaningZH": "放弃", "MeaningEN": "To leave behind.",
                   "ExampleEN": "Never <mark>abandon</mark> hope.", "ExampleZH": "永不放弃希望。",
                   "Topic": "思维", "CEFR": "B2", "SourceId": "abandon",
                   "Illustration": '<img src="wa_abandon_img.webp">',
                   "AudioUK": "[sound:wa_abandon_uk.mp3]"})
    db.execute("INSERT INTO notes(id,flds) VALUES(?,?)", (101, FIELD_SEPARATOR.join(fields[name] for name in WORD_ATLAS_FIELDS)))
    for index in range(1, word_count):
        spelling = f"word-{chr(97 + index // 26)}{chr(97 + index % 26)}"
        fields.update(Word=spelling, SourceId=spelling)
        db.execute("INSERT INTO notes(id,flds) VALUES(?,?)", (101 + index, FIELD_SEPARATOR.join(fields[name] for name in WORD_ATLAS_FIELDS)))
        db.execute("INSERT INTO cards VALUES(?,?,1,1,1)", (201 + index, 101 + index))
    db.commit()
    db.close()


def attempt(index: int, **changes) -> dict:
    item = {"attempt_id": f"a-{index}", "word_key": "word-atlas:abandon", "word": "abandon",
            "chinese_meaning": "放弃", "category": "思维", "user_input": "abandon", "is_correct": True,
            "rating": 3, "reviewed_at": f"2026-10-29T16:{index // 60 % 60:02d}:{index % 60:02d}+08:00",
            "duration_ms": 7000, "first_input_ms": 200}
    item.update(changes)
    return item


class ServerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.collection = self.root / "collection.anki2"
        make_anki_db(self.collection, word_count=3)
        with closing(sqlite3.connect(self.collection)) as db:
            db.execute("UPDATE cards SET type=0,queue=0 WHERE nid=103")
            db.commit()
        self.app = create_app(make_config(self.root, str(self.collection)), start_background_tasks=False)
        self.state = self.app.extensions["cijian_state"]
        self.addCleanup(self.state.close)
        self.client = self.app.test_client()

    def sync(self, device="desktop-a", cursor=0, attempts=()):
        response = self.client.post("/api/sync", json={"device_id": device, "cursor": cursor, "attempts": list(attempts)})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["data"]

    def test_only_health_vocabulary_and_sync_remain(self):
        self.assertEqual(self.client.get("/api/health").json, {"success": True, "status": "ok"})
        for path in ("/", "/stats.html", "/login", "/api/config", "/api/practice/queue", "/api/stats/overview",
                     "/api/memory/optimization", "/api/media/101/illustration", "/assets/style.css"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)
            self.assertEqual(response.json["success"], False)
        self.assertEqual(self.client.get("/api/sync").status_code, 405)

    def test_vocabulary_snapshot_lists_the_whole_deck_with_learning_state(self):
        data = self.client.get("/api/vocab").json["data"]
        self.assertEqual((data["format"], data["deck_name"]), (1, "Word Atlas"))
        self.assertTrue(data["generated_at"].endswith("Z"))
        self.assertEqual(data["last_anki_sync_at"], data["generated_at"])
        self.assertEqual(data["sync_history"], [], "the initial pool is a baseline")
        words = {word["source_id"]: word for word in data["words"]}
        self.assertEqual(list(words), ["abandon", "word-ab", "word-ac"])
        self.assertEqual([word["learned"] for word in words.values()], [True, True, False])
        self.assertEqual(words["abandon"]["illustration_file"], "wa_abandon_img.webp")
        self.assertEqual(words["abandon"]["chinese_senses"][0]["chinese_meaning"], "放弃")
        self.state.reader.close()
        self.state.reader = None
        self.assertEqual(self.client.get("/api/vocab").json["data"], data, "the last successful scan remains available")

    def test_vocabulary_filters_only_tagged_words_and_keeps_their_answer_history(self):
        self.sync(attempts=[attempt(1)])
        with closing(sqlite3.connect(self.collection)) as db:
            db.execute("UPDATE notes SET tags=' word_atlas::excluded word_atlas::canonical::word-ac ' WHERE id=101")
            db.execute("UPDATE cards SET queue=-1 WHERE nid=101")
            db.commit()
        self.state.scan_vocabulary()
        data = self.client.get("/api/vocab").json["data"]
        self.assertEqual(data["format"], 1)
        self.assertEqual([(w["source_id"], w["learned"]) for w in data["words"]],
                         [("word-ab", True), ("word-ac", True)])
        self.assertEqual(self.sync()["attempts"][0]["word_key"], "word-atlas:abandon")

    def test_api_reads_do_not_discover_words_and_devices_receive_the_same_history(self):
        before = self.client.get("/api/vocab").json["data"]
        with closing(sqlite3.connect(self.collection)) as db:
            db.execute("UPDATE cards SET type=1,queue=1 WHERE nid=103")
            db.commit()
        self.assertEqual(self.client.get("/api/vocab").json["data"], before)
        self.state.scan_vocabulary()
        first = self.client.get("/api/vocab").json["data"]
        other = self.app.test_client().get("/api/vocab").json["data"]
        self.assertEqual(first, other)
        self.assertEqual(len(first["sync_history"]), 1)
        batch = first["sync_history"][0]
        self.assertEqual((batch["before_words"], batch["after_words"], batch["added_words"]), (2, 3, 1))
        self.assertEqual(batch["added_word_list"][0]["source_id"], "word-ac")
        self.state.scan_vocabulary()
        self.assertEqual(self.client.get("/api/vocab").json["data"]["sync_history"], first["sync_history"])

    def test_failed_scan_keeps_snapshot_and_retry_records_the_new_word(self):
        before = self.state.vocabulary()
        with closing(sqlite3.connect(self.collection)) as db:
            db.execute("ALTER TABLE notes RENAME TO unavailable_notes")
            db.commit()
        with self.assertRaises(sqlite3.Error):
            self.state.scan_vocabulary()
        self.assertEqual(self.state.vocabulary(), before)
        with closing(sqlite3.connect(self.collection)) as db:
            db.execute("ALTER TABLE unavailable_notes RENAME TO notes")
            db.execute("UPDATE cards SET type=1,queue=1 WHERE nid=103")
            db.commit()
        self.state.scan_vocabulary()
        self.assertEqual(self.state.vocabulary()["sync_history"][0]["added_words"], 1)

    def test_scheduled_copy_scans_the_copied_collection(self):
        source_dir = self.root / "source"
        source_dir.mkdir()
        source = source_dir / "collection.anki2"
        make_anki_db(source, word_count=3)
        with patch.dict("os.environ", {"ANKI_SYNC_STABLE_SECONDS": "0"}):
            self.assertEqual(self.state.refresh_collection(str(source_dir), str(self.collection)), 3)
        self.assertEqual(self.state.vocabulary()["sync_history"][0]["added_words"], 1)

    def test_restart_without_anki_keeps_the_published_snapshot(self):
        before = self.state.vocabulary()
        self.state.close()
        self.collection.unlink()
        restarted = create_app(make_config(self.root, str(self.collection)), start_background_tasks=False)
        self.addCleanup(restarted.extensions["cijian_state"].close)
        self.assertEqual(restarted.test_client().get("/api/vocab").json["data"], before)

    def test_hourly_schedule_also_checks_direct_anki_paths(self):
        for source, target in (("", ""), ("source", "target")):
            with self.subTest(source=source):
                state = Mock()
                state.stop.wait.side_effect = [False, True]
                state.stop.is_set.return_value = False
                with patch.dict("os.environ", {"ANKI_SYNC_INTERVAL_SECONDS": "", "ANKI_SYNC_INITIAL_WAIT_SECONDS": ""}), \
                        patch("app.threading.Thread") as thread:
                    start_collection_refresh(state, source, target)
                    thread.call_args.kwargs["target"]()
                self.assertEqual([call.args[0] for call in state.stop.wait.call_args_list], [60, 3600])
                if source:
                    state.refresh_collection.assert_called_once_with(source, target)
                else:
                    state.scan_vocabulary.assert_called_once_with()

    def test_sync_deduplicates_and_pages_by_cursor(self):
        first = self.sync(attempts=[attempt(1), attempt(2)])
        self.assertEqual((first["accepted"], first["duplicates"], first["next_cursor"], first["more"]), (2, 0, 2, False))
        self.assertEqual(first["attempts"][0], {**attempt(1), "reviewed_at": "2026-10-29T08:00:01.000000Z",
                                                 "duration_ms": 7000.0, "first_input_ms": 200.0})
        # A retry and another device: the first copy wins, the cursor returns only newer rows.
        changed = attempt(2, user_input="changed", is_correct=False, rating=1)
        other = self.sync("desktop-b", cursor=0, attempts=[changed, attempt(3, first_input_ms=None)])
        self.assertEqual((other["accepted"], other["duplicates"]), (1, 1))
        self.assertEqual([row["attempt_id"] for row in other["attempts"]], ["a-1", "a-2", "a-3"])
        self.assertEqual(other["attempts"][1]["user_input"], "abandon")
        self.assertIsNone(other["attempts"][2]["first_input_ms"])
        # Cursors are row ids: increasing, not necessarily contiguous.
        later = self.sync(cursor=2)
        end = other["next_cursor"]
        self.assertEqual(([row["attempt_id"] for row in later["attempts"]], later["next_cursor"]), (["a-3"], end))
        self.assertEqual((self.sync(cursor=end)["attempts"], self.sync(cursor=end)["next_cursor"]), ([], end))

    def test_large_logs_are_paged(self):
        import ledger
        for start in range(0, 1200, 400):
            self.sync(attempts=[attempt(i, attempt_id=f"bulk-{i}") for i in range(start, start + 400)])
        cursor, seen, pages = 0, [], 0
        while True:
            data = self.sync(cursor=cursor)
            seen += [row["attempt_id"] for row in data["attempts"]]
            cursor, pages = data["next_cursor"], pages + 1
            if not data["more"]:
                break
        self.assertEqual((len(seen), len(set(seen)), pages), (1200, 1200, -(-1200 // ledger.PAGE_SIZE)))

    def test_invalid_requests_change_nothing(self):
        bad = [{}, {"device_id": ""}, {"device_id": "d", "cursor": -1}, {"device_id": "d", "cursor": True},
               {"device_id": "d", "attempts": {}}, {"device_id": "d", "attempts": [attempt(i) for i in range(501)]}]
        for field, value in (("attempt_id", ""), ("word_key", "abandon"), ("word_key", "word-atlas:"),
                             ("is_correct", 1), ("rating", 5), ("rating", True), ("reviewed_at", "2026-10-29T08:00:00"),
                             ("reviewed_at", "yesterday"), ("duration_ms", -1), ("first_input_ms", "1"),
                             ("user_input", "x" * 1001)):
            bad.append({"device_id": "d", "attempts": [attempt(1), attempt(2, **{field: value})]})
        for payload in bad:
            response = self.client.post("/api/sync", json=payload)
            self.assertEqual(response.status_code, 400, payload)
            self.assertFalse(response.json["success"])
        self.assertEqual(self.client.post("/api/sync", data="nope", content_type="text/plain").status_code, 400)
        self.assertEqual(self.sync()["attempts"], [])

    def test_web_history_is_imported_once_as_the_initial_log(self):
        self.state.close()
        path = self.root / "web.db"
        with closing(sqlite3.connect(path)) as db:
            db.execute("""CREATE TABLE word_reviews (id INTEGER PRIMARY KEY, attempt_id TEXT UNIQUE, word_key TEXT, word TEXT,
                chinese_meaning TEXT, category TEXT, user_input TEXT, is_correct INTEGER, rating INTEGER, reviewed_at TEXT,
                received_at TEXT, duration_ms REAL, first_input_ms REAL)""")
            for row_id, at in ((1, "2026-10-02T00:00:00.000000Z"), (2, "2026-10-01T00:00:00.000000Z")):
                db.execute("INSERT INTO word_reviews VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (row_id, f"web-{row_id}",
                           "word-atlas:abandon", "abandon", "放弃", "思维", "abandon", 1, 3, at, at, 7000, None))
            db.commit()
        config = make_config(self.root, str(self.collection))
        config.db_path = str(path)
        for _ in range(2):
            app = create_app(config, start_background_tasks=False)
            data = app.test_client().post("/api/sync", json={"device_id": "d"}).json["data"]
            app.extensions["cijian_state"].close()
            self.assertEqual([row["attempt_id"] for row in data["attempts"]], ["web-2", "web-1"])
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM word_reviews").fetchone()[0], 2, "old tables are kept")


if __name__ == "__main__":
    unittest.main()
