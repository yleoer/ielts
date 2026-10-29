"""Offline, read-only training; writes a candidate artifact, never changes the live schedule."""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from fsrs import Card, Rating, ReviewLog, Scheduler

from srs import parse_time, time_text, utc_now

MINIMUM_REVIEWS = 1000


def load_logs(path: Path, through_id: int | None = None) -> list[ReviewLog]:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("""SELECT memory_id,rating,reviewed_at,duration_ms FROM word_reviews
            WHERE (? IS NULL OR id <= ?) ORDER BY reviewed_at,id""", (through_id, through_id)).fetchall()
    return [ReviewLog(card_id, Rating(rating), parse_time(when), round(duration)) for card_id, rating, when, duration in rows]


def effective_count(logs: list[ReviewLog], max_per_card: int | None = None) -> int:
    previous, seen = {}, defaultdict(int)
    count = 0
    for log in logs:
        seen[log.card_id] += 1
        if max_per_card and seen[log.card_id] > max_per_card:
            continue
        last = previous.get(log.card_id)
        if last and (log.review_datetime - last).days > 0:
            count += 1
        previous[log.card_id] = log.review_datetime
    return count


def evaluate(logs: list[ReviewLog], parameters, cutoff) -> dict:
    """Predict before applying each answer; holdout outcomes never fit weights."""
    scheduler = Scheduler(parameters=parameters, enable_fuzzing=False)
    cards, losses, squared = {}, [], []
    for log in logs:
        card = cards.get(log.card_id) or Card(card_id=log.card_id, due=log.review_datetime)
        if card.last_review and (log.review_datetime - card.last_review).days > 0 and log.review_datetime >= cutoff:
            p = min(max(scheduler.get_card_retrievability(card, log.review_datetime), 1e-9), 1 - 1e-9)
            y = int(log.rating != Rating.Again)
            losses.append(-y * math.log(p) - (1 - y) * math.log(1 - p))
            squared.append((p - y) ** 2)
        cards[log.card_id], _ = scheduler.review_card(card, log.rating, log.review_datetime)
    return {"reviews": len(losses), "log_loss": sum(losses) / len(losses) if losses else None,
            "brier_score": sum(squared) / len(squared) if squared else None}


def optimize(logs, current_parameters=None, optimizer_factory=None):
    logs = sorted(logs, key=lambda log: (log.review_datetime, log.card_id))
    # The installed optimizer only uses the first 64 events per card.
    effective = effective_count(logs, max_per_card=64)
    metadata = {"fsrs_version": "6.3.2", "created_at": time_text(utc_now()),
                "effective_reviews": effective, "total_events": len(logs),
                "training_start": time_text(logs[0].review_datetime) if logs else None,
                "validation_through": time_text(logs[-1].review_datetime) if logs else None}
    if effective < MINIMUM_REVIEWS:
        return {**metadata, "accepted": False, "outcome": "insufficient_data",
                "reason": f"有效间隔复习不足：{effective} / {MINIMUM_REVIEWS}"}
    cutoff = logs[int(len(logs) * 0.8)].review_datetime
    train = [log for log in logs if log.review_datetime < cutoff]
    metadata.update(training_before=time_text(cutoff), training_events=len(train),
                    training_effective_reviews=effective_count(train, max_per_card=64))
    if effective_count(train, max_per_card=64) < 512:
        return {**metadata, "accepted": False, "outcome": "insufficient_data", "reason": "训练区间内有效复习不足 512 条"}
    default_parameters = list(Scheduler().parameters)
    baseline_parameters = current_parameters or default_parameters
    baseline = evaluate(logs, baseline_parameters, cutoff)
    default = evaluate(logs, default_parameters, cutoff)
    if baseline["reviews"] < 100:
        return {**metadata, "accepted": False, "outcome": "insufficient_data", "baseline": baseline,
                "default": default, "reason": "留出的验证区间内有效复习不足 100 条"}
    if optimizer_factory is None:
        from fsrs import Optimizer
        optimizer_factory = Optimizer
    parameters = list(optimizer_factory(train).compute_optimal_parameters())
    if len(parameters) != 21 or not all(math.isfinite(value) for value in parameters):
        raise ValueError("优化器返回无效参数")
    candidate = evaluate(logs, parameters, cutoff)
    accepted = candidate["log_loss"] < min(baseline["log_loss"], default["log_loss"]) and candidate["brier_score"] <= baseline["brier_score"]
    return {
        **metadata, "accepted": accepted, "parameters": parameters,
        "outcome": "accepted" if accepted else "not_improved",
        "baseline": baseline, "default": default, "candidate": candidate,
        "reason": "验证误差改善" if accepted else "验证结果未改善，保留现用参数",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--current", type=Path, help="当前启用的参数文件；省略表示默认参数")
    parser.add_argument("--through-id", type=int, help="仅训练此作答日志 ID 及以前的数据")
    args = parser.parse_args()
    if args.output.resolve() == args.db.resolve() or (args.current and args.output.resolve() == args.current.resolve()):
        parser.error("输出必须使用独立的新参数文件，不能覆盖数据库或当前参数")
    current = None
    if args.current:
        artifact = json.loads(args.current.read_text(encoding="utf-8"))
        if artifact.get("fsrs_version") != "6.3.2" or artifact.get("accepted") is not True:
            parser.error("当前参数文件无效")
        current = artifact["parameters"]
    try:
        import torch
        torch.set_num_threads(1)
        result = optimize(load_logs(args.db, args.through_id), current)
    except ImportError:
        parser.exit(1, '训练需要在本地安装：python -m pip install "fsrs[optimizer]==6.3.2"\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(result["reason"])


if __name__ == "__main__":
    main()
