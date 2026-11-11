//! Two desktop stores syncing through an in-memory server with the same
//! semantics as `typing-practice/backend/ledger.py`.

mod common;

use std::sync::{Arc, Mutex};

use chrono::TimeDelta;
use cijian_core::fsrs::{Card, Rating};
use cijian_core::remote::{sync_all, Remote};
use cijian_core::srs::{fuzz_sample, MemoryConfig, Srs};
use cijian_core::time::parse_time;
use common::{at, word, Env};
use serde_json::{json, Value};

#[derive(Default)]
struct FakeServer {
    log: Mutex<Vec<Value>>,
    words: Mutex<Vec<Value>>,
    history: Mutex<Vec<Value>>,
    page: usize,
    offline: Mutex<bool>,
    requests: Mutex<Vec<Value>>,
}

impl Remote for FakeServer {
    fn vocab(&self) -> Result<Value, String> {
        if *self.offline.lock().unwrap() {
            return Err("无法连接同步服务器".into());
        }
        Ok(json!({"format": 1, "words": *self.words.lock().unwrap(),
                  "last_anki_sync_at": "2026-10-01T07:00:00.000000Z", "sync_history": *self.history.lock().unwrap()}))
    }

    fn sync(&self, request: &Value) -> Result<Value, String> {
        if *self.offline.lock().unwrap() {
            return Err("无法连接同步服务器".into());
        }
        self.requests.lock().unwrap().push(request.clone());
        let mut log = self.log.lock().unwrap();
        let mut accepted = 0;
        for item in request["attempts"].as_array().unwrap() {
            if !log.iter().any(|row| row["attempt_id"] == item["attempt_id"]) {
                log.push(item.clone());
                accepted += 1;
            }
        }
        let cursor = request["cursor"].as_u64().unwrap() as usize;
        let page: Vec<Value> = log.iter().skip(cursor).take(self.page).cloned().collect();
        Ok(json!({"accepted": accepted, "attempts": page, "next_cursor": cursor + page.len(),
                  "more": cursor + page.len() < log.len()}))
    }
}

fn server(page: usize) -> Arc<FakeServer> {
    let server = FakeServer { page, ..Default::default() };
    *server.words.lock().unwrap() = vocabulary();
    Arc::new(server)
}

fn vocabulary() -> Vec<Value> {
    vec![word("apple", 1, true), word("banana", 2, true)]
}

fn device() -> Env {
    Env::new(at(2026, 10, 1, 8, 0, 0), vocabulary())
}

fn card(env: &Env, source: &str) -> Value {
    let text: String = env.db().query_row("SELECT card_json FROM word_memory WHERE word_key=?", [format!("word-atlas:{source}")],
                                          |r| r.get(0)).unwrap();
    let mut card: Value = serde_json::from_str(&text).unwrap();
    // card_id is the local row id and differs between devices; it never affects scheduling.
    card.as_object_mut().unwrap().remove("card_id");
    card
}

fn log_ids(env: &Env) -> Vec<String> {
    let db = env.db();
    let mut stmt = db.prepare("SELECT attempt_id FROM word_reviews ORDER BY reviewed_at,attempt_id").unwrap();
    stmt.query_map([], |r| r.get(0)).unwrap().map(Result::unwrap).collect()
}

#[test]
fn interleaved_answers_from_two_devices_converge_to_one_replayed_schedule() {
    let remote = server(500);
    let (a, b) = (device(), device());
    a.review("apple", "apple");
    b.set(a.now() + TimeDelta::hours(1));
    b.review("apple", "wrong");
    a.set(b.now() + TimeDelta::hours(1));
    a.review("apple", "apple");
    b.review("banana", "banana");

    let first = sync_all(a.store(), remote.as_ref()).unwrap();
    assert_eq!((first["uploaded_attempts"].as_u64(), first["merged_attempts"].as_u64()), (Some(2), Some(0)));
    let second = sync_all(b.store(), remote.as_ref()).unwrap();
    assert_eq!((second["uploaded_attempts"].as_u64(), second["merged_attempts"].as_u64()), (Some(2), Some(2)));
    let third = sync_all(a.store(), remote.as_ref()).unwrap();
    assert_eq!((third["uploaded_attempts"].as_u64(), third["merged_attempts"].as_u64()), (Some(0), Some(2)));
    assert!(third["message"].as_str().unwrap().contains("合并其他设备 2 条"));

    assert_eq!(log_ids(&a), log_ids(&b));
    assert_eq!(log_ids(&a).len(), 4);
    for source in ["apple", "banana"] {
        assert_eq!(card(&a, source), card(&b, source), "{source}");
    }
    // The shared result is the time-ordered replay of all three apple answers.
    let db = a.db();
    let mut stmt = db.prepare("SELECT reviewed_at,rating,attempt_id FROM word_reviews WHERE word_key='word-atlas:apple' ORDER BY reviewed_at").unwrap();
    let logs: Vec<_> = stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, u8>(1)?, r.get::<_, String>(2)?))).unwrap()
        .map(|r| { let (t, rating, id) = r.unwrap(); (parse_time(&t).unwrap(), Rating::try_from(rating).unwrap(), Some(fuzz_sample(&id))) })
        .collect();
    assert_eq!(logs.iter().map(|l| l.1).collect::<Vec<_>>(), [Rating::Easy, Rating::Again, Rating::Easy]);
    let srs = Srs::new(MemoryConfig { enable_fuzzing: false, ..MemoryConfig::default() }).unwrap();
    let mut expected = serde_json::to_value(srs.scheduler.reschedule(&Card::new(0, logs[0].0), &logs)).unwrap();
    expected.as_object_mut().unwrap().remove("card_id");
    assert_eq!(card(&a, "apple"), expected);
    // Stats see the merged history on both devices.
    assert_eq!(a.data("/api/stats/overview")["total_words_practiced"], 4);
    assert_eq!(b.data("/api/stats/word-errors?source_id=apple")["total_attempts"], 3);
}

