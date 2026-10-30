"""Content safety, missing media, and a real genanki/SQLite package round trip."""
import importlib.util
import html
import json
import re
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_word_atlas.py"
SPEC = importlib.util.spec_from_file_location("word_atlas", SCRIPT)
atlas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(atlas)
TEST_IDS = ("sustainable", "commute", "innovation", "curriculum", "consequence",
            "allocate", "resilience", "ambiguous", "feasible", "library")


def render_anki_template(template, fields, renderer):
    # Anki inserts stored field HTML verbatim, unlike chevron's default escaping.
    raw = re.sub(r"\{\{(\w+)\}\}", r"{{{\1}}}", template)
    return renderer.render(raw, fields)


def entry():
    return {"id": "test", "w": "test", "uk": "/test/", "us": "/test/",
            "senses": [{"pos": "n.", "zh": "测试", "en": "A test."}],
            "ex": [{"en": "A test & another test.", "zh": "一个测试。"}],
            "cefr": "B2", "topic": "education", "col": [], "fam": [],
            "syn": [], "ant": [], "tip": "", "note": ""}


class ContentTests(unittest.TestCase):
    def test_source_html_is_escaped_before_emphasis(self):
        result = atlas.highlighted('<script>test & tests</script>', "test")
        self.assertEqual(result, '&lt;script&gt;<mark>test</mark> &amp; tests&lt;/script&gt;')
        sample = entry()
        sample["senses"][0]["zh"] = '<img src="x" onerror="alert(1)">'
        self.assertNotIn("<img", atlas.build_fields(sample, {})["MeaningZH"])

    def test_optional_content_and_collocations(self):
        sample = entry()
        sample["col"] = ["test case｜测试用例", "plain expression"]
        fields = atlas.build_fields(sample, {})
        self.assertEqual(fields["Extra"], "")
        self.assertEqual(fields["MoreSenses"], "")
        self.assertEqual(fields["IELTSExampleEN"], "")
        self.assertIn("测试用例", fields["Collocations"])
        self.assertIn("plain expression", fields["Collocations"])

    def test_selection_rejects_unknown_or_duplicate_ids(self):
        for ids in (["unknown"], ["test", "test"], []):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                atlas.select_entries([entry()], ids)

    def test_media_names_keep_accents_separate_and_missing_files_are_omitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for accent in ("uk", "us"):
                folder = root / "source/audio" / accent
                folder.mkdir(parents=True)
                (folder / "test.mp3").write_bytes(accent.encode())
            output = root / "output"
            output.mkdir()
            fields, report = atlas.copy_media(entry(), 15, root / "source", output)
            self.assertEqual((output / "wa_test_uk.mp3").read_bytes(), b"uk")
            self.assertEqual((output / "wa_test_us.mp3").read_bytes(), b"us")
            self.assertNotEqual(fields["AudioUK"], fields["AudioUS"])
            self.assertEqual(fields["Illustration"], "")
            self.assertEqual(fields["AudioExample"], "")
            self.assertEqual(sum(item["available"] for item in report), 2)
            undeclared, _ = atlas.copy_media(entry(), 0, root / "source", output)
            self.assertEqual(undeclared["AudioUK"], "")


@unittest.skipUnless(Path("D:/me/word-atlas-main/dist/atlas/index.json").is_file()
                     and Path("D:/me/genanki/genanki/__init__.py").is_file(),
                     "需要本地 Word Atlas 和 genanki 源仓库")
