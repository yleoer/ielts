//! Vocabulary snapshot served by the sync server (`GET /api/vocab`).

use serde_json::{Map, Value};

use crate::error::{ApiError, ApiResult};

#[derive(Clone, Debug, PartialEq)]
pub struct Word {
    pub note_id: i64,
    pub source_id: String,
    pub learned: bool,
    pub illustration_file: String,
    /// Fields returned to the page, same shape as `anki.parse_word`.
    pub data: Map<String, Value>,
}

impl Word {
    pub fn key(&self) -> String {
        format!("word-atlas:{}", self.source_id)
    }

    pub fn text(&self, field: &str) -> &str {
        self.data.get(field).and_then(Value::as_str).unwrap_or_default()
    }
}

fn required_text<'a>(word: &'a Map<String, Value>, field: &str, index: usize) -> ApiResult<&'a str> {
    match word.get(field) {
        Some(Value::String(v)) => Ok(v),
        _ => Err(ApiError::bad(format!("词库第 {} 项缺少字段 {field}", index + 1))),
    }
}

/// Parses a server snapshot `{"format": 1, "words": [...]}`.
pub fn parse_snapshot(value: &Value) -> ApiResult<Vec<Word>> {
    if value.get("format").and_then(Value::as_i64) != Some(1) {
        return Err(ApiError::bad("不支持的词库文件格式"));
    }
    let items = value.get("words").and_then(Value::as_array).ok_or_else(|| ApiError::bad("词库文件缺少 words"))?;
    items.iter().enumerate().map(|(index, item)| {
        let mut data = item.as_object().cloned().ok_or_else(|| ApiError::bad(format!("词库第 {} 项不是对象", index + 1)))?;
        let note_id = data.get("id").and_then(Value::as_i64).ok_or_else(|| ApiError::bad(format!("词库第 {} 项缺少 id", index + 1)))?;
        for field in ["word", "chinese_meaning", "part_of_speech", "category"] {
            required_text(&data, field, index)?;
        }
        let source_id = required_text(&data, "source_id", index)?.trim().to_string();
        let learned = data.remove("learned").and_then(|v| v.as_bool()).unwrap_or(false);
        let illustration_file = match data.remove("illustration_file") {
            Some(Value::String(v)) => v,
            _ => String::new(),
        };
        // The app resolves media against its locally installed SourceId manifest, never the server.
        data.insert("illustration_url".into(), Value::String(String::new()));
        data.remove("audio_url");
        data.remove("audio_urls");
        Ok(Word { note_id, source_id, learned, illustration_file, data })
    }).collect()
}

/// Learned words keyed by `word-atlas:<SourceId>`, rejecting missing or duplicate ids
/// like `memory.pool_by_key`. Order follows note id.
pub fn pool_by_key(words: &[Word]) -> ApiResult<Vec<(String, &Word)>> {
    let mut seen = std::collections::HashSet::new();
    let mut result = Vec::new();
    for word in words.iter().filter(|w| w.learned) {
        if word.source_id.is_empty() {
            return Err(ApiError::bad(format!("词条 {} 缺少 SourceId，请更新 Word Atlas 牌组", word.note_id)));
        }
        let key = word.key();
        if !seen.insert(key.clone()) {
            return Err(ApiError::bad(format!("Word Atlas SourceId 重复：{}", word.source_id)));
        }
        result.push((key, word));
    }
    Ok(result)
}
