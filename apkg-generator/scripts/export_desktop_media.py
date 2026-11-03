"""Export a standalone Word Atlas resource ZIP for desktop import."""
from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from generate_word_atlas import ROOT, load_source, media_report

KINDS = {"img": "illustration", "uk": "audio_uk", "us": "audio_us",
         "ex": "audio_example", "ex2": "audio_ielts"}
DEFAULT_OUTPUT = ROOT.parent / "typing-desktop/media"


def export(source: Path, output: Path) -> dict:
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
                if not item["available"]:
                    continue
                original = Path(item["source"])
                media[KINDS[item["kind"]]] = {"file": item["filename"]}
                sources[item["filename"]] = original
                counts[KINDS[item["kind"]]] += 1
            words[entry["id"]] = media
            if position % 1000 == 0 or position == len(entries):
                print(f"导出桌面媒体：{position:,}/{len(entries):,}", flush=True)
        metadata = {
            "manifest.json": (json.dumps({"format": 1, "words": words}, ensure_ascii=False,
                                         indent=2, sort_keys=True) + "\n").encode("utf-8"),
            "CONTENT_LICENSE.md": (source / "CONTENT_LICENSE.md").read_bytes(),
            "ATTRIBUTION.txt": ("Word Atlas contributors — CC BY 4.0\n"
                                "https://creativecommons.org/licenses/by/4.0/\n"
                                "Illustrations and recordings copied without modification; filenames changed.\n").encode("utf-8"),
        }
        archive = staging / "cijian-media.zip"
        print(f"压缩 {len(sources):,} 个媒体文件……", flush=True)
        with zipfile.ZipFile(archive, "w") as package:
            for name in sorted(set(sources) | set(metadata)):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                package.writestr(info, metadata[name] if name in metadata else sources[name].read_bytes(),
                                 compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        output.mkdir(exist_ok=True)
        target = output / archive.name
        archive.replace(target)
    return {"words": len(entries), "files": sum(counts.values()), "media_counts": dict(counts),
            "archive_bytes": target.stat().st_size, "output": str(target)}



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT.parent.parent / "word-atlas-main")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        report = export(args.source, args.output)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"导出失败：{error}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
