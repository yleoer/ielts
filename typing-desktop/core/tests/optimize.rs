//! Ports of `test_optimizer.py` / `test_optimizer_service.py`, plus a real fsrs-rs run.

mod common;

use chrono::TimeDelta;
use cijian_core::fsrs::{Card, Rating, State, DEFAULT_PARAMETERS};
use cijian_core::optimize::{
    effective_count, evaluate, evaluate_with_fsrs_rs, next_month, optimize, OptimizationConfig, ReviewLog, MINIMUM_REVIEWS,
};
use cijian_core::time::{time_text, Time};
use common::{at, word, Env};
use rusqlite::params;
use serde_json::{json, Value};

fn start() -> Time {
    at(2026, 1, 1, 0, 0, 0)
}

/// Like `seed_history`: `cards` review cards and one review per card per day.
fn seed(env: &Env, cards: i64, days: i64) {
    env.import((1..=cards).map(|id| word(&format!("word-{id}"), id, true)).collect());
    let db = env.db();
    for id in 1..=cards {
        let card = Card { card_id: id, state: State::Review, step: None, stability: Some(10.0), difficulty: Some(5.0),
                          due: env.now(), last_review: Some(start() + TimeDelta::days(days - 1)) };
        db.execute("INSERT INTO word_memory(id,word_key,card_json,due,state,stability,first_review,last_review,version,config_version)
            VALUES(?,?,?,?,?,?,?,?,?,?)", params![id, format!("word-atlas:word-{id}"), serde_json::to_string(&card).unwrap(),
            time_text(card.due), 2, 10.0, time_text(start()), time_text(card.last_review.unwrap()), 1, env.store().config_version()]).unwrap();
    }
    for day in 0..days {
        append_day(env, day, 1, cards);
    }
}

fn append_day(env: &Env, day: i64, first: i64, cards: i64) {
    let when = time_text(start() + TimeDelta::days(day));
    let db = env.db();
    for id in first..first + cards {
        let wrong = (day + id) % 7 == 0;
        db.execute("INSERT INTO word_reviews(attempt_id,request_hash,session_id,memory_id,word_key,word,chinese_meaning,category,
            user_input,is_correct,rating,reviewed_at,received_at,duration_ms,answer_length,before_json,after_json,config_version,response_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", params![format!("day-{day}-card-{id}"), "fixture", format!("day-{day}"), id,
            format!("word-atlas:word-{id}"), format!("word-{id}"), "模拟词", "测试", "answer", !wrong, if wrong { 1 } else { 3 },
            when, when, 7000.0, 6, Option::<String>::None, "{}", env.store().config_version(), "{}"]).unwrap();
    }
}

/// Stub evaluation like `candidate()` in the Python tests.
fn candidate(accepted: bool) -> impl Fn(&[ReviewLog], [f64; 21]) -> Result<Value, String> {
    move |_logs, baseline| {
        let mut parameters = baseline.to_vec();
        parameters[0] *= 1.05;
        Ok(json!({"fsrs_version": "6.3.2", "accepted": accepted, "outcome": if accepted { "accepted" } else { "not_improved" },
            "parameters": parameters,
            "baseline": {"reviews": 200, "log_loss": 0.5, "brier_score": 0.2},
            "default": {"reviews": 200, "log_loss": 0.5, "brier_score": 0.2},
            "candidate": {"reviews": 200, "log_loss": if accepted { 0.4 } else { 0.6 }, "brier_score": 0.15},
            "reason": if accepted { "验证误差改善" } else { "验证结果未改善" }}))
    }
}

fn env() -> Env {
    Env::new(at(2026, 3, 31, 8, 0, 0), vec![])
}

fn config() -> OptimizationConfig {
    OptimizationConfig::default()
}

fn log(card_id: i64, rating: Rating, at: Time) -> ReviewLog {
    ReviewLog { card_id, rating, at }
}

fn synthetic_logs() -> Vec<ReviewLog> {
    (0..15).flat_map(|day| (0..100).map(move |card| {
        let rating = if (day + card) % 7 == 0 { Rating::Again } else { Rating::Good };
        log(card, rating, start() + TimeDelta::days(day * 2))
    })).collect()
}

