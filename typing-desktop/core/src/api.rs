//! Request router mirroring the Flask routes used by the practice page.
//! The desktop shell forwards custom-protocol requests here, so the existing
//! frontend (`axios` against `location.origin + "/api"`) runs unchanged.

use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};

use serde_json::{json, Value};

use crate::error::{ApiError, ApiResult};
use crate::optimize::OptimizationConfig;
use crate::media_install::MediaManager;
use std::sync::{Arc, RwLock};

use crate::remote::{sync_all, HttpRemote, Remote, ServerConfig};
use crate::store::{Store, FREE_PRACTICE_LIMIT};

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

    fn get(&self, name: &str) -> &str {
        self.query.get(name).map_or("", String::as_str)
    }

    /// Strict integer parameter: absent → default, malformed → `error`.
    fn strict(&self, name: &str, default: i64, error: &str) -> ApiResult<i64> {
        self.query.get(name).map_or(Ok(default), |v| v.trim().parse().map_err(|_| ApiError::bad(error)))
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
    /// Writable resource-package directory (active.json and versioned ZIP files).
    pub media_dir: Option<PathBuf>,
    /// Where the sync server chosen in the first-run dialog is saved (`server.json`).
    pub server_file: Option<PathBuf>,
}

/// Where the current server setting came from.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum ServerSource {
    /// `CIJIAN_SERVER_URL` / `CIJIAN_SERVER_TOKEN`; not editable in the app.
    Environment,
    /// `server.json`, written by the settings dialog.
    File,
}

struct Connection {
    config: ServerConfig,
    source: ServerSource,
    remote: Arc<dyn Remote>,
}

pub type Connector = Box<dyn Fn(&ServerConfig) -> Arc<dyn Remote> + Send + Sync>;

pub struct App {
    pub store: Store,
    pub config: AppConfig,
    pub optimization: OptimizationConfig,
    /// Builds the client for a server setting (HTTP in the app, a fake in tests).
    pub connect: Connector,
    connection: RwLock<Option<Connection>>,
    media: Arc<MediaManager>,
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
        Some("mp3") => "audio/mpeg",
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
    pub fn new(store: Store, config: AppConfig, optimization: OptimizationConfig) -> Self {
        let media = MediaManager::new(config.media_dir.as_deref());
        App {
            store, config, optimization,
            connect: Box::new(|c| Arc::new(HttpRemote::new(c.clone()))),
            connection: RwLock::new(None),
            media,
        }
    }

    /// Uses `config` for all later syncs; does not contact the server.
    pub fn set_server(&self, config: ServerConfig, source: ServerSource) {
        let remote = (self.connect)(&config);
        *self.connection.write().unwrap_or_else(|p| p.into_inner()) = Some(Connection { config, source, remote });
    }

    /// The configured sync server, if any.
    pub fn remote(&self) -> Option<Arc<dyn Remote>> {
        self.connection.read().unwrap_or_else(|p| p.into_inner()).as_ref().map(|c| c.remote.clone())
    }

    fn server_settings(&self) -> Value {
        let connection = self.connection.read().unwrap_or_else(|p| p.into_inner());
        match connection.as_ref() {
            Some(c) => json!({"configured": true, "url": c.config.url, "has_token": !c.config.token.is_empty(),
                              "editable": c.source == ServerSource::File,
                              "source": if c.source == ServerSource::File { "file" } else { "environment" }}),
            None => json!({"configured": false, "url": null, "has_token": false, "editable": true, "source": null}),
        }
    }

