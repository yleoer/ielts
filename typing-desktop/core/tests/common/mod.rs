//! File-backed store with a controllable clock, shared by the stats and optimizer tests.
#![allow(dead_code)]

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use chrono::{TimeDelta, TimeZone, Utc};
use cijian_core::api::{App, AppConfig, Request};
use cijian_core::fsrs::{Card, State};
use cijian_core::optimize::OptimizationConfig;
use cijian_core::srs::MemoryConfig;
use cijian_core::store::Store;
use cijian_core::time::{time_text, Time};
use cijian_core::vocab::parse_snapshot;
use rusqlite::{params, Connection};
use serde_json::{json, Value};

pub fn at(y: i32, m: u32, d: u32, h: u32, min: u32, s: u32) -> Time {
    Utc.with_ymd_and_hms(y, m, d, h, min, s).unwrap()
}

pub fn word(source: &str, id: i64, learned: bool) -> Value {
    json!({"id": id, "source_id": source, "word": source, "chinese_meaning": "释义", "category": "思维", "cefr": "B2",
           "part_of_speech": "n.", "learned": learned, "illustration_file": ""})
}

pub struct Env {
    _dir: tempfile::TempDir,
    pub path: PathBuf,
    pub clock: Arc<Mutex<Time>>,
    pub app: App,
    /// The snapshot last imported, so a single word can be practiced and then restored.
    pub words: Mutex<Vec<Value>>,
}

impl Env {
    pub fn new(now: Time, words: Vec<Value>) -> Self {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cijian.db");
        let clock = Arc::new(Mutex::new(now));
        let store = open_store(&path, &clock);
        let app = App {
            store,
            config: AppConfig { dist_dir: dir.path().into(), media_dir: None, vocab_path: None },
            optimization: OptimizationConfig::default(),
        };
        let env = Env { _dir: dir, path, clock, app, words: Mutex::new(vec![]) };
        env.import(words);
        env
    }

    pub fn store(&self) -> &Store {
        &self.app.store
    }

    pub fn reopen(&self) -> Store {
        open_store(&self.path, &self.clock)
    }

    pub fn db(&self) -> Connection {
        Connection::open(&self.path).unwrap()
    }

    pub fn now(&self) -> Time {
        *self.clock.lock().unwrap()
    }

    pub fn set(&self, t: Time) {
        *self.clock.lock().unwrap() = t;
    }

    pub fn advance(&self, d: TimeDelta) {
        self.set(self.now() + d);
    }

    pub fn import(&self, words: Vec<Value>) {
        let parsed = parse_snapshot(&json!({"format": 1, "words": words}).to_string()).unwrap();
        self.store().import_vocabulary(parsed).unwrap();
        *self.words.lock().unwrap() = words;
    }

    /// Answers `source` once in free practice (1 second later), keeping the vocabulary unchanged.
    pub fn review(&self, source: &str, answer: &str) -> Value {
        let original = self.words.lock().unwrap().clone();
        let mut found = false;
        let only: Vec<Value> = original.iter().map(|w| {
            let mut w = w.clone();
            let chosen = !found && w["source_id"] == source;
            found |= chosen;
            w["learned"] = chosen.into();
            w
        }).collect();
        self.import(only);
        let q = self.store().queue("test", Some(1), "free").unwrap()["items"][0].clone();
        self.advance(TimeDelta::seconds(1));
        let result = self.store().submit(&json!({"attempt_id": q["attempt_id"], "session_id": "test", "user_input": answer,
            "duration_ms": 1000, "reviewed_at": time_text(self.now())})).unwrap();
        self.import(original);
        result
    }

    pub fn get(&self, uri: &str) -> (u16, Value) {
        let r = self.app.handle(&Request::new("GET", uri, vec![]));
        (r.status, serde_json::from_slice(&r.body).unwrap_or(Value::Null))
    }

    pub fn data(&self, uri: &str) -> Value {
        let (status, body) = self.get(uri);
        assert_eq!(status, 200, "{uri}: {body}");
        body["data"].clone()
    }

    /// `word_memory` rows plus the total change counter, to prove a read made no writes.
    pub fn fingerprint(&self) -> Vec<String> {
        let db = self.db();
        let mut stmt = db.prepare("SELECT * FROM word_memory ORDER BY id").unwrap();
        let n = stmt.column_count();
        let mut rows: Vec<String> = stmt.query_map([], |r| {
            Ok((0..n).map(|i| format!("{:?}", r.get_ref(i).unwrap())).collect::<Vec<_>>().join("|"))
        }).unwrap().map(Result::unwrap).collect();
        for table in ["word_reviews", "practice_items", "sync_history"] {
            rows.push(db.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |r| r.get::<_, i64>(0)).unwrap().to_string());
        }
        rows
    }

    /// Writes a review-state card due at `due` for `source`.
    pub fn set_card(&self, source: &str, due: Time, state: State, stability: f64) {
        let db = self.db();
        let key = format!("word-atlas:{source}");
        let existing: Option<i64> = db.query_row("SELECT id FROM word_memory WHERE word_key=?", [&key], |r| r.get(0)).ok();
        let id = existing.unwrap_or_else(|| {
            db.query_row("SELECT COALESCE(MAX(id),0)+1 FROM word_memory", [], |r| r.get(0)).unwrap()
        });
        let card = Card { card_id: id, state, step: None, stability: Some(stability), difficulty: Some(5.0), due,
                          last_review: Some(self.now() - TimeDelta::days(1)) };
        db.execute("INSERT OR REPLACE INTO word_memory(id,word_key,card_json,due,state,stability,first_review,last_review,version,config_version)
            VALUES(?,?,?,?,?,?,?,?,?,?)", params![id, key, serde_json::to_string(&card).unwrap(), time_text(due), state as i64,
            stability, time_text(self.now()), time_text(card.last_review.unwrap()), 1, self.store().config_version()]).unwrap();
    }
}

fn open_store(path: &std::path::Path, clock: &Arc<Mutex<Time>>) -> Store {
    let shared = clock.clone();
    Store::open(path, MemoryConfig { enable_fuzzing: false, ..MemoryConfig::default() }, Box::new(move || *shared.lock().unwrap())).unwrap()
}
