//! Local SQLite store: practice queue, review ledger and FSRS cards.
//! Port of `typing-practice/backend/memory.py` (queue / submit / summary).

use std::collections::HashMap;
use std::path::Path;
use std::sync::Mutex;

use chrono::{FixedOffset, TimeDelta};
use rand::seq::SliceRandom;
use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::answer::{is_correct, normalize_answer};
use crate::error::{ApiError, ApiResult};
use crate::fsrs::{Card, State};
use crate::srs::{MemoryConfig, Srs};
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

#[derive(Deserialize)]
struct VocabularySync {
    last_anki_sync_at: String,
    sync_history: Vec<VocabularyBatch>,
}

#[derive(Deserialize)]
struct VocabularyBatch {
    id: i64,
    synced_at: String,
    before_words: usize,
    after_words: usize,
    added_words: usize,
    added_word_list: Vec<Value>,
}

pub fn shanghai() -> FixedOffset {
    FixedOffset::east_opt(8 * 3600).unwrap()
}

/// The scheduling rules in force; replaced when an optimization run is accepted.
pub(crate) struct Active {
    pub srs: Srs,
    pub version: String,
    pub snapshot: Value,
}

impl Active {
    pub(crate) fn new(config: MemoryConfig) -> ApiResult<Self> {
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
        let version = format!("{:x}", Sha256::digest(snapshot.to_string().as_bytes()))[..20].to_string();
        Ok(Active { srs, version, snapshot })
    }

    pub(crate) fn save(&self, db: &Connection) -> ApiResult<()> {
        db.execute("INSERT OR IGNORE INTO srs_configs VALUES(?,?)", params![self.version, self.snapshot.to_string()])?;
        Ok(())
    }
}

pub(crate) struct Inner {
    pub db: Connection,
    pub vocabulary: Vec<Word>,
    pub active: Active,
}

pub struct Store {
    inner: Mutex<Inner>,
    now: Clock,
    /// Held for the whole of a server sync (see `remote::sync_all`).
    pub(crate) sync_running: Mutex<()>,
}

pub(crate) struct MemoryRow {
    pub card_json: String,
    pub due: String,
    pub state: i64,
    pub version: i64,
    pub config_version: String,
}

