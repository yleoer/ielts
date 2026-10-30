"""Build and verify the complete offline Word Atlas Anki deck."""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import importlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile
from collections import Counter
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "word-atlas"
TOPICS = {
    "education": "教育", "work": "工作", "technology": "科技", "science": "科学",
    "environment": "环境", "health": "健康", "society": "社会", "government": "政府",
    "economy": "经济", "media": "媒体", "arts": "艺术", "travel": "旅行",
    "city": "城市", "nature": "自然", "daily": "日常", "emotion": "情绪",
    "thinking": "思维", "sport": "运动", "history": "历史",
}
FIELDS = (
    "Word", "UK", "US", "PartOfSpeech", "MeaningZH", "MeaningEN", "MoreSenses",
    "ExampleEN", "ExampleZH", "IELTSExampleEN", "IELTSExampleZH", "Collocations",
    "Tip", "Extra", "CEFR", "Topic", "Illustration", "AudioUK", "AudioUS",
    "AudioExample", "AudioIELTS", "SourceId",
)
MODEL_ID = 1548670924
DECK_ID = 1958430017
CONFIG_ID = 1958430018
LEARNING_STEPS_MINUTES = [1, 600, 360]
STUDY_TIMES = {"morning": "07:00", "afternoon_commute": "17:00", "bedtime": "23:00"}


def study_plan_summary(deck_name: str) -> dict:
    return {"preset_name": deck_name, "study_times": STUDY_TIMES.copy(),
            "learning_steps": "1m 10h 6h", "learning_steps_minutes": LEARNING_STEPS_MINUTES.copy(),
            "reviews_before_new": True, "new_cards_per_day": 20, "review_limit": 9999,
            "description": "", "autoplay": False}


def configure_study_plan(cursor, deck_name: str = "Word Atlas") -> dict:
    """Set a deck-specific plan; preserve the collection's default preset."""
    configs = json.loads(cursor.execute("SELECT dconf FROM col").fetchone()[0])
    preset = copy.deepcopy(configs.get(str(CONFIG_ID), configs["1"]))
    preset.update({"id": CONFIG_ID, "name": deck_name, "autoplay": False,
                   "newMix": 1, "newGatherPriority": 1, "newSortOrder": 1,
                   "mod": int(time.time())})
    preset["new"].update({"delays": LEARNING_STEPS_MINUTES.copy(), "perDay": 20,
                          "order": 1, "bury": True})
    # This is a ceiling, not a daily target: do not hide due old cards before new cards.
    preset["rev"]["perDay"] = 9999
    configs[str(CONFIG_ID)] = preset
    cursor.execute("UPDATE col SET dconf = ?", (json.dumps(configs),))
    decks = json.loads(cursor.execute("SELECT decks FROM col").fetchone()[0])
    deck = decks[str(DECK_ID)]
    deck.update({"name": deck_name, "conf": CONFIG_ID, "desc": "", "mod": int(time.time())})
    cursor.execute("UPDATE col SET decks = ?", (json.dumps(decks),))
    collection = json.loads(cursor.execute("SELECT conf FROM col").fetchone()[0])
    collection["newSpread"] = 1  # Legacy scheduler: new cards after reviews.
    cursor.execute("UPDATE col SET conf = ?", (json.dumps(collection),))
    return study_plan_summary(deck_name)


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def highlighted(text: str, word: str) -> str:
    """Escape source text before adding markup around exact headword matches."""
    pattern = re.compile(r"(?<!\w)(" + re.escape(word) + r")(?!\w)", re.IGNORECASE)
    parts = pattern.split(text)
    return "".join(f"<mark>{escaped(part)}</mark>" if i % 2 else escaped(part)
                   for i, part in enumerate(parts))


def load_source(source: Path) -> tuple[list[dict], dict]:
    entries = json.loads((source / "data/word-atlas.json").read_text(encoding="utf-8"))
    index = json.loads((source / "dist/atlas/index.json").read_text(encoding="utf-8"))
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("词库 id 不唯一，无法生成稳定的 Anki 笔记。")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", item) for item in ids):
        raise ValueError("词条 id 含不支持的媒体文件名字符。")
    return entries, index


