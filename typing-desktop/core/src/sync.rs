//! Local side of log sync: which answers still need uploading, the server
//! cursor, and merging answers from other devices.
//!
//! Merged answers are inserted into `word_reviews`; every affected word is then
//! rebuilt by replaying its whole log ordered by `reviewed_at, attempt_id`.
//! Fuzz is derived from `attempt_id`, so all devices reach the same schedule.

use std::collections::BTreeSet;

use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use serde_json::{json, Value};

use crate::answer::normalize_answer;
use crate::error::{ApiError, ApiResult};
use crate::fsrs::{Card, Rating};
use crate::srs::{fuzz_sample, Srs};
use crate::store::Store;
use crate::time::{parse_time, time_text, Time};

pub const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS synced_attempts (attempt_id TEXT PRIMARY KEY);
"#;

fn state(db: &Connection, key: &str) -> ApiResult<Option<String>> {
    Ok(db.query_row("SELECT value FROM sync_state WHERE key=?", [key], |r| r.get(0)).optional()?)
}

fn set_state(db: &Connection, key: &str, value: &str) -> ApiResult<()> {
    db.execute("INSERT INTO sync_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", [key, value])?;
    Ok(())
}

/// A server answer, checked before it may touch local cards.
struct RemoteAttempt<'a> {
    attempt_id: &'a str,
    word_key: &'a str,
    word: &'a str,
    chinese_meaning: &'a str,
    category: &'a str,
    user_input: &'a str,
    is_correct: bool,
    rating: Rating,
    reviewed_at: String,
    duration_ms: f64,
    first_input_ms: Option<f64>,
}

fn remote_attempt(item: &Value) -> Result<RemoteAttempt<'_>, String> {
    let text = |name: &str| item[name].as_str().ok_or_else(|| format!("缺少 {name}"));
    let rating = item["rating"].as_u64().and_then(|r| Rating::try_from(r as u8).ok()).ok_or("无效的 rating")?;
    let reviewed = parse_time(text("reviewed_at")?)?;
    let (attempt_id, word_key) = (text("attempt_id")?, text("word_key")?);
    if !word_key.starts_with("word-atlas:") || attempt_id.is_empty() {
        return Err("无效的作答标识".into());
    }
    Ok(RemoteAttempt {
        attempt_id, word_key, word: text("word")?, chinese_meaning: text("chinese_meaning")?,
        category: text("category")?, user_input: text("user_input")?,
        is_correct: item["is_correct"].as_bool().ok_or("无效的 is_correct")?, rating, reviewed_at: time_text(reviewed),
        duration_ms: item["duration_ms"].as_f64().filter(|v| v.is_finite() && *v >= 0.0).ok_or("无效的 duration_ms")?,
        first_input_ms: item["first_input_ms"].as_f64(),
    })
}

/// One word's full log in replay order (`reviewed_at, attempt_id`), with fuzz from the attempt id.
pub(crate) fn review_logs(db: &Connection, word_key: &str) -> ApiResult<Vec<(Time, Rating, Option<f64>)>> {
    let mut stmt = db.prepare("SELECT reviewed_at,rating,attempt_id FROM word_reviews WHERE word_key=? ORDER BY reviewed_at,attempt_id")?;
    let rows = stmt.query_map([word_key], |r| Ok((r.get::<_, String>(0)?, r.get::<_, u8>(1)?, r.get::<_, String>(2)?)))?;
    rows.map(|row| {
        let (at, rating, attempt) = row?;
        Ok((parse_time(&at).map_err(ApiError::Unavailable)?, Rating::try_from(rating).map_err(ApiError::Unavailable)?,
            Some(fuzz_sample(&attempt))))
    }).collect()
}

/// Rebuilds one word's card from its full log (the word has just received at least one answer).
fn replay(db: &Connection, srs: &Srs, version: &str, word_key: &str) -> ApiResult<()> {
    let id: i64 = db.query_row("SELECT id FROM word_memory WHERE word_key=?", [word_key], |r| r.get(0))?;
    let logs = review_logs(db, word_key)?;
    let (first, last) = (&logs[0], &logs[logs.len() - 1]);
    let card = srs.scheduler.reschedule(&Card::new(id, first.0), &logs);
    db.execute("UPDATE word_memory SET card_json=?,due=?,state=?,stability=?,first_review=?,last_review=?,version=version+1,config_version=? WHERE id=?",
        params![serde_json::to_string(&card)?, time_text(card.due), card.state as i64, card.stability, time_text(first.0),
                time_text(last.0), version, id])?;
    Ok(())
}

