//! Ports of `typing-practice/backend/test_memory.py` / `test_app.py` practice cases.

use std::sync::{Arc, Mutex};

use chrono::{TimeDelta, TimeZone, Utc};
use cijian_core::api::{App, AppConfig, Request};
use cijian_core::error::ApiError;
use cijian_core::srs::MemoryConfig;
use cijian_core::store::Store;
use cijian_core::time::{parse_time, time_text, Time};
use cijian_core::vocab::{parse_snapshot, Word};
use rusqlite::Connection;
use serde_json::{json, Value};

fn word(source: &str, id: i64) -> Value {
    json!({"id": id, "source_id": source, "word": source, "chinese_meaning": "释义", "category": "测试",
           "part_of_speech": "n.", "illustration_url": "", "learned": true, "illustration_file": ""})
}

fn words(items: Vec<Value>) -> Vec<Word> {
    parse_snapshot(&json!({"format": 1, "words": items}).to_string()).unwrap()
}

struct Fixture {
    clock: Arc<Mutex<Time>>,
    store: Store,
}

impl Fixture {
    fn new() -> Self {
        let clock = Arc::new(Mutex::new(Utc.with_ymd_and_hms(2026, 10, 29, 8, 0, 0).unwrap()));
        let shared = clock.clone();
        let store = Store::with_connection(
            Connection::open_in_memory().unwrap(),
            MemoryConfig { enable_fuzzing: false, ..MemoryConfig::default() },
            Box::new(move || *shared.lock().unwrap()),
        ).unwrap();
        store.import_vocabulary(words(vec![word("apple", 1)])).unwrap();
        Fixture { clock, store }
    }

    fn now(&self) -> Time {
        *self.clock.lock().unwrap()
    }

    fn set(&self, t: Time) {
        *self.clock.lock().unwrap() = t;
    }

    fn advance(&self, d: TimeDelta) {
        self.set(self.now() + d);
    }

    fn question(&self) -> Value {
        self.store.queue("test", None, "scheduled").unwrap()["items"][0].clone()
    }

    fn payload(&self, q: &Value, input: &str, elapsed: i64) -> Value {
        self.advance(TimeDelta::milliseconds(elapsed));
        json!({"attempt_id": q["attempt_id"], "session_id": "test", "user_input": input, "duration_ms": elapsed,
               "first_input_ms": elapsed.min(200), "reviewed_at": time_text(self.now())})
    }
}

fn due(result: &Value) -> Time {
    parse_time(result["memory"]["due"].as_str().unwrap()).unwrap()
}

#[test]
fn actual_fsrs_learning_relearning_and_mastery() {
    let f = Fixture::new();
    let mut answer = f.store.submit(&f.payload(&f.question(), "apple", 7000)).unwrap();
    assert_eq!(answer["rating"], 3);
    assert_eq!(due(&answer) - f.now(), TimeDelta::minutes(10));
    assert_eq!(f.store.summary().unwrap()["due_count"], 0);
    f.set(due(&answer));
    answer = f.store.submit(&f.payload(&f.question(), "apple", 7000)).unwrap();
    assert_eq!(answer["memory"]["state"], 2);
    for _ in 0..12 {
        if answer["memory"]["status"] == "mastered" {
            break;
        }
        f.set(due(&answer));
        answer = f.store.submit(&f.payload(&f.question(), "apple", 7000)).unwrap();
    }
    assert_eq!(answer["memory"]["status"], "mastered");
    f.set(due(&answer));
    answer = f.store.submit(&f.payload(&f.question(), "wrong", 7000)).unwrap();
    assert_eq!(answer["memory"]["state"], 3);
    assert_eq!(answer["memory"]["status"], "learning");
    assert_eq!(due(&answer) - f.now(), TimeDelta::minutes(10));
}