#[test]
fn repeated_sync_uploads_nothing_new_and_merges_nothing() {
    let remote = server(500);
    let a = device();
    a.review("apple", "apple");
    sync_all(a.store(), remote.as_ref()).unwrap();
    let again = sync_all(a.store(), remote.as_ref()).unwrap();
    assert_eq!((again["uploaded_attempts"].as_u64(), again["merged_attempts"].as_u64()), (Some(0), Some(0)));
    assert_eq!(remote.log.lock().unwrap().len(), 1);
    let requests = remote.requests.lock().unwrap();
    let last = requests.last().unwrap();
    assert_eq!(last["attempts"], json!([]));
    assert_eq!(last["cursor"], 1);
    assert_eq!(last["device_id"], requests[0]["device_id"]);
    let uploaded = &requests[0]["attempts"][0];
    let keys: std::collections::BTreeSet<&str> = uploaded.as_object().unwrap().keys().map(String::as_str).collect();
    assert_eq!(keys, ["attempt_id", "category", "chinese_meaning", "duration_ms", "first_input_ms", "is_correct", "rating",
                      "reviewed_at", "user_input", "word", "word_key"].into());
}

#[test]
fn small_pages_are_fetched_until_the_log_is_exhausted() {
    let remote = server(2);
    let (a, b) = (device(), device());
    for _ in 0..5 {
        a.review("apple", "apple");
        a.advance(TimeDelta::days(1));
    }
    sync_all(a.store(), remote.as_ref()).unwrap();
    let merged = sync_all(b.store(), remote.as_ref()).unwrap();
    assert_eq!(merged["merged_attempts"], 5);
    assert_eq!(card(&a, "apple"), card(&b, "apple"));
    assert_eq!(b.store().sync_cursor().unwrap(), 5);
}

#[test]
fn offline_sync_fails_without_changes_and_later_catches_up() {
    let remote = server(500);
    let a = device();
    a.review("apple", "apple");
    *remote.offline.lock().unwrap() = true;
    let before = a.fingerprint();
    let error = sync_all(a.store(), remote.as_ref()).unwrap_err();
    assert!(error.to_string().contains("无法连接"));
    assert_eq!(a.fingerprint(), before);
    assert_eq!(a.store().pending_uploads(10).unwrap().len(), 1);
    *remote.offline.lock().unwrap() = false;
    assert_eq!(sync_all(a.store(), remote.as_ref()).unwrap()["uploaded_attempts"], 1);
    assert!(a.store().pending_uploads(10).unwrap().is_empty());
}

#[test]
fn server_vocabulary_replaces_the_local_snapshot() {
    let remote = server(500);
    let a = device();
    remote.words.lock().unwrap().push(word("cherry", 3, true));
    sync_all(a.store(), remote.as_ref()).unwrap();
    let status = a.data("/api/sync/status");
    assert_eq!((status["added_words"].as_u64(), status["after_words"].as_u64()), (Some(0), Some(3)));
    assert_eq!(status["history"], json!([]), "the device never invents an initial batch");
    assert_eq!(a.store().summary().unwrap()["total"], 3);
}

fn batch() -> Value {
    json!({"id": 7, "synced_at": "2026-09-30T23:00:00.000000Z", "before_words": 1, "after_words": 2,
           "added_words": 1, "added_word_list": [{"id": 2, "source_id": "banana", "word": "banana",
                                                  "chinese_meaning": "香蕉", "category": "食物"}]})
}

