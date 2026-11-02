//! Errors mapped to the same HTTP statuses and JSON as the Flask app.

use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub enum ApiError {
    /// 400 `{"success": false, "error": ...}`
    BadRequest(String),
    /// 409 with `code: practice_conflict`
    Conflict(String),
    /// 503
    Unavailable(String),
    NotFound,
}

impl ApiError {
    pub fn bad(message: impl Into<String>) -> Self {
        ApiError::BadRequest(message.into())
    }

    pub fn conflict(message: impl Into<String>) -> Self {
        ApiError::Conflict(message.into())
    }

    pub fn status(&self) -> u16 {
        match self {
            ApiError::BadRequest(_) => 400,
            ApiError::Conflict(_) => 409,
            ApiError::Unavailable(_) => 503,
            ApiError::NotFound => 404,
        }
    }

    pub fn body(&self) -> serde_json::Value {
        match self {
            ApiError::Conflict(m) => serde_json::json!({"success": false, "error": m, "code": "practice_conflict"}),
            ApiError::BadRequest(m) | ApiError::Unavailable(m) => serde_json::json!({"success": false, "error": m}),
            ApiError::NotFound => serde_json::json!({"success": false, "error": "not found"}),
        }
    }
}

impl fmt::Display for ApiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.body()["error"].as_str().unwrap_or_default())
    }
}

impl std::error::Error for ApiError {}

impl From<rusqlite::Error> for ApiError {
    fn from(error: rusqlite::Error) -> Self {
        eprintln!("practice storage unavailable: {error}");
        ApiError::Unavailable("练习数据暂不可用，请稍后重试".into())
    }
}

impl From<serde_json::Error> for ApiError {
    fn from(error: serde_json::Error) -> Self {
        eprintln!("stored JSON is invalid: {error}");
        ApiError::Unavailable("练习数据暂不可用，请稍后重试".into())
    }
}

pub type ApiResult<T> = Result<T, ApiError>;