#[test]
fn short_steps_are_history_but_not_effective() {
    let mut logs: Vec<_> = (0..60).map(|i| log(1, Rating::Good, start() + TimeDelta::minutes(i))).collect();
    logs.push(log(1, Rating::Good, start() + TimeDelta::days(2)));
    assert_eq!(effective_count(&logs, None), 1);
    let never = |_: &[ReviewLog]| -> Result<Vec<f64>, String> { panic!("must not train") };
    let result = optimize(&logs, None, &never, start()).unwrap();
    assert_eq!((result["accepted"].as_bool(), result["outcome"].as_str()), (Some(false), Some("insufficient_data")));
}

#[test]
fn time_split_does_not_leak_and_unchanged_parameters_are_rejected() {
    let trained = std::cell::RefCell::new(vec![]);
    let same = |train: &[ReviewLog]| {
        trained.borrow_mut().extend_from_slice(train);
        Ok(DEFAULT_PARAMETERS.to_vec())
    };
    let result = optimize(&synthetic_logs(), None, &same, start()).unwrap();
    assert_eq!(result["accepted"], false);
    let cutoff = result["training_before"].as_str().unwrap();
    assert!(!trained.borrow().is_empty());
    assert!(trained.borrow().iter().all(|l| time_text(l.at).as_str() < cutoff));
    assert_eq!(result["candidate"], result["baseline"]);
    assert_eq!(result["candidate"]["reviews"], 300);
}

#[test]
fn evaluation_predicts_before_reviewing_the_answer() {
    let correct = [log(1, Rating::Good, start()), log(1, Rating::Good, start() + TimeDelta::days(1))];
    let wrong = [correct[0].clone(), log(1, Rating::Again, correct[1].at)];
    let loss = |logs: &[ReviewLog]| evaluate(logs, &DEFAULT_PARAMETERS, start()).unwrap()["log_loss"].as_f64().unwrap();
    assert!(loss(&correct) < loss(&wrong));
}

#[test]
fn fsrs_rs_training_produces_valid_parameters() {
    let result = evaluate_with_fsrs_rs(&synthetic_logs(), DEFAULT_PARAMETERS).unwrap();
    assert_eq!(result["optimizer"], "fsrs-rs 6.6.2");
    let parameters: Vec<f64> = serde_json::from_value(result["parameters"].clone()).unwrap();
    assert_eq!(parameters.len(), 21);
    assert!(parameters.iter().all(|v| v.is_finite()));
    assert_ne!(parameters, DEFAULT_PARAMETERS.to_vec());
    assert_eq!(result["candidate"]["reviews"], result["baseline"]["reviews"]);
    assert!(result["candidate"]["log_loss"].as_f64().unwrap().is_finite());
    assert!(["accepted", "not_improved"].contains(&result["outcome"].as_str().unwrap()));
}

#[test]
fn first_attempt_starts_at_1000_effective_reviews_and_is_not_repeated() {
    let env = env();
    seed(&env, 100, 10);
    append_day(&env, 10, 1, 99);
    let store = env.store();
    let stub = candidate(false);
    assert!(store.check_optimization(&config(), &stub).unwrap().is_none());
    assert_eq!(store.optimization_status(&config()).unwrap()["effective_reviews"], 999);
    assert_eq!(store.optimization_history(0, 20).unwrap()["items"], json!([]));
    append_day(&env, 10, 100, 1);
    let result = store.check_optimization(&config(), &stub).unwrap().unwrap();
    assert_eq!(result["effective_reviews"], MINIMUM_REVIEWS);
    assert_eq!(result["status"], "rejected");
    assert!(result.get("owner").is_none() && result["report"]["baseline_parameters"].is_array());
    assert!(store.check_optimization(&config(), &stub).unwrap().is_none());
    assert_eq!(store.optimization_history(0, 20).unwrap()["items"].as_array().unwrap().len(), 1);
    assert_eq!(store.optimization_status(&config()).unwrap()["next_evaluation_at"], "2026-04-30T08:00:00.000000Z");
}

