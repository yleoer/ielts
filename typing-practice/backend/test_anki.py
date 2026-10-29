from __future__ import annotations

import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from anki import AnkiReader, FIELD_SEPARATOR, WORD_ATLAS_FIELDS, clean_field, media_filename, parse_word
from config import AnkiConfig, DEFAULT_DECK_ID, DEFAULT_DECK_NAME, load_config


def atlas_fields(**changes: str) -> str:
    fields = {name: "" for name in WORD_ATLAS_FIELDS}
    fields.update({
        "Word": "library", "UK": "/ˈlaɪbrəri/", "US": "/ˈlaɪbreri/",
        "PartOfSpeech": "n.", "MeaningZH": "图书馆；藏书室",
        "MeaningEN": "A place where people read or borrow books.",
        "MoreSenses": '<div class="atlas-sense">资料库</div>',
        "ExampleEN": 'I borrowed books from the <mark>library</mark>.',
        "ExampleZH": "我从图书馆借了书。", "IELTSExampleEN": "Public libraries support lifelong learning.",
        "IELTSExampleZH": "公共图书馆支持终身学习。", "CEFR": "A1", "Topic": "教育",
        "Illustration": '<img src="wa_library_img.webp">',
        "AudioUK": "[sound:wa_library_uk.mp3]", "AudioUS": "[sound:wa_library_us.mp3]",
        "AudioExample": "[sound:wa_library_ex.mp3]", "SourceId": "library",
    })
    fields.update(changes)
    return FIELD_SEPARATOR.join(fields[name] for name in WORD_ATLAS_FIELDS)


