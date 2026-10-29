"""Persistent FSRS evaluation schedule and an isolated background training process."""

from __future__ import annotations

import calendar
import json
import logging
import math
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from optimize_fsrs import MINIMUM_REVIEWS, effective_count, load_logs
from srs import SHANGHAI, SRS, parse_time, time_text, utc_now

LOG = logging.getLogger(__name__)
LEASE_SECONDS = 120
SCHEMA = """
CREATE TABLE IF NOT EXISTS fsrs_optimization_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    owner TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    lease_until TEXT,
    snapshot_review_id INTEGER NOT NULL,
    total_events INTEGER NOT NULL,
    effective_reviews INTEGER NOT NULL,
    new_effective_reviews INTEGER NOT NULL,
    baseline_version TEXT NOT NULL,
    activated_version TEXT,
    reason TEXT NOT NULL DEFAULT '',
    report_json TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fsrs_one_training
    ON fsrs_optimization_runs(status) WHERE status='running';
CREATE TABLE IF NOT EXISTS fsrs_optimizer_state (
    id INTEGER PRIMARY KEY CHECK(id=1),
    active_run_id INTEGER REFERENCES fsrs_optimization_runs(id),
    next_evaluation_at TEXT,
    last_evaluated_effective INTEGER NOT NULL DEFAULT 0,
    last_checked_at TEXT,
    effective_reviews INTEGER NOT NULL DEFAULT 0,
    total_events INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO fsrs_optimizer_state(id) VALUES(1);
"""