#[test]
fn again_repeats_only_when_due() {
    let f = Fixture::new();
    let response = f.store.submit(&f.payload(&f.question(), "", 7000)).unwrap();
    assert_eq!(response["rating"], 1);
    f.set(due(&response) - TimeDelta::microseconds(1));
    assert_eq!(f.store.queue("test", None, "scheduled").unwrap()["items"], json!([]));
    f.advance(TimeDelta::microseconds(1));
    let next = f.question();
    assert_ne!(next["attempt_id"], response["attempt_id"]);
    f.store.submit(&f.payload(&next, "apple", 7000)).unwrap();
}

#[test]
fn retry_is_idempotent_and_changed_retry_conflicts() {
    let f = Fixture::new();
    let payload = f.payload(&f.question(), "apple", 7000);
    let original = f.store.submit(&payload).unwrap();
    assert_eq!(f.store.submit(&payload).unwrap(), original);
    let mut changed = payload.clone();
    changed["user_input"] = "wrong".into();
    assert!(matches!(f.store.submit(&changed), Err(ApiError::Conflict(_))));
}

#[test]
fn two_tabs_conflict() {
    let f = Fixture::new();
    let (a, b) = (f.question(), f.question());
    f.store.submit(&f.payload(&a, "apple", 7000)).unwrap();
    let error = f.store.submit(&f.payload(&b, "apple", 7000)).unwrap_err();
    assert_eq!(error, ApiError::conflict("这个词已在其他题目中完成复习，请继续下一题"));
}

#[test]
fn free_practice_reviews_before_due_but_scheduled_cannot() {
    let f = Fixture::new();
    let first = f.store.submit(&f.payload(&f.question(), "apple", 1000)).unwrap();
    assert!(due(&first) > f.now() + TimeDelta::days(1));
    let scheduled = f.store.queue("test", Some(5), "scheduled").unwrap();
    assert_eq!(scheduled["items"], json!([]));
    let free = f.store.queue("free", None, "free").unwrap();
    let q = &free["items"][0];
    assert_eq!(q["memory"]["is_due"], false);
    let mut payload = f.payload(q, "apple", 7000);
    payload["session_id"] = "free".into();
    let answer = f.store.submit(&payload).unwrap();
    assert_eq!(answer["card_version"], 2);
}

#[test]
fn free_practice_caps_the_sample() {
    let f = Fixture::new();
    f.store.import_vocabulary(words((1..=25).map(|i| word(&format!("w{i:02}"), i)).collect())).unwrap();
    let items = f.store.queue("free", None, "free").unwrap()["items"].as_array().unwrap().len();
    assert_eq!(items, 20);
    f.store.import_vocabulary(words(vec![word("apple", 1), word("book", 2)])).unwrap();
    assert_eq!(f.store.queue("free", None, "free").unwrap()["items"].as_array().unwrap().len(), 2);
}

#[test]
fn due_learning_precedes_review_then_new() {
    let f = Fixture::new();
    f.store.import_vocabulary(words(vec![word("apple", 1)])).unwrap();
    f.store.submit(&f.payload(&f.question(), "apple", 1000)).unwrap();
    f.store.import_vocabulary(words(vec![word("apple", 1), word("book", 2)])).unwrap();
    let book = f.question();
    assert_eq!(book["source_id"], "book");
    f.store.submit(&f.payload(&book, "wrong", 1000)).unwrap();
    f.store.import_vocabulary(words(vec![word("apple", 1), word("book", 2), word("cat", 3)])).unwrap();
    f.advance(TimeDelta::days(30));
    let items = f.store.queue("next", Some(3), "scheduled").unwrap()["items"].clone();
    let order: Vec<&str> = items.as_array().unwrap().iter().map(|i| i["source_id"].as_str().unwrap()).collect();
    assert_eq!(order, ["book", "apple", "cat"]);
}

