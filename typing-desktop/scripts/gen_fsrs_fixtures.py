"""Generate py-fsrs golden vectors for the desktop (Rust) FSRS port.

The desktop scheduler must reproduce typing-practice/backend/srs.py exactly
(fuzz disabled). Run from the repository root:

    .venv/Scripts/python.exe typing-desktop/scripts/gen_fsrs_fixtures.py
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "typing-practice" / "backend"))

from fsrs import Card, Rating  # noqa: E402

from srs import SRS, MemoryConfig, answer_candidates, normalize_answer, time_text  # noqa: E402

OUTPUT = ROOT / "typing-desktop" / "fixtures" / "fsrs-golden.json"
START = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
# Gaps cover learning steps (minutes), same-day relearning and long reviews.
GAPS = [timedelta(seconds=30), timedelta(minutes=1), timedelta(minutes=10), timedelta(hours=6),
        timedelta(days=1), timedelta(days=3), timedelta(days=10), timedelta(days=40), timedelta(days=200)]


def card_state(card: Card) -> dict:
    return {
        "state": int(card.state), "step": card.step,
        "stability": card.stability, "difficulty": card.difficulty,
        "due": time_text(card.due), "last_review": time_text(card.last_review) if card.last_review else None,
    }


def sequences(srs: SRS, count: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    result = []
    for index in range(count):
        card = Card(card_id=index + 1, due=START)
        now = START
        steps = []
        for _ in range(rng.randint(1, 14)):
            # Mostly review at/after due, sometimes early (free practice).
            gap = rng.choice(GAPS) if rng.random() < 0.3 else max(card.due - now, timedelta(0)) + rng.choice(GAPS[:5])
            now = now + gap
            rating = Rating(rng.choices([1, 2, 3, 4], weights=[3, 2, 5, 2])[0])
            card, _ = srs.scheduler.review_card(card, rating, now)
            steps.append({
                "reviewed_at": time_text(now), "rating": int(rating),
                "after": card_state(card),
                "retrievability_at_review_plus_1d": srs.scheduler.get_card_retrievability(card, now + timedelta(days=1)),
            })
        result.append({"card_id": index + 1, "start": time_text(START), "steps": steps})
    return result


def grade_cases(srs: SRS) -> list[dict]:
    cases = []
    for correct in (True, False):
        for ms in (0, 5999.9, 6000, 6000.1, 19999, 20000, 20000.1, 60000):
            cases.append({"correct": correct, "duration_ms": ms, "rating": int(srs.grade(correct, ms))})
    return cases


def answer_cases() -> list[dict]:
    words = ["apple", "Mother-in-law", "o'clock", "colour/color", "ice cream", " well-being ", "a/an/the"]
    inputs = ["apple", " APPLE ", "mother-in-law", "oclock", "o'clock", "color", "colour", "ice  cream",
              "icecream", "well-being", "an", "the", "app1e", "", "  ", "café", "a"]
    return [{"word": word, "input": value, "normalized": normalize_answer(value),
             "candidates": answer_candidates(word),
             "correct": bool(normalize_answer(value)) and normalize_answer(value) in answer_candidates(word)}
            for word in words for value in inputs]


def main() -> None:
    config = MemoryConfig(enable_fuzzing=False)
    srs = SRS(config)
    data = {
        "generator": "typing-desktop/scripts/gen_fsrs_fixtures.py",
        "fsrs_version": "6.3.2",
        "scheduler": srs.scheduler.to_dict(),
        "grading": {"easy_seconds": config.easy_seconds, "hard_seconds": config.hard_seconds, "cases": grade_cases(srs)},
        "answers": answer_cases(),
        "sequences": sequences(srs, 300, seed=20261102),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}: {len(data['sequences'])} sequences, "
          f"{sum(len(s['steps']) for s in data['sequences'])} reviews")


if __name__ == "__main__":
    main()