class PackageTests(unittest.TestCase):
    def test_study_plan_upgrade_preserves_cards_notes_and_media(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            report = atlas.generate(Path("D:/me/word-atlas-main"), Path("D:/me/genanki"),
                                    output, ["library", "sustainable"])
            package_path = Path(report["package"])
            with zipfile.ZipFile(package_path) as package:
                members = {name: package.read(name) for name in package.namelist()}
            database = output / "legacy.anki2"
            database.write_bytes(members["collection.anki2"])
            with closing(sqlite3.connect(database)) as connection:
                configs = json.loads(connection.execute("SELECT dconf FROM col").fetchone()[0])
                configs[str(atlas.CONFIG_ID)]["name"] = "Word Atlas · 手动播放"
                configs[str(atlas.CONFIG_ID)]["new"]["delays"] = [1, 10]
                configs[str(atlas.CONFIG_ID)]["newMix"] = 0
                decks = json.loads(connection.execute("SELECT decks FROM col").fetchone()[0])
                decks[str(atlas.DECK_ID)]["desc"] = "旧描述"
                connection.execute("UPDATE col SET decks = ?, dconf = ?", (json.dumps(decks), json.dumps(configs)))
                connection.execute("UPDATE cards SET reps = 3, ivl = 5 WHERE id = (SELECT min(id) FROM cards)")
                connection.commit()
                before_notes = connection.execute("SELECT * FROM notes ORDER BY id").fetchall()
                before_cards = connection.execute("SELECT * FROM cards ORDER BY id").fetchall()
            members["collection.anki2"] = database.read_bytes()
            with zipfile.ZipFile(package_path, "w") as package:
                for name, content in members.items():
                    package.writestr(name, content)
            genanki, _ = atlas.load_genanki(Path("D:/me/genanki"))
            result = atlas.update_package_study_plan(package_path, genanki)
            self.assertTrue(result["notes_cards_unchanged"])
            self.assertTrue(result["media_unchanged"])
            self.assertEqual(result["verification"]["study_plan"], "ok")
            with zipfile.ZipFile(package_path) as package:
                for name, content in members.items():
                    if name != "collection.anki2":
                        self.assertEqual(package.read(name), content)
                database.write_bytes(package.read("collection.anki2"))
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT * FROM notes ORDER BY id").fetchall(), before_notes)
                self.assertEqual(connection.execute("SELECT * FROM cards ORDER BY id").fetchall(), before_cards)
                decks, configs, collection = connection.execute("SELECT decks,dconf,conf FROM col").fetchone()
                preset = json.loads(configs)[str(atlas.CONFIG_ID)]
                self.assertEqual(json.loads(decks)[str(atlas.DECK_ID)]["desc"], "")
                self.assertEqual(preset["name"], "Word Atlas")
                self.assertEqual(preset["new"]["delays"], [1, 600, 360])
                self.assertEqual(preset["newMix"], 1)
                self.assertEqual(preset["newGatherPriority"], 1)
                self.assertEqual(preset["newSortOrder"], 1)
                self.assertEqual(preset["new"]["perDay"], 20)
                self.assertEqual(preset["rev"]["perDay"], 9999)
                self.assertEqual(json.loads(collection)["newSpread"], 1)

    def test_full_mode_preserves_source_order_and_deck_name(self):
        original = Path("D:/me/word-atlas-main")
        entries, index = atlas.load_source(original)
        subset = [entries[-1], entries[0]]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            (source / "data").mkdir(parents=True)
            (source / "dist/atlas").mkdir(parents=True)
            (source / "dist/assets").mkdir(parents=True)
            (source / "data/word-atlas.json").write_text(json.dumps(subset), encoding="utf-8")
            (source / "dist/atlas/index.json").write_text(json.dumps(index), encoding="utf-8")
            font = next((original / "dist/assets").glob("fraunces-latin-opsz-normal-*.woff2"))
            shutil.copy2(font, source / "dist/assets" / font.name)
            shutil.copy2(original / "CONTENT_LICENSE.md", source / "CONTENT_LICENSE.md")
            output = Path(temporary) / "full"
            report = atlas.generate(source, Path("D:/me/genanki"), output, None)
            self.assertEqual(report["entry_ids"], [entry["id"] for entry in subset])
            self.assertEqual(report["deck_name"], "Word Atlas")
            self.assertEqual(report["mode"], "full")
            self.assertEqual(Path(report["package"]).name, "Word Atlas.apkg")
            self.assertEqual(report["verification"]["deck_name"], "Word Atlas")
            self.assertEqual((report["notes"], report["cards"]), (2, 2))
            self.assertEqual(report["verification"]["cards"], 2)
            self.assertEqual(report["verification"]["new_card_positions"], "ok")
            self.assertEqual(report["verification"]["missing_media_references"], 0)

    def test_real_package_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            report = atlas.generate(Path("D:/me/word-atlas-main"), Path("D:/me/genanki"),
                                    output, list(TEST_IDS))
            self.assertEqual((report["notes"], report["cards"]), (10, 10))
            with zipfile.ZipFile(report["package"]) as package:
                self.assertIsNone(package.testzip())
                media = json.loads(package.read("media"))
                self.assertEqual(len(set(media.values())), len(media))
                self.assertEqual(len(media), report["media_count"])
                package.extract("collection.anki2", output)
                media_by_name = {name: package.read(key) for key, name in media.items()}
                with closing(sqlite3.connect(output / "collection.anki2")) as connection:
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(connection.execute("SELECT count(*) FROM notes").fetchone()[0], 10)
                    self.assertEqual(connection.execute("SELECT ord, count(*) FROM cards GROUP BY ord").fetchall(), [(0, 10)])
                    model = json.loads(connection.execute("SELECT models FROM col").fetchone()[0])[str(atlas.MODEL_ID)]
                    self.assertEqual([(t["name"], t["ord"]) for t in model["tmpls"]], [("英→中 · 词义回忆", 0)])
                    rows = connection.execute("SELECT guid, flds FROM notes ORDER BY id").fetchall()
                    genanki, chevron = atlas.load_genanki(Path("D:/me/genanki"))
                    for (guid, raw), word_id in zip(rows, TEST_IDS):
                        self.assertEqual(guid, genanki.guid_for("word-atlas:v1", word_id))
                        for match in re.finditer(r'src="([^"]+)"|\[sound:([^\]]+)\]', raw):
                            self.assertIn(match.group(1) or match.group(2), media_by_name)
                        fields = dict(zip(atlas.FIELDS, raw.split("\x1f")))
                        front = render_anki_template(model["tmpls"][0]["qfmt"], fields, chevron)
                        back = render_anki_template(model["tmpls"][0]["afmt"], fields, chevron)
                        self.assertIn(fields["Word"], front)
                        self.assertNotIn(fields["MeaningZH"], front)
                        self.assertNotIn("<img", front)
                        self.assertIn(html.unescape(fields["MeaningZH"]), html.unescape(back))
                        self.assertIn("<img", back)
                    models, configs, decks = connection.execute("SELECT models, dconf, decks FROM col").fetchone()
                    model = json.loads(models)[str(atlas.MODEL_ID)]
                    self.assertEqual(len(model["tmpls"]), 1)
                    self.assertEqual([field["name"] for field in model["flds"]], list(atlas.FIELDS))
                    self.assertEqual(json.loads(decks)[str(atlas.DECK_ID)]["conf"], atlas.CONFIG_ID)
                    self.assertFalse(json.loads(configs)[str(atlas.CONFIG_ID)]["autoplay"])
                    self.assertEqual(json.loads(configs)[str(atlas.CONFIG_ID)]["name"], "Word Atlas")
                    self.assertEqual(json.loads(configs)[str(atlas.CONFIG_ID)]["new"]["delays"], [1, 600, 360])
                    self.assertEqual(json.loads(decks)[str(atlas.DECK_ID)]["desc"], "")
                    self.assertTrue(json.loads(configs)["1"]["autoplay"])
                self.assertNotEqual(media_by_name["wa_sustainable_uk.mp3"], media_by_name["wa_sustainable_us.mp3"])
                self.assertIn("wa_library_ex2.mp3", media_by_name)
                self.assertNotIn("wa_sustainable_ex2.mp3", media_by_name)

    def test_verifier_rejects_reverse_cards_but_plan_update_preserves_legacy_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            report = atlas.generate(Path("D:/me/word-atlas-main"), Path("D:/me/genanki"),
                                    output, ["library"])
            package_path = Path(report["package"])
            with zipfile.ZipFile(package_path) as package:
                members = {name: package.read(name) for name in package.namelist()}
            database = output / "legacy.anki2"
            database.write_bytes(members["collection.anki2"])
            with closing(sqlite3.connect(database)) as connection:
                models = json.loads(connection.execute("SELECT models FROM col").fetchone()[0])
                model = models[str(atlas.MODEL_ID)]
                model["tmpls"].append({**model["tmpls"][0], "name": "中→英 · 表达回忆",
                                       "ord": 1, "qfmt": "{{MeaningZH}}"})
                model["req"].append([1, "all", [atlas.FIELDS.index("MeaningZH")]])
                connection.execute("UPDATE col SET models = ?", (json.dumps(models),))
                reverse = list(connection.execute("SELECT * FROM cards").fetchone())
                reverse[0] += 1000
                reverse[3] = 1
                connection.execute("INSERT INTO cards VALUES (" + ",".join("?" for _ in reverse) + ")", reverse)
                connection.commit()
                before = connection.execute("SELECT * FROM cards ORDER BY id").fetchall()
            members["collection.anki2"] = database.read_bytes()
            with zipfile.ZipFile(package_path, "w") as package:
                for name, content in members.items():
                    package.writestr(name, content)
            genanki, _ = atlas.load_genanki(Path("D:/me/genanki"))
            with self.assertRaisesRegex(ValueError, "模板方向"):
                atlas.verify_package(package_path, ["library"], genanki)
            result = atlas.update_package_study_plan(package_path, genanki)
            self.assertEqual(result["verification"]["cards"], 2)
            self.assertTrue(result["notes_cards_unchanged"])
            self.assertTrue(result["media_unchanged"])
            with zipfile.ZipFile(package_path) as package:
                database.write_bytes(package.read("collection.anki2"))
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT * FROM cards ORDER BY id").fetchall(), before)


if __name__ == "__main__":
    unittest.main()
