//! Local FSRS parameter optimization.
//!
//! Port of `optimize_fsrs.py` (time-split evaluation and acceptance rules) and
//! `optimizer_service.py` (run ledger, monthly schedule, activation). Training uses
//! fsrs-rs `compute_parameters` in a background thread instead of a PyTorch process.
//! A run left `running` when the app exits is marked interrupted on the next start.

use std::collections::HashMap;
use std::panic::{catch_unwind, AssertUnwindSafe};

use chrono::{Datelike, NaiveDate, TimeDelta};
use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use serde_json::{json, Value};

use crate::error::{ApiError, ApiResult};
use crate::fsrs::{Card, Rating, Scheduler, DEFAULT_PARAMETERS};
use crate::srs::MemoryConfig;
use crate::stats::query_objects;
use crate::store::{shanghai, Active, Store};
use crate::time::{parse_time, time_text, whole_days, Time};

pub const MINIMUM_REVIEWS: usize = 1000;
/// Like py-fsrs, only the first 64 events of each card are used.
const MAX_PER_CARD: usize = 64;
pub const FSRS_VERSION: &str = "6.3.2";

pub const SCHEMA: &str = r#"
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
"#;

#[derive(Clone, Debug)]
pub struct OptimizationConfig {
    pub enabled: bool,
    pub check_interval_seconds: u64,
    pub min_new_reviews: usize,
}

impl Default for OptimizationConfig {
    fn default() -> Self {
        OptimizationConfig { enabled: true, check_interval_seconds: 86400, min_new_reviews: 100 }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ReviewLog {
    pub card_id: i64,
    pub rating: Rating,
    pub at: Time,
}

/// Fits parameters from training logs (fsrs-rs in production, a stub in tests).
pub type Trainer<'a> = &'a dyn Fn(&[ReviewLog]) -> Result<Vec<f64>, String>;
/// Produces the evaluation report for a run from the snapshot logs and the
/// parameters in force (normally [`evaluate_with_fsrs_rs`]).
pub type Evaluation<'a> = &'a dyn Fn(&[ReviewLog], [f64; 21]) -> Result<Value, String>;

/// Review ledger up to `through_id`, ordered by answer time.
pub fn load_logs(db: &Connection, through_id: i64) -> ApiResult<Vec<ReviewLog>> {
    let mut stmt = db.prepare("SELECT memory_id,rating,reviewed_at FROM word_reviews WHERE id <= ? ORDER BY reviewed_at,id")?;
    let rows = stmt.query_map([through_id], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, u8>(1)?, r.get::<_, String>(2)?)))?;
    rows.map(|row| {
        let (card_id, rating, at) = row?;
        Ok(ReviewLog { card_id, rating: Rating::try_from(rating).map_err(ApiError::Unavailable)?, at: parse_time(&at).map_err(ApiError::Unavailable)? })
    }).collect()
}

/// Reviews at least one whole day after the card's previous review.
pub fn effective_count(logs: &[ReviewLog], max_per_card: Option<usize>) -> usize {
    let mut previous: HashMap<i64, Time> = HashMap::new();
    let mut seen: HashMap<i64, usize> = HashMap::new();
    let mut count = 0;
    for log in logs {
        let n = seen.entry(log.card_id).or_default();
        *n += 1;
        if max_per_card.is_some_and(|m| *n > m) {
            continue;
        }
        if previous.get(&log.card_id).is_some_and(|last| whole_days(log.at - *last) > 0) {
            count += 1;
        }
        previous.insert(log.card_id, log.at);
    }
    count
}

fn evaluation_scheduler(parameters: &[f64; 21]) -> Result<Scheduler, String> {
    Scheduler::new(*parameters, 0.9, vec![TimeDelta::minutes(1), TimeDelta::minutes(10)], vec![TimeDelta::minutes(10)], 36500, false)
}

