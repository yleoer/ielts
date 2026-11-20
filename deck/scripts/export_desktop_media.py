"""Export a standalone Word Atlas resource ZIP for desktop import.

The manifest carries a dotted version (default: today, e.g. 2026.11.19); the desktop app
refuses packages without one or older than the installed package. `--repack` rewrites an
existing ZIP with a new version, without the Word Atlas source.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Callable

from generate_word_atlas import ROOT, load_source, media_report

KINDS = {"img": "illustration", "uk": "audio_uk", "us": "audio_us"}
DEFAULT_OUTPUT = ROOT.parent / "desktop/media"
PACKAGE = "cijian-media.zip"


def check_version(version: str) -> str:
    if not re.fullmatch(r"\d+(\.\d+)*", version):
        raise ValueError(f"版本号须为点分数字，例如 2026.11.19：{version}")
    return version


def manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_package(target: Path, entries: dict[str, Callable[[], bytes]]) -> None:
    """Writes sorted entries with fixed timestamps, so equal inputs give identical bytes."""
    with zipfile.ZipFile(target, "w") as package:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            package.writestr(info, entries[name](), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)


def export(source: Path, output: Path, version: str) -> dict:
    check_version(version)
    source, output = source.resolve(), output.resolve()
    entries, index = load_source(source)
    flags = {row[0]: row[-1] for row in index["words"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="desktop-media-", dir=output.parent) as temporary:
        staging = Path(temporary)
        words, counts, sources = {}, Counter(), {}
        for position, entry in enumerate(entries, 1):
            media = {}
            for item in media_report(entry, flags.get(entry["id"], 0), source / "dist/atlas"):
                if item["kind"] not in KINDS or not item["available"]:
                    continue
                original = Path(item["source"])
                media[KINDS[item["kind"]]] = {"file": item["filename"]}
                sources[item["filename"]] = original
                counts[KINDS[item["kind"]]] += 1
            words[entry["id"]] = media
            if position % 1000 == 0 or position == len(entries):
                print(f"导出桌面媒体：{position:,}/{len(entries):,}", flush=True)
        metadata = {
            "manifest.json": manifest_bytes({"format": 1, "version": version, "words": words}),
            "CONTENT_LICENSE.md": (source / "CONTENT_LICENSE.md").read_bytes(),
            "ATTRIBUTION.txt": ("Word Atlas contributors — CC BY 4.0\n"
                                "https://creativecommons.org/licenses/by/4.0/\n"
                                "Original illustrations and most recordings preserved; personal spelling revisions applied.\n"
                                "Four revised words use Microsoft Zira Desktop en-US speech; their obsolete UK clips are omitted.\n").encode("utf-8"),
        }
        archive = staging / PACKAGE
        print(f"压缩 {len(sources):,} 个媒体文件……", flush=True)
        entries = {name: path.read_bytes for name, path in sources.items()}
        entries.update({name: (lambda body=body: body) for name, body in metadata.items()})
        write_package(archive, entries)
        output.mkdir(exist_ok=True)
        target = output / archive.name
        archive.replace(target)
    return {"version": version, "words": len(entries), "files": sum(counts.values()), "media_counts": dict(counts),
            "archive_bytes": target.stat().st_size, "output": str(target)}


def repack(package: Path, output: Path, version: str) -> dict:
    """Copies every entry of an existing pack and sets the manifest version."""
    check_version(version)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="desktop-media-", dir=output) as temporary:
        archive = Path(temporary) / PACKAGE
        with zipfile.ZipFile(package) as old:
            manifest = json.loads(old.read("manifest.json"))
            if manifest.get("format") != 1:
                raise ValueError(f"不支持的资源包格式：{manifest.get('format')}")
            previous = manifest.get("version")
            manifest["version"] = version
            entries = {name: (lambda name=name: old.read(name)) for name in old.namelist()}
            entries["manifest.json"] = lambda: manifest_bytes(manifest)
            print(f"重新打包 {len(entries):,} 个文件……", flush=True)
            write_package(archive, entries)
        target = output / PACKAGE
        archive.replace(target)
    files = sum(len(assets) for assets in manifest["words"].values())
    return {"version": version, "previous_version": previous, "words": len(manifest["words"]), "files": files,
            "archive_bytes": target.stat().st_size, "output": str(target)}



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT.parent.parent / "word-atlas-main")
    parser.add_argument("--repack", type=Path, metavar="ZIP", help="给已有资源包写入新版本号，不读取 --source")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--version", default=date.today().strftime("%Y.%m.%d"), help="资源包版本，默认今天")
    args = parser.parse_args()
    try:
        if args.repack:
            report = repack(args.repack, args.output, args.version)
        else:
            report = export(args.source, args.output, args.version)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f"导出失败：{error}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