#[test]
fn devices_cache_the_same_server_batches_despite_different_local_vocabulary_and_clocks() {
    let remote = server(500);
    *remote.history.lock().unwrap() = vec![batch()];
    let (a, b) = (device(), device());
    b.import(vec![]);
    b.advance(TimeDelta::days(10));
    sync_all(a.store(), remote.as_ref()).unwrap();
    sync_all(b.store(), remote.as_ref()).unwrap();
    assert_eq!(a.store().sync_history().unwrap(), vec![batch()]);
    assert_eq!(b.store().sync_history().unwrap(), vec![batch()]);
    let status = b.data("/api/sync/status");
    assert_eq!(status["added_words"], 1, "opening status still shows the latest server batch");
    assert_eq!(status["last_anki_sync_at"], "2026-10-01T07:00:00.000000Z");
    assert_ne!(status["last_sync_at"], status["last_anki_sync_at"]);
    assert_eq!(b.reopen().sync_history().unwrap(), vec![batch()], "offline restart keeps the cache");
    remote.words.lock().unwrap()[1]["id"] = 999.into();
    sync_all(a.store(), remote.as_ref()).unwrap();
    assert_eq!(a.store().sync_history().unwrap(), vec![batch()]);
    *remote.offline.lock().unwrap() = true;
    assert!(sync_all(a.store(), remote.as_ref()).is_err());
    assert_eq!(a.store().sync_history().unwrap(), vec![batch()]);
}

#[test]
fn first_server_history_replaces_legacy_rows_without_touching_answers() {
    let remote = server(500);
    let a = device();
    a.review("apple", "apple");
    a.db().execute("INSERT INTO sync_history VALUES(99,'2026-11-03T05:44:49Z',0,105,105,'旧记录','[]')", []).unwrap();
    assert!(a.store().sync_history().unwrap().is_empty(), "legacy history is not presented as server history");
    *remote.history.lock().unwrap() = vec![batch()];
    sync_all(a.store(), remote.as_ref()).unwrap();
    assert_eq!(a.store().sync_history().unwrap(), vec![batch()]);
    assert_eq!(log_ids(&a).len(), 1);
    sync_all(a.store(), remote.as_ref()).unwrap();
    assert_eq!(a.store().sync_history().unwrap(), vec![batch()]);
    remote.history.lock().unwrap().clear();
    sync_all(a.store(), remote.as_ref()).unwrap();
    assert!(a.store().sync_history().unwrap().is_empty(), "an empty server history also replaces the cache");
}

#[test]
fn invalid_history_does_not_partially_replace_the_cached_vocabulary() {
    let remote = server(500);
    let a = device();
    *remote.history.lock().unwrap() = vec![batch()];
    sync_all(a.store(), remote.as_ref()).unwrap();
    let mut snapshot = remote.vocab().unwrap();
    snapshot["words"] = json!([word("cherry", 3, true)]);
    snapshot["sync_history"] = json!([batch(), batch()]);
    assert!(a.store().import_server_vocabulary(&snapshot).is_err());
    assert_eq!(a.store().sync_history().unwrap(), vec![batch()]);
    assert_eq!(a.store().learned_count(), 2);
    snapshot.as_object_mut().unwrap().remove("sync_history");
    assert!(a.store().import_server_vocabulary(&snapshot).unwrap_err().to_string().contains("请先升级服务器"));
    assert_eq!(a.store().learned_count(), 2);
}

#[test]
fn merged_answers_invalidate_outstanding_questions_for_the_same_word() {
    let remote = server(500);
    let (a, b) = (device(), device());
    a.import(vec![word("apple", 1, true), word("banana", 2, false)]);
    b.import(vec![word("apple", 1, true), word("banana", 2, false)]);
    *remote.words.lock().unwrap() = vec![word("apple", 1, true), word("banana", 2, false)];
    let question = b.store().queue("s", Some(1), "free").unwrap()["items"][0].clone();
    a.review("apple", "apple");
    sync_all(a.store(), remote.as_ref()).unwrap();
    b.set(a.now() + TimeDelta::minutes(1));
    sync_all(b.store(), remote.as_ref()).unwrap();
    b.advance(TimeDelta::seconds(1));
    let result = b.store().submit(&json!({"attempt_id": question["attempt_id"], "session_id": "s", "user_input": "apple",
        "duration_ms": 1000, "reviewed_at": cijian_core::time::time_text(b.now())}));
    assert!(matches!(result, Err(cijian_core::error::ApiError::Conflict(_))), "{result:?}");
}

