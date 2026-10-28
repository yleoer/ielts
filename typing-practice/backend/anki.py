"""Read-only access to an Anki collection database."""

from __future__ import annotations

import html
import json
import re
import sqlite3
import threading
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote


FIELD_SEPARATOR = "\x1f"
HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
WORD_ATLAS_FIELDS = (
    "Word", "UK", "US", "PartOfSpeech", "MeaningZH", "MeaningEN", "MoreSenses",
    "ExampleEN", "ExampleZH", "IELTSExampleEN", "IELTSExampleZH", "Collocations",
    "Tip", "Extra", "CEFR", "Topic", "Illustration", "AudioUK", "AudioUS",
    "AudioExample", "AudioIELTS", "SourceId",
)


class _IllustrationParser(HTMLParser):
    def __init__(self, markup: str):
        super().__init__(convert_charrefs=True)
        self.filename = ""
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img" and not self.filename:
            self.filename = dict(attrs).get("src", "") or ""


def media_filename(values: dict[str, str], kind: str) -> str:
    if kind == "illustration":
        filename = _IllustrationParser(values.get("Illustration", "")).filename
        extensions = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".avif"}
    elif kind == "audio":
        filename = ""
        for field in ("AudioUK", "AudioUS"):
            match = re.search(r"\[sound:([^\]]+)\]", values.get(field, ""))
            if match:
                filename = html.unescape(match.group(1))
                break
        extensions = {".mp3", ".ogg", ".wav", ".m4a"}
    else:
        return ""
    if not filename or filename.startswith(".") or any(char in filename for char in "/\\:\x00"):
        return ""
    return filename if Path(filename).suffix.lower() in extensions else ""


def clean_field(value: str) -> str:
    value = value or ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = HTML_TAG_PATTERN.sub("", value)
    return html.unescape(value).strip()


def parse_word(note_id: int, raw_fields: str) -> dict[str, Any] | None:
    fields = (raw_fields or "").split(FIELD_SEPARATOR)
    if len(fields) != len(WORD_ATLAS_FIELDS):
        return None
    values = dict(zip(WORD_ATLAS_FIELDS, fields))
    word = {
        "id": note_id,
        "word": clean_field(values["Word"]),
        "phonetic": clean_field(values["UK"]) or clean_field(values["US"]),
        "part_of_speech": clean_field(values["PartOfSpeech"]),
        "chinese_meaning": clean_field(values["MeaningZH"]),
        "example_en": clean_field(values["ExampleEN"]),
        "example_cn": clean_field(values["ExampleZH"]),
        "category": clean_field(values["Topic"]),
        "illustration_url": f"/api/media/{note_id}/illustration" if media_filename(values, "illustration") else "",
        "audio_url": f"/api/media/{note_id}/audio" if media_filename(values, "audio") else "",
    }
    if not word["word"] or not word["chinese_meaning"]:
        return None
    return word


