//! Vocabulary snapshot produced by `scripts/export_vocab.py` (later `/api/vocab`).

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

fn required_text(word: &Map<String, Value>, field: &str, index: usize) -> ApiResult<String> {
    match word.get(field) {
        Some(Value::String(v)) => Ok(v.clone()),
        _ => Err(ApiError::bad(format!("词库第 {} 项缺少字段 {field}", index + 1))),
    }
}

/// Parses a snapshot `{"format": 1, "words": [...]}`.
pub fn parse_snapshot(text: &str) -> ApiResult<Vec<Word>> {
    let value: Value = serde_json::from_str(text).map_err(|e| ApiError::bad(format!("词库文件不是有效 JSON：{e}")))?;
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
        let url = if illustration_file.is_empty() { String::new() } else { format!("/api/media/{note_id}/illustration") };
        data.insert("illustration_url".into(), Value::String(url));
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

/// Media file names come from the snapshot; only plain image names are served.
pub fn safe_media_name(name: &str) -> bool {
    const EXTENSIONS: [&str; 6] = [".webp", ".png", ".jpg", ".jpeg", ".gif", ".avif"];
    !name.is_empty()
        && !name.starts_with('.')
        && !name.chars().any(|c| matches!(c, '/' | '\\' | ':' | '\0'))
        && EXTENSIONS.iter().any(|ext| name.to_ascii_lowercase().ends_with(ext))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unsafe_media_names() {
        assert!(safe_media_name("demo_library.webp"));
        assert!(!safe_media_name("../secret.webp"));
        assert!(!safe_media_name("C:evil.png"));
        assert!(!safe_media_name("sound.mp3"));
    }
}
