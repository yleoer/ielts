//! Read-only statistics for the stats page.
//! Port of `stats.py`, `activity.py`, `vocabulary.py` and the calendar / vocabulary
//! queries in `memory.py`; JSON shapes match the Flask routes.

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};

use chrono::{Datelike, NaiveDate, TimeDelta};
use rusqlite::types::ValueRef;
use rusqlite::{params_from_iter, Connection, ToSql};
use serde_json::{json, Map, Value};

use crate::error::{ApiError, ApiResult};
use crate::store::{memory_rows, shanghai, Store};
use crate::time::{parse_time, Time};
use crate::vocab::{pool_by_key, Word};

const CEFR_LEVELS: [(&str, &str); 6] =
    [("A1", "入门"), ("A2", "基础"), ("B1", "进阶"), ("B2", "中高级"), ("C1", "高级"), ("C2", "熟练")];
const UNKNOWN_CEFR: &str = "未分级";
const UNKNOWN_TOPIC: &str = "未分类";

fn json_value(value: ValueRef) -> Value {
    match value {
        ValueRef::Null | ValueRef::Blob(_) => Value::Null,
        ValueRef::Integer(v) => v.into(),
        ValueRef::Real(v) => v.into(),
        ValueRef::Text(v) => String::from_utf8_lossy(v).into_owned().into(),
    }
}

/// Rows as JSON objects keyed by column name, like `dict(sqlite3.Row)`.
pub(crate) fn query_objects(db: &Connection, sql: &str, params: &[&dyn ToSql]) -> ApiResult<Vec<Map<String, Value>>> {
    let mut stmt = db.prepare(sql)?;
    let names: Vec<String> = stmt.column_names().into_iter().map(String::from).collect();
    let rows = stmt.query_map(params_from_iter(params.iter()), |row| {
        names.iter().enumerate().map(|(i, name)| Ok((name.clone(), json_value(row.get_ref(i)?)))).collect()
    })?;
    Ok(rows.collect::<Result<_, _>>()?)
}

fn month_start(today: NaiveDate, offset: i32) -> NaiveDate {
    let index = today.year() * 12 + today.month0() as i32 + offset;
    NaiveDate::from_ymd_opt(index.div_euclid(12), index.rem_euclid(12) as u32 + 1, 1).unwrap()
}

/// Six months back to the end of the fifth month ahead, like `activity.calendar_window`.
pub fn calendar_window(today: NaiveDate) -> (NaiveDate, NaiveDate) {
    (month_start(today, -6), month_start(today, 6) - TimeDelta::days(1))
}

fn calendar_day(value: &str, today: NaiveDate) -> ApiResult<NaiveDate> {
    let selected = NaiveDate::parse_from_str(value, "%Y-%m-%d").ok().filter(|d| d.to_string() == value)
        .ok_or_else(|| ApiError::bad("需要 YYYY-MM-DD 格式的日期"))?;
    let (start, end) = calendar_window(today);
    if !(start <= selected && selected <= end) {
        return Err(ApiError::bad("请选择学习日历范围内的日期，请刷新后重试"));
    }
    Ok(selected)
}

/// Shared daily totals for the calendar and the recent activity chart (Beijing days).
fn daily_activity(db: &Connection, start: NaiveDate, end: NaiveDate) -> ApiResult<Vec<Map<String, Value>>> {
    query_objects(db, "SELECT date(reviewed_at,'+8 hours') date,
        COUNT(DISTINCT word_key) practiced,COUNT(*) attempts,AVG(is_correct)*100 accuracy
        FROM word_reviews WHERE date(reviewed_at,'+8 hours') BETWEEN ? AND ?
        GROUP BY date ORDER BY date", &[&start.to_string(), &end.to_string()])
}

fn due_day(due: Time, today: NaiveDate) -> NaiveDate {
    today.max(due.with_timezone(&shanghai()).date_naive())
}

fn days(start: NaiveDate, end: NaiveDate) -> impl Iterator<Item = NaiveDate> {
    start.iter_days().take_while(move |d| *d <= end)
}

fn text<'a>(word: &'a Map<String, Value>, field: &str) -> &'a str {
    word.get(field).and_then(Value::as_str).unwrap_or_default()
}