#[test]
fn monthly_skip_is_recorded_and_new_data_accumulates() {
    let env = env();
    seed(&env, 100, 11);
    let store = env.store();
    let stub = candidate(false);
    store.check_optimization(&config(), &stub).unwrap();
    env.set(next_month(env.now()));
    let result = store.check_optimization(&config(), &stub).unwrap().unwrap();
    assert_eq!((result["status"].as_str(), result["new_effective_reviews"].as_i64()), (Some("skipped"), Some(0)));
    assert!(result["reason"].as_str().unwrap().contains("新增有效间隔复习不足"));
    append_day(&env, 11, 1, 100);
    assert!(store.check_optimization(&config(), &stub).unwrap().is_none());
    env.set(next_month(env.now()));
    let result = store.check_optimization(&config(), &stub).unwrap().unwrap();
    assert_eq!((result["status"].as_str(), result["new_effective_reviews"].as_i64()), (Some("rejected"), Some(100)));
    let statuses: Vec<Value> = store.optimization_history(0, 20).unwrap()["items"].as_array().unwrap().iter().map(|r| r["status"].clone()).collect();
    assert_eq!(statuses, [json!("rejected"), json!("skipped"), json!("rejected")]);
    let first = store.optimization_history(0, 2).unwrap();
    assert_eq!(first["items"].as_array().unwrap().len(), 2);
    let rest = store.optimization_history(first["next_before_id"].as_i64().unwrap(), 2).unwrap();
    assert_eq!(rest["items"].as_array().unwrap().len(), 1);
    assert!(rest["next_before_id"].is_null());
}

#[test]
fn activation_preserves_due_dates_and_accepts_an_outstanding_question() {
    let env = env();
    seed(&env, 100, 11);
    let store = env.store();
    let question = store.queue("pending", None, "scheduled").unwrap()["items"][0].clone();
    let dues = |env: &Env| -> Vec<(String, i64)> {
        let db = env.db();
        let mut stmt = db.prepare("SELECT due,version FROM word_memory ORDER BY id").unwrap();
        stmt.query_map([], |r| Ok((r.get(0)?, r.get(1)?))).unwrap().map(Result::unwrap).collect()
    };
    let before = dues(&env);
    let result = store.check_optimization(&config(), &candidate(true)).unwrap().unwrap();
    assert_eq!(result["status"], "accepted");
    assert_eq!(result["activated_version"], store.config_version());
    assert_ne!(result["baseline_version"], store.config_version());
    assert!((store.memory_config().parameters[0] - DEFAULT_PARAMETERS[0] * 1.05).abs() < 1e-12);
    assert_eq!(dues(&env), before);
    assert_eq!(store.optimization_status(&config()).unwrap()["active_run_id"], result["id"]);
    env.advance(TimeDelta::seconds(7));
    let answer = store.submit(&json!({"session_id": "pending", "attempt_id": question["attempt_id"], "user_input": "answer",
        "duration_ms": 7000, "reviewed_at": time_text(env.now())})).unwrap();
    assert_eq!(answer["card_version"], 2);
    let version: String = env.db().query_row("SELECT config_version FROM word_memory WHERE word_key=?",
        [format!("word-atlas:{}", question["source_id"].as_str().unwrap())], |r| r.get(0)).unwrap();
    assert_eq!(version, store.config_version());
}

#[test]
fn restart_restores_the_accepted_version() {
    let env = env();
    seed(&env, 100, 11);
    let accepted = env.store().check_optimization(&config(), &candidate(true)).unwrap().unwrap();
    let reopened = env.reopen();
    assert_eq!(accepted["activated_version"], reopened.config_version());
    assert_eq!(reopened.optimization_history(0, 20).unwrap()["items"].as_array().unwrap().len(), 1);
    let disabled = OptimizationConfig { enabled: false, ..config() };
    assert!(reopened.check_optimization(&disabled, &candidate(true)).unwrap().is_none());
    assert_eq!(reopened.optimization_status(&disabled).unwrap()["enabled"], false);
}