class WordAtlasFieldTest(unittest.TestCase):
    def test_maps_word_atlas_fields_without_positional_mixups(self):
        word = parse_word(101, atlas_fields())
        self.assertEqual(word, {
            "id": 101, "source_id": "library", "word": "library", "phonetic": "/ˈlaɪbrəri/",
            "part_of_speech": "n.", "chinese_meaning": "图书馆；藏书室",
            "example_en": "I borrowed books from the library.",
            "example_cn": "我从图书馆借了书。", "category": "教育",
            "illustration_url": "/api/media/101/illustration",
        })

    def test_media_references_are_local_and_only_illustrations_are_exposed(self):
        values = dict(zip(WORD_ATLAS_FIELDS, atlas_fields(AudioUK="").split(FIELD_SEPARATOR)))
        self.assertEqual(media_filename(values, "audio"), "")
        self.assertEqual(media_filename(values, "illustration"), "wa_library_img.webp")
        for reference in ("../outside.webp", "..\\outside.webp", "https://example.com/a.webp", "C:\\a.webp", "file.svg"):
            with self.subTest(reference=reference):
                word = parse_word(101, atlas_fields(Illustration=f'<img src="{reference}">'))
                self.assertEqual(word["illustration_url"], "")
        word = parse_word(101, atlas_fields(Illustration="", AudioUK="", AudioUS=""))
        self.assertEqual(word["illustration_url"], "")
        self.assertNotIn("audio_url", word)

    def test_only_accepts_the_22_field_word_atlas_layout(self):
        old = FIELD_SEPARATOR.join(["library", "/ipa/", "n.", "图书馆", "Example", "译文", "", "core"])
        self.assertIsNone(parse_word(101, old))
        self.assertIsNone(parse_word(101, atlas_fields() + FIELD_SEPARATOR + "extra"))
        self.assertIsNone(parse_word(101, FIELD_SEPARATOR.join(atlas_fields().split(FIELD_SEPARATOR)[:-1])))
        self.assertIsNone(parse_word(101, atlas_fields(MeaningZH="")))
        self.assertIsNone(parse_word(101, atlas_fields(Word="")))

    def test_uses_us_when_uk_is_empty_and_allows_optional_content_to_be_empty(self):
        word = parse_word(101, atlas_fields(UK="", PartOfSpeech="", ExampleEN="", ExampleZH="", Topic=""))
        self.assertEqual(word["phonetic"], "/ˈlaɪbreri/")
        self.assertEqual(word["part_of_speech"], "")
        self.assertEqual(word["example_en"], "")
        self.assertEqual(word["example_cn"], "")
        self.assertEqual(word["category"], "")

    def test_removes_html_before_decoding_escaped_text(self):
        self.assertEqual(clean_field("<mark>A &amp; B</mark><br>&lt;3 &gt;2"), "A & B\n<3 >2")

    def test_default_configuration_targets_word_atlas(self):
        self.assertEqual(AnkiConfig().deck_name, "Word Atlas")
        self.assertEqual(AnkiConfig().deck_id, 1958430017)
        with patch("config.load_dotenv"), patch("config.default_anki_db_path", return_value=""), patch.dict("os.environ", {}, clear=True):
            config = load_config()
            with patch("config._config_path", return_value=None):
                fallback = load_config()
        self.assertEqual(config.anki.deck_name, DEFAULT_DECK_NAME)
        self.assertEqual(config.anki.deck_id, DEFAULT_DECK_ID)
        self.assertEqual(fallback.anki.deck_name, DEFAULT_DECK_NAME)
        self.assertEqual(fallback.anki.deck_id, DEFAULT_DECK_ID)

    def test_media_directory_environment_overrides_yaml(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.yaml"
            path.write_text('anki:\n  media_dir: "from-yaml"\n', encoding="utf-8")
            with patch("config.load_dotenv"), patch("config.default_anki_db_path", return_value=""), patch("config._config_path", return_value=path), patch.dict("os.environ", {"ANKI_MEDIA_DIR": "from-env"}, clear=True):
                self.assertEqual(load_config().anki.media_dir, "from-env")


class WordAtlasReaderTest(unittest.TestCase):
    def test_learned_words_are_unique_and_include_child_decks(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "collection.anki2"
            with closing(sqlite3.connect(path)) as db:
                db.executescript("""
                    CREATE TABLE decks(id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE notes(id INTEGER PRIMARY KEY, flds TEXT);
                    CREATE TABLE cards(id INTEGER PRIMARY KEY,nid INTEGER,did INTEGER,type INTEGER,queue INTEGER);
                    INSERT INTO decks VALUES(1,'Word Atlas'),(2,'Word Atlas::工作'),(3,'Other');
                    INSERT INTO cards VALUES(201,101,1,1,1),(202,101,1,2,2),(203,102,1,0,0),
                                            (204,103,2,2,2),(205,104,3,2,2);
                """)
                db.executemany("INSERT INTO notes VALUES(?,?)", [
                    (101, atlas_fields()),
                    (102, atlas_fields(Word="unlearned")),
                    (103, atlas_fields(Word="commute", PartOfSpeech="v.", MeaningZH="通勤", Topic="工作")),
                    (104, atlas_fields(Word="outside")),
                ])
                db.commit()
            reader = AnkiReader(str(path), "Word Atlas", DEFAULT_DECK_ID)
            try:
                self.assertEqual(reader.count_learned(), 2)
                self.assertEqual([word["word"] for word in reader.get_learned_word_pool()], ["library", "commute"])
                self.assertEqual(reader.get_learned_words(10, "教育")[0]["word"], "library")
                self.assertEqual(reader.get_word_by_id(103)["part_of_speech"], "v.")
                self.assertEqual(reader.get_media_filename(101, "illustration"), "wa_library_img.webp")
                self.assertEqual(reader.get_media_filename(101, "audio"), "")
                self.assertEqual(reader.get_media_filename(999, "audio"), "")
            finally:
                reader.close()

    @unittest.skipUnless((Path(__file__).resolve().parents[2] / "apkg-generator/anki_export/word-atlas/Word Atlas.apkg").is_file(),
                         "本地完整 Word Atlas APKG 不存在")
    def test_actual_word_atlas_package_is_read_with_correct_meanings(self):
        package = Path(__file__).resolve().parents[2] / "apkg-generator/anki_export/word-atlas/Word Atlas.apkg"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "collection.anki2"
            with zipfile.ZipFile(package) as source:
                path.write_bytes(source.read("collection.anki2"))
            # Mark two cards learned only in this disposable copy, never in Anki or the APKG.
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE cards SET type=1,queue=1 WHERE ord=0 AND nid IN (SELECT id FROM notes ORDER BY id LIMIT 2)")
                db.commit()
            reader = AnkiReader(str(path), DEFAULT_DECK_NAME, DEFAULT_DECK_ID)
            try:
                words = reader.get_learned_word_pool()
                self.assertEqual(len(words), 2)
                self.assertEqual(words[0]["word"], "library")
                self.assertEqual(words[0]["part_of_speech"], "n.")
                self.assertEqual(words[0]["chinese_meaning"], "图书馆；藏书室")
                self.assertEqual(words[0]["phonetic"], "/ˈlaɪbrəri/")
                self.assertEqual(words[0]["category"], "教育")
                self.assertIn("I borrowed three books", words[0]["example_en"])
                self.assertEqual(words[1]["word"], "Thursday")
            finally:
                reader.close()


if __name__ == "__main__":
    unittest.main()
