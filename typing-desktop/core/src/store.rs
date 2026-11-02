//! Local SQLite store: practice queue, review ledger and FSRS cards.
//! Port of `typing-practice/backend/memory.py` (queue / submit / summary).

use std::collections::HashMap;
use std::path::Path;
use std::sync::Mutex;

use chrono::{FixedOffset, TimeDelta};
use rand::seq::SliceRandom;
use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::answer::{is_correct, normalize_answer};
use crate::error::{ApiError, ApiResult};
use crate::fsrs::{Card, Rating, State};
use crate::srs::{validate_duration, MemoryConfig, Srs};
use crate::time::{parse_time, time_text, Time};
use crate::vocab::{pool_by_key, Word};

pub const FREE_PRACTICE_LIMIT: usize = 20;
const RATING_VERSION: i64 = 1;

const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS srs_configs (version TEXT PRIMARY KEY, config_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS word_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_key TEXT UNIQUE NOT NULL,
    card_json TEXT NOT NULL,
    due TEXT NOT NULL,
    state INTEGER NOT NULL,
    stability REAL,
    first_review TEXT NOT NULL,
    last_review TEXT NOT NULL,
    version INTEGER NOT NULL,
    config_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_due ON word_memory(due);
CREATE TABLE IF NOT EXISTS practice_items (
    attempt_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    word_key TEXT NOT NULL,
    word_json TEXT NOT NULL,
    card_version INTEGER NOT NULL,
    issued_at TEXT NOT NULL,
    config_version TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'scheduled'
);
CREATE INDEX IF NOT EXISTS idx_items_issued ON practice_items(issued_at);
CREATE TABLE IF NOT EXISTS word_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id TEXT UNIQUE NOT NULL,
    request_hash TEXT NOT NULL,
    session_id TEXT NOT NULL,
    memory_id INTEGER NOT NULL REFERENCES word_memory(id),
    word_key TEXT NOT NULL,
    word TEXT NOT NULL,
    chinese_meaning TEXT NOT NULL,
    category TEXT NOT NULL,
    user_input TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 4),
    reviewed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    first_input_ms REAL,
    answer_length INTEGER NOT NULL,
    before_json TEXT,
    after_json TEXT NOT NULL,
    config_version TEXT NOT NULL REFERENCES srs_configs(version),
    response_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_time ON word_reviews(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_reviews_word ON word_reviews(word_key, reviewed_at);
CREATE INDEX IF NOT EXISTS idx_reviews_session ON word_reviews(session_id);
CREATE TABLE IF NOT EXISTS vocabulary (
    note_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    learned INTEGER NOT NULL,
    illustration_file TEXT NOT NULL,
    word_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at TEXT NOT NULL,
    before_words INTEGER NOT NULL,
    after_words INTEGER NOT NULL,
    added_words INTEGER NOT NULL,
    message TEXT NOT NULL,
    added_word_list TEXT NOT NULL
);
"#;

pub type Clock = Box<dyn Fn() -> Time + Send + Sync>;

pub fn shanghai() -> FixedOffset {
    FixedOffset::east_opt(8 * 3600).unwrap()
}

struct Inner {
    db: Connection,
    vocabulary: Vec<Word>,
}

pub struct Store {
    inner: Mutex<Inner>,
    pub srs: Srs,
    version: String,
    snapshot: Value,
    now: Clock,
}

struct MemoryRow {
    id: i64,
    card_json: String,
    due: String,
    state: i64,
    version: i64,
    config_version: String,
}

fn memory_rows(db: &Connection) -> ApiResult<HashMap<String, MemoryRow>> {
    let mut stmt = db.prepare("SELECT word_key,id,card_json,due,state,version,config_version FROM word_memory")?;
    let rows = stmt.query_map([], |r| {
        Ok((r.get::<_, String>(0)?, MemoryRow {
            id: r.get(1)?, card_json: r.get(2)?, due: r.get(3)?, state: r.get(4)?, version: r.get(5)?, config_version: r.get(6)?,
        }))
    })?;
    Ok(rows.collect::<Result<_, _>>()?)
}

fn text_field<'a>(payload: &'a Value, name: &str) -> ApiResult<&'a str> {
    match payload.get(name).and_then(Value::as_str) {
        Some(v) if (1..=100).contains(&v.chars().count()) => Ok(v),
        _ => Err(ApiError::bad(format!("需要有效的 {name}"))),
    }
}

fn number_field(payload: &Value, name: &str) -> ApiResult<f64> {
    let value = payload.get(name).and_then(Value::as_f64).unwrap_or(f64::NAN);
    validate_duration(value, name).map_err(ApiError::BadRequest)
}