class AnkiReader:
    def __init__(self, db_path: str, deck_name: str, deck_id: int):
        self.db_path = str(Path(db_path).expanduser())
        self.deck_name = deck_name.strip()
        self.deck_id = int(deck_id)
        self.deck_ids: list[int] = []
        self._lock = threading.RLock()
        self.db = self._open()
        try:
            self.deck_ids = self._resolve_deck_ids()
            if self.deck_ids:
                self.deck_id = self.deck_ids[0]
        except sqlite3.Error:
            self.deck_ids = [self.deck_id] if self.deck_id else []

    def _open(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        if not path.is_file():
            raise FileNotFoundError(f"Anki database not found at {path}")
        # The first URI allows a live WAL to be read. Immutable mode is a
        # fallback for copied collections that do not expose a WAL file.
        uri_path = quote(path.resolve().as_posix(), safe="/:\\")
        errors: list[Exception] = []
        for suffix in (
            "?mode=ro&cache=shared&_busy_timeout=5000",
            "?mode=ro&immutable=1&cache=shared&_busy_timeout=5000",
        ):
            try:
                db = sqlite3.connect(
                    f"file:{uri_path}{suffix}",
                    uri=True,
                    check_same_thread=False,
                    timeout=5,
                )
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA busy_timeout = 5000")
                db.execute("SELECT 1")
                return db
            except Exception as exc:  # pragma: no cover - depends on SQLite file state
                errors.append(exc)
        raise errors[-1]

    def close(self) -> None:
        with self._lock:
            if self.db:
                self.db.close()

    def reopen(self) -> None:
        with self._lock:
            self.close()
            self.db = self._open()
            self.deck_ids = self._resolve_deck_ids()
            if self.deck_ids:
                self.deck_id = self.deck_ids[0]

    def _resolve_deck_ids(self) -> list[int]:
        if self.deck_name:
            try:
                rows = self.db.execute("SELECT id, name FROM decks").fetchall()
                exact = [int(row["id"]) for row in rows if row["name"] == self.deck_name]
                children = [
                    int(row["id"])
                    for row in rows
                    if isinstance(row["name"], str)
                    and row["name"].startswith(self.deck_name + "::")
                ]
                if exact or children:
                    return exact + children
            except sqlite3.Error:
                pass
            try:
                raw = self.db.execute("SELECT decks FROM col LIMIT 1").fetchone()
                decks = json.loads(raw[0] or "{}") if raw else {}
                exact: list[int] = []
                children: list[int] = []
                for key, deck in decks.items():
                    name = deck.get("name", "")
                    if name == self.deck_name:
                        exact.append(int(key))
                    elif name.startswith(self.deck_name + "::"):
                        children.append(int(key))
                if exact or children:
                    return exact + children
            except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError):
                pass
        return [self.deck_id] if self.deck_id else []

    def _learned_deck_ids(self) -> list[int]:
        return self.deck_ids or ([self.deck_id] if self.deck_id else [0])

    def _deck_placeholders(self) -> str:
        return ",".join("?" for _ in self._learned_deck_ids())

    def _read_words(self, query: str, args: list[Any], category: str, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(query, args).fetchall()
        words: list[dict[str, Any]] = []
        for row in rows:
            word = parse_word(int(row["id"]), row["flds"])
            if not word:
                continue
            if category != "all" and word["category"].lower() != category.lower():
                continue
            words.append(word)
            if limit and len(words) >= limit:
                break
        return words

    def get_learned_words(self, limit: int, category: str = "all") -> list[dict[str, Any]]:
        category = category.strip() or "all"
        query_limit = limit if category.lower() == "all" else min(max(limit * 20, 100), 1000)
        query = f"""
            SELECT n.id, n.flds
            FROM notes n
            WHERE n.id IN (
                SELECT DISTINCT c.nid FROM cards c
                WHERE c.did IN ({self._deck_placeholders()})
                  AND (c.type >= 1 OR c.queue >= 2)
            )
            ORDER BY RANDOM() LIMIT ?
        """
        return self._read_words(query, self._learned_deck_ids() + [query_limit], category, limit)

    def get_learned_word_pool(self, category: str = "all") -> list[dict[str, Any]]:
        category = category.strip() or "all"
        query = f"""
            SELECT n.id, n.flds
            FROM notes n
            WHERE n.id IN (
                SELECT DISTINCT c.nid FROM cards c
                WHERE c.did IN ({self._deck_placeholders()})
                  AND (c.type >= 1 OR c.queue >= 2)
            )
            ORDER BY n.id
        """
        return self._read_words(query, self._learned_deck_ids(), category)

    def get_word_by_id(self, note_id: int) -> dict[str, Any]:
        with self._lock:
            row = self.db.execute("SELECT flds FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            raise KeyError(f"note {note_id} not found")
        word = parse_word(note_id, row["flds"])
        if not word:
            raise ValueError(f"note {note_id} does not contain the expected word fields")
        return word

    def get_media_filename(self, note_id: int, kind: str) -> str:
        with self._lock:
            row = self.db.execute("SELECT flds FROM notes WHERE id = ?", (note_id,)).fetchone()
        fields = row["flds"].split(FIELD_SEPARATOR) if row else []
        if len(fields) != len(WORD_ATLAS_FIELDS):
            return ""
        return media_filename(dict(zip(WORD_ATLAS_FIELDS, fields)), kind)

    def count_learned(self) -> int:
        query = f"""
            SELECT COUNT(DISTINCT c.nid) FROM cards c
            WHERE c.did IN ({self._deck_placeholders()})
              AND (c.type >= 1 OR c.queue >= 2)
        """
        with self._lock:
            return int(self.db.execute(query, self._learned_deck_ids()).fetchone()[0])

