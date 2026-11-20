"""Helpers for copying a stable Anki collection into the read cache."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

SUFFIXES = ("", "-wal", "-shm")


def latest_collection(source_dir: str) -> str:
    candidates = [path for path in Path(source_dir).rglob("collection.anki2")
                  if path.is_file() and path.stat().st_size > 0]
    if not candidates:
        raise FileNotFoundError(f"no collection.anki2 found under {source_dir}")
    return str(max(candidates, key=lambda path: path.stat().st_mtime))


def _group_stats(source: str) -> list[tuple[str, int, int]]:
    result = []
    for suffix in SUFFIXES:
        path = Path(source + suffix)
        if suffix and not path.exists():
            continue
        stat = path.stat()
        result.append((suffix, stat.st_size, stat.st_mtime_ns))
    return result


def copy_collection_group(source: str, target: str, stable_seconds: float) -> None:
    """Copy collection.anki2 and any SQLite sidecars after a stability check."""
    first = _group_stats(source)
    time.sleep(stable_seconds)
    if first != _group_stats(source):
        raise RuntimeError("Anki collection files are changing; try again later")
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    for suffix in SUFFIXES:
        src, dst = Path(source + suffix), Path(target + suffix)
        if suffix and not src.exists():
            dst.unlink(missing_ok=True)
            continue
        tmp = Path(str(dst) + ".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
