"""Desktop export contracts: SourceId, variants, missing and stale media."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_desktop_media import export


class DesktopMediaTests(unittest.TestCase):
    def contents(self):
        with zipfile.ZipFile(self.output / "cijian-media.zip") as package:
            return {name: package.read(name) for name in package.namelist()}

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.output = self.root / "media"
        (self.source / "data").mkdir(parents=True)
        (self.source / "dist/atlas").mkdir(parents=True)
        (self.source / "data/word-atlas.json").write_text(
            json.dumps([{"id": "library"}, {"id": "missing"}]), encoding="utf-8")
        (self.source / "dist/atlas/index.json").write_text(
            json.dumps({"words": [["library", 15], ["missing", 0]]}), encoding="utf-8")
        (self.source / "CONTENT_LICENSE.md").write_text("Word Atlas — CC BY 4.0", encoding="utf-8")

    def media(self, folder, name, body):
        path = self.source / "dist/atlas" / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def test_manifest_maps_all_variants_to_exact_bytes_and_is_reproducible(self):
        expected = {"illustration": b"picture", "audio_uk": b"uk", "audio_us": b"us",
                    "audio_example": b"example", "audio_ielts": b"ielts"}
        for folder, ext, kind in (("img", ".webp", "illustration"), ("audio/uk", ".mp3", "audio_uk"),
                                  ("audio/us", ".mp3", "audio_us"), ("audio/ex", ".mp3", "audio_example"),
                                  ("audio/ex2", ".mp3", "audio_ielts")):
            self.media(folder, "library" + ext, expected[kind])
        # A file that is not declared by the index must not be bundled.
        self.media("audio/uk", "missing.mp3", b"undeclared")
        report = export(self.source, self.output)
        manifest_bytes = self.contents()["manifest.json"]
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["format"], 1)
        self.assertEqual(manifest["words"]["missing"], {})
        self.assertEqual(report["files"], 5)
        contents = self.contents()
        for kind, item in manifest["words"]["library"].items():
            self.assertEqual(contents[item["file"]], expected[kind])
            self.assertEqual(set(item), {"file"})
        self.assertNotIn("sha256", report)
        self.assertEqual(len({item["file"] for item in manifest["words"]["library"].values()}), 5)
        self.assertEqual(contents["CONTENT_LICENSE.md"],
                         (self.source / "CONTENT_LICENSE.md").read_bytes())
        self.assertIn("Word Atlas contributors", contents["ATTRIBUTION.txt"].decode("utf-8"))
        export(self.source, self.output)
        self.assertEqual(self.contents()["manifest.json"], manifest_bytes)
        second = self.root / "second"
        export(self.source, second)
        self.assertEqual((second / "cijian-media.zip").read_bytes(), (self.output / "cijian-media.zip").read_bytes())

    def test_refresh_repairs_changed_and_corrupt_files(self):
        source = self.media("img", "library.webp", b"old")
        export(self.source, self.output)
        target = self.output / "cijian-media.zip"
        target.write_bytes(b"corrupt")
        export(self.source, self.output)
        self.assertEqual(self.contents()["wa_library_img.webp"], b"old")
        source.write_bytes(b"updated")
        export(self.source, self.output)
        self.assertEqual(self.contents()["wa_library_img.webp"], b"updated")
        item = json.loads(self.contents()["manifest.json"])["words"]["library"]["illustration"]
        self.assertEqual(item, {"file": "wa_library_img.webp"})

    def test_refresh_replaces_obsolete_entries_and_keeps_unrelated_files(self):
        source = self.media("img", "library.webp", b"old")
        export(self.source, self.output)
        (self.output / "keep.txt").write_bytes(b"unrelated")
        source.unlink()
        self.media("audio/uk", "library.mp3", b"new")
        export(self.source, self.output)
        self.assertFalse((self.output / "wa_library_img.webp").exists())
        self.assertEqual({k: v for k, v in self.contents().items() if k.startswith("wa_")}, {"wa_library_uk.mp3": b"new"})
        self.assertEqual((self.output / "keep.txt").read_bytes(), b"unrelated")
        self.assertEqual(set(json.loads(self.contents()["manifest.json"])["words"]["library"]), {"audio_uk"})

    def test_failed_assembly_preserves_previous_export(self):
        self.media("img", "library.webp", b"old")
        export(self.source, self.output)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        (self.source / "CONTENT_LICENSE.md").unlink()
        with self.assertRaises(OSError):
            export(self.source, self.output)
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()}, before)



if __name__ == "__main__":
    unittest.main()