def select_entries(entries: list[dict], ids: list[str]) -> list[dict]:
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("请指定至少一个词，且不能重复。")
    lookup = {entry["id"]: entry for entry in entries}
    missing = [item for item in ids if item not in lookup]
    if missing:
        raise ValueError("词库中不存在这些 id：" + ", ".join(missing))
    return [lookup[item] for item in ids]


def copy_media(entry: dict, flags: int, atlas: Path, output: Path) -> tuple[dict, list[dict]]:
    """Anki flattens filenames: UK, US and examples must have distinct basenames."""
    result = {}
    report = []
    specs = (
        ("Illustration", "img", ".webp", 1, "img"),
        ("AudioUK", "audio/uk", ".mp3", 2, "uk"),
        ("AudioUS", "audio/us", ".mp3", 4, "us"),
        ("AudioExample", "audio/ex", ".mp3", 8, "ex"),
        # ex2 is present in this build, but absent from docs/dataset.md.
        ("AudioIELTS", "audio/ex2", ".mp3", None, "ex2"),
    )
    for field, folder, extension, bit, kind in specs:
        original = atlas / folder / (entry["id"] + extension)
        declared = bool(flags & bit) if bit is not None else None
        available = original.is_file() and (declared is not False)
        filename = f"wa_{entry['id']}_{kind}{extension}"
        report.append({"kind": kind, "declared": declared, "available": available,
                       "source": original.as_posix(), "filename": filename if available else None})
        if not available:
            result[field] = ""
            continue
        shutil.copy2(original, output / filename)
        result[field] = (f'<img src="{filename}" alt="词义插画">'
                         if kind == "img" else f"[sound:{filename}]")
    return result, report


def build_fields(entry: dict, media: dict) -> dict[str, str]:
    senses = entry.get("senses", [])
    if not senses or not entry.get("w") or not senses[0].get("zh"):
        raise ValueError(f"{entry['id']} 缺少词头或核心义项。")
    primary = senses[0]
    examples = entry.get("ex", [])
    extra = []
    for key, label in (("fam", "词族"), ("syn", "近义词"), ("ant", "反义词")):
        if entry.get(key):
            extra.append(f"<section><h3>{label}</h3><p>{' · '.join(escaped(x) for x in entry[key])}</p></section>")
    if entry.get("note"):
        extra.append(f'<section><h3>补充说明</h3><p>{escaped(entry["note"])}</p></section>')
    more_senses = "".join(
        f'<div class="atlas-sense"><span class="atlas-pos">{escaped(s["pos"])}</span> '
        f'{escaped(s["zh"])}<p lang="en">{escaped(s["en"])}</p></div>'
        for s in senses[1:]
    )
    collocations = []
    for item in entry.get("col", []):
        en, separator, zh = item.partition("｜")
        translation = f"<small>{escaped(zh)}</small>" if separator else ""
        collocations.append(f'<li><span lang="en">{escaped(en)}</span>{translation}</li>')
    result = {name: "" for name in FIELDS}
    result.update({
        "Word": escaped(entry["w"]), "UK": escaped(entry.get("uk", "")),
        "US": escaped(entry.get("us", "")), "PartOfSpeech": escaped(primary["pos"]),
        "MeaningZH": escaped(primary["zh"]), "MeaningEN": escaped(primary["en"]),
        "MoreSenses": more_senses, "Collocations": "".join(collocations),
        "Tip": escaped(entry.get("tip", "")), "Extra": "".join(extra),
        "CEFR": escaped(entry["cefr"]), "Topic": escaped(TOPICS.get(entry["topic"], entry["topic"])),
        "SourceId": escaped(entry["id"]), **media,
    })
    for index, en_key, zh_key in ((0, "ExampleEN", "ExampleZH"), (1, "IELTSExampleEN", "IELTSExampleZH")):
        if len(examples) > index:
            result[en_key] = highlighted(examples[index]["en"], entry["w"])
            result[zh_key] = escaped(examples[index].get("zh", ""))
    return result


def load_genanki(path: Path):
    if not (path / "genanki/__init__.py").is_file():
        raise ValueError(f"找不到 genanki 源码：{path}")
    sys.path.insert(0, str(path))
    try:
        genanki = importlib.import_module("genanki")
        chevron = importlib.import_module("chevron")
    except ImportError as error:
        raise ValueError("缺少 genanki 依赖，请安装 apkg-generator/requirements-word-atlas.txt。") from error
    if not Path(genanki.__file__).resolve().is_relative_to(path.resolve()):
        raise ValueError("当前 Python 已加载其他位置的 genanki，请在独立进程运行本脚本。")
    return genanki, chevron