pub(crate) fn memory_rows(db: &Connection) -> ApiResult<HashMap<String, MemoryRow>> {
    let mut stmt = db.prepare("SELECT word_key,card_json,due,state,version,config_version FROM word_memory")?;
    let rows = stmt.query_map([], |r| {
        Ok((r.get::<_, String>(0)?, MemoryRow {
            card_json: r.get(1)?, due: r.get(2)?, state: r.get(3)?, version: r.get(4)?, config_version: r.get(5)?,
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

/// Durations must be finite and non-negative, or the attempt would be graded as Easy.
fn number_field(payload: &Value, name: &str) -> ApiResult<f64> {
    match payload.get(name).and_then(Value::as_f64) {
        Some(v) if v.is_finite() && v >= 0.0 => Ok(v),
        _ => Err(ApiError::bad(format!("{name} 必须是非负有限数值"))),
    }
}

impl Store {
    pub fn open(path: &Path, config: MemoryConfig, now: Clock) -> ApiResult<Self> {
        Self::with_connection(Connection::open(path)?, config, now)
    }

    pub fn with_connection(db: Connection, config: MemoryConfig, now: Clock) -> ApiResult<Self> {
        db.busy_timeout(std::time::Duration::from_secs(5))?;
        db.execute_batch(SCHEMA)?;
        db.execute_batch(crate::optimize::SCHEMA)?;
        db.execute_batch(crate::sync::SCHEMA)?;
        db.execute("INSERT OR IGNORE INTO schema_migrations VALUES('desktop-v1',?)", params![time_text(now())])?;
        // Parameters accepted by an earlier optimization run replace the configured defaults.
        let active = match crate::optimize::accepted_parameters(&db)? {
            Some(parameters) => Active::new(MemoryConfig { parameters, ..config })?,
            None => Active::new(config)?,
        };
        active.save(&db)?;
        crate::optimize::recover_interrupted(&db, now())?;
        let vocabulary = Self::load_vocabulary(&db)?;
        Ok(Store { inner: Mutex::new(Inner { db, vocabulary, active }), now, sync_running: Mutex::new(()) })
    }

    /// Scheduling rules currently in force (thresholds and FSRS parameters).
    pub fn memory_config(&self) -> MemoryConfig {
        self.lock().active.srs.config.clone()
    }

    pub fn config_version(&self) -> String {
        self.lock().active.version.clone()
    }

    pub fn now(&self) -> Time {
        (self.now)()
    }

    pub(crate) fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
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

    pub fn source_id(&self, note_id: i64) -> Option<String> {
        self.lock().vocabulary.iter().find(|w| w.note_id == note_id).map(|w| w.source_id.clone())
    }

    /// Replaces a vocabulary without inventing history from a device's local changes.
    pub fn import_vocabulary(&self, words: Vec<Word>) -> ApiResult<()> {
        self.replace_vocabulary(words, None)
    }

    /// Vocabulary and server-owned history are cached in the same transaction.
    pub fn import_server_vocabulary(&self, snapshot: &Value) -> ApiResult<()> {
        let sync: VocabularySync = serde_json::from_value(snapshot.clone())
            .map_err(|_| ApiError::bad("同步服务器缺少有效的词库历史，请先升级服务器"))?;
        self.replace_vocabulary(crate::vocab::parse_snapshot(snapshot)?, Some(sync))
    }

    fn replace_vocabulary(&self, words: Vec<Word>, sync: Option<VocabularySync>) -> ApiResult<()> {
        pool_by_key(&words)?;
        let mut inner = self.lock();
        let tx = inner.db.transaction_with_behavior(TransactionBehavior::Immediate)?;
        tx.execute("DELETE FROM vocabulary", [])?;
        for w in &words {
            tx.execute("INSERT INTO vocabulary VALUES(?,?,?,?,?)", params![
                w.note_id, w.source_id, w.learned, w.illustration_file, Value::Object(w.data.clone()).to_string()
            ])?;
        }
        if let Some(sync) = sync {
            tx.execute("DELETE FROM sync_history", [])?;
            for batch in sync.sync_history {
                tx.execute("INSERT INTO sync_history(id,synced_at,before_words,after_words,added_words,message,added_word_list) VALUES(?,?,?,?,?,?,?)",
                    params![batch.id, batch.synced_at, batch.before_words as i64, batch.after_words as i64,
                            batch.added_words as i64, "Anki 新增已学词", Value::Array(batch.added_word_list).to_string()])?;
            }
            tx.execute("INSERT INTO sync_state VALUES('last_anki_sync_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       [sync.last_anki_sync_at])?;
        }
        tx.commit()?;
        inner.vocabulary = words;
        Ok(())
    }

    /// The 50 most recent server batches; legacy device-generated rows stay hidden.
    pub fn sync_history(&self) -> ApiResult<Vec<Value>> {
        let inner = self.lock();
        let cached: bool = inner.db.query_row("SELECT EXISTS(SELECT 1 FROM sync_state WHERE key='last_anki_sync_at')", [], |r| r.get(0))?;
        if !cached { return Ok(vec![]); }
        let mut stmt = inner.db.prepare("SELECT id,synced_at,before_words,after_words,added_words,added_word_list FROM sync_history ORDER BY id DESC LIMIT 50")?;
        let rows = stmt.query_map([], |r| {
            Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?, r.get::<_, i64>(2)?, r.get::<_, i64>(3)?, r.get::<_, i64>(4)?, r.get::<_, String>(5)?))
        })?;
        rows.map(|row| {
            let (id, synced_at, before, after, added, list) = row?;
            Ok(json!({"id": id, "synced_at": synced_at, "before_words": before, "after_words": after, "added_words": added,
                      "added_word_list": serde_json::from_str::<Value>(&list)?}))
        }).collect()
    }

    // ---- practice ---------------------------------------------------------------------

pub(crate) fn describe_row(srs: &Srs, row: &MemoryRow, now: Time) -> ApiResult<Value> {
        let card: Card = serde_json::from_str(&row.card_json)?;
        Ok(serde_json::to_value(srs.describe(&card, now))?)
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
                Some(row) => Self::describe_row(&inner.active.srs, row, now)?,
                None => json!({"status": "new", "is_due": false}),
            };
            let card_version = row.map_or(0, |r| r.version);
            let attempt_id = uuid::Uuid::new_v4().to_string();
            item.insert("memory".into(), memory);
            item.insert("card_version".into(), card_version.into());
            item.insert("attempt_id".into(), attempt_id.clone().into());
            item.insert("issued_at".into(), time_text(now).into());
            tx.execute("INSERT INTO practice_items(attempt_id,session_id,word_key,word_json,card_version,issued_at,config_version,mode) VALUES(?,?,?,?,?,?,?,?)",
                params![attempt_id, session_id, key, Value::Object(word.data.clone()).to_string(), card_version, time_text(now), inner.active.version, mode])?;
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
        let active = &inner.active;
        if config_version != active.version {
            // Every issued version was saved to `srs_configs` when it became active.
            let rules: String = tx.query_row("SELECT config_json FROM srs_configs WHERE version=?", [&config_version], |r| r.get(0))?;
            let rules: Value = serde_json::from_str(&rules)?;
            if ["rating_version", "easy_seconds", "hard_seconds"].iter().any(|k| rules[k].as_f64() != active.snapshot[k].as_f64()) {
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
            "SELECT card_json,due,state,version,config_version FROM word_memory WHERE word_key=?", [&word_key],
            |r| Ok(MemoryRow { card_json: r.get(0)?, due: r.get(1)?, state: r.get(2)?, version: r.get(3)?, config_version: r.get(4)? }),
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
                if row.config_version != active.version {
                    card = active.srs.scheduler.reschedule(&card, &crate::sync::review_logs(&tx, &word_key)?);
                }
                let before = serde_json::to_string(&card)?;
                (card, Some(before))
            }
            None => {
                tx.execute("INSERT INTO word_memory(word_key,card_json,due,state,first_review,last_review,version,config_version) VALUES(?, '', ?, 1, ?, ?, 0, ?)",
                    params![word_key, time_text(reviewed), time_text(reviewed), time_text(reviewed), active.version])?;
                (Card::new(tx.last_insert_rowid(), reviewed), None)
            }
        };
        let correct = is_correct(word.text("word"), user_input);
        let (updated, rating) = active.srs.review(&card, correct, elapsed, reviewed, attempt_id);
        let version = card_version + 1;
        let after_json = serde_json::to_string(&updated)?;
        tx.execute("UPDATE word_memory SET card_json=?,due=?,state=?,stability=?,last_review=?,version=?,config_version=? WHERE id=?",
            params![after_json, time_text(updated.due), updated.state as i64, updated.stability, time_text(reviewed), version, active.version, card.card_id])?;
        let response = json!({
            "attempt_id": attempt_id, "is_correct": correct, "rating": rating as u8, "rating_name": rating.name(),
            "reviewed_at": time_text(reviewed), "duration_ms": elapsed,
            "memory": active.srs.describe(&updated, now), "card_version": version,
        });
        tx.execute("INSERT INTO word_reviews(attempt_id,request_hash,session_id,memory_id,word_key,word,chinese_meaning,category,user_input,is_correct,rating,reviewed_at,received_at,duration_ms,first_input_ms,answer_length,before_json,after_json,config_version,response_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            params![attempt_id, request_hash, session_id, card.card_id, word_key, word.text("word"), word.text("chinese_meaning"),
                    word.text("category"), user_input, correct, rating as u8, time_text(reviewed), time_text(now), elapsed, first_input,
                    normalize_answer(user_input).chars().count(), before_json, after_json, active.version, response.to_string()])?;
        tx.commit()?;
        Ok(response)
    }
}
