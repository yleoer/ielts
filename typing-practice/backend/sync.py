"""Helpers for copying a stable Anki collection into the read cache."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


def sync_configured() -> bool:
    return bool(
        os.environ.get("ANKI_SYNC_SOURCE_DIR", "").strip()
        and os.environ.get("ANKI_SYNC_TARGET", "").strip()
    )


def sync_target_path(default_path: str) -> str:
    return os.environ.get("ANKI_SYNC_TARGET", "").strip() or default_path


def latest_collection(source_dir: str) -> str:
    root = Path(source_dir.strip())
    if not source_dir.strip():
        raise ValueError("ANKI_SYNC_SOURCE_DIR is not configured")
    candidates = [
        path
        for path in root.rglob("collection.anki2")
        if path.is_file() and path.stat().st_size > 0
    ]
    if not candidates:
        raise FileNotFoundError(f"no collection.anki2 found under {root}")
    return str(max(candidates, key=lambda path: path.stat().st_mtime))


def _group_stats(source: str) -> list[tuple[str, int, float]]:
    result = []
    for suffix in ("", "-wal", "-shm"):
        path = Path(source + suffix)
        if not path.exists():
            if suffix:
                continue
            raise FileNotFoundError(path)
        stat = path.stat()
        result.append((str(path), stat.st_size, stat.st_mtime_ns))
    return result


def copy_collection_group(source: str, target: str, stable_seconds: float = 2) -> list[str]:
    """Copy collection.anki2 and any SQLite sidecars after a stability check."""
    if not target.strip():
        raise ValueError("ANKI_SYNC_TARGET is not configured")
    first = _group_stats(source)
    if stable_seconds:
        time.sleep(stable_seconds)
    if first != _group_stats(source):
        raise RuntimeError("Anki collection files are changing; try again later")

    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for suffix in ("", "-wal", "-shm"):
        src = Path(source + suffix)
        dst = Path(str(target_path) + suffix)
        if not src.exists():
            if suffix:
                dst.unlink(missing_ok=True)
                continue
            raise FileNotFoundError(src)
        tmp = Path(str(dst) + ".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
        copied.append(dst.name)
    return copied