def write_package(genanki, model, notes: list, media: list[Path], target: Path,
                  deck_name: str = "Word Atlas") -> None:
    class AtlasDeck(genanki.Deck):
        def to_json(self):
            result = super().to_json()
            result["conf"] = CONFIG_ID
            return result

    class AtlasPackage(genanki.Package):
        def write_to_db(self, cursor, timestamp, id_gen):
            super().write_to_db(cursor, timestamp, id_gen)
            configure_study_plan(cursor, deck_name)

    deck = AtlasDeck(DECK_ID, deck_name, description="")
    for note in notes:
        deck.add_note(note)
    AtlasPackage(deck, media_files=[str(path) for path in media]).write_to_file(str(target))


def verify_package(package_path: Path, entry_ids: list[str], genanki,
                   card_ordinals: tuple[int, ...] = (0,)) -> dict:
    """Check the actual archive, every note/card, and every media reference."""
    with zipfile.ZipFile(package_path) as package:
        broken = package.testzip()
        if broken:
            raise ValueError(f"APKG ZIP 校验失败：{broken}")
        media = json.loads(package.read("media"))
        names = list(media.values())
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValueError("APKG 媒体文件名重复。")
        archive_members = set(package.namelist())
        if any(key not in archive_members for key in media):
            raise ValueError("APKG 媒体索引引用缺失文件。")
        if any(package.getinfo(key).file_size == 0 for key in media):
            raise ValueError("APKG 包含空媒体文件。")
        known_names = set(names)
        with tempfile.TemporaryDirectory(prefix="word-atlas-verify-") as temporary:
            database = Path(temporary) / "collection.anki2"
            database.write_bytes(package.read("collection.anki2"))
            with closing(sqlite3.connect(database)) as connection:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Anki SQLite 完整性检查失败。")
                rows = connection.execute("SELECT id, guid, flds FROM notes ORDER BY id").fetchall()
                if len(rows) != len(entry_ids):
                    raise ValueError("Anki 笔记数量不匹配。")
                references = set()
                for (_, guid, raw), entry_id in zip(rows, entry_ids):
                    values = raw.split("\x1f")
                    if len(values) != len(FIELDS):
                        raise ValueError(f"{entry_id} 字段数量不匹配。")
                    fields = dict(zip(FIELDS, values))
                    if fields["SourceId"] != entry_id or guid != genanki.guid_for("word-atlas:v1", entry_id):
                        raise ValueError(f"{entry_id} 源顺序或笔记 GUID 不匹配。")
                    for match in re.finditer(r'src="([^"]+)"|\[sound:([^\]]+)\]', raw):
                        filename = match.group(1) or match.group(2)
                        if filename not in known_names:
                            raise ValueError(f"{entry_id} 媒体引用缺失：{filename}")
                        references.add(filename)
                models = json.loads(connection.execute("SELECT models FROM col").fetchone()[0])
                model = models[str(MODEL_ID)]
                if tuple(template["ord"] for template in model["tmpls"]) != card_ordinals:
                    raise ValueError("Anki 卡片模板方向不匹配。")
                cards = connection.execute("SELECT nid, did, ord, due FROM cards").fetchall()
                expected_cards = {(nid, DECK_ID, ordinal, position)
                                  for position, (nid, _, _) in enumerate(rows, 1) for ordinal in card_ordinals}
                if len(cards) != len(expected_cards) or set(cards) != expected_cards:
                    raise ValueError("Anki 卡片方向、数量、所属牌组或新卡位置不匹配。")
                decks = json.loads(connection.execute("SELECT decks FROM col").fetchone()[0])
                name = decks[str(DECK_ID)]["name"]
                configs = json.loads(connection.execute("SELECT dconf FROM col").fetchone()[0])
                preset = configs[str(CONFIG_ID)]
                if (decks[str(DECK_ID)]["desc"] != "" or preset["name"] != name
                        or preset["new"]["delays"] != LEARNING_STEPS_MINUTES
                        or preset.get("newMix") != 1 or preset.get("newGatherPriority") != 1
                        or preset.get("newSortOrder") != 1 or preset["new"]["perDay"] != 20
                        or preset["rev"]["perDay"] != 9999):
                    raise ValueError("牌组名称、描述或学习计划校验失败。")
        return {"zip_crc": "ok", "sqlite_integrity": "ok", "deck_name": name,
                "notes": len(rows), "cards": len(cards), "unique_media": len(names),
                "referenced_media": len(references), "missing_media_references": 0,
                "source_order_and_guids": "ok", "new_card_positions": "ok", "study_plan": "ok"}


