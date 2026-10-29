"""FSRS scheduling and the application's automatic spelling grades."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fsrs import Card, Rating, Scheduler, State

SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
MASTERED_STABILITY = 21


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def time_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("时间必须包含时区") from exc


def duration(value: object, name: str = "duration_ms") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} 必须是非负有限数值")
    return float(value)


def normalize_answer(value: str) -> str:
    # Keep identical to the browser's sanitizeInput / normalizeAnswer.
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z\s'\-]", "", value)).strip().lower()


def answer_candidates(word: str) -> list[str]:
    return [normalized for part in word.split("/") if (normalized := normalize_answer(part))]


@dataclass
class MemoryConfig:
    desired_retention: float = 0.9
    daily_new: int = 20
    easy_seconds: float = 6
    hard_seconds: float = 20
    parameters_path: str = ""
    enable_fuzzing: bool = True

    def validate(self) -> None:
        if not 0 < self.desired_retention < 1:
            raise ValueError("memory.desired_retention 必须在 0 和 1 之间")
        if isinstance(self.daily_new, bool) or not isinstance(self.daily_new, int) or self.daily_new < 0:
            raise ValueError("memory.daily_new 必须是非负整数")
        duration(self.easy_seconds, "memory.easy_seconds")
        duration(self.hard_seconds, "memory.hard_seconds")
        if not 0 < self.easy_seconds < self.hard_seconds:
            raise ValueError("评分阈值必须满足 0 < easy_seconds < hard_seconds")
        if not isinstance(self.enable_fuzzing, bool):
            raise ValueError("memory.enable_fuzzing 必须是布尔值")


class SRS:
    def __init__(self, config: MemoryConfig, parameters=None):
        config.validate()
        self.config = config
        kwargs = {}
        if parameters is not None:
            kwargs["parameters"] = parameters
        elif config.parameters_path:
            artifact = json.loads(Path(config.parameters_path).read_text(encoding="utf-8"))
            if artifact.get("fsrs_version") != "6.3.2" or artifact.get("accepted") is not True:
                raise ValueError("参数文件必须是经过验证的 fsrs 6.3.2 优化结果")
            kwargs["parameters"] = artifact["parameters"]
        self.scheduler = Scheduler(
            **kwargs, desired_retention=config.desired_retention,
            learning_steps=(timedelta(minutes=1), timedelta(minutes=10)),
            relearning_steps=(timedelta(minutes=10),), enable_fuzzing=config.enable_fuzzing,
        )
        self.snapshot = {
            "fsrs_version": "6.3.2", "rating_version": 1,
            "easy_seconds": config.easy_seconds, "hard_seconds": config.hard_seconds,
            "scheduler": self.scheduler.to_dict(),
        }
        self.version = hashlib.sha256(json.dumps(self.snapshot, sort_keys=True).encode()).hexdigest()[:20]

    def grade(self, correct: bool, duration_ms: float) -> Rating:
        elapsed = duration(duration_ms)
        if not correct:
            return Rating.Again
        if elapsed > self.config.hard_seconds * 1000:
            return Rating.Hard
        if elapsed < self.config.easy_seconds * 1000:
            return Rating.Easy
        return Rating.Good

    def review(self, card: Card, correct: bool, duration_ms: float, now: datetime):
        return self.scheduler.review_card(card, self.grade(correct, duration_ms), now, round(duration_ms))

    def describe(self, card: Card, now: datetime) -> dict:
        return {
            "status": "mastered" if is_mastered(card) else "learning",
            "state": int(card.state), "stability": card.stability, "difficulty": card.difficulty,
            "due": time_text(card.due), "is_due": card.due <= now,
            "retrievability": self.scheduler.get_card_retrievability(card, now),
        }


def is_mastered(card: Card) -> bool:
    return card.state == State.Review and (card.stability or 0) >= MASTERED_STABILITY