/// Predicts before applying each answer; holdout outcomes never fit weights.
pub fn evaluate(logs: &[ReviewLog], parameters: &[f64; 21], cutoff: Time) -> Result<Value, String> {
    let scheduler = evaluation_scheduler(parameters)?;
    let mut cards: HashMap<i64, Card> = HashMap::new();
    let (mut losses, mut squared) = (vec![], vec![]);
    for log in logs {
        let card = cards.remove(&log.card_id).unwrap_or_else(|| Card::new(log.card_id, log.at));
        if card.last_review.is_some_and(|last| whole_days(log.at - last) > 0) && log.at >= cutoff {
            let p = scheduler.retrievability(&card, log.at).clamp(1e-9, 1.0 - 1e-9);
            let y = if log.rating == Rating::Again { 0.0 } else { 1.0 };
            losses.push(-y * p.ln() - (1.0 - y) * (1.0 - p).ln());
            squared.push((p - y).powi(2));
        }
        cards.insert(log.card_id, scheduler.review_card(&card, log.rating, log.at, None));
    }
    let mean = |v: &[f64]| if v.is_empty() { Value::Null } else { (v.iter().sum::<f64>() / v.len() as f64).into() };
    Ok(json!({"reviews": losses.len(), "log_loss": mean(&losses), "brier_score": mean(&squared)}))
}

/// Bounds (and so finiteness) are checked by `Scheduler::new` when the parameters are used.
fn as_parameters(values: &[f64]) -> Result<[f64; 21], String> {
    values.try_into().map_err(|_| "优化器返回无效参数".to_string())
}

/// Time-split evaluation like `optimize_fsrs.optimize`: train on the first 80% of
/// events, accept only when the holdout error beats both current and default parameters.
pub fn optimize(logs: &[ReviewLog], current: Option<[f64; 21]>, trainer: Trainer, now: Time) -> Result<Value, String> {
    let mut logs = logs.to_vec();
    logs.sort_by_key(|log| (log.at, log.card_id));
    let effective = effective_count(&logs, Some(MAX_PER_CARD));
    let mut report = json!({
        "fsrs_version": FSRS_VERSION, "optimizer": "fsrs-rs 6.6.2", "created_at": time_text(now),
        "effective_reviews": effective, "total_events": logs.len(),
        "training_start": logs.first().map(|l| time_text(l.at)), "validation_through": logs.last().map(|l| time_text(l.at)),
    });
    let insufficient = |mut report: Value, reason: String| {
        report["accepted"] = false.into();
        report["outcome"] = "insufficient_data".into();
        report["reason"] = reason.into();
        Ok(report)
    };
    if effective < MINIMUM_REVIEWS {
        return insufficient(report, format!("有效间隔复习不足：{effective} / {MINIMUM_REVIEWS}"));
    }
    let cutoff = logs[logs.len() * 8 / 10].at;
    let train: Vec<ReviewLog> = logs.iter().filter(|l| l.at < cutoff).cloned().collect();
    let train_effective = effective_count(&train, Some(MAX_PER_CARD));
    report["training_before"] = time_text(cutoff).into();
    report["training_events"] = train.len().into();
    report["training_effective_reviews"] = train_effective.into();
    if train_effective < 512 {
        return insufficient(report, "训练区间内有效复习不足 512 条".into());
    }
    let baseline_parameters = current.unwrap_or(DEFAULT_PARAMETERS);
    let baseline = evaluate(&logs, &baseline_parameters, cutoff)?;
    let default = evaluate(&logs, &DEFAULT_PARAMETERS, cutoff)?;
    if baseline["reviews"].as_u64().unwrap_or(0) < 100 {
        report["baseline"] = baseline;
        report["default"] = default;
        return insufficient(report, "留出的验证区间内有效复习不足 100 条".into());
    }
    let parameters = as_parameters(&trainer(&train)?)?;
    let candidate = evaluate(&logs, &parameters, cutoff).map_err(|_| "优化器返回无效参数".to_string())?;
    let metric = |m: &Value, k: &str| m[k].as_f64().unwrap_or(f64::INFINITY);
    let accepted = metric(&candidate, "log_loss") < metric(&baseline, "log_loss").min(metric(&default, "log_loss"))
        && metric(&candidate, "brier_score") <= metric(&baseline, "brier_score");
    report["accepted"] = accepted.into();
    report["parameters"] = parameters.to_vec().into();
    report["outcome"] = if accepted { "accepted" } else { "not_improved" }.into();
    report["baseline"] = baseline;
    report["default"] = default;
    report["candidate"] = candidate;
    report["reason"] = if accepted { "验证误差改善" } else { "验证结果未改善，保留现用参数" }.into();
    Ok(report)
}

/// Production evaluation: [`optimize`] with [`train_fsrs`].
pub fn evaluate_with_fsrs_rs(logs: &[ReviewLog], baseline: [f64; 21]) -> Result<Value, String> {
    optimize(logs, Some(baseline), &train_fsrs, chrono::Utc::now())
}

