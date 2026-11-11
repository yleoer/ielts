"""Server-owned vocabulary snapshots and the first discovery of learned words."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ledger import time_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS vocabulary_snapshot (
    id INTEGER PRIMARY KEY CHECK(id=1),
    checked_at TEXT NOT NULL,
    learned_count INTEGER NOT NULL,
    words_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS anki_learned_words (source_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS vocabulary_sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at TEXT NOT NULL,
    before_words INTEGER NOT NULL,
    after_words INTEGER NOT NULL,
    added_words INTEGER NOT NULL,
    added_word_list TEXT NOT NULL
);
"""


class VocabularyStore:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def refresh(self, words: list[dict[str, Any]]) -> int:
        """Publish a successful scan; the first scan establishes a quiet baseline."""
        learned = [word for word in words if word["learned"]]
        sources = [word["source_id"] for word in learned]
        if any(not source for source in sources) or len(set(sources)) != len(sources):
            raise ValueError("已学词条需要唯一且非空的 SourceId")
        checked_at = time_text(datetime.now(timezone.utc))
        with self.lock, self.db:
            previous = self.db.execute("SELECT learned_count FROM vocabulary_snapshot WHERE id=1").fetchone()
            seen = {row[0] for row in self.db.execute("SELECT source_id FROM anki_learned_words")}
            added = [{key: word[key] for key in ("id", "source_id", "word", "chinese_meaning", "category")}
                     for word in learned if word["source_id"] not in seen]
            if previous is not None and added:
                self.db.execute("""INSERT INTO vocabulary_sync_history
                    (synced_at,before_words,after_words,added_words,added_word_list) VALUES(?,?,?,?,?)""",
                                (checked_at, previous[0], len(learned), len(added), json.dumps(added, ensure_ascii=False)))
            self.db.executemany("INSERT OR IGNORE INTO anki_learned_words VALUES(?)", [(source,) for source in sources])
            self.db.execute("INSERT OR REPLACE INTO vocabulary_snapshot VALUES(1,?,?,?)",
                            (checked_at, len(learned), json.dumps(words, ensure_ascii=False)))
        return len(learned)

    def snapshot(self) -> dict[str, Any]:
        """Read the last successful scan, including its 50 most recent batches."""
        with self.lock:
            row = self.db.execute("SELECT checked_at,words_json FROM vocabulary_snapshot WHERE id=1").fetchone()
            if row is None:
                raise RuntimeError("Anki 数据库不可用，尚无成功检查的词库")
            history = [dict(item) for item in self.db.execute(
                "SELECT * FROM vocabulary_sync_history ORDER BY id DESC LIMIT 50")]
        for item in history:
            item["added_word_list"] = json.loads(item["added_word_list"])
        return {"generated_at": row["checked_at"], "last_anki_sync_at": row["checked_at"],
                "words": json.loads(row["words_json"]), "sync_history": history}