#[test]
fn daily_new_count_uses_shanghai_midnight() {
    let f = Fixture::new();
    f.store.import_vocabulary(words(vec![word("apple", 1), word("book", 2)])).unwrap();
    f.set(Utc.with_ymd_and_hms(2026, 10, 29, 15, 59, 40).unwrap());
    f.store.submit(&f.payload(&f.question(), "apple", 1000)).unwrap();
    assert_eq!(f.store.summary().unwrap()["new_today"], 1);
    assert_eq!(f.store.summary().unwrap()["new_available"], 1);
    f.set(Utc.with_ymd_and_hms(2026, 10, 29, 16, 0, 0).unwrap());
    assert_eq!(f.store.summary().unwrap()["new_today"], 0);
    assert_eq!(f.store.summary().unwrap()["new_available"], 1);
}

#[test]
fn variants_and_whitespace_are_accepted() {
    let f = Fixture::new();
    let mut w = word("apple", 1);
    w["word"] = "colour / color".into();
    f.store.import_vocabulary(words(vec![w])).unwrap();
    let result = f.store.submit(&f.payload(&f.question(), " COLOR ", 5999)).unwrap();
    assert_eq!(result["is_correct"], true);
    assert_eq!(result["rating"], 4);
    assert_eq!(result["memory"]["state"], 2);
}

#[test]
fn delay_preserves_original_answer_time() {
    let f = Fixture::new();
    let payload = f.payload(&f.question(), "apple", 7000);
    let reviewed = f.now();
    f.advance(TimeDelta::hours(2));
    let response = f.store.submit(&payload).unwrap();
    assert_eq!(due(&response), reviewed + TimeDelta::minutes(10));
}

#[test]
fn invalid_and_expired_tickets() {
    let f = Fixture::new();
    let payload = f.payload(&f.question(), "apple", 7000);
    let mut invented = payload.clone();
    invented["attempt_id"] = "invented".into();
    assert!(matches!(f.store.submit(&invented), Err(ApiError::Conflict(_))));
    f.advance(TimeDelta::days(8));
    assert!(matches!(f.store.submit(&payload), Err(ApiError::Conflict(_))));
}

#[test]
fn invalid_times_and_changed_question_do_not_mutate_memory() {
    let f = Fixture::new();
    let payload = f.payload(&f.question(), "apple", 7000);
    let mut future = payload.clone();
    future["reviewed_at"] = time_text(f.now() + TimeDelta::days(1)).into();
    assert!(matches!(f.store.submit(&future), Err(ApiError::Conflict(_))));
    let mut bad = payload.clone();
    bad["duration_ms"] = Value::Null;
    assert!(matches!(f.store.submit(&bad), Err(ApiError::BadRequest(_))));
    let mut too_long = payload.clone();
    too_long["duration_ms"] = 60_000.into();
    assert!(matches!(f.store.submit(&too_long), Err(ApiError::BadRequest(_))));
    let mut changed = word("apple", 1);
    changed["word"] = "changed".into();
    f.store.import_vocabulary(words(vec![changed])).unwrap();
    assert!(matches!(f.store.submit(&payload), Err(ApiError::Conflict(_))));
    assert_eq!(f.store.summary().unwrap()["new_available"], 1);
}

#[test]
fn missing_and_duplicate_source_ids_are_rejected() {
    let f = Fixture::new();
    assert!(f.store.import_vocabulary(words(vec![word("", 1)])).is_err());
    assert!(f.store.import_vocabulary(words(vec![word("a", 1), word("a", 2)])).is_err());
    // A rejected import keeps the previous vocabulary.
    assert_eq!(f.store.summary().unwrap()["total"], 1);
}