/// Fits parameters with fsrs-rs. Each item is a card's history up to a review at
/// least one day after the previous one; `delta_t` counts whole elapsed days.
pub fn train_fsrs(logs: &[ReviewLog]) -> Result<Vec<f64>, String> {
    let mut by_card: Vec<(i64, Vec<&ReviewLog>)> = vec![];
    let mut index: HashMap<i64, usize> = HashMap::new();
    for log in logs {
        let i = *index.entry(log.card_id).or_insert_with(|| {
            by_card.push((log.card_id, vec![]));
            by_card.len() - 1
        });
        if by_card[i].1.len() < MAX_PER_CARD {
            by_card[i].1.push(log);
        }
    }
    let (mut train_set, mut card_ids) = (vec![], vec![]);
    for (card_id, history) in &by_card {
        let reviews: Vec<fsrs::FSRSReview> = history.iter().enumerate().map(|(i, log)| fsrs::FSRSReview {
            rating: log.rating as u32,
            delta_t: if i == 0 { 0 } else { whole_days(log.at - history[i - 1].at).max(0) as u32 },
        }).collect();
        for end in 1..reviews.len() {
            if reviews[end].delta_t > 0 {
                train_set.push(fsrs::FSRSItem { reviews: reviews[..=end].to_vec() });
                card_ids.push(*card_id);
            }
        }
    }
    let input = fsrs::ComputeParametersInput {
        train_set, card_ids: Some(card_ids), enable_short_term: true, num_relearning_steps: Some(1),
        ..Default::default()
    };
    let parameters = fsrs::compute_parameters(input).map_err(|e| format!("fsrs-rs 训练失败：{e}"))?;
    Ok(parameters.into_iter().map(|v| v as f64).collect())
}

/// Same wall-clock time next month in Beijing, clamped to the month's last day.
pub fn next_month(now: Time) -> Time {
    let local = now.with_timezone(&shanghai());
    let (year, month) = if local.month() == 12 { (local.year() + 1, 1) } else { (local.year(), local.month() + 1) };
    let following = if month == 12 { (year + 1, 1) } else { (year, month + 1) };
    let last_day = NaiveDate::from_ymd_opt(following.0, following.1, 1).unwrap().pred_opt().unwrap().day();
    let date = NaiveDate::from_ymd_opt(year, month, local.day().min(last_day)).unwrap();
    date.and_time(local.time()).and_local_timezone(shanghai()).unwrap().to_utc()
}

