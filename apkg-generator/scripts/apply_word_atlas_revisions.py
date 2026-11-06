"""Update an existing collection through Anki's API, preserving cards and history.

Run inside Anki's Python environment, or call run_in_anki(mw) from its console.
The ordinary project Python can prepare the update plan without importing Anki.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path

import generate_word_atlas as atlas


def media_fields(entry: dict, flags: int, source: Path) -> tuple[dict, dict]:
    fields, revised_files = {}, {}
    for (field, _, _, _, kind), item in zip(atlas.MEDIA_SPECS, atlas.media_report(entry, flags, source / "dist/atlas")):
        if not item["available"]:
            fields[field] = ""
            continue
        name = item["filename"]
        fields[field] = f'<img src="{name}" alt="词义插画">' if kind == "img" else f"[sound:{name}]"
        if kind in entry.get("_media_overrides", {}):
            revised_files[name] = Path(item["source"])
    return fields, revised_files


def prepare_updates(source: Path) -> tuple[dict, dict]:
    source = source.resolve()
    raw = json.loads((source / "data/word-atlas.json").read_text(encoding="utf-8"))
    index = json.loads((source / "dist/atlas/index.json").read_text(encoding="utf-8"))
    flags = {row[0]: row[-1] for row in index["words"]}
    rules = atlas.revision_rules()
    updates, media = {}, {}
    for entry in raw:
        source_id = entry["id"]
        if source_id not in rules["excluded"] and source_id not in rules["rewrites"]:
            continue
        revised = atlas.revise_entry(entry, rules)
        old_media, _ = media_fields(entry, flags.get(source_id, 0), source)
        new_media, files = media_fields(revised, flags.get(source_id, 0), source)
        old_fields = atlas.build_fields(entry, old_media)
        new_fields = atlas.build_fields(revised, new_media)
        tags = []
        if canonical := revised.get("_excluded_for"):
            tags = [rules["excluded_tag"], rules["canonical_tag_prefix"] + canonical]
        updates[source_id] = {
            "expected_words": [entry["w"], revised["w"]],
            "fields": {key: value for key, value in new_fields.items() if value != old_fields[key]},
            "tags": tags, "suspend": bool(tags),
        }
        media.update(files)
    return updates, media


def card_history(col, note_ids: list[int]) -> list:
    ids = ",".join(map(str, note_ids))
    return col.db.all(f"SELECT id,nid,did,ord,type,due,ivl,factor,reps,lapses,left,odue,odid,flags,data FROM cards WHERE nid IN ({ids}) ORDER BY id")


def review_digest(col) -> str:
    return hashlib.sha256(repr(col.db.all("SELECT * FROM revlog ORDER BY id")).encode()).hexdigest()


def apply_to_collection(col, source: Path, report_dir: Path, *, apply: bool = False) -> dict:
    updates, media = prepare_updates(source)
    found, changed, suspend = {}, [], []
    before_notes = []
    for note_id in col.find_notes('deck:"Word Atlas"'):
        note = col.get_note(note_id)
        if "SourceId" not in note:
            continue
        source_id = note["SourceId"]
        if source_id not in updates:
            continue
        if source_id in found:
            raise ValueError(f"Anki 中 SourceId 重复：{source_id}")
        update = updates[source_id]
        word = html.unescape(re.sub(r"<[^>]*>", "", note["Word"])).strip()
        if word not in update["expected_words"]:
            raise ValueError(f"{source_id} 的当前词头为 {word}，与修订表不符。")
        found[source_id] = int(note_id)
        before_notes.append({"note_id": int(note_id), "guid": note.guid, "fields": dict(note.items()), "tags": list(note.tags)})
        pending_fields = {key: value for key, value in update["fields"].items() if note[key] != value}
        pending_tags = [tag for tag in update["tags"] if tag not in note.tags]
        if pending_fields or pending_tags:
            for key, value in pending_fields.items():
                note[key] = value
            for tag in pending_tags:
                note.add_tag(tag)
            changed.append(note)
        if update["suspend"]:
            suspend += list(col.find_cards(f"nid:{note_id} -is:suspended"))
    missing = sorted(set(updates) - set(found))
    if missing:
        raise ValueError("Anki 牌组缺少待处理词条：" + ", ".join(missing))
    summary = {"matched_notes": len(found), "notes_to_update": len(changed), "cards_to_suspend": len(suspend),
               "media_files": len(media), "applied": False}
    if not apply:
        return summary
    report_dir.mkdir(parents=True, exist_ok=True)
    before_cards = card_history(col, list(found.values()))
    before_reviews = review_digest(col)
    if changed or suspend:
        backups = report_dir / "backups"
        backups.mkdir(exist_ok=True)
        col.create_backup(backup_folder=str(backups), force=True, wait_for_completion=True)
        (report_dir / "notes-before.json").write_text(json.dumps(before_notes, ensure_ascii=False, indent=2), encoding="utf-8")
        undo = col.add_custom_undo_entry("整理 Word Atlas 变体")
        for name, path in media.items():
            actual = col.media.write_data(name, path.read_bytes())
            if actual != name:
                raise ValueError(f"修订媒体文件名冲突：{name} -> {actual}")
        if changed:
            col.update_notes(changed)
        if suspend:
            col.sched.suspend_cards(suspend)
        col.merge_undo_entries(undo)
    if card_history(col, list(found.values())) != before_cards or review_digest(col) != before_reviews:
        raise RuntimeError("更新后卡片调度数据或复习日志发生意外变化，请使用备份恢复。")
    for item in before_notes:
        note = col.get_note(item["note_id"])
        if note.guid != item["guid"] or note["SourceId"] not in found:
            raise RuntimeError("更新后的笔记稳定标识发生变化。")
    summary.update(applied=True, history_preserved=True, report_dir=str(report_dir.resolve()))
    (report_dir / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def run_in_anki(mw) -> dict:
    report_dir = atlas.ROOT / "anki_export/word-atlas/updates" / datetime.now().strftime("%Y%m%d-%H%M%S")
    result = apply_to_collection(mw.col, Path("D:/me/word-atlas-main"), report_dir, apply=True)
    mw.reset()
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True, help="Anki 已正常关闭的 collection.anki2")
    parser.add_argument("--source", type=Path, default=Path("D:/me/word-atlas-main"))
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="默认只预览；指定后备份并应用")
    args = parser.parse_args()
    from anki.collection import Collection
    col = Collection(str(args.collection.resolve()))
    try:
        print(json.dumps(apply_to_collection(col, args.source, args.report_dir, apply=args.apply), ensure_ascii=False, indent=2), flush=True)
    finally:
        col.close()


if __name__ == "__main__":
    main()
