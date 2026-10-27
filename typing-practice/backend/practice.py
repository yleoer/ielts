"""Weighted word selection used by the practice endpoint."""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Any


def normalize_word(word: str) -> str:
    return (word or "").strip().lower()


def rounded_percent(total: int, percent: int) -> int:
    return (total * percent + 50) // 100


def bucket_quotas(limit: int) -> dict[str, int]:
    weak = rounded_percent(limit, 40)
    learning = rounded_percent(limit, 25)
    review = rounded_percent(limit, 20)
    return {"weak": weak, "learning": learning, "review": review, "random": max(0, limit - weak - learning - review)}


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def days_since(last_attempt: Any, now: datetime) -> int:
    value = _parse_time(last_attempt)
    if not value or now < value:
        return 0
    return int((now - value).total_seconds() // 86400)


def base_score(level: str) -> float:
    return {"weak": 80, "learning": 45, "familiar": 20, "mastered": 5, "new": 30}.get((level or "").strip().lower(), 30)


def bucket_for(item: dict[str, Any], now: datetime) -> str:
    if not item or not item.get("total_attempts"):
        return "random"
    level = str(item.get("mastery_level") or "").lower().strip()
    due = days_since(item.get("last_attempt_time"), now) >= 7
    if not item.get("last_attempt_correct", True) or level == "weak" or item.get("incorrect_attempts", 0) > item.get("correct_attempts", 0):
        return "weak"
    if due and level in {"mastered", "familiar"}:
        return "review"
    if level in {"learning", "familiar"}:
        return "learning"
    return "random"


def score_word(item: dict[str, Any], now: datetime) -> float:
    if not item or not item.get("total_attempts"):
        return base_score("new")
    score = base_score(str(item.get("mastery_level", "")))
    score += int(item.get("incorrect_attempts", 0)) * 8
    score -= int(item.get("correct_attempts", 0)) * 2
    if not item.get("last_attempt_correct", True):
        score += 25
    elapsed = days_since(item.get("last_attempt_time"), now)
    if elapsed >= 14:
        score += 35
    elif elapsed >= 7:
        score += 25
    elif elapsed >= 3:
        score += 10
    average = float(item.get("average_time") or 0)
    if average > 8:
        score += 15
    elif average > 5:
        score += 10
    elif average > 3:
        score += 5
    return max(score, 1)


def _weighted_index(pool: list[dict[str, Any]], rng: random.Random) -> int:
    total = sum(max(float(item["score"]), 0) for item in pool)
    if total <= 0:
        return rng.randrange(len(pool))
    needle = rng.random() * total
    for index, item in enumerate(pool):
        needle -= max(float(item["score"]), 0)
        if needle <= 0:
            return index
    return len(pool) - 1


def _take_from_bucket(items: list[dict[str, Any]], bucket: str, count: int, selected: set[int], rng: random.Random) -> list[dict[str, Any]]:
    pool = [item for item in items if item["word"].get("id") not in selected and (not bucket or item["bucket"] == bucket)]
    result: list[dict[str, Any]] = []
    while pool and len(result) < count:
        index = _weighted_index(pool, rng)
        item = pool.pop(index)
        selected.add(item["word"].get("id"))
        result.append(item["word"])
    return result


def select_words(candidates: list[dict[str, Any]], stats_by_word: dict[str, dict[str, Any]], limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
    if limit <= 0 or not candidates:
        return []
    limit = min(limit, len(candidates))
    now = now or datetime.now(timezone.utc)
    lookup = {normalize_word(key): value for key, value in stats_by_word.items()}
    items: list[dict[str, Any]] = []
    for word in candidates:
        item = lookup.get(normalize_word(word.get("word", "")), {})
        items.append({"word": word, "score": score_word(item, now), "bucket": bucket_for(item, now)})
    selected: set[int] = set()
    result: list[dict[str, Any]] = []
    rng = random.Random()
    for bucket in ("weak", "learning", "review", "random"):
        result.extend(_take_from_bucket(items, bucket, bucket_quotas(limit)[bucket], selected, rng))
    if len(result) < limit:
        result.extend(_take_from_bucket(items, "", limit - len(result), selected, rng))
    return result[:limit]