/// Parameters of the run recorded as active, if it was accepted.
pub(crate) fn accepted_parameters(db: &Connection) -> ApiResult<Option<[f64; 21]>> {
    let report: Option<String> = db.query_row("SELECT r.report_json FROM fsrs_optimizer_state s
        JOIN fsrs_optimization_runs r ON r.id=s.active_run_id WHERE s.id=1 AND r.status='accepted'", [], |r| r.get(0)).optional()?;
    let Some(report) = report else { return Ok(None) };
    let report: Value = serde_json::from_str(&report)?;
    let values: Vec<f64> = serde_json::from_value(report["parameters"].clone())?;
    Ok(Some(as_parameters(&values).map_err(ApiError::Unavailable)?))
}

/// The app runs training in-process, so a `running` row at startup was cut off.
pub(crate) fn recover_interrupted(db: &Connection, now: Time) -> ApiResult<()> {
    let changed = db.execute("UPDATE fsrs_optimization_runs SET status='interrupted',finished_at=?,
        reason='应用退出，后台训练中断，将重新评估' WHERE status='running'", [time_text(now)])?;
    if changed > 0 {
        db.execute("UPDATE fsrs_optimizer_state SET next_evaluation_at=? WHERE id=1", [time_text(now)])?;
    }
    Ok(())
}

fn record(mut row: serde_json::Map<String, Value>) -> ApiResult<Value> {
    row.remove("owner");
    row.remove("lease_until");
    let report = row.remove("report_json").and_then(|v| v.as_str().map(String::from)).unwrap_or_else(|| "{}".into());
    row.insert("report".into(), serde_json::from_str(&report)?);
    Ok(Value::Object(row))
}

impl Store {
    pub fn optimization_status(&self, config: &OptimizationConfig) -> ApiResult<Value> {
        let inner = self.lock();
        let mut state = query_objects(&inner.db, "SELECT * FROM fsrs_optimizer_state WHERE id=1", &[])?.remove(0);
        state.remove("id");
        let running: Option<i64> = inner.db.query_row("SELECT id FROM fsrs_optimization_runs WHERE status='running'", [], |r| r.get(0)).optional()?;
        let mut status = Value::Object(state);
        for (key, value) in [
            ("enabled", json!(config.enabled)), ("minimum_reviews", json!(MINIMUM_REVIEWS)),
            ("min_new_reviews", json!(config.min_new_reviews)), ("check_interval_seconds", json!(config.check_interval_seconds)),
            ("current_version", json!(inner.active.version)), ("desired_retention", json!(inner.active.srs.config.desired_retention)),
            ("running_run_id", json!(running)),
        ] {
            status[key] = value;
        }
        Ok(status)
    }

    pub fn optimization_history(&self, before_id: i64, limit: usize) -> ApiResult<Value> {
        let limit = limit.clamp(1, 100);
        let rows = query_objects(&self.lock().db, "SELECT * FROM fsrs_optimization_runs WHERE (?=0 OR id < ?)
            ORDER BY id DESC LIMIT ?", &[&before_id, &before_id, &(limit as i64 + 1)])?;
        let next = if rows.len() > limit { rows[limit - 1]["id"].clone() } else { Value::Null };
        let items = rows.into_iter().take(limit).map(record).collect::<ApiResult<Vec<_>>>()?;
        Ok(json!({"items": items, "next_before_id": next}))
    }

    pub fn optimization_run(&self, run_id: i64) -> ApiResult<Option<Value>> {
        let mut rows = query_objects(&self.lock().db, "SELECT * FROM fsrs_optimization_runs WHERE id=?", &[&run_id])?;
        rows.pop().map(record).transpose()
    }

    /// One scheduled check: records the evaluated volume, and once a month (after at
    /// least `MINIMUM_REVIEWS` effective reviews) trains, validates and maybe activates.
    pub fn check_optimization(&self, config: &OptimizationConfig, evaluation: Evaluation) -> ApiResult<Option<Value>> {
        if !config.enabled {
            return Ok(None);
        }
        let Some((run_id, skipped, logs, baseline)) = self.claim(config)? else { return Ok(None) };
        if !skipped {
            // fsrs-rs may panic on unusual data; record that as a failed run.
            let outcome = catch_unwind(AssertUnwindSafe(|| evaluation(&logs, baseline)))
                .unwrap_or_else(|_| Err("后台训练异常终止".into()));
            if let Err(error) = outcome.and_then(|result| self.finish(run_id, Ok(result))) {
                eprintln!("FSRS evaluation {run_id} failed: {error}");
                self.finish(run_id, Err(error)).map_err(ApiError::Unavailable)?;
            }
        }
        self.optimization_run(run_id)
    }

    /// Starts a run when one is due. Training happens on the single optimizer thread
    /// and `recover_interrupted` clears runs cut off by an exit, so none is running here.
    #[allow(clippy::type_complexity)]
    fn claim(&self, config: &OptimizationConfig) -> ApiResult<Option<(i64, bool, Vec<ReviewLog>, [f64; 21])>> {
        let now = self.now();
        let mut guard = self.lock();
        let inner = &mut *guard;
        let tx = inner.db.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let snapshot_id: i64 = tx.query_row("SELECT COALESCE(MAX(id),0) FROM word_reviews", [], |r| r.get(0))?;
        let logs = load_logs(&tx, snapshot_id)?;
        let effective = effective_count(&logs, Some(MAX_PER_CARD));
        tx.execute("UPDATE fsrs_optimizer_state SET last_checked_at=?,effective_reviews=?,total_events=? WHERE id=1",
            params![time_text(now), effective, logs.len()])?;
        let (next_at, last_evaluated): (Option<String>, usize) = tx.query_row(
            "SELECT next_evaluation_at,last_evaluated_effective FROM fsrs_optimizer_state WHERE id=1", [], |r| Ok((r.get(0)?, r.get(1)?)))?;
        let not_yet = next_at.map(|t| parse_time(&t)).transpose().map_err(ApiError::Unavailable)?.is_some_and(|t| t > now);
        if effective < MINIMUM_REVIEWS || not_yet {
            tx.commit()?;
            return Ok(None);
        }
        let new_reviews = effective as i64 - last_evaluated as i64;
        let skipped = last_evaluated > 0 && new_reviews < config.min_new_reviews as i64;
        let reason = if skipped { format!("新增有效间隔复习不足：{new_reviews} / {}", config.min_new_reviews) } else { "后台评估中".into() };
        let baseline = inner.active.srs.config.parameters;
        let report = json!({
            "fsrs_version": FSRS_VERSION, "baseline_parameters": baseline.to_vec(),
            "training_start": time_text(logs[0].at), "validation_through": time_text(logs[logs.len() - 1].at),
        });
        tx.execute("INSERT INTO fsrs_optimization_runs(status,owner,started_at,finished_at,lease_until,snapshot_review_id,
            total_events,effective_reviews,new_effective_reviews,baseline_version,reason,report_json) VALUES(?,'',?,?,NULL,?,?,?,?,?,?,?)",
            params![if skipped { "skipped" } else { "running" }, time_text(now), skipped.then(|| time_text(now)), snapshot_id, logs.len(), effective, new_reviews,
                    inner.active.version, reason, report.to_string()])?;
        let run_id = tx.last_insert_rowid();
        tx.execute("UPDATE fsrs_optimizer_state SET next_evaluation_at=? WHERE id=1", [time_text(next_month(now))])?;
        tx.commit()?;
        Ok(Some((run_id, skipped, logs, baseline)))
    }

    /// Records the outcome; an accepted candidate becomes the active schedule
    /// unless the baseline changed while training.
    fn finish(&self, run_id: i64, result: Result<Value, String>) -> Result<(), String> {
        let now = self.now();
        let mut guard = self.lock();
        let inner = &mut *guard;
        let db_error = |e: rusqlite::Error| format!("无法保存优化结果：{e}");
        let tx = inner.db.transaction_with_behavior(TransactionBehavior::Immediate).map_err(db_error)?;
        let (report, effective, baseline_version): (String, i64, String) = tx.query_row(
            "SELECT report_json,effective_reviews,baseline_version FROM fsrs_optimization_runs WHERE id=?", [run_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?))).map_err(db_error)?;
        let mut report: Value = serde_json::from_str(&report).map_err(|e| e.to_string())?;
        let mut updated = None;
        let (status, reason, next_at) = match result {
            Err(error) => {
                report["error"] = error.clone().into();
                ("failed", error, now + TimeDelta::days(1))
            }
            Ok(result) => {
                for (key, value) in result.as_object().into_iter().flatten() {
                    report[key] = value.clone();
                }
                let outcome = if result["accepted"] == true {
                    let values: Vec<f64> = serde_json::from_value(result["parameters"].clone()).map_err(|e| e.to_string())?;
                    let parameters = as_parameters(&values)?;
                    let active = Active::new(MemoryConfig { parameters, ..inner.active.srs.config.clone() }).map_err(|e| e.to_string())?;
                    if inner.active.version != baseline_version {
                        ("superseded", "现用配置已变更，本次候选不启用".to_string(), now + TimeDelta::days(1))
                    } else {
                        active.save(&tx).map_err(|e| e.to_string())?;
                        tx.execute("UPDATE fsrs_optimizer_state SET active_run_id=? WHERE id=1", [run_id]).map_err(db_error)?;
                        updated = Some(active);
                        ("accepted", "验证误差改善，已自动启用".to_string(), next_month(now))
                    }
                } else {
                    let status = if result["outcome"] == "insufficient_data" { "skipped" } else { "rejected" };
                    (status, result["reason"].as_str().unwrap_or_default().to_string(), next_month(now))
                };
                tx.execute("UPDATE fsrs_optimizer_state SET last_evaluated_effective=? WHERE id=1", [effective]).map_err(db_error)?;
                outcome
            }
        };
        tx.execute("UPDATE fsrs_optimization_runs SET status=?,finished_at=?,activated_version=?,reason=?,report_json=? WHERE id=?",
            params![status, time_text(now), updated.as_ref().map(|a| a.version.clone()), reason, report.to_string(), run_id]).map_err(db_error)?;
        tx.execute("UPDATE fsrs_optimizer_state SET next_evaluation_at=? WHERE id=1", [time_text(next_at)]).map_err(db_error)?;
        tx.commit().map_err(db_error)?;
        // Publish while still holding the lock used by formal reviews.
        if let Some(active) = updated {
            inner.active = active;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    #[test]
    fn next_month_clamps_to_month_end_in_beijing() {
        let at = |y, m, d, h| shanghai().with_ymd_and_hms(y, m, d, h, 30, 0).unwrap().to_utc();
        assert_eq!(next_month(at(2026, 1, 31, 7)), at(2026, 2, 28, 7));
        assert_eq!(next_month(at(2026, 12, 15, 23)), at(2027, 1, 15, 23));
        assert_eq!(next_month(at(2027, 3, 31, 0)), at(2027, 4, 30, 0));
    }
}