impl Store {
    pub fn open(path: &Path, config: MemoryConfig, now: Clock) -> ApiResult<Self> {
        Self::with_connection(Connection::open(path)?, config, now)
    }

    pub fn with_connection(db: Connection, config: MemoryConfig, now: Clock) -> ApiResult<Self> {
        db.busy_timeout(std::time::Duration::from_secs(5))?;
        db.execute_batch(SCHEMA)?;
        let srs = Srs::new(config).map_err(ApiError::BadRequest)?;
        let s = &srs.scheduler;
        let snapshot = json!({
            "engine": "cijian-core", "fsrs_version": "6.3.2", "rating_version": RATING_VERSION,
            "easy_seconds": srs.config.easy_seconds, "hard_seconds": srs.config.hard_seconds,
            "scheduler": {
                "parameters": s.parameters, "desired_retention": s.desired_retention,
                "learning_steps": s.learning_steps.iter().map(|d| d.num_seconds()).collect::<Vec<_>>(),
                "relearning_steps": s.relearning_steps.iter().map(|d| d.num_seconds()).collect::<Vec<_>>(),
                "maximum_interval": s.maximum_interval, "enable_fuzzing": s.enable_fuzzing,
            },
        });
        let text = snapshot.to_string();
        let version: String = format!("{:x}", Sha256::digest(text.as_bytes()))[..20].to_string();
        db.execute("INSERT OR IGNORE INTO srs_configs VALUES(?,?)", params![version, text])?;
        db.execute("INSERT OR IGNORE INTO schema_migrations VALUES('desktop-v1',?)", params![time_text(now())])?;
        let vocabulary = Self::load_vocabulary(&db)?;
        Ok(Store { inner: Mutex::new(Inner { db, vocabulary }), srs, version, snapshot, now })
    }