#[test]
fn failure_is_saved_and_retried_after_a_day() {
    let env = env();
    seed(&env, 100, 11);
    let store = env.store();
    let original = store.config_version();
    let fail = |_: &[ReviewLog], _: [f64; 21]| -> Result<Value, String> { Err("fsrs-rs 训练失败：测试".into()) };
    let result = store.check_optimization(&config(), &fail).unwrap().unwrap();
    assert_eq!(result["status"], "failed");
    assert!(result["report"]["error"].as_str().unwrap().contains("训练失败"));
    assert_eq!(store.config_version(), original);
    assert!(store.check_optimization(&config(), &fail).unwrap().is_none());
    env.advance(TimeDelta::days(1));
    let panics = |_: &[ReviewLog], _: [f64; 21]| -> Result<Value, String> { panic!("boom") };
    let result = store.check_optimization(&config(), &panics).unwrap().unwrap();
    assert_eq!((result["status"].as_str(), result["reason"].as_str()), (Some("failed"), Some("后台训练异常终止")));
    assert_eq!(store.optimization_history(0, 20).unwrap()["items"].as_array().unwrap().len(), 2);
}

#[test]
fn out_of_bounds_accepted_parameters_are_recorded_as_failure() {
    let env = env();
    seed(&env, 100, 11);
    let store = env.store();
    let original = store.config_version();
    let stub = candidate(true);
    let invalid = |logs: &[ReviewLog], baseline: [f64; 21]| {
        let mut report = stub(logs, baseline)?;
        report["parameters"][0] = 1000.0.into();
        Ok(report)
    };
    let result = store.check_optimization(&config(), &invalid).unwrap().unwrap();
    assert_eq!(result["status"], "failed");
    assert!(result["reason"].as_str().unwrap().contains("out of bounds"));
    assert_eq!(store.config_version(), original);
    assert!(store.optimization_status(&config()).unwrap()["active_run_id"].is_null());
}

#[test]
fn training_cut_off_by_exit_is_marked_interrupted_on_restart() {
    let env = env();
    seed(&env, 100, 11);
    env.db().execute("INSERT INTO fsrs_optimization_runs(status,owner,started_at,snapshot_review_id,total_events,effective_reviews,
        new_effective_reviews,baseline_version,reason) VALUES('running','x',?,1,1,1,1,'v','后台评估中')", [time_text(env.now())]).unwrap();
    env.db().execute("UPDATE fsrs_optimizer_state SET next_evaluation_at=? WHERE id=1", [time_text(next_month(env.now()))]).unwrap();
    let reopened = env.reopen();
    let status = reopened.optimization_status(&config()).unwrap();
    assert!(status["running_run_id"].is_null());
    assert_eq!(status["next_evaluation_at"], time_text(env.now()));
    assert_eq!(reopened.optimization_run(1).unwrap().unwrap()["status"], "interrupted");
    assert_eq!(reopened.check_optimization(&config(), &candidate(false)).unwrap().unwrap()["status"], "rejected");
}

#[test]
fn optimization_routes_match_flask() {
    let env = env();
    seed(&env, 100, 11);
    env.store().check_optimization(&config(), &candidate(false)).unwrap();
    let status = env.data("/api/memory/optimization");
    assert_eq!((status["enabled"].as_bool(), status["minimum_reviews"].as_u64(), status["desired_retention"].as_f64()), (Some(true), Some(1000), Some(0.9)));
    assert_eq!(status["current_version"], env.store().config_version());
    let runs = env.data("/api/memory/optimization/runs?limit=1");
    assert_eq!(runs["items"][0]["status"], "rejected");
    assert_eq!(env.data("/api/memory/optimization/runs/1")["id"], 1);
    assert_eq!(env.get("/api/memory/optimization/runs/99").0, 404);
    assert_eq!(env.get("/api/memory/optimization/runs/abc").0, 404);
    for cursor in ["-1", "bad"] {
        assert_eq!(env.get(&format!("/api/memory/optimization/runs?before_id={cursor}")).0, 400);
    }
}

#[test]
fn next_month_handles_leap_year_and_year_boundary() {
    use chrono::Datelike;
    assert_eq!(next_month(at(2028, 1, 31, 0, 0, 0)).day(), 29);
    assert_eq!(next_month(at(2026, 12, 31, 0, 0, 0)).year(), 2027);
}