/// `dimension` is `cefr` or `topic` (checked by `vocabulary_words`).
fn group_value(word: &Map<String, Value>, dimension: &str) -> String {
    if dimension == "cefr" {
        let value = text(word, "cefr").trim().to_uppercase();
        if CEFR_LEVELS.iter().any(|(level, _)| *level == value) { value } else { UNKNOWN_CEFR.into() }
    } else {
        let value = text(word, "category").trim();
        if value.is_empty() { UNKNOWN_TOPIC.into() } else { value.into() }
    }
}

/// Insertion-ordered groups, like the Python dicts in `vocabulary.progress`.
#[derive(Default)]
struct Groups {
    order: Vec<Value>,
    index: HashMap<String, usize>,
}

impl Groups {
    fn entry(&mut self, value: &str, label: Option<&str>) -> &mut Value {
        let next = self.order.len();
        let i = *self.index.entry(value.into()).or_insert(next);
        if i == next {
            self.order.push(empty_group(value, label));
        }
        &mut self.order[i]
    }
}

fn empty_group(value: &str, label: Option<&str>) -> Value {
    json!({"value": value, "label": label.unwrap_or(value), "total": 0, "learned": 0, "new": 0, "learning": 0, "mastered": 0})
}

fn count(group: &mut Value, status: &str) {
    for field in ["total", status].into_iter().chain((status != "new").then_some("learned")) {
        group[field] = (group[field].as_i64().unwrap_or(0) + 1).into();
    }
}

fn progress(entries: &[Map<String, Value>]) -> Value {
    let mut levels = Groups::default();
    for (value, label) in CEFR_LEVELS {
        levels.entry(value, Some(label));
    }
    let mut topics = Groups::default();
    let mut overall = empty_group("all", None);
    for word in entries {
        let status = text(word, "status");
        count(&mut overall, status);
        count(levels.entry(&group_value(word, "cefr"), None), status);
        count(topics.entry(&group_value(word, "topic"), None), status);
    }
    json!({"overall": overall, "levels": levels.order, "topics": topics.order})
}

/// Practiced words first, prioritising a smoothed lifetime error rate (`vocabulary.word_sort_key`).
fn word_order(a: &Map<String, Value>, b: &Map<String, Value>) -> Ordering {
    let key = |w: &Map<String, Value>| {
        let total = w.get("total_attempts").and_then(Value::as_i64).unwrap_or(0);
        let errors = total - w.get("correct_attempts").and_then(Value::as_i64).unwrap_or(0);
        (total == 0, -(errors + 1) as f64 / (total + 2) as f64, -errors, text(w, "word").to_lowercase())
    };
    let (ka, kb) = (key(a), key(b));
    ka.0.cmp(&kb.0)
        .then(ka.1.total_cmp(&kb.1))
        .then(ka.2.cmp(&kb.2))
        .then(ka.3.cmp(&kb.3))
        .then_with(|| text(a, "source_id").cmp(text(b, "source_id")))
}

fn word_key(word: &Map<String, Value>) -> String {
    format!("word-atlas:{}", text(word, "source_id").trim())
}

/// Adds lifetime `correct_attempts` / `total_attempts` to each item.
fn with_attempt_counts(db: &Connection, items: &mut [Map<String, Value>]) -> ApiResult<()> {
    let mut stmt = db.prepare("SELECT word_key,SUM(is_correct),COUNT(*) FROM word_reviews GROUP BY word_key")?;
    let counts: HashMap<String, (i64, i64)> = stmt
        .query_map([], |r| Ok((r.get(0)?, (r.get(1)?, r.get(2)?))))?
        .collect::<Result<_, _>>()?;
    for item in items {
        let (correct, total) = counts.get(&word_key(item)).copied().unwrap_or((0, 0));
        item.insert("correct_attempts".into(), correct.into());
        item.insert("total_attempts".into(), total.into());
    }
    Ok(())
}

fn merged(word: &Map<String, Value>, memory: Value) -> Map<String, Value> {
    let mut item = word.clone();
    if let Value::Object(memory) = memory {
        item.extend(memory);
    }
    item
}

impl Store {
    fn today(&self) -> NaiveDate {
        self.now().with_timezone(&shanghai()).date_naive()
    }