impl Store {
    /// Stable random id for this installation, sent with every sync.
    pub fn device_id(&self) -> ApiResult<String> {
        let inner = self.lock();
        if let Some(id) = state(&inner.db, "device_id")? {
            return Ok(id);
        }
        let id = uuid::Uuid::new_v4().to_string();
        set_state(&inner.db, "device_id", &id)?;
        Ok(id)
    }

    pub fn last_sync_at(&self) -> ApiResult<Option<String>> {
        state(&self.lock().db, "last_sync_at")
    }

    pub fn sync_cursor(&self) -> ApiResult<i64> {
        Ok(state(&self.lock().db, "cursor")?.and_then(|v| v.parse().ok()).unwrap_or(0))
    }

    /// Local answers the server has not acknowledged, oldest first.
    pub fn pending_uploads(&self, limit: usize) -> ApiResult<Vec<Value>> {
        let inner = self.lock();
        let mut stmt = inner.db.prepare("SELECT attempt_id,word_key,word,chinese_meaning,category,user_input,is_correct,rating,
            reviewed_at,duration_ms,first_input_ms FROM word_reviews r
            WHERE NOT EXISTS (SELECT 1 FROM synced_attempts s WHERE s.attempt_id=r.attempt_id) ORDER BY id LIMIT ?")?;
        let rows = stmt.query_map([limit as i64], |r| Ok(json!({
            "attempt_id": r.get::<_, String>(0)?, "word_key": r.get::<_, String>(1)?, "word": r.get::<_, String>(2)?,
            "chinese_meaning": r.get::<_, String>(3)?, "category": r.get::<_, String>(4)?, "user_input": r.get::<_, String>(5)?,
            "is_correct": r.get::<_, bool>(6)?, "rating": r.get::<_, u8>(7)?, "reviewed_at": r.get::<_, String>(8)?,
            "duration_ms": r.get::<_, f64>(9)?, "first_input_ms": r.get::<_, Option<f64>>(10)?,
        })))?;
        Ok(rows.collect::<Result<_, _>>()?)
    }

    /// Marks `uploaded` as acknowledged, inserts unseen server answers, replays the
    /// affected words and stores the new cursor in one transaction. Returns the number merged.
    pub fn merge_remote(&self, uploaded: &[Value], attempts: &[Value], next_cursor: i64) -> ApiResult<usize> {
        let parsed = attempts.iter().enumerate()
            .map(|(i, item)| remote_attempt(item).map_err(|e| ApiError::bad(format!("同步服务器第 {} 条作答无效：{e}", i + 1))))
            .collect::<ApiResult<Vec<_>>>()?;
        let now = time_text(self.now());
        let mut guard = self.lock();
        let inner = &mut *guard;
        let tx = inner.db.transaction_with_behavior(TransactionBehavior::Immediate)?;
        for item in uploaded {
            tx.execute("INSERT OR IGNORE INTO synced_attempts VALUES(?)", [item["attempt_id"].as_str().unwrap_or_default()])?;
        }
        let version = inner.active.version.clone();
        let mut affected = BTreeSet::new();
        let mut merged = 0;
        for a in &parsed {
            tx.execute("INSERT OR IGNORE INTO synced_attempts VALUES(?)", [a.attempt_id])?;
            let known = tx.query_row("SELECT 1 FROM word_reviews WHERE attempt_id=?", [a.attempt_id], |_| Ok(())).optional()?;
            if known.is_some() {
                continue;
            }
            tx.execute("INSERT OR IGNORE INTO word_memory(word_key,card_json,due,state,first_review,last_review,version,config_version)
                VALUES(?,'{}',?,1,?,?,0,?)", params![a.word_key, a.reviewed_at, a.reviewed_at, a.reviewed_at, version])?;
            let memory_id: i64 = tx.query_row("SELECT id FROM word_memory WHERE word_key=?", [a.word_key], |r| r.get(0))?;
            tx.execute("INSERT INTO word_reviews(attempt_id,request_hash,session_id,memory_id,word_key,word,chinese_meaning,category,
                user_input,is_correct,rating,reviewed_at,received_at,duration_ms,first_input_ms,answer_length,before_json,after_json,
                config_version,response_json) VALUES(?,'remote','remote',?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,'{}',?,'{}')",
                params![a.attempt_id, memory_id, a.word_key, a.word, a.chinese_meaning, a.category, a.user_input, a.is_correct,
                        a.rating as u8, a.reviewed_at, now, a.duration_ms, a.first_input_ms,
                        normalize_answer(a.user_input).chars().count(), version])?;
            affected.insert(a.word_key.to_string());
            merged += 1;
        }
        for key in &affected {
            replay(&tx, &inner.active.srs, &version, key)?;
        }
        set_state(&tx, "cursor", &next_cursor.to_string())?;
        set_state(&tx, "last_sync_at", &now)?;
        tx.commit()?;
        Ok(merged)
    }
}