def update_package_study_plan(package_path: Path, genanki, deck_name: str = "Word Atlas") -> dict:
    """Rewrite only collection metadata, then validate before replacing the APKG."""
    package_path = package_path.resolve()
    with tempfile.TemporaryDirectory(prefix="word-atlas-plan-", dir=package_path.parent) as temporary:
        database = Path(temporary) / "collection.anki2"
        updated = Path(temporary) / "updated.apkg"
        with zipfile.ZipFile(package_path) as original:
            original_members = {item.filename: (item.CRC, item.file_size) for item in original.infolist()
                                if item.filename != "collection.anki2"}
            database.write_bytes(original.read("collection.anki2"))
            with closing(sqlite3.connect(database)) as connection:
                before_notes = connection.execute("SELECT * FROM notes ORDER BY id").fetchall()
                before_cards = connection.execute("SELECT * FROM cards ORDER BY id").fetchall()
                models = json.loads(connection.execute("SELECT models FROM col").fetchone()[0])
                # A metadata-only update also preserves cards in older bidirectional packages.
                card_ordinals = tuple(template["ord"] for template in models[str(MODEL_ID)]["tmpls"])
                entry_ids = [row[0].split("\x1f")[-1] for row in connection.execute("SELECT flds FROM notes ORDER BY id")]
                plan = configure_study_plan(connection.cursor(), deck_name)
                connection.commit()
                if (before_notes != connection.execute("SELECT * FROM notes ORDER BY id").fetchall()
                        or before_cards != connection.execute("SELECT * FROM cards ORDER BY id").fetchall()):
                    raise ValueError("学习计划更新不应改变笔记或卡片数据。")
            with zipfile.ZipFile(updated, "w", allowZip64=True) as result:
                for item in original.infolist():
                    if item.filename == "collection.anki2":
                        result.writestr(copy.copy(item), database.read_bytes())
                    else:
                        with original.open(item) as src, result.open(copy.copy(item), "w") as dst:
                            shutil.copyfileobj(src, dst, length=1024 * 1024)
        verification = verify_package(updated, entry_ids, genanki, card_ordinals)
        with zipfile.ZipFile(updated) as result:
            updated_members = {item.filename: (item.CRC, item.file_size) for item in result.infolist()
                               if item.filename != "collection.anki2"}
        if updated_members != original_members:
            raise ValueError("学习计划更新不应改变媒体或媒体索引。")
        updated.replace(package_path)
    return {"study_plan": plan, "verification": verification,
            "notes_cards_unchanged": True, "media_unchanged": True}


