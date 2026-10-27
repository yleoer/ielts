from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from config import AnkiConfig, Config, PracticeConfig, ServerConfig, StatsConfig
from stats import analyze_error_type


def make_config(root: Path, anki_path: str = "") -> Config:
    return Config(
        server=ServerConfig(host="127.0.0.1", port=0),
        anki=AnkiConfig(db_path=anki_path, deck_name="IELTS Vocabulary", deck_id=1),
        practice=PracticeConfig(default_limit=20, max_limit=100),
        stats=StatsConfig(db_path=str(root / "stats.db")),
    )


def make_anki_db(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE decks(id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE notes(id INTEGER PRIMARY KEY, flds TEXT);
        CREATE TABLE cards(id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER, type INTEGER, queue INTEGER);
        INSERT INTO decks(id,name) VALUES(1,'IELTS Vocabulary');
        INSERT INTO notes(id,flds) VALUES(101,'abandon\x1f/əˈbændən/\x1fverb\x1f放弃\x1fto leave\x1f离开\x1f\x1fcore');
        INSERT INTO cards(id,nid,did,type,queue) VALUES(201,101,1,1,1);
        """
    )
    db.commit()
    db.close()


class FlaskAppTest(unittest.TestCase):
    def test_health_and_jinja_rendered_pages(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        app = create_app(make_config(Path(temporary.name)))
        app.testing = True
        self.addCleanup(app.extensions["typing_practice_state"].close)
        client = app.test_client()
        self.assertEqual(client.get("/api/health").json, {"success": True, "status": "ok"})
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn(b"vue@3.4.21", client.get("/").data)
        self.assertEqual(client.get("/stats.html").status_code, 200)
        assets_response = client.get("/assets/style.css")
        source_response = client.get("/src/app.js")
        self.assertEqual(assets_response.status_code, 200)
        self.assertEqual(source_response.status_code, 200)
        assets_response.close()
        source_response.close()

    def test_anki_words_and_stats_api(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        anki_path = root / "collection.anki2"
        make_anki_db(anki_path)
        app = create_app(make_config(root, str(anki_path)))
        app.testing = True
        self.addCleanup(app.extensions["typing_practice_state"].close)
        client = app.test_client()

        response = client.get("/api/words?limit=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"][0]["word"], "abandon")

        payload = {
                "session_id": "test-session",
                "start_time": "2026-10-27T08:00:00Z",
                "end_time": "2026-10-27T08:01:00Z",
                "total_words": 2,
                "correct_words": 1,
                "incorrect_words": 1,
                "accuracy": 50,
                "duration_seconds": 60,
                "word_attempts": [
                    {"word": "abandon", "chinese_meaning": "放弃", "user_input": "abandon", "is_correct": True, "time_spent": 2},
                    {"word": "wrong", "chinese_meaning": "错误", "user_input": "wron", "is_correct": False, "time_spent": 5},
                ],
        }
        self.assertEqual(client.post("/api/stats/sessions", json=payload).status_code, 200)
        self.assertEqual(client.post("/api/stats/sessions", json=payload).status_code, 200)
        overview = client.get("/api/stats/overview").json["data"]
        self.assertEqual(overview["total_sessions"], 1)
        self.assertEqual(overview["total_words_practiced"], 2)
        heatmap = client.get("/api/stats/heatmap?start_date=2026-10-27&end_date=2026-10-27").json["data"]
        self.assertEqual(heatmap, [{"date": "2026-10-27", "words": 2, "accuracy": 50.0}])
        self.assertEqual(client.get("/api/stats/error-types").json["data"]["missing_letter"], 1)
        for endpoint in (
            "/api/stats/heatmap",
            "/api/stats/accuracy-trend",
            "/api/stats/mastery-distribution",
            "/api/stats/mastery-words?level=learning",
            "/api/stats/mastery-words?level=new",
            "/api/stats/error-type-words?type=missing_letter",
        ):
            result = client.get(endpoint)
            self.assertEqual(result.status_code, 200, endpoint)
            self.assertTrue(result.json["success"], endpoint)

        for endpoint in (
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
        app = create_app(make_config(root, str(anki_path)))
        app.testing = True
        self.addCleanup(app.extensions["typing_practice_state"].close)
        state = app.extensions["typing_practice_state"]

        def fail_selection():
            raise OSError("stats database is unavailable")

        state.stats.selection_stats = fail_selection
        response = app.test_client().get("/api/words?limit=5")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "Practice statistics are unavailable")

    def test_error_type_rules(self):
        self.assertEqual(analyze_error_type("abandon", ""), "skipped")
        self.assertEqual(analyze_error_type("abandon", "abandn"), "missing_letter")
        self.assertEqual(analyze_error_type("abandon", "abandonx"), "extra_letter")
        self.assertEqual(analyze_error_type("abandon", "zzzzzz"), "completely_wrong")


if __name__ == "__main__":
    unittest.main()