@dataclass
class OptimizationConfig:
    enabled: bool = True
    check_interval_seconds: int = 86400
    min_new_reviews: int = 100
    timeout_seconds: int = 3600

    def validate(self):
        if not isinstance(self.enabled, bool):
            raise ValueError("optimization.enabled 必须为布尔值")
        for name, minimum in (("check_interval_seconds", 1), ("min_new_reviews", 1), ("timeout_seconds", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"optimization.{name} 必须是正整数")


def next_month(now):
    local = now.astimezone(SHANGHAI)
    month = local.month % 12 + 1
    year = local.year + (local.month == 12)
    return local.replace(year=year, month=month, day=min(local.day, calendar.monthrange(year, month)[1]))


def _record(row):
    if row is None:
        return None
    result = dict(row)
    result.pop("owner", None)
    result.pop("lease_until", None)
    result["report"] = json.loads(result.pop("report_json"))
    return result


class OptimizationService:
    def __init__(self, stats, memory, config=None, now=utc_now, trainer=None):
        self.stats, self.memory = stats, memory
        self.db, self.lock = stats.db, stats.lock
        self.config = config or OptimizationConfig()
        self.config.validate()
        self.now, self.trainer = now, trainer
        self.folder = stats.path.resolve().parent / "fsrs-optimization"
        self._stop = threading.Event()
        self._checking = threading.Lock()
        self._thread = None
        with self.lock:
            self.db.executescript(SCHEMA)
        self.refresh_active()

    def refresh_active(self):
        if not self.config.enabled:
            return
        with self.lock:
            row = self.db.execute("""SELECT r.* FROM fsrs_optimizer_state s
                JOIN fsrs_optimization_runs r ON r.id=s.active_run_id WHERE s.id=1""").fetchone()
            if not row or row["status"] != "accepted":
                return
            parameters = json.loads(row["report_json"])["parameters"]
            if list(self.memory.srs.scheduler.parameters) != parameters:
                updated = SRS(self.memory.srs.config, parameters=parameters)
                with self.db:
                    self.db.execute("INSERT OR IGNORE INTO srs_configs VALUES(?,?)",
                                    (updated.version, json.dumps(updated.snapshot)))
                self.memory.srs = updated

    def start(self):
        if not self.config.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="fsrs-optimizer", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception:
                LOG.exception("FSRS automatic evaluation check failed")
            self._stop.wait(self.config.check_interval_seconds)

    def status(self):
        with self.lock:
            state = dict(self.db.execute("SELECT * FROM fsrs_optimizer_state WHERE id=1").fetchone())
            running = self.db.execute("SELECT id FROM fsrs_optimization_runs WHERE status='running'").fetchone()
            state.pop("id")
            return {**state, "enabled": self.config.enabled, "minimum_reviews": MINIMUM_REVIEWS,
                    "min_new_reviews": self.config.min_new_reviews,
                    "check_interval_seconds": self.config.check_interval_seconds,
                    "current_version": self.memory.srs.version,
                    "desired_retention": self.memory.srs.config.desired_retention,
                    "running_run_id": running[0] if running else None}

    def history(self, before_id=0, limit=20):
        limit = min(max(limit, 1), 100)
        with self.lock:
            rows = self.db.execute("""SELECT * FROM fsrs_optimization_runs WHERE (?=0 OR id < ?)
                ORDER BY id DESC LIMIT ?""", (before_id, before_id, limit + 1)).fetchall()
        return {"items": [_record(row) for row in rows[:limit]],
                "next_before_id": rows[limit - 1]["id"] if len(rows) > limit else None}

    def run_record(self, run_id):
        with self.lock:
            return _record(self.db.execute("SELECT * FROM fsrs_optimization_runs WHERE id=?", (run_id,)).fetchone())

    def _claim(self, snapshot_id, logs):
        now = self.now()
        effective = effective_count(logs, max_per_card=64)
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            expired = self.db.execute("""UPDATE fsrs_optimization_runs SET status='interrupted',
                finished_at=?,reason='后台任务中断，租约到期后重新评估' WHERE status='running' AND lease_until <= ?""",
                (time_text(now), time_text(now))).rowcount
            if expired:
                self.db.execute("UPDATE fsrs_optimizer_state SET next_evaluation_at=? WHERE id=1", (time_text(now),))
            self.db.execute("""UPDATE fsrs_optimizer_state SET last_checked_at=?,effective_reviews=?,total_events=? WHERE id=1""",
                            (time_text(now), effective, len(logs)))
            if self.db.execute("SELECT 1 FROM fsrs_optimization_runs WHERE status='running'").fetchone():
                return None
            state = self.db.execute("SELECT * FROM fsrs_optimizer_state WHERE id=1").fetchone()
            if effective < MINIMUM_REVIEWS or (state["next_evaluation_at"] and parse_time(state["next_evaluation_at"]) > now):
                return None
            new_reviews = effective - state["last_evaluated_effective"]
            skipped = state["last_evaluated_effective"] > 0 and new_reviews < self.config.min_new_reviews
            reason = f"新增有效间隔复习不足：{new_reviews} / {self.config.min_new_reviews}" if skipped else "后台评估中"
            owner = str(uuid4())
            baseline = self.memory.srs
            report = {"fsrs_version": "6.3.2", "baseline_parameters": list(baseline.scheduler.parameters),
                      "training_start": time_text(logs[0].review_datetime),
                      "validation_through": time_text(logs[-1].review_datetime)}
            cursor = self.db.execute("""INSERT INTO fsrs_optimization_runs
                (status,owner,started_at,finished_at,lease_until,snapshot_review_id,total_events,effective_reviews,
                 new_effective_reviews,baseline_version,reason,report_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    "skipped" if skipped else "running", owner, time_text(now), time_text(now) if skipped else None,
                    time_text(now + timedelta(seconds=LEASE_SECONDS)), snapshot_id, len(logs), effective,
                    new_reviews, baseline.version, reason, json.dumps(report),
                ))
            self.db.execute("UPDATE fsrs_optimizer_state SET next_evaluation_at=? WHERE id=1", (time_text(next_month(now)),))
            return cursor.lastrowid, owner, skipped

    def check_once(self):
        if not self.config.enabled or not self._checking.acquire(blocking=False):
            return None
        try:
            self.refresh_active()
            with self.lock:
                snapshot_id = self.db.execute("SELECT COALESCE(MAX(id),0) FROM word_reviews").fetchone()[0]
            logs = load_logs(self.stats.path, snapshot_id)
            claim = self._claim(snapshot_id, logs)
            if claim is None:
                return None
            run_id, owner, skipped = claim
            if skipped:
                return self.run_record(run_id)
            record = self.run_record(run_id)
            try:
                result = (self.trainer(record, logs) if self.trainer is not None
                          else self._train_process(record, owner))
                self._finish(run_id, owner, result)
            except Exception as exc:
                LOG.exception("FSRS evaluation %s failed", run_id)
                self._finish(run_id, owner, None, str(exc))
            return self.run_record(run_id)
        finally:
            self._checking.release()

    def _heartbeat(self, run_id, owner):
        with self.lock, self.db:
            return self.db.execute("""UPDATE fsrs_optimization_runs SET lease_until=?
                WHERE id=? AND owner=? AND status='running'""",
                (time_text(self.now() + timedelta(seconds=LEASE_SECONDS)), run_id, owner)).rowcount == 1

    def _train_process(self, record, owner):
        self.folder.mkdir(parents=True, exist_ok=True)
        run_id = record["id"]
        baseline_path = self.folder / f"run-{run_id}-baseline.json"
        output_path = self.folder / f"run-{run_id}.json"
        baseline_path.write_text(json.dumps({"fsrs_version": "6.3.2", "accepted": True,
            "parameters": record["report"]["baseline_parameters"]}), encoding="utf-8")
        command = [sys.executable, str(Path(__file__).with_name("optimize_fsrs.py")),
                   "--db", str(self.stats.path.resolve()), "--output", str(output_path),
                   "--current", str(baseline_path), "--through-id", str(record["snapshot_review_id"])]
        env = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
               "CUDA_VISIBLE_DEVICES": "", "PYTHONIOENCODING": "utf-8"}
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == "nt" else 0
        log_path = self.folder / f"run-{run_id}.log"
        with log_path.open("wb") as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, env=env, creationflags=flags)
            deadline = time.monotonic() + self.config.timeout_seconds
            try:
                while True:
                    if self._stop.is_set():
                        raise RuntimeError("服务停止，后台训练已中断")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("后台训练超过时限，已停止")
                    if not self._heartbeat(run_id, owner):
                        raise RuntimeError("后台任务租约已失效")
                    try:
                        code = process.wait(timeout=min(1, max(0.01, deadline - time.monotonic())))
                        break
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        if code != 0:
            raise RuntimeError(log_path.read_text(encoding="utf-8", errors="replace")[-4000:] or f"训练进程退出码 {code}")
        return json.loads(output_path.read_text(encoding="utf-8"))

    def _finish(self, run_id, owner, result, error=""):
        now = self.now()
        updated = None
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM fsrs_optimization_runs WHERE id=?", (run_id,)).fetchone()
            if row["status"] != "running" or row["owner"] != owner:
                return
            report = json.loads(row["report_json"])
            if error:
                status, reason = "failed", error
                next_at = now + timedelta(days=1)
                report["error"] = error
            else:
                report.update(result)
                next_at = next_month(now)
                if result.get("accepted") is True:
                    if result.get("fsrs_version") != "6.3.2":
                        raise ValueError("优化结果的 FSRS 版本不匹配")
                    parameters = result["parameters"]
                    if len(parameters) != 21 or not all(isinstance(value, (int, float)) and
                            not isinstance(value, bool) and math.isfinite(value) for value in parameters):
                        raise ValueError("优化结果包含无效参数")
                    for label in ("baseline", "default", "candidate"):
                        metric = result[label]
                        if metric["reviews"] < 100 or not all(isinstance(metric[key], (int, float)) and
                                math.isfinite(metric[key]) and metric[key] >= 0 for key in ("log_loss", "brier_score")):
                            raise ValueError("优化结果缺少有效验证指标")
                    baseline, default, candidate = (result[key] for key in ("baseline", "default", "candidate"))
                    if (candidate["reviews"] != baseline["reviews"] or candidate["reviews"] != default["reviews"] or
                            candidate["log_loss"] >= min(baseline["log_loss"], default["log_loss"]) or
                            candidate["brier_score"] > baseline["brier_score"]):
                        raise ValueError("候选参数未通过验证，不予启用")
                    updated = SRS(self.memory.srs.config, parameters=result["parameters"])
                    if self.memory.srs.version != row["baseline_version"]:
                        status, reason, updated = "superseded", "现用配置已变更，本次候选不启用", None
                        next_at = now + timedelta(days=1)
                    else:
                        status, reason = "accepted", "验证误差改善，已自动启用"
                        self.db.execute("INSERT OR IGNORE INTO srs_configs VALUES(?,?)", (updated.version, json.dumps(updated.snapshot)))
                        self.db.execute("UPDATE fsrs_optimizer_state SET active_run_id=? WHERE id=1", (run_id,))
                else:
                    status = "skipped" if result.get("outcome") == "insufficient_data" else "rejected"
                    reason = result["reason"]
                self.db.execute("UPDATE fsrs_optimizer_state SET last_evaluated_effective=? WHERE id=1", (row["effective_reviews"],))
            self.db.execute("""UPDATE fsrs_optimization_runs SET status=?,finished_at=?,activated_version=?,reason=?,report_json=?
                WHERE id=?""", (status, time_text(now), updated.version if updated else None, reason,
                                json.dumps(report, ensure_ascii=False, allow_nan=False), run_id))
            self.db.execute("UPDATE fsrs_optimizer_state SET next_evaluation_at=? WHERE id=1", (time_text(next_at),))
            # Publish after commit while retaining the same lock used by formal reviews.
            self.db.commit()
            if updated is not None:
                self.memory.srs = updated