#[test]
fn invalid_server_answers_are_rejected_before_any_merge() {
    let remote = server(500);
    let a = device();
    remote.log.lock().unwrap().push(json!({"attempt_id": "x", "word_key": "word-atlas:apple", "rating": 9}));
    let before = a.fingerprint();
    let error = sync_all(a.store(), remote.as_ref()).unwrap_err();
    assert!(error.to_string().contains("第 1 条作答无效"), "{error}");
    assert_eq!(a.fingerprint(), before);
    assert_eq!(a.store().sync_cursor().unwrap(), 0);
}

/// Serves the fake log only to the right token, like the real server's Bearer check.
struct Gate {
    server: Arc<FakeServer>,
    authorized: bool,
}

impl Remote for Gate {
    fn vocab(&self) -> Result<Value, String> {
        if self.authorized { self.server.vocab() } else { Err("访问令牌无效，请检查同步设置".into()) }
    }
    fn sync(&self, request: &Value) -> Result<Value, String> {
        if self.authorized { self.server.sync(request) } else { Err("访问令牌无效，请检查同步设置".into()) }
    }
}

fn post(env: &Env, path: &str, body: Value) -> (u16, Value) {
    let r = env.app.handle(&cijian_core::api::Request::new("POST", path, body.to_string().into_bytes()));
    (r.status, serde_json::from_slice(&r.body).unwrap())
}

#[test]
fn first_run_settings_check_the_token_save_and_enable_sync() {
    let remote = server(500);
    let mut a = device();
    let shared = remote.clone();
    a.app.connect = Box::new(move |config| Arc::new(Gate { server: shared.clone(), authorized: config.token == "secret" }));
    let file = a.path.with_file_name("server.json");
    a.review("apple", "apple");

    assert_eq!(a.data("/api/settings/server"), json!({"configured": false, "url": null, "has_token": false, "editable": true, "source": null}));
    for (body, error) in [
        (json!({"url": "example.com", "token": "secret"}), "http://"),
        (json!({"url": "https://", "token": "secret"}), "http://"),
        (json!({"url": "https://sync.example.com", "token": " "}), "访问令牌"),
        (json!({"url": "https://sync.example.com", "token": "wrong"}), "访问令牌无效"),
    ] {
        let (status, response) = post(&a, "/api/settings/server", body);
        assert_eq!(status, 400);
        assert!(response["error"].as_str().unwrap().contains(error), "{response}");
    }
    assert!(!file.exists(), "nothing is saved until the server accepts the token");
    assert!(a.app.remote().is_none());

    let (status, saved) = post(&a, "/api/settings/server", json!({"url": " https://sync.example.com/ ", "token": " secret "}));
    assert_eq!(status, 200, "{saved}");
    assert_eq!(saved["data"], json!({"configured": true, "url": "https://sync.example.com", "has_token": true, "editable": true, "source": "file"}));
    let stored: Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(stored, json!({"url": "https://sync.example.com", "token": "secret"}));

    let (status, synced) = post(&a, "/api/sync/now", json!({}));
    assert_eq!(status, 200, "{synced}");
    assert_eq!(synced["data"]["uploaded_attempts"], 1);
    assert_eq!(synced["data"]["target_path"], "同步服务器");

    // Changing only the address keeps the saved token.
    let (status, _) = post(&a, "/api/settings/server", json!({"url": "https://other.example.com", "token": ""}));
    assert_eq!(status, 200);
    let stored = cijian_core::remote::ServerConfig::load(&file).unwrap().unwrap();
    assert_eq!((stored.url.as_str(), stored.token.as_str()), ("https://other.example.com", "secret"));

    *remote.offline.lock().unwrap() = true;
    assert_eq!(post(&a, "/api/sync/now", json!({})).0, 400);
}

#[test]
fn environment_settings_cannot_be_changed_in_the_app() {
    let a = device();
    let config = cijian_core::remote::ServerConfig::new("https://env.example.com", "token").unwrap();
    a.app.set_server(config, cijian_core::api::ServerSource::Environment);
    let settings = a.data("/api/settings/server");
    assert_eq!((settings["configured"].as_bool(), settings["editable"].as_bool(), settings["source"].as_str()), (Some(true), Some(false), Some("environment")));
    let (status, body) = post(&a, "/api/settings/server", json!({"url": "https://x.example.com", "token": "t"}));
    assert_eq!(status, 400);
    assert!(body["error"].as_str().unwrap().contains("CIJIAN_SERVER_URL"));
}

#[test]
fn damaged_settings_files_are_reported() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("server.json");
    assert_eq!(cijian_core::remote::ServerConfig::load(&path).unwrap(), None);
    std::fs::write(&path, "{").unwrap();
    assert!(cijian_core::remote::ServerConfig::load(&path).unwrap_err().contains("不是有效 JSON"));
    std::fs::write(&path, r#"{"url": "ftp://x", "token": "t"}"#).unwrap();
    assert!(cijian_core::remote::ServerConfig::load(&path).is_err());
}
