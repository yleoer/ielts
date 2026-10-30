"""Verify the original generator's English-to-Chinese export in SQLite."""
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_anki_import.py"
SPEC = importlib.util.spec_from_file_location("anki_import", SCRIPT)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class PackageTests(unittest.TestCase):
    def test_export_has_one_forward_card_per_note(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            package_path = output / "test.apkg"
            with (patch.object(generator, "OUTPUT_DIR", output),
                  patch.object(generator, "OUTPUT_TSV", output / "test.tsv"),
                  patch.object(generator, "OUTPUT_APKG", package_path),
                  patch.object(generator, "refresh_phonetics", return_value={}),
                  patch.object(generator, "refresh_ai", return_value={"translations": {}, "etymologies": {}}),
                  patch.object(generator, "find_audio", return_value=None)):
                summary = generator.build_export(skip_ai=True, limit=2)
            self.assertEqual((summary["notes"], summary["cards"]), (2, 2))
            with zipfile.ZipFile(package_path) as package:
                self.assertIsNone(package.testzip())
                package.extract("collection.anki2", output)
            with closing(sqlite3.connect(output / "collection.anki2")) as connection:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                notes = connection.execute("SELECT id, guid, flds FROM notes ORDER BY id").fetchall()
                cards = connection.execute("SELECT nid, ord, due FROM cards ORDER BY due").fetchall()
                self.assertEqual(cards, [(note[0], 0, i) for i, note in enumerate(notes, 1)])
                model = json.loads(connection.execute("SELECT models FROM col").fetchone()[0])[str(generator.MODEL_ID)]
                self.assertEqual([(t["name"], t["ord"]) for t in model["tmpls"]], [("Forward", 0)])
                self.assertEqual(model["req"], [[0, "any", [0]]])
                self.assertIn("{{Word}}", model["tmpls"][0]["qfmt"])
                self.assertNotIn("{{ChineseMeaning}}", model["tmpls"][0]["qfmt"])
                self.assertIn("{{ChineseMeaning}}", model["tmpls"][0]["afmt"])
                records = generator.parse_vocabulary()[:2]
                self.assertEqual([note[1] for note in notes], [generator.stable_guid(record) for record in records])
                self.assertEqual([field["name"] for field in model["flds"]], generator.FIELDS)


if __name__ == "__main__":
    unittest.main()