#[test]
fn parameter_change_replays_logs_on_next_review() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("cijian.db");
    let clock = Arc::new(Mutex::new(Utc.with_ymd_and_hms(2026, 10, 29, 8, 0, 0).unwrap()));
    let open = |retention: f64| {
        let shared = clock.clone();
        Store::open(&path, MemoryConfig { enable_fuzzing: false, desired_retention: retention, ..MemoryConfig::default() },
                    Box::new(move || *shared.lock().unwrap())).unwrap()
    };
    let store = open(0.9);
    store.import_vocabulary(words(vec![word("apple", 1)])).unwrap();
    let mut answer = Value::Null;
    for _ in 0..3 {
        let q = store.queue("s", None, "scheduled").unwrap()["items"][0].clone();
        *clock.lock().unwrap() += TimeDelta::seconds(7);
        let at = *clock.lock().unwrap();
        answer = store.submit(&json!({"attempt_id": q["attempt_id"], "session_id": "s", "user_input": "apple",
            "duration_ms": 7000, "reviewed_at": time_text(at)})).unwrap();
        *clock.lock().unwrap() = due(&answer);
    }
    let old_due = due(&answer);
    drop(store);
    let store = open(0.8);
    // Due date is kept until the next review applies the new parameters.
    assert_eq!(store.queue("s", None, "scheduled").unwrap()["items"][0]["memory"]["due"], time_text(old_due));
    let q = store.queue("s", None, "scheduled").unwrap()["items"][0].clone();
    *clock.lock().unwrap() += TimeDelta::seconds(7);
    let at = *clock.lock().unwrap();
    let replayed = store.submit(&json!({"attempt_id": q["attempt_id"], "session_id": "s", "user_input": "apple",
        "duration_ms": 7000, "reviewed_at": time_text(at)})).unwrap();
    assert_eq!(replayed["card_version"], 4);
    assert!(due(&replayed) > at);
}

#[test]
fn router_serves_practice_api_with_flask_shapes() {
    let f = Fixture::new();
    let dist = tempfile::tempdir().unwrap();
    std::fs::write(dist.path().join("index.html"), "<html>词间</html>").unwrap();
    let app = App { store: f.store, config: AppConfig { dist_dir: dist.path().into(), media_dir: None, vocab_path: None }, optimization: Default::default() };
    let get = |uri: &str| app.handle(&Request::new("GET", uri, vec![]));
    let body = |r: &cijian_core::api::Response| serde_json::from_slice::<Value>(&r.body).unwrap();

    assert_eq!(body(&get("http://cijian.localhost/api/health"))["status"], "ok");
    let page = get("http://cijian.localhost/");
    assert_eq!((page.status, page.content_type.as_str()), (200, "text/html; charset=utf-8"));
    assert_eq!(get("/anything").status, 200, "unknown pages fall back to index.html");
    assert_eq!(get("/src/../index.html").status, 404);
    assert_eq!(get("/api/media/1/audio").status, 404);
    assert_eq!(get("/api/unknown").status, 404);

    let queue = body(&get("/api/practice/queue?session_id=s&limit=3&mode=scheduled"));
    let q = &queue["data"]["items"][0];
    let at = time_text(*f.clock.lock().unwrap() + TimeDelta::seconds(7));
    *f.clock.lock().unwrap() += TimeDelta::seconds(7);
    let payload = json!({"attempt_id": q["attempt_id"], "session_id": "s", "user_input": "apple", "duration_ms": 7000, "reviewed_at": at});
    let post = |uri: &str| app.handle(&Request::new("POST", uri, payload.to_string().into_bytes()));
    assert_eq!(post("/api/practice/attempts?next_limit=4").status, 400);
    let saved = post("/api/practice/attempts?next_limit=3");
    let saved_body = body(&saved);
    assert_eq!(saved.status, 200);
    assert_eq!(saved_body["data"]["is_correct"], true);
    assert_eq!(saved_body["next_queue"]["items"], json!([]));
    assert_eq!(body(&post("/api/practice/attempts")), json!({"success": true, "data": saved_body["data"]}));

    let sync = app.handle(&Request::new("POST", "/api/sync/now", vec![]));
    assert_eq!(sync.status, 400);
    assert_eq!(body(&get("/api/sync/status"))["data"]["sync_configured"], false);
}
