from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sync import copy_collection_group, latest_collection


class SyncHelpersTest(unittest.TestCase):
    def test_copy_collection_group_copies_and_removes_sidecars(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source" / "collection.anki2"
            target = root / "cache" / "collection.anki2"
            source.parent.mkdir()
            source.write_bytes(b"collection")
            Path(str(source) + "-wal").write_bytes(b"wal")

            self.assertEqual(latest_collection(str(root / "source")), str(source))
            copied = copy_collection_group(str(source), str(target), stable_seconds=0)
            self.assertEqual(copied, ["collection.anki2", "collection.anki2-wal"])
            self.assertEqual(target.read_bytes(), b"collection")
            self.assertEqual(Path(str(target) + "-wal").read_bytes(), b"wal")

            Path(str(source) + "-wal").unlink()
            copied = copy_collection_group(str(source), str(target), stable_seconds=0)
            self.assertEqual(copied, ["collection.anki2"])
            self.assertFalse(Path(str(target) + "-wal").exists())


if __name__ == "__main__":
    unittest.main()