def generate(source: Path, genanki_source: Path, output: Path, ids: list[str] | None = None,
             deck_name: str | None = None) -> dict:
    source, genanki_source, output = source.resolve(), genanki_source.resolve(), output.resolve()
    if output == source or source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError("输出目录必须位于 Word Atlas 源仓库之外。")
    all_entries, index = load_source(source)
    entries = all_entries if ids is None else select_entries(all_entries, ids)
    if not entries:
        raise ValueError("词库为空。")
    ids = [entry["id"] for entry in entries]
    deck_name = deck_name or "Word Atlas"
    genanki, _ = load_genanki(genanki_source)
    templates = {name: (TEMPLATES / f"{name}.html").read_text(encoding="utf-8")
                 for name in ("front", "back")}
    css = (TEMPLATES / "card.css").read_text(encoding="utf-8")
    model = genanki.Model(MODEL_ID, "Word Atlas IELTS · 词义与表达 v1",
                          fields=[{"name": name} for name in FIELDS], css=css,
                          templates=[{"name": "英→中 · 词义回忆", "qfmt": templates["front"], "afmt": templates["back"]}])
    fonts = sorted((source / "dist/assets").glob("fraunces-latin-opsz-normal-*.woff2"))
    if not fonts:
        raise ValueError("dist/assets 中缺少 Fraunces Latin WOFF2 字体，请先构建源项目。")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fonts[0], output / "_wa_fraunces.woff2")
    shutil.copy2(TEMPLATES / "FONT-LICENSE.txt", output / "_wa_font_license.txt")
    shutil.copy2(source / "CONTENT_LICENSE.md", output / "CONTENT_LICENSE.md")
    # Include the licence both inside the package and beside the exported file.
    shutil.copy2(source / "CONTENT_LICENSE.md", output / "_wa_content_license.txt")
    flags_by_id = {row[0]: row[-1] for row in index["words"]}
    notes, media_report = [], []
    package_media = [output / "_wa_fraunces.woff2", output / "_wa_font_license.txt", output / "_wa_content_license.txt"]
    for position, entry in enumerate(entries, 1):
        media, report = copy_media(entry, flags_by_id.get(entry["id"], 0), source / "dist/atlas", output)
        fields = build_fields(entry, media)
        package_media.extend(output / item["filename"] for item in report if item["available"])
        notes.append(genanki.Note(model=model, fields=[fields[name] for name in FIELDS],
                                  due=position,
                                  guid=genanki.guid_for("word-atlas:v1", entry["id"]),
                                  tags=["word_atlas", f"topic::{entry['topic']}", f"cefr::{entry['cefr']}"]))
        media_report.append({"id": entry["id"], "media": report})
        if position % 500 == 0 or position == len(entries):
            print(f"整理词条与媒体：{position:,}/{len(entries):,}", flush=True)
    package_name = "Word Atlas.apkg"
    print(f"打包 {len(notes):,} 条笔记、{len(package_media):,} 个媒体/授权文件……", flush=True)
    write_package(genanki, model, notes, package_media, output / package_name, deck_name)
    print("校验 APKG、SQLite、全部卡片与媒体引用……", flush=True)
    verification = verify_package(output / package_name, ids, genanki)
    shutil.copy2(TEMPLATES / "card.css", output / "card.css")
    (output / "entries.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"source": source.as_posix(), "source_count": len(all_entries), "mode": "full" if len(entries) == len(all_entries) else "selection",
              "deck_name": deck_name, "entry_ids": ids,
              "cefr_counts": dict(Counter(e["cefr"] for e in all_entries)),
              "notes": len(notes), "cards": len(notes),
              "media_count": len(package_media), "genanki_source": str(Path(genanki.__file__).parent),
              "package": str(output / package_name), "media": media_report,
              "media_counts_by_kind": dict(Counter(item["kind"] for row in media_report for item in row["media"] if item["available"])),
              "package_bytes": (output / package_name).stat().st_size, "verification": verification,
              "content_changes": "Original text and media preserved; HTML formatting and exact-headword emphasis added."}
    report["study_plan"] = study_plan_summary(deck_name)
    (output / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("D:/me/word-atlas-main"))
    parser.add_argument("--genanki-source", type=Path, default=Path("D:/me/genanki"))
    parser.add_argument("--output", type=Path, default=ROOT / "anki_export/word-atlas", help="完整牌组输出目录")
    parser.add_argument("--all", action="store_true", help="兼容原命令；默认即生成完整词库")
    parser.add_argument("--deck-name", default="Word Atlas", help="牌组名称，默认为 Word Atlas")
    parser.add_argument("--update-study-plan", action="store_true", help="仅更新输出目录已有 APKG 的学习计划、选项名称与描述")
    args = parser.parse_args()
    try:
        if args.update_study_plan:
            package_path = args.output / "Word Atlas.apkg"
            genanki, _ = load_genanki(args.genanki_source)
            result = update_package_study_plan(package_path, genanki, args.deck_name)
            report_path = args.output / "build-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
            report.update(result)
            report.update({"deck_name": args.deck_name, "package": str(package_path.resolve()),
                           "package_bytes": package_path.stat().st_size})
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            with package_path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            package_path.with_suffix(".apkg.sha256").write_text(f"{digest}  {package_path.name}\n", encoding="utf-8")
            print(json.dumps({"package": str(package_path), **result}, ensure_ascii=False, indent=2))
            return
        report = generate(args.source, args.genanki_source, args.output, deck_name=args.deck_name)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"生成失败：{error}\n")
    print(json.dumps({key: report[key] for key in ("deck_name", "source_count", "notes", "cards", "media_count", "media_counts_by_kind", "package_bytes", "package", "verification")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
