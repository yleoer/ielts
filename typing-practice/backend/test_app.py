from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import create_app
from anki import FIELD_SEPARATOR, WORD_ATLAS_FIELDS
from config import AnkiConfig, Config, PracticeConfig, ServerConfig, StatsConfig


def make_config(root: Path, anki_path: str = "") -> Config:
    return Config(
        server=ServerConfig(host="127.0.0.1", port=0),
        anki=AnkiConfig(db_path=anki_path, deck_name="Word Atlas", deck_id=1),
        practice=PracticeConfig(default_limit=20, max_limit=100),
        stats=StatsConfig(db_path=str(root / "stats.db")),
    )


def make_anki_db(path: Path, word_count: int = 1) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE decks(id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE notes(id INTEGER PRIMARY KEY, flds TEXT);
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
        db.execute("INSERT INTO notes VALUES(?,?)", (101 + index, FIELD_SEPARATOR.join(fields[name] for name in WORD_ATLAS_FIELDS)))
        db.execute("INSERT INTO cards VALUES(?,?,1,1,1)", (201 + index, 101 + index))
    db.commit()
    db.close()


class FlaskAppTest(unittest.TestCase):
    def test_answer_can_return_the_new_queue_and_retries_only_commit_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection.anki2"
            make_anki_db(collection, word_count=4)
            app = create_app(make_config(root, str(collection)), start_background_tasks=False)
            try:
                state = app.extensions["typing_practice_state"]
                now = datetime(2026, 10, 30, 8, tzinfo=timezone.utc)
                state.memory.now = lambda: now
                client = app.test_client()
                first = client.get("/api/practice/queue?session_id=fast&limit=3").json["data"]["items"][0]
                now += timedelta(seconds=2)
                payload = {"attempt_id": first["attempt_id"], "session_id": "fast", "user_input": first["word"],
                           "duration_ms": 2000, "reviewed_at": now.isoformat()}
                for limit in ("-1", "4", "bad"):
                    self.assertEqual(client.post(f"/api/practice/attempts?next_limit={limit}", json=payload).status_code, 400)
                self.assertEqual(state.stats.overview()["total_words_practiced"], 0)
                saved = client.post("/api/practice/attempts?next_limit=3", json=payload)
                self.assertEqual(saved.status_code, 200)
                following = saved.json["next_queue"]
                self.assertEqual(len(following["items"]), 3)
                self.assertEqual(following["summary"]["new_available"], 3)
                self.assertNotIn(first["source_id"], [item["source_id"] for item in following["items"]])
                retry = client.post("/api/practice/attempts?next_limit=3", json=payload)
                self.assertEqual(retry.json["data"], saved.json["data"])
                self.assertEqual(state.stats.overview()["total_words_practiced"], 1)

                # A newly due learning item must beat the earlier media previews.
                state.stats.db.execute("UPDATE word_memory SET due=?", (now.isoformat(),))
                state.stats.db.commit()
                due = client.post("/api/practice/attempts?next_limit=3", json=payload).json["next_queue"]
                self.assertEqual(due["items"][0]["source_id"], first["source_id"])
            finally:
                app.extensions["typing_practice_state"].close()

    def test_next_queue_failure_does_not_hide_a_committed_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection.anki2"
            make_anki_db(collection)
            app = create_app(make_config(root, str(collection)), start_background_tasks=False)
            try:
                state = app.extensions["typing_practice_state"]
                now = datetime(2026, 10, 30, 8, tzinfo=timezone.utc)
                state.memory.now = lambda: now
                client = app.test_client()
                first = client.get("/api/practice/queue?session_id=fallback").json["data"]["items"][0]
                now += timedelta(seconds=2)
                original_queue = state.memory.queue
                def fail_queue(*args, **kwargs):
                    raise RuntimeError("queue unavailable")
                state.memory.queue = fail_queue
                with self.assertLogs("app", level="ERROR"):
                    saved = client.post("/api/practice/attempts?next_limit=3", json={
                        "attempt_id": first["attempt_id"], "session_id": "fallback", "user_input": first["word"],
                        "duration_ms": 2000, "reviewed_at": now.isoformat(),
                    })
                self.assertEqual(saved.status_code, 200)
                self.assertTrue(saved.json["data"]["is_correct"])
                self.assertNotIn("next_queue", saved.json)
                self.assertEqual(state.stats.overview()["total_words_practiced"], 1)
                state.memory.queue = original_queue
                self.assertEqual(client.get("/api/practice/queue?session_id=fallback").json["data"]["items"], [])
            finally:
                app.extensions["typing_practice_state"].close()

    def test_scheduled_practice_uses_the_entire_pool_without_session_or_daily_quotas(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        collection = root / "collection.anki2"
        make_anki_db(collection, word_count=125)
        app = create_app(make_config(root, str(collection)), start_background_tasks=False)
        self.addCleanup(app.extensions["typing_practice_state"].close)
        state = app.extensions["typing_practice_state"]
        now = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)
        state.memory.now = lambda: now
        client = app.test_client()
        free = client.get("/api/practice/queue?session_id=free&mode=free").json["data"]
        self.assertEqual(len(free["items"]), 20)
        self.assertEqual(len({item["source_id"] for item in free["items"]}), 20)
        self.assertTrue(all("attempt_id" in item for item in free["items"]))
        self.assertEqual(state.stats.db.execute("SELECT COUNT(*) FROM practice_items").fetchone()[0], 20)
        limited = client.get("/api/practice/queue?session_id=free&mode=free&limit=5").json["data"]
        self.assertEqual(len(limited["items"]), 5)
        self.assertEqual(state.stats.overview()["total_words_practiced"], 0)

        practiced = set()
        for remaining in range(125, 0, -1):
            response = client.get("/api/practice/queue?session_id=whole-pool")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("session_limit", response.json)
            data = response.json["data"]
            self.assertEqual(data["summary"]["new_available"], remaining)
            self.assertEqual(len(data["items"]), 1)
            question = data["items"][0]
            practiced.add(question["source_id"])
            now += timedelta(seconds=1)
            response = client.post("/api/practice/attempts", json={
                "attempt_id": question["attempt_id"], "session_id": "whole-pool",
                "user_input": question["word"], "duration_ms": 1000, "reviewed_at": now.isoformat(),
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["data"]["rating"], 4)
        self.assertEqual(len(practiced), 125)
        empty = client.get("/api/practice/queue?session_id=whole-pool").json["data"]
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["summary"]["new_today"], 125)
        self.assertEqual(state.stats.overview()["total_words_practiced"], 125)

    def test_free_practice_saves_twenty_answers_and_can_review_before_due(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        collection = root / "collection.anki2"
        make_anki_db(collection, word_count=25)
        app = create_app(make_config(root, str(collection)), start_background_tasks=False)
        state = app.extensions["typing_practice_state"]
        self.addCleanup(state.close)
        now = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)
        state.memory.now = lambda: now
        client = app.test_client()
        items = client.get("/api/practice/queue?session_id=free&mode=free&limit=1000").json["data"]["items"]
        self.assertEqual(len(items), 20)
        for question in items:
            now += timedelta(seconds=1)
            response = client.post("/api/practice/attempts", json={
                "attempt_id": question["attempt_id"], "session_id": "free",
                "user_input": question["word"], "duration_ms": 1000, "reviewed_at": now.isoformat(),
            })
            self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/api/stats/overview").json["data"]["total_words_practiced"], 20)
        self.assertEqual(state.stats.db.execute("SELECT COUNT(*) FROM word_memory").fetchone()[0], 20)
        items = client.get("/api/practice/queue?session_id=early&mode=free").json["data"]["items"]
        question = next(item for item in items if item["card_version"] > 0)
        self.assertFalse(question["memory"]["is_due"])
        now += timedelta(seconds=1)
        payload = {"attempt_id": question["attempt_id"], "session_id": "early", "user_input": "",
                   "duration_ms": 1000, "reviewed_at": now.isoformat()}
        response = client.post("/api/practice/attempts", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"]["rating"], 1)
        self.assertEqual(response.json["data"]["card_version"], 2)
        self.assertNotEqual(response.json["data"]["memory"]["due"], question["memory"]["due"])
        self.assertEqual(client.post("/api/practice/attempts", json=payload).json, response.json)
        overview = client.get("/api/stats/overview").json["data"]
        self.assertEqual(overview["total_words_practiced"], 21)
        month = client.get("/api/stats/monthly-activity").json["data"]
        self.assertEqual(next(day for day in month["days"] if day["date"] == "2026-10-29")["words"], 21)

    def test_optimization_history_api_and_invalid_cursors(self):
        from test_optimizer_service import seed_history, candidate
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        app = create_app(make_config(Path(temporary.name)), start_background_tasks=False)
        self.addCleanup(app.extensions["typing_practice_state"].close)
        client = app.test_client()
        state = app.extensions["typing_practice_state"]
        self.assertEqual(client.get("/api/memory/optimization/runs").json["data"]["items"], [])
        seed_history(state.stats, state.memory)
        state.optimizer.trainer = candidate
        result = state.optimizer.check_once()
        status = client.get("/api/memory/optimization").json["data"]
        self.assertEqual(status["effective_reviews"], 1000)
        self.assertEqual(status["desired_retention"], 0.9)
        history = client.get("/api/memory/optimization/runs?limit=1").json["data"]
        self.assertEqual(history["items"][0]["id"], result["id"])
        record = client.get(f"/api/memory/optimization/runs/{result['id']}").json["data"]
        self.assertIn("candidate", record["report"])
        self.assertNotIn("owner", record)
        self.assertEqual(client.get("/api/memory/optimization/runs/999").status_code, 404)
        for query in ("before_id=-1", "before_id=abc"):
            self.assertEqual(client.get(f"/api/memory/optimization/runs?{query}").status_code, 400)

    def test_media_api_serves_illustrations_and_rejects_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection.anki2"
            make_anki_db(collection)
            media = root / "collection.media"
            media.mkdir()
            image_content = b"RIFF-test-WEBP"
            audio_content = b"ID3-test-audio"
            (media / "wa_abandon_img.webp").write_bytes(image_content)
            (media / "wa_abandon_uk.mp3").write_bytes(audio_content)
            app = create_app(make_config(root, str(collection)), start_background_tasks=False)
            try:
                client = app.test_client()
                word = client.get("/api/words").json["data"][0]
                with client.get(word["illustration_url"]) as response:
                    self.assertEqual(response.data, image_content)
                    self.assertEqual(response.mimetype, "image/webp")
                self.assertNotIn("audio_url", word)
                self.assertEqual(client.get("/api/media/101/audio").status_code, 404)
                for path in ("/api/media/999/audio", "/api/media/101/private", "/api/media/101/../collection.anki2"):
                    self.assertEqual(client.get(path).status_code, 404, path)
                (media / "wa_abandon_img.webp").unlink()
                self.assertEqual(client.get(word["illustration_url"]).status_code, 404)
            finally:
                app.extensions["typing_practice_state"].close()

    def test_media_directory_override_and_access_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection.anki2"
            make_anki_db(collection)
            media = root / "separate-media"
            media.mkdir()
            (media / "wa_abandon_img.webp").write_bytes(b"test-image")
            cfg = make_config(root, str(collection))
            cfg.anki.media_dir = str(media)
            app = create_app(replace(cfg, access_password="test-password"), start_background_tasks=False)
            try:
                client = app.test_client()
                path = "/api/media/101/illustration"
                self.assertEqual(client.get(path).status_code, 401)
                client.post("/login", data={"password": "test-password"})
                with client.get(path) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, b"test-image")
                    self.assertTrue(response.cache_control.no_store)
                versioned = client.get("/api/practice/queue?session_id=media").json["data"]["items"][0]["illustration_url"]
                self.assertIn("?v=", versioned)
                with client.get(versioned) as response:
                    self.assertTrue(response.cache_control.private)
                    self.assertEqual(response.cache_control.max_age, 31536000)
                    self.assertFalse(response.cache_control.no_store)
                    etag = response.headers["ETag"]
                with client.get(versioned, headers={"If-None-Match": etag}) as response:
                    self.assertEqual(response.status_code, 304)
                    self.assertTrue(response.cache_control.private)
                unauthorized = app.test_client().get(versioned)
                self.assertEqual(unauthorized.status_code, 401)
                self.assertTrue(unauthorized.cache_control.no_store)
                (media / "wa_abandon_img.webp").write_bytes(b"changed-image")
                changed = client.get("/api/practice/queue?session_id=media").json["data"]["items"][0]["illustration_url"]
                self.assertNotEqual(changed, versioned)
                with client.get(versioned) as response:
                    self.assertEqual(response.data, b"changed-image")
                    self.assertTrue(response.cache_control.no_store)
            finally:
                app.extensions["typing_practice_state"].close()

    def test_health_and_jinja_rendered_pages(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        app = create_app(make_config(Path(temporary.name)), start_background_tasks=False)
        app.testing = True
        self.addCleanup(app.extensions["typing_practice_state"].close)
        client = app.test_client()
        self.assertEqual(client.get("/api/health").json, {"success": True, "status": "ok"})
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn(b"vue@3.4.21", client.get("/").data)
        self.assertNotIn(b"<audio", client.get("/").data)
        self.assertNotIn(b"playPronunciation", client.get("/").data)
        self.assertIn(b"currentWord.illustration_url", client.get("/").data)
        page = client.get("/").data
        self.assertIn(b'aria-controls="practice-extra-meanings"', page)
        self.assertIn(b':aria-expanded="otherSensesExpanded"', page)
        self.assertLess(page.index(b'id="answer-input"'), page.index(b'class="practice-more-meanings"'))
        self.assertLess(page.index(b'class="practice-more-meanings"'), page.index(b'id="practice-extra-meanings"'))
        self.assertNotIn("IELTS 打字练习".encode(), client.get("/").data)
        self.assertNotIn(b"English Vocabulary Practice", client.get("/").data)
        self.assertNotIn("IELTS 打字练习".encode(), client.get("/stats.html").data)
        self.assertNotIn("IELTS 打字练习".encode(), client.get("/practice").data)
        self.assertIn("<title>词间 · 练习</title>".encode(), client.get("/").data)
        self.assertIn("<title>词间 · 统计</title>".encode(), client.get("/stats.html").data)
        self.assertEqual(client.get("/stats.html").status_code, 200)
        assets_response = client.get("/assets/style.css")
        source_response = client.get("/src/app.js")
        self.assertEqual(assets_response.status_code, 200)
        self.assertEqual(source_response.status_code, 200)
        assets_response.close()
        source_response.close()

    def test_practice_apis_return_all_chinese_senses_but_keep_the_primary_meaning(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection.anki2"
            make_anki_db(collection, word_count=2)
            with closing(sqlite3.connect(collection)) as db, db:
                for row in db.execute("SELECT id,flds FROM notes").fetchall():
                    fields = row[1].split(FIELD_SEPARATOR)
                    fields[WORD_ATLAS_FIELDS.index("MoreSenses")] = (
                        '<div class="atlas-sense"><span class="atlas-pos">n.</span> 放纵；放任'
                        '<p lang="en">A lack of restraint.</p></div>'
                    )
                    db.execute("UPDATE notes SET flds=? WHERE id=?", (FIELD_SEPARATOR.join(fields), row[0]))
            app = create_app(make_config(root, str(collection)), start_background_tasks=False)
            state = app.extensions["typing_practice_state"]
            try:
                client = app.test_client()
                now = datetime(2026, 10, 31, 8, tzinfo=timezone.utc)
                state.memory.now = lambda: now
                expected = [{"part_of_speech": "v.", "chinese_meaning": "放弃"},
                            {"part_of_speech": "n.", "chinese_meaning": "放纵；放任"}]
                self.assertEqual(client.get("/api/words").json["data"][0]["chinese_senses"], expected)
                for query in ("session_id=senses", "session_id=free&mode=free"):
                    items = client.get(f"/api/practice/queue?{query}").json["data"]["items"]
                    for item in items:
                        self.assertEqual(item["chinese_senses"], expected)
                        self.assertEqual(item["chinese_meaning"], "放弃")
                        self.assertEqual(item["part_of_speech"], "v.")
                question = client.get("/api/practice/queue?session_id=senses").json["data"]["items"][0]
                now += timedelta(seconds=1)
                response = client.post("/api/practice/attempts?next_limit=3", json={
                    "attempt_id": question["attempt_id"], "session_id": "senses", "user_input": question["word"],
                    "duration_ms": 1000, "reviewed_at": now.isoformat(),
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["next_queue"]["items"][0]["chinese_senses"], expected)
            finally:
                state.close()

    def test_anki_words_and_stats_api(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        anki_path = root / "collection.anki2"
        make_anki_db(anki_path)
        app = create_app(make_config(root, str(anki_path)), start_background_tasks=False)
        app.testing = True
        self.addCleanup(app.extensions["typing_practice_state"].close)
        client = app.test_client()

        response = client.get("/api/words?limit=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"][0]["word"], "abandon")
        self.assertEqual(response.json["data"][0]["phonetic"], "/əˈbændən/")
        self.assertEqual(response.json["data"][0]["part_of_speech"], "v.")
        self.assertEqual(response.json["data"][0]["chinese_meaning"], "放弃")
        self.assertEqual(response.json["data"][0]["example_en"], "Never abandon hope.")
        self.assertEqual(response.json["data"][0]["example_cn"], "永不放弃希望。")
        self.assertEqual(response.json["data"][0]["category"], "思维")

        state = app.extensions["typing_practice_state"]
        now = datetime(2026, 10, 27, 8, tzinfo=timezone.utc)
        state.memory.now = lambda: now
        question = client.get("/api/practice/queue?session_id=test-session").json["data"]["items"][0]
        now += timedelta(seconds=7)
        payload = {"attempt_id": question["attempt_id"], "session_id": "test-session", "user_input": "abandon",
                   "duration_ms": 7000, "reviewed_at": now.isoformat()}
        first = client.post("/api/practice/attempts", json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json["data"]["rating"], 3)
        self.assertEqual(client.post("/api/practice/attempts", json=payload).json, first.json)
        self.assertEqual(client.post("/api/stats/sessions", json={}).status_code, 410)
        overview = client.get("/api/stats/overview").json["data"]
        self.assertEqual(set(overview), {"total_words_practiced", "total_time_minutes", "current_streak"})
        self.assertEqual(overview["total_words_practiced"], 1)
        calendar = client.get("/api/stats/calendar").json["data"]
        day = next(day for day in calendar["days"] if day["date"] == "2026-10-27")
        self.assertEqual((day["practiced"], day["attempts"], day["accuracy"], day["due_count"]), (1, 1, 100.0, 1))
        memory = client.get("/api/memory/summary").json["data"]
        self.assertEqual(set(memory), {"total", "due_count", "new_available", "new_today", "next_due"})
        self.assertEqual(memory["new_available"], 0)
        day_words = client.get("/api/stats/calendar-words?date=2026-10-27").json["data"]
        self.assertEqual([item["word"] for item in day_words["practiced"]], ["abandon"])
        self.assertEqual([item["word"] for item in day_words["due"]], ["abandon"])
        for endpoint in (
            "/api/stats/calendar",
            "/api/stats/calendar-words?date=2026-10-27",
            "/api/stats/monthly-activity",
            "/api/stats/vocabulary-progress",
            "/api/stats/vocabulary-words?dimension=cefr&value=B2",
            "/api/stats/word-errors?source_id=abandon",
        ):
            result = client.get(endpoint)
            self.assertEqual(result.status_code, 200, endpoint)
            self.assertTrue(result.json["success"], endpoint)

        for endpoint in (
            "/api/stats/heatmap",
            "/api/stats/accuracy-trend",
            "/api/memory/forecast-words?date=2026-10-27",
            "/api/stats/mastery-distribution",
            "/api/stats/mastery-words?level=learning",
            "/api/stats/error-types",
            "/api/stats/error-type-words?type=missing_letter",
            "/api/stats/speed-trend",
            "/api/stats/daily-duration",
            "/api/stats/streak",
            "/api/stats/milestones",
        ):
            self.assertEqual(client.get(endpoint).status_code, 404, endpoint)

    def test_stats_failure_is_reported_instead_of_using_random_words(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        anki_path = root / "collection.anki2"
        make_anki_db(anki_path)
        app = create_app(make_config(root, str(anki_path)), start_background_tasks=False)
        app.testing = True
        self.addCleanup(app.extensions["typing_practice_state"].close)
        state = app.extensions["typing_practice_state"]

        def fail_selection(*args, **kwargs):
            raise OSError("stats database is unavailable")

        state.memory.queue = fail_selection
        response = app.test_client().get("/api/practice/queue?session_id=test")
        self.assertEqual(response.status_code, 503)
        self.assertIn("暂不可用", response.json["error"])


if __name__ == "__main__":
    unittest.main()