    pub fn now(&self) -> Time {
        (self.now)()
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    fn load_vocabulary(db: &Connection) -> ApiResult<Vec<Word>> {
        let mut stmt = db.prepare("SELECT note_id,source_id,learned,illustration_file,word_json FROM vocabulary ORDER BY note_id")?;
        let rows = stmt.query_map([], |r| {
            Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?, r.get::<_, bool>(2)?, r.get::<_, String>(3)?, r.get::<_, String>(4)?))
        })?;
        rows.map(|row| {
            let (note_id, source_id, learned, illustration_file, data) = row?;
            Ok(Word { note_id, source_id, learned, illustration_file, data: serde_json::from_str(&data)? })
        }).collect()
    }

    // ---- vocabulary -------------------------------------------------------------------

    pub fn learned_count(&self) -> usize {
        self.lock().vocabulary.iter().filter(|w| w.learned).count()
    }

    pub fn illustration_file(&self, note_id: i64) -> Option<String> {
        self.lock().vocabulary.iter().find(|w| w.note_id == note_id).map(|w| w.illustration_file.clone()).filter(|f| !f.is_empty())
    }

    /// Replaces the vocabulary and records a sync history row, like `AppState.sync_now`.
    pub fn import_vocabulary(&self, words: Vec<Word>) -> ApiResult<Value> {
        pool_by_key(&words)?;
        let now = time_text(self.now());
        let mut inner = self.lock();
        let before: std::collections::HashSet<i64> = inner.vocabulary.iter().filter(|w| w.learned).map(|w| w.note_id).collect();
        let added: Vec<Value> = words.iter().filter(|w| w.learned && !before.contains(&w.note_id)).map(|w| Value::Object(w.data.clone())).collect();
        let after = words.iter().filter(|w| w.learned).count();
        let tx = inner.db.transaction_with_behavior(TransactionBehavior::Immediate)?;
        tx.execute("DELETE FROM vocabulary", [])?;
        for w in &words {
            tx.execute("INSERT INTO vocabulary VALUES(?,?,?,?,?)", params![
                w.note_id, w.source_id, w.learned, w.illustration_file, Value::Object(w.data.clone()).to_string()
            ])?;
        }
        if !added.is_empty() {
            let brief: Vec<Value> = added.iter().map(|w| json!({
                "id": w["id"], "word": w["word"], "chinese_meaning": w["chinese_meaning"], "category": w["category"],
            })).collect();
            tx.execute("INSERT INTO sync_history(synced_at,before_words,after_words,added_words,message,added_word_list) VALUES(?,?,?,?,?,?)",
                params![now, before.len(), after, added.len(), "词库已更新", Value::Array(brief).to_string()])?;
        }
        tx.commit()?;
        inner.vocabulary = words;
        Ok(json!({
            "last_sync_at": now, "before_words": before.len(), "after_words": after,
            "added_words": added.len(), "added_word_list": added, "success": true, "message": "词库已更新",
        }))
    }

    pub fn sync_history(&self, limit: usize) -> ApiResult<Vec<Value>> {
        let inner = self.lock();
        let mut stmt = inner.db.prepare("SELECT synced_at,before_words,after_words,added_words,message,added_word_list FROM sync_history ORDER BY synced_at DESC,id DESC LIMIT ?")?;
        let rows = stmt.query_map([limit.clamp(1, 50) as i64], |r| {
            Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?, r.get::<_, i64>(2)?, r.get::<_, i64>(3)?, r.get::<_, String>(4)?, r.get::<_, String>(5)?))
        })?;
        rows.map(|row| {
            let (synced_at, before, after, added, message, list) = row?;
            Ok(json!({"synced_at": synced_at, "before_words": before, "after_words": after, "added_words": added,
                      "success": true, "message": message, "added_word_list": serde_json::from_str::<Value>(&list)?}))
        }).collect()
    }

    // ---- practice ---------------------------------------------------------------------

    fn describe_row(&self, row: &MemoryRow, now: Time) -> ApiResult<Value> {
        let card: Card = serde_json::from_str(&row.card_json)?;
        Ok(serde_json::to_value(self.srs.describe(&card, now))?)
    }

    fn new_today(db: &Connection, now: Time) -> ApiResult<i64> {
        let day = now.with_timezone(&shanghai()).date_naive().to_string();
        Ok(db.query_row("SELECT COUNT(*) FROM word_memory WHERE date(first_review,'+8 hours')=?", [day], |r| r.get(0))?)
    }

    /// Returns ordered keys (due learning → due review → fresh) and the summary.
    fn plan(db: &Connection, words: &[(String, &Word)], states: &HashMap<String, MemoryRow>, now: Time) -> ApiResult<(Vec<String>, Value)> {
        let (mut learning, mut review, mut fresh, mut future) = (vec![], vec![], vec![], vec![]);
        for (key, _) in words {
            match states.get(key) {
                None => fresh.push(key.clone()),
                Some(row) if parse_time(&row.due).map_err(ApiError::Unavailable)? <= now => {
                    if row.state == State::Review as i64 { review.push(key.clone()) } else { learning.push(key.clone()) }
                }
                Some(row) => future.push(row.due.clone()),
            }
        }
        let by_due = |keys: &mut Vec<String>| keys.sort_by(|a, b| (&states[a].due, a).cmp(&(&states[b].due, b)));
        by_due(&mut learning);
        by_due(&mut review);
        fresh.sort();
        let summary = json!({
            "total": words.len(), "due_count": learning.len() + review.len(),
            "new_available": fresh.len(), "new_today": Self::new_today(db, now)?,
            "next_due": future.iter().min(),
        });
        Ok(([learning, review, fresh].concat(), summary))
    }

    pub fn summary(&self) -> ApiResult<Value> {
        let inner = self.lock();
        let words = pool_by_key(&inner.vocabulary)?;
        let states = memory_rows(&inner.db)?;
        Ok(Self::plan(&inner.db, &words, &states, self.now())?.1)
    }

    pub fn queue(&self, session_id: &str, limit: Option<usize>, mode: &str) -> ApiResult<Value> {
        if !(1..=100).contains(&session_id.chars().count()) {
            return Err(ApiError::bad("需要有效的 session_id"));
        }
        if mode != "scheduled" && mode != "free" {
            return Err(ApiError::bad("无效练习模式"));
        }
        let now = self.now();
        let mut guard = self.lock();
        let inner = &mut *guard;
        let words = pool_by_key(&inner.vocabulary)?;
        let tx = inner.db.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let states = memory_rows(&tx)?;
        let (mut keys, summary) = Self::plan(&tx, &words, &states, now)?;
        tx.execute("DELETE FROM practice_items WHERE issued_at < ?", [time_text(now - TimeDelta::days(7))])?;
        let free = mode == "free";
        if free {
            // Free practice samples the whole pool, including cards not yet due.
            keys = words.iter().map(|(k, _)| k.clone()).collect();
            keys.shuffle(&mut rand::rng());
        }
        let (maximum, default) = if free { (FREE_PRACTICE_LIMIT, FREE_PRACTICE_LIMIT) } else { (100, 1) };
        let item_limit = limit.unwrap_or(default).clamp(1, maximum);
        let lookup: HashMap<&str, &Word> = words.iter().map(|(k, w)| (k.as_str(), *w)).collect();
        let mut items = vec![];
        for key in keys.iter().take(item_limit) {
            let word = lookup[key.as_str()];
            let mut item = word.data.clone();
            let row = states.get(key);
            let memory = match row {
                Some(row) => self.describe_row(row, now)?,
                None => json!({"status": "new", "is_due": false}),
            };
            let card_version = row.map_or(0, |r| r.version);
            let attempt_id = uuid::Uuid::new_v4().to_string();
            item.insert("memory".into(), memory);
            item.insert("card_version".into(), card_version.into());
            item.insert("attempt_id".into(), attempt_id.clone().into());
            item.insert("issued_at".into(), time_text(now).into());
            tx.execute("INSERT INTO practice_items(attempt_id,session_id,word_key,word_json,card_version,issued_at,config_version,mode) VALUES(?,?,?,?,?,?,?,?)",
                params![attempt_id, session_id, key, Value::Object(word.data.clone()).to_string(), card_version, time_text(now), self.version, mode])?;
            items.push(Value::Object(item));
        }
        tx.commit()?;
        Ok(json!({"items": items, "summary": summary, "server_time": time_text(now)}))
    }

    pub fn submit(&self, payload: &Value) -> ApiResult<Value> {
        if !payload.is_object() {
            return Err(ApiError::bad("请求必须是 JSON 对象"));
        }
        let attempt_id = text_field(payload, "attempt_id")?;
        let session_id = text_field(payload, "session_id")?;
        let elapsed = number_field(payload, "duration_ms")?;
        let first_input = match payload.get("first_input_ms") {
            None | Some(Value::Null) => None,
            Some(_) => Some(number_field(payload, "first_input_ms")?),
        };
        if first_input.is_some_and(|v| v > elapsed) {
            return Err(ApiError::bad("首次输入时间不能超过总耗时"));
        }
        let user_input = match payload.get("user_input").and_then(Value::as_str) {
            Some(v) if v.chars().count() <= 1000 => v,
            _ => return Err(ApiError::bad("无效输入")),
        };
        let reviewed = payload.get("reviewed_at").and_then(Value::as_str).ok_or("时间必须包含时区".to_string())
            .and_then(parse_time).map_err(ApiError::BadRequest)?;
        // serde_json maps are sorted, so this hash is canonical.
        let request_hash = format!("{:x}", Sha256::digest(payload.to_string().as_bytes()));
        let now = self.now();

        let mut guard = self.lock();
        let inner = &mut *guard;
        let tx = inner.db.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let previous: Option<(String, String)> = tx.query_row(
            "SELECT request_hash,response_json FROM word_reviews WHERE attempt_id=?", [attempt_id], |r| Ok((r.get(0)?, r.get(1)?)),
        ).optional()?;
        if let Some((hash, response)) = previous {
            if hash != request_hash {
                return Err(ApiError::conflict("这道题已保存，不能更改已提交的答案"));
            }
            return Ok(serde_json::from_str(&response)?);
        }
        let item: Option<(String, String, String, i64, String, String, String)> = tx.query_row(
            "SELECT session_id,word_key,word_json,card_version,issued_at,config_version,mode FROM practice_items WHERE attempt_id=?",
            [attempt_id], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?, r.get(5)?, r.get(6)?)),
        ).optional()?;
        let Some((item_session, word_key, word_json, card_version, issued_at, config_version, mode)) = item else {
            return Err(ApiError::conflict("题目已过期，请重新获取"));
        };
        if item_session != session_id {
            return Err(ApiError::conflict("题目已过期，请重新获取"));
        }
        let issued = parse_time(&issued_at).map_err(ApiError::Unavailable)?;
        if now - issued > TimeDelta::days(7) {
            return Err(ApiError::conflict("题目已过期，请重新获取"));
        }
        if reviewed < issued || reviewed > now + TimeDelta::seconds(5) {
            return Err(ApiError::conflict("作答时间异常，请重新获取题目校准时间"));
        }
        if elapsed > (reviewed - issued).num_microseconds().unwrap_or(i64::MAX) as f64 / 1000.0 + 2000.0 {
            return Err(ApiError::bad("有效耗时不能超过题目展示后的实际时间"));
        }
        if config_version != self.version {
            let previous: Option<String> = tx.query_row("SELECT config_json FROM srs_configs WHERE version=?", [&config_version], |r| r.get(0)).optional()?;
            let rules: Value = previous.map(|t| serde_json::from_str(&t)).transpose()?.unwrap_or(Value::Null);
            if ["rating_version", "easy_seconds", "hard_seconds"].iter().any(|k| rules[k].as_f64() != self.snapshot[k].as_f64()) {
                return Err(ApiError::conflict("评分配置已更新，请重新获取题目"));
            }
        }
        let words = pool_by_key(&inner.vocabulary)?;
        let snapshot: Map<String, Value> = serde_json::from_str(&word_json)?;
        let word = words.iter().find(|(k, _)| *k == word_key).map(|(_, w)| *w);
        let changed = |w: &Word| ["word", "chinese_meaning", "part_of_speech"].iter().any(|f| w.data.get(*f) != snapshot.get(*f))
            || (snapshot.contains_key("chinese_senses") && w.data.get("chinese_senses") != snapshot.get("chinese_senses"));
        let word = match word {
            Some(w) if !changed(w) => w,
            _ => return Err(ApiError::conflict("词条已更新或移出练习池，请重新获取")),
        };
        let row: Option<MemoryRow> = tx.query_row(
            "SELECT id,card_json,due,state,version,config_version FROM word_memory WHERE word_key=?", [&word_key],
            |r| Ok(MemoryRow { id: r.get(0)?, card_json: r.get(1)?, due: r.get(2)?, state: r.get(3)?, version: r.get(4)?, config_version: r.get(5)? }),
        ).optional()?;
        if row.as_ref().map_or(0, |r| r.version) != card_version {
            return Err(ApiError::conflict("这个词已在其他题目中完成复习，请继续下一题"));
        }
        let (card, before_json) = match &row {
            Some(row) => {
                let mut card: Card = serde_json::from_str(&row.card_json)?;
                if card.last_review.is_some_and(|last| reviewed <= last) {
                    return Err(ApiError::conflict("作答时间必须晚于上次复习，请重新获取题目"));
                }
                if mode != "free" && reviewed < card.due {
                    return Err(ApiError::conflict("这个词尚未到期，请重新获取题目"));
                }
                if row.config_version != self.version {
                    let mut stmt = tx.prepare("SELECT reviewed_at,rating,attempt_id FROM word_reviews WHERE memory_id=? ORDER BY reviewed_at,id")?;
                    let logs = stmt.query_map([row.id], |r| Ok((r.get::<_, String>(0)?, r.get::<_, u8>(1)?, r.get::<_, String>(2)?)))?
                        .map(|log| {
                            let (at, rating, id) = log?;
                            Ok((parse_time(&at).map_err(ApiError::Unavailable)?, Rating::try_from(rating).map_err(ApiError::Unavailable)?,
                                Some(crate::srs::fuzz_sample(&id))))
                        })
                        .collect::<ApiResult<Vec<_>>>()?;
                    card = self.srs.scheduler.reschedule(&card, &logs);
                }
                let before = serde_json::to_string(&card)?;
                (card, Some(before))
            }
            None => {
                tx.execute("INSERT INTO word_memory(word_key,card_json,due,state,first_review,last_review,version,config_version) VALUES(?, '', ?, 1, ?, ?, 0, ?)",
                    params![word_key, time_text(reviewed), time_text(reviewed), time_text(reviewed), self.version])?;
                (Card::new(tx.last_insert_rowid(), reviewed), None)
            }
        };
        let correct = is_correct(word.text("word"), user_input);
        let (updated, rating) = self.srs.review(&card, correct, elapsed, reviewed, attempt_id).map_err(ApiError::BadRequest)?;
        let version = card_version + 1;
        let after_json = serde_json::to_string(&updated)?;
        tx.execute("UPDATE word_memory SET card_json=?,due=?,state=?,stability=?,last_review=?,version=?,config_version=? WHERE id=?",
            params![after_json, time_text(updated.due), updated.state as i64, updated.stability, time_text(reviewed), version, self.version, card.card_id])?;
        let response = json!({
            "attempt_id": attempt_id, "is_correct": correct, "rating": rating as u8, "rating_name": rating.name(),
            "reviewed_at": time_text(reviewed), "duration_ms": elapsed,
            "memory": self.srs.describe(&updated, now), "card_version": version,
        });
        tx.execute("INSERT INTO word_reviews(attempt_id,request_hash,session_id,memory_id,word_key,word,chinese_meaning,category,user_input,is_correct,rating,reviewed_at,received_at,duration_ms,first_input_ms,answer_length,before_json,after_json,config_version,response_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            params![attempt_id, request_hash, session_id, card.card_id, word_key, word.text("word"), word.text("chinese_meaning"),
                    word.text("category"), user_input, correct, rating as u8, time_text(reviewed), time_text(now), elapsed, first_input,
                    normalize_answer(user_input).chars().count(), before_json, after_json, self.version, response.to_string()])?;
        tx.commit()?;
        Ok(response)
    }
}