    /// Checks the address and token against the server, then saves and applies them.
    /// An empty token keeps the saved one, so the address can change alone.
    fn save_server_settings(&self, payload: &Value) -> ApiResult<Value> {
        let current = self.connection.read().unwrap_or_else(|p| p.into_inner()).as_ref()
            .map(|c| (c.config.clone(), c.source));
        if current.as_ref().is_some_and(|(_, source)| *source == ServerSource::Environment) {
            return Err(ApiError::bad("服务器由环境变量 CIJIAN_SERVER_URL 指定，请修改环境变量"));
        }
        let text = |k: &str| payload.get(k).and_then(Value::as_str).unwrap_or_default();
        let token = match (text("token").trim(), &current) {
            ("", Some((saved, _))) => saved.token.clone(),
            (token, _) => token.to_string(),
        };
        let config = ServerConfig::new(text("url"), &token).map_err(ApiError::BadRequest)?;
        (self.connect)(&config).check().map_err(ApiError::BadRequest)?;
        if let Some(path) = &self.config.server_file {
            config.save(path).map_err(ApiError::Unavailable)?;
        }
        self.set_server(config, ServerSource::File);
        Ok(self.server_settings())
    }

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
            return if request.method == "GET" { self.media(rest) } else { Response::error(ApiError::NotFound) };
        }
        if let Some(id) = path.strip_prefix("/api/memory/optimization/runs/").filter(|_| request.method == "GET") {
            return match id.parse::<i64>().ok().map(|id| self.store.optimization_run(id)) {
                Some(Ok(Some(record))) => Response::json(200, json!({"success": true, "data": record})),
                Some(Err(error)) => Response::error(error),
                _ => Response::error(ApiError::NotFound),
            };
        }
        match self.api(request) {
            Ok(mut value) => {
                self.media.current().decorate(&mut value);
                Response::json(200, value)
            }
            Err(error) => Response::error(error),
        }
    }

    fn media(&self, rest: &str) -> Response {
        let result = if let Some(rest) = rest.strip_prefix("source/") {
            rest.split_once('/').map(|(source, route)| self.media.current().read(source, route))
        } else {
            rest.split_once('/').and_then(|(id, route)| {
                id.parse().ok().and_then(|id| self.store.source_id(id)).map(|source| self.media.current().read(&source, route))
            })
        }.unwrap_or(Err(ApiError::NotFound));
        match result {
            Ok((path, body)) => Response { status: 200, content_type: content_type(&path).into(), body },
            Err(error) => Response::error(error),
        }
    }

    fn api(&self, request: &Request) -> ApiResult<Value> {
        if request.path.starts_with("/api/resources/") {
            let payload = || serde_json::from_slice::<Value>(&request.body).map_err(|_| ApiError::bad("无效请求"));
            let data = match (request.method.as_str(), request.path.as_str()) {
                ("GET", "/api/resources/status") => self.media.status(),
                ("POST", "/api/resources/urls") => {
                    let payload = payload()?;
                    let ids = payload["ids"].as_array()
                        .ok_or_else(|| ApiError::bad("无效词条列表"))?;
                    Value::Array(ids.iter().filter_map(|id| {
                        let id = id.as_i64()?;
                        self.store.source_id(id).map(|source| json!({"id": id, "source_id": source}))
                    }).collect())
                }
                ("POST", "/api/resources/upload") => self.media.begin_upload(payload()?["size"].as_u64().unwrap_or(0))?,
                ("POST", "/api/resources/chunk") => {
                    let offset = request.get("offset").parse().map_err(|_| ApiError::bad("无效分块位置"))?;
                    self.media.append(request.get("id"), offset, &request.body)?;
                    json!({})
                }
                ("POST", "/api/resources/finish") => { self.media.finish_upload(request.get("id"))?; json!({}) }
                ("POST", "/api/resources/cancel") => { self.media.cancel_upload(request.get("id"))?; json!({}) }
                _ => return Err(ApiError::NotFound),
            };
            return Ok(json!({"success": true, "data": data}));
        }
        let s = &self.store;
        let config = s.memory_config();
        match (request.method.as_str(), request.path.as_str()) {
            ("GET", "/api/health") => Ok(json!({"success": true, "status": "ok"})),
            ("GET", "/api/config") => Ok(json!({
                "success": true, "anki_available": true,
                "anki_path": self.remote().map(|r| r.label()),
                "deck_name": "Word Atlas", "total_learned": s.learned_count(),
                "default_limit": FREE_PRACTICE_LIMIT, "max_limit": MAX_LIMIT,
                "easy_seconds": config.easy_seconds, "hard_seconds": config.hard_seconds,
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
            ("GET", "/api/memory/optimization") => Ok(json!({"success": true, "data": s.optimization_status(&self.optimization)?})),
            ("GET", "/api/memory/optimization/runs") => {
                let before_id = request.strict("before_id", 0, "无效的记录游标")?;
                if before_id < 0 {
                    return Err(ApiError::bad("无效的记录游标"));
                }
                Ok(json!({"success": true, "data": s.optimization_history(before_id, request.int("limit", 20))?}))
            }
            ("GET", "/api/stats/overview") => Ok(json!({"success": true, "data": s.overview()?})),
            ("GET", "/api/stats/calendar") => Ok(json!({"success": true, "data": s.activity_calendar()?})),
            ("GET", "/api/stats/calendar-words") => Ok(json!({"success": true, "data": s.calendar_words(request.get("date"))?})),
            ("GET", "/api/stats/recent-activity") => Ok(json!({"success": true, "data": s.recent_activity()?})),
            ("GET", "/api/stats/vocabulary-progress") => Ok(json!({"success": true, "data": s.vocabulary_progress()?})),
            ("GET", "/api/stats/vocabulary-words") => {
                let offset = request.strict("offset", 0, "无效的分页参数")?;
                let limit = request.strict("limit", 100, "无效的分页参数")?;
                if offset < 0 || !(1..=200).contains(&limit) {
                    return Err(ApiError::bad("无效的分页参数"));
                }
                let status = request.query.get("status").map_or("all", String::as_str);
                let data = s.vocabulary_words(request.get("dimension"), request.get("value"), status, offset as usize, limit as usize)?;
                Ok(json!({"success": true, "data": data}))
            }
            ("GET", "/api/stats/word-errors") => {
                let before_id = request.strict("before_id", 0, "无效的分页参数")?;
                let limit = request.strict("limit", 50, "无效的分页参数")?;
                if before_id < 0 || !(1..=200).contains(&limit) {
                    return Err(ApiError::bad("无效的分页参数"));
                }
                Ok(json!({"success": true, "data": s.word_errors(request.get("source_id"), before_id, limit as usize)?}))
            }
            ("GET", "/api/settings/server") => Ok(json!({"success": true, "data": self.server_settings()})),
            ("POST", "/api/settings/server") => {
                let payload: Value = serde_json::from_slice(&request.body).unwrap_or(Value::Null);
                Ok(json!({"success": true, "data": self.save_server_settings(&payload)?}))
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
        let remote = self.remote();
        status["sync_configured"] = remote.is_some().into();
        status["target_path"] = remote.map(|r| r.label()).into();
        status["history"] = self.store.sync_history(50)?.into();
        if status.get("last_sync_at").is_none() {
            let last = self.store.last_sync_at()?.map(Value::from);
            status["last_sync_at"] = last.unwrap_or_else(|| status["history"].get(0).map_or(Value::Null, |h| h["synced_at"].clone()));
        }
        Ok(status)
    }

    /// Full log sync with the configured server (set on first launch).
    fn sync_now(&self) -> ApiResult<Value> {
        let remote = self.remote().ok_or_else(|| ApiError::bad("尚未设置同步服务器"))?;
        let result = sync_all(&self.store, remote.as_ref())?;
        Ok(json!({"success": true, "data": self.sync_status(Some(result))?}))
    }
}
