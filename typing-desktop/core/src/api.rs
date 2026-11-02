//! Request router mirroring the Flask routes used by the practice page.
//! The desktop shell forwards custom-protocol requests here, so the existing
//! frontend (`axios` against `location.origin + "/api"`) runs unchanged.

use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};

use serde_json::{json, Value};

use crate::error::{ApiError, ApiResult};
use crate::store::{Store, FREE_PRACTICE_LIMIT};
use crate::vocab::{parse_snapshot, safe_media_name};

const MAX_LIMIT: usize = 100;

pub struct Request {
    pub method: String,
    pub path: String,
    pub query: HashMap<String, String>,
    pub body: Vec<u8>,
}

impl Request {
    /// `uri` may be absolute (`http://cijian.localhost/api/x?a=1`) or a path.
    pub fn new(method: &str, uri: &str, body: Vec<u8>) -> Self {
        let rest = uri.split_once("://").map_or(uri, |(_, r)| r.find('/').map_or("/", |i| &r[i..]));
        let (path, query) = rest.split_once('?').unwrap_or((rest, ""));
        let query = query.split('&').filter(|p| !p.is_empty()).map(|pair| {
            let (k, v) = pair.split_once('=').unwrap_or((pair, ""));
            (percent_decode(k), percent_decode(v))
        }).collect();
        Request { method: method.to_ascii_uppercase(), path: percent_decode(path), query, body }
    }

    fn int(&self, name: &str, default: usize) -> usize {
        match self.query.get(name).and_then(|v| v.parse::<i64>().ok()) {
            Some(v) if v > 0 => v as usize,
            _ => default,
        }
    }
}