    pub fn overview(&self) -> ApiResult<Value> {
        let today = self.today();
        let inner = self.lock();
        let mut row = query_objects(&inner.db, "SELECT COUNT(*) total_words_practiced,
            COALESCE(SUM(duration_ms),0)/60000 total_time_minutes FROM word_reviews", &[])?.remove(0);
        let mut stmt = inner.db.prepare("SELECT DISTINCT date(reviewed_at,'+8 hours') FROM word_reviews")?;
        let practiced: HashSet<String> = stmt.query_map([], |r| r.get(0))?.collect::<Result<_, _>>()?;
        let mut cursor = if practiced.contains(&today.to_string()) { today } else { today - TimeDelta::days(1) };
        let mut streak = 0;
        while practiced.contains(&cursor.to_string()) {
            streak += 1;
            cursor -= TimeDelta::days(1);
        }
        row.insert("current_streak".into(), streak.into());
        Ok(Value::Object(row))
    }

    /// The last 30 Beijing days, oldest first.
    pub fn recent_activity(&self) -> ApiResult<Value> {
        let end = self.today();
        let start = end - TimeDelta::days(29);
        let rows = daily_activity(&self.lock().db, start, end)?;
        let by_date: HashMap<&str, &Map<String, Value>> = rows.iter().map(|r| (text(r, "date"), r)).collect();
        let days: Vec<Value> = days(start, end).map(|day| {
            let date = day.to_string();
            let row = by_date.get(date.as_str());
            json!({"date": date, "words": row.map_or(0.into(), |r| r["attempts"].clone()),
                   "accuracy": row.map_or(Value::Null, |r| r["accuracy"].clone())})
        }).collect();
        Ok(json!({"start_date": start.to_string(), "end_date": end.to_string(), "days": days}))
    }

    pub fn activity_calendar(&self) -> ApiResult<Value> {
        let today = self.today();
        let (start, end) = calendar_window(today);
        let mut list: Vec<Map<String, Value>> = days(start, end).map(|day| {
            json!({"date": day.to_string(), "practiced": 0, "attempts": 0, "accuracy": null, "due_count": 0})
                .as_object().unwrap().clone()
        }).collect();
        let index = |day: &str| NaiveDate::parse_from_str(day, "%Y-%m-%d").ok()
            .filter(|d| (start..=end).contains(d)).map(|d| (d - start).num_days() as usize);
        let inner = self.lock();
        for row in daily_activity(&inner.db, start, end)? {
            if let Some(i) = index(text(&row, "date")) {
                list[i].extend(row);
            }
        }
        let states = memory_rows(&inner.db)?;
        for (key, _) in pool_by_key(&inner.vocabulary)? {
            if let Some(row) = states.get(&key) {
                let due = due_day(parse_time(&row.due).map_err(ApiError::Unavailable)?, today);
                if let Some(i) = index(&due.to_string()) {
                    list[i]["due_count"] = (list[i]["due_count"].as_i64().unwrap_or(0) + 1).into();
                }
            }
        }
        Ok(json!({"start_date": start.to_string(), "end_date": end.to_string(), "today": today.to_string(), "days": list}))
    }

    /// Words reviewed on `day` (latest attempt per word) and, for today or later, words due then.
    pub fn calendar_words(&self, day: &str) -> ApiResult<Value> {
        let now = self.now();
        let today = self.today();
        let selected = calendar_day(day, today)?;
        let inner = self.lock();
        let srs = &inner.active.srs;
        let states = memory_rows(&inner.db)?;
        let current: HashMap<String, &Word> = pool_by_key(&inner.vocabulary)?.into_iter().collect();
        let describe = |key: &str| states.get(key).map(|row| Self::describe_row(srs, row, now)).transpose();
        let rows = query_objects(&inner.db, "WITH ranked AS (
                SELECT memory_id,word_key,word,chinese_meaning,category,reviewed_at,
                    ROW_NUMBER() OVER(PARTITION BY word_key ORDER BY reviewed_at DESC,id DESC) position
                FROM word_reviews WHERE date(reviewed_at,'+8 hours')=?
            ) SELECT * FROM ranked WHERE position=1", &[&day])?;
        let mut practiced = vec![];
        for row in rows {
            let key = text(&row, "word_key");
            let word = match current.get(key) {
                Some(word) => word.data.clone(),
                None => json!({
                    "id": format!("history-{}", row["memory_id"]), "source_id": key.strip_prefix("word-atlas:").unwrap_or(key),
                    "word": row["word"], "chinese_meaning": row["chinese_meaning"], "category": row["category"], "cefr": "",
                }).as_object().unwrap().clone(),
            };
            practiced.push(merged(&word, describe(key)?.unwrap_or(Value::Null)));
        }
        let mut due = vec![];
        if selected >= today {
            for (key, word) in pool_by_key(&inner.vocabulary)? {
                if let Some(row) = states.get(&key) {
                    if due_day(parse_time(&row.due).map_err(ApiError::Unavailable)?, today) == selected {
                        due.push(merged(&word.data, Self::describe_row(srs, row, now)?));
                    }
                }
            }
        }
        for items in [&mut practiced, &mut due] {
            with_attempt_counts(&inner.db, items)?;
            items.sort_by(word_order);
        }
        Ok(json!({"practiced": practiced, "due": due}))
    }

    /// Every vocabulary item (learned or not), one per SourceId, with its memory status.
    fn vocabulary_entries(&self, inner: &crate::store::Inner) -> ApiResult<Vec<Map<String, Value>>> {
        let now = self.now();
        let states = memory_rows(&inner.db)?;
        let mut seen = HashSet::new();
        let mut entries = vec![];
        for word in &inner.vocabulary {
            if word.source_id.is_empty() {
                return Err(ApiError::bad(format!("词条 {} 缺少 SourceId，请更新 Word Atlas 牌组", word.note_id)));
            }
            if !seen.insert(word.source_id.as_str()) {
                continue;
            }
            let memory = match states.get(&word.key()) {
                Some(row) => Self::describe_row(&inner.active.srs, row, now)?,
                None => json!({"status": "new", "is_due": false}),
            };
            entries.push(merged(&word.data, memory));
        }
        Ok(entries)
    }

    pub fn vocabulary_progress(&self) -> ApiResult<Value> {
        let inner = self.lock();
        Ok(progress(&self.vocabulary_entries(&inner)?))
    }

    pub fn vocabulary_words(&self, dimension: &str, value: &str, status: &str, offset: usize, limit: usize) -> ApiResult<Value> {
        if dimension != "cefr" && dimension != "topic" {
            return Err(ApiError::bad("无效的词库分组"));
        }
        if value.is_empty() || !["all", "new", "learning", "mastered"].contains(&status) {
            return Err(ApiError::bad("无效的词库筛选"));
        }
        let inner = self.lock();
        let mut entries = self.vocabulary_entries(&inner)?;
        with_attempt_counts(&inner.db, &mut entries)?;
        let mut matches: Vec<_> = entries.into_iter()
            .filter(|word| group_value(word, dimension) == value && (status == "all" || text(word, "status") == status))
            .collect();
        matches.sort_by(word_order);
        let total = matches.len();
        let items: Vec<_> = matches.into_iter().skip(offset).take(limit).collect();
        let end = offset + items.len();
        Ok(json!({"items": items, "total": total, "next_offset": (end < total).then_some(end)}))
    }

    /// Wrong answers for one word, newest first, paged by review id.
    pub fn word_errors(&self, source_id: &str, before_id: i64, limit: usize) -> ApiResult<Value> {
        let source_id = source_id.trim();
        if source_id.is_empty() {
            return Err(ApiError::bad("需要有效的 SourceId"));
        }
        let key = format!("word-atlas:{source_id}");
        let inner = self.lock();
        let counts = query_objects(&inner.db, "SELECT COUNT(*) total_attempts,
            COALESCE(SUM(is_correct),0) correct_attempts FROM word_reviews WHERE word_key=?", &[&key])?.remove(0);
        let rows = query_objects(&inner.db, "SELECT id,word,user_input,reviewed_at
            FROM word_reviews WHERE word_key=? AND is_correct=0 AND (?=0 OR id<?)
            ORDER BY id DESC LIMIT ?", &[&key, &before_id, &before_id, &(limit as i64 + 1)])?;
        let more = rows.len() > limit;
        let items: Vec<_> = rows.into_iter().take(limit).collect();
        let next = if more { items.last().map_or(Value::Null, |r| r["id"].clone()) } else { Value::Null };
        Ok(json!({"items": items, "correct_attempts": counts["correct_attempts"],
                  "total_attempts": counts["total_attempts"], "next_before_id": next}))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn calendar_window_spans_months_across_years() {
        let today = NaiveDate::from_ymd_opt(2026, 3, 15).unwrap();
        assert_eq!(calendar_window(today), (NaiveDate::from_ymd_opt(2025, 9, 1).unwrap(), NaiveDate::from_ymd_opt(2026, 8, 31).unwrap()));
        assert!(calendar_day("2026-3-15", today).is_err());
        assert!(calendar_day("2026-09-01", today).is_err());
        assert_eq!(calendar_day("2025-09-01", today).unwrap(), NaiveDate::from_ymd_opt(2025, 9, 1).unwrap());
    }
}
