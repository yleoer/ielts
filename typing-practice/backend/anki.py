"""Read-only access to an Anki collection database."""

from __future__ import annotations

import html
import re
import sqlite3
import threading
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote


FIELD_SEPARATOR = "\x1f"
EXCLUDED_TAG = "word_atlas::excluded"
CANONICAL_TAG_PREFIX = "word_atlas::canonical::"
HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".avif"}
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
        if tag == "img" and not self.filename:
            self.filename = dict(attrs).get("src") or ""


class _ChineseSensesParser(HTMLParser):
    """Read Word Atlas sense blocks without their English explanations."""

    def __init__(self, markup: str):
        super().__init__(convert_charrefs=True)
        self.senses = []
        self._sense = None
        self._field = None
        self.feed(markup)
        self.close()
        self._finish_sense()

    def _finish_sense(self):
        if self._sense is not None:
            sense = {key: "".join(parts).strip() for key, parts in self._sense.items()}
            if sense["chinese_meaning"]:
                self.senses.append(sense)
            self._sense = None
            self._field = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "div" and "atlas-sense" in classes:
            self._finish_sense()
            self._sense = {"part_of_speech": [], "chinese_meaning": []}
            self._field = "chinese_meaning"
        elif self._sense is not None:
            if tag == "span" and "atlas-pos" in classes:
                self._field = "part_of_speech"
            elif tag == "p" and (attributes.get("lang") or "").lower().split("-")[0] == "en":
                self._field = None
            elif tag == "br" and self._field:
                self._sense[self._field].append("\n")

    def handle_endtag(self, tag):
        if self._sense is None:
            return
        if tag in {"span", "p"}:
            self._field = "chinese_meaning"
        elif tag == "div":
            self._finish_sense()

    def handle_data(self, data):
        if self._sense is not None and self._field:
            self._sense[self._field].append(data)


def illustration_filename(markup: str) -> str:
    """The local image named by the Illustration field, or "" for paths, URLs and other types."""
    filename = _IllustrationParser(markup).filename
    if not filename or filename.startswith(".") or any(char in filename for char in "/\\:\x00"):
        return ""
    return filename if Path(filename).suffix.lower() in IMAGE_EXTENSIONS else ""


def clean_field(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = HTML_TAG_PATTERN.sub("", value)
    return html.unescape(value).strip()


def parse_word(note_id: int, raw_fields: str) -> dict[str, Any] | None:
    fields = raw_fields.split(FIELD_SEPARATOR)
    if len(fields) != len(WORD_ATLAS_FIELDS):
        return None
    values = dict(zip(WORD_ATLAS_FIELDS, fields))
    word = {
        "id": note_id,
        "source_id": clean_field(values["SourceId"]),
        "word": clean_field(values["Word"]),
        "phonetic": clean_field(values["UK"]) or clean_field(values["US"]),
        "part_of_speech": clean_field(values["PartOfSpeech"]),
        "chinese_meaning": clean_field(values["MeaningZH"]),
        "example_en": clean_field(values["ExampleEN"]),
        "example_cn": clean_field(values["ExampleZH"]),
        "category": clean_field(values["Topic"]),
        "cefr": clean_field(values["CEFR"]).upper(),
        "illustration_file": illustration_filename(values["Illustration"]),
    }
    if not word["word"] or not word["chinese_meaning"]:
        return None
    word["chinese_senses"] = [
        {"part_of_speech": word["part_of_speech"], "chinese_meaning": word["chinese_meaning"]},
        *_ChineseSensesParser(values["MoreSenses"]).senses,
    ]
    return word


class AnkiReader:
    def __init__(self, db_path: str, deck_name: str, deck_id: int):
        self.db_path = Path(db_path).expanduser()
        self._lock = threading.Lock()
        self.db = self._open()
        self.deck_ids = self._resolve_deck_ids(deck_name.strip(), int(deck_id))
        self._version = None
        self._words: list[dict[str, Any]] = []

    def _open(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise FileNotFoundError(f"Anki database not found at {self.db_path}")
        # The first URI allows a live WAL to be read. Immutable mode is a
        # fallback for copied collections that do not expose a WAL file.
        uri_path = quote(self.db_path.resolve().as_posix(), safe="/:\\")
        for suffix in ("?mode=ro", "?mode=ro&immutable=1"):
            db = sqlite3.connect(f"file:{uri_path}{suffix}", uri=True, check_same_thread=False, timeout=5)
            try:
                # Reading the schema is the first access that actually opens the file.
                db.execute("SELECT 1 FROM sqlite_master LIMIT 1")
                return db
            except sqlite3.Error as exc:
                db.close()
                error = exc
        raise error

    def close(self) -> None:
        with self._lock:
            self.db.close()

    def _resolve_deck_ids(self, deck_name: str, deck_id: int) -> list[int]:
        """The named deck and its children, or the configured id when the name is absent."""
        rows = self.db.execute("SELECT id, name FROM decks").fetchall()
        exact = [int(row_id) for row_id, name in rows if name == deck_name]
        children = [int(row_id) for row_id, name in rows if name.startswith(deck_name + "::")]
        return exact + children or [deck_id]

    def snapshot(self) -> list[dict[str, Any]]:
        """Non-excluded deck words with `learned` and illustration names (format 1).

        The parsed list is cached until the collection changes; callers must not mutate it.
        """
        placeholders = ",".join("?" * len(self.deck_ids))
        with self._lock:
            # data_version also notices commits still in a live collection's WAL.
            version = self.db.execute("PRAGMA data_version").fetchone()[0]
            if version != self._version:
                rows = self.db.execute(f"""
                    SELECT n.id, n.flds, n.tags, c.learned FROM notes n JOIN (
                        SELECT nid, MAX(type >= 1 OR queue >= 2) AS learned FROM cards
                        WHERE did IN ({placeholders}) GROUP BY nid
                    ) c ON c.nid = n.id
                    ORDER BY n.id
                """, self.deck_ids).fetchall()
                words, learned_aliases = [], set()
                for note_id, fields, raw_tags, learned in rows:
                    tags = set(raw_tags.split())
                    if EXCLUDED_TAG in tags:
                        if learned:
                            learned_aliases.update(tag[len(CANONICAL_TAG_PREFIX):] for tag in tags
                                                   if tag.startswith(CANONICAL_TAG_PREFIX))
                        continue
                    if word := parse_word(int(note_id), fields):
                        words.append({**word, "learned": bool(learned)})
                for word in words:
                    if word["source_id"] in learned_aliases:
                        word["learned"] = True
                self._words = words
                self._version = version
            return self._words