fn percent_decode(text: &str) -> String {
    let bytes = text.replace('+', " ").into_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(v) = u8::from_str_radix(std::str::from_utf8(&bytes[i + 1..i + 3]).unwrap_or(""), 16) {
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

pub struct Response {
    pub status: u16,
    pub content_type: String,
    pub body: Vec<u8>,
}

impl Response {
    fn json(status: u16, value: Value) -> Self {
        Response { status, content_type: "application/json".into(), body: value.to_string().into_bytes() }
    }

    fn error(error: ApiError) -> Self {
        Self::json(error.status(), error.body())
    }
}

pub struct AppConfig {
    /// Rendered frontend (`scripts/build_frontend.py` output).
    pub dist_dir: PathBuf,
    /// Directory holding illustration files named in the vocabulary snapshot.
    pub media_dir: Option<PathBuf>,
    /// Vocabulary snapshot imported by “同步”.
    pub vocab_path: Option<PathBuf>,
}

pub struct App {
    pub store: Store,
    pub config: AppConfig,
}

fn content_type(path: &Path) -> &'static str {
    match path.extension().and_then(|e| e.to_str()).map(str::to_ascii_lowercase).as_deref() {
        Some("html") => "text/html; charset=utf-8",
        Some("js") => "text/javascript; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("svg") => "image/svg+xml",
        Some("png") => "image/png",
        Some("ico") => "image/x-icon",
        Some("webp") => "image/webp",
        Some("jpg" | "jpeg") => "image/jpeg",
        Some("gif") => "image/gif",
        Some("avif") => "image/avif",
        Some("json") => "application/json",
        _ => "application/octet-stream",
    }
}

/// Joins a URL path under `root`, refusing `..`, absolute and prefixed components.
fn safe_join(root: &Path, relative: &str) -> Option<PathBuf> {
    let rel = Path::new(relative.trim_start_matches('/'));
    if rel.as_os_str().is_empty() || !rel.components().all(|c| matches!(c, Component::Normal(_))) {
        return None;
    }
    Some(root.join(rel))
}

fn file(path: Option<PathBuf>) -> Response {
    match path.filter(|p| p.is_file()).and_then(|p| std::fs::read(&p).ok().map(|body| (p, body))) {
        Some((p, body)) => Response { status: 200, content_type: content_type(&p).into(), body },
        None => Response::error(ApiError::NotFound),
    }
}

impl App {
    pub fn handle(&self, request: &Request) -> Response {
        let path = request.path.as_str();
        if !path.starts_with("/api/") {
            if request.method != "GET" {
                return Response::error(ApiError::NotFound);
            }
            let page = match path {
                "/" | "/index.html" => "index.html",
                "/stats.html" => "stats.html",
                p if p.starts_with("/assets/") || p.starts_with("/src/") || p.starts_with("/vendor/") => {
                    return file(safe_join(&self.config.dist_dir, p));
                }
                _ => "index.html",
            };
            return file(Some(self.config.dist_dir.join(page)));
        }
        if let Some(rest) = path.strip_prefix("/api/media/") {
            return self.media(rest);
        }
        match self.api(request) {
            Ok(value) => Response::json(200, value),
            Err(error) => Response::error(error),
        }
    }

    fn media(&self, rest: &str) -> Response {
        let file_name = match rest.split_once('/') {
            Some((id, "illustration")) => id.parse().ok().and_then(|id| self.store.illustration_file(id)),
            _ => None,
        };
        match (file_name.filter(|f| safe_media_name(f)), &self.config.media_dir) {
            (Some(name), Some(dir)) => file(Some(dir.join(name))),
            _ => Response::error(ApiError::NotFound),
        }
    }

    fn api(&self, request: &Request) -> ApiResult<Value> {
        let s = &self.store;
        match (request.method.as_str(), request.path.as_str()) {
            ("GET", "/api/health") => Ok(json!({"success": true, "status": "ok"})),
            ("GET", "/api/config") => Ok(json!({
                "success": true, "anki_available": true,
                "anki_path": self.config.vocab_path.as_ref().map(|p| p.display().to_string()),
                "deck_name": "Word Atlas", "total_learned": s.learned_count(),
                "default_limit": FREE_PRACTICE_LIMIT, "max_limit": MAX_LIMIT,
                "easy_seconds": s.srs.config.easy_seconds, "hard_seconds": s.srs.config.hard_seconds,
            })),
            ("GET", "/api/memory/summary") => Ok(json!({"success": true, "data": s.summary()?})),
            ("GET", "/api/practice/queue") => {
                let mode = request.query.get("mode").map_or("scheduled", String::as_str);
                let default = if mode == "free" { FREE_PRACTICE_LIMIT } else { 1 };
                let limit = request.int("limit", default).min(MAX_LIMIT);
                let session = request.query.get("session_id").map_or("", String::as_str);
                Ok(json!({"success": true, "data": s.queue(session, Some(limit), mode)?}))
            }
            ("POST", "/api/practice/attempts") => {
                let next_limit = match request.query.get("next_limit").map(|v| v.parse::<usize>()) {
                    None => 0,
                    Some(Ok(v)) if v <= 3 => v,
                    _ => return Err(ApiError::bad("next_limit 必须在 0–3 之间")),
                };
                let payload: Value = serde_json::from_slice(&request.body).unwrap_or(Value::Null);
                let result = s.submit(&payload)?;
                let mut response = json!({"success": true, "data": result});
                if next_limit > 0 {
                    let session = payload["session_id"].as_str().unwrap_or_default();
                    // The answer is committed; a follow-up selection failure falls back to GET /queue.
                    match s.queue(session, Some(next_limit), "scheduled") {
                        Ok(next) => response["next_queue"] = next,
                        Err(error) => eprintln!("could not select the next practice item: {error}"),
                    }
                }
                Ok(response)
            }
            ("GET", "/api/sync/status") => Ok(json!({"success": true, "data": self.sync_status(None)?})),
            ("POST", "/api/sync/now") => self.sync_now(),
            _ => Err(ApiError::NotFound),
        }
    }

    fn sync_status(&self, last: Option<Value>) -> ApiResult<Value> {
        let mut status = last.unwrap_or_else(|| json!({
            "before_words": 0, "after_words": self.store.learned_count(), "added_words": 0,
            "added_word_list": [], "success": false,
        }));
        status["sync_configured"] = self.config.vocab_path.is_some().into();
        status["target_path"] = self.config.vocab_path.as_ref().map(|p| p.display().to_string()).into();
        status["history"] = self.store.sync_history(50)?.into();
        if status.get("last_sync_at").is_none() {
            status["last_sync_at"] = status["history"].get(0).map_or(Value::Null, |h| h["synced_at"].clone());
        }
        Ok(status)
    }

    /// Offline phase: re-import the configured vocabulary snapshot.
    fn sync_now(&self) -> ApiResult<Value> {
        let result = self.config.vocab_path.as_ref()
            .ok_or_else(|| ApiError::bad("未配置词库文件（CIJIAN_VOCAB_PATH）"))
            .and_then(|p| std::fs::read_to_string(p).map_err(|e| ApiError::bad(format!("无法读取词库文件：{e}"))))
            .and_then(|text| parse_snapshot(&text))
            .and_then(|words| self.store.import_vocabulary(words));
        Ok(json!({"success": true, "data": self.sync_status(Some(result?))?}))
    }
}
