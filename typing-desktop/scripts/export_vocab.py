"""Export a Word Atlas vocabulary snapshot for the desktop app.

Uses typing-practice/backend/anki.py so the desktop never parses Anki markup.
The same JSON shape will later be served by the sync server (`/api/vocab`).

    .venv/Scripts/python.exe typing-desktop/scripts/export_vocab.py \
        --db typing-practice/data/local-demo/collection.anki2 --out vocab.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "typing-practice" / "backend"))

from anki import AnkiReader  # noqa: E402


def export(db: str, deck_name: str, deck_id: int) -> dict:
    reader = AnkiReader(db, deck_name, deck_id)
    try:
        learned = {word["id"] for word in reader.get_learned_word_pool()}
        words = []
        for word in reader.get_word_pool():
            word["learned"] = word["id"] in learned
            word["illustration_file"] = reader.get_media_filename(word["id"], "illustration")
            words.append(word)
    finally:
        reader.close()
    return {
        "format": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "deck_name": deck_name,
        "words": words,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, help="collection.anki2 路径")
    parser.add_argument("--out", required=True, help="输出 JSON 路径")
    parser.add_argument("--deck-name", default="Word Atlas")
    parser.add_argument("--deck-id", type=int, default=1958430017)
    args = parser.parse_args()
    data = export(args.db, args.deck_name, args.deck_id)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    learned = sum(word["learned"] for word in data["words"])
    print(f"wrote {args.out}: {len(data['words'])} words, {learned} learned")


if __name__ == "__main__":
    main()
