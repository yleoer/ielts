//! Sync server client: vocabulary snapshot and the shared answer log.
//!
//! The server (`typing-practice/backend`) only stores answers; every device
//! replays the merged log with FSRS (see [`crate::sync`]).

use std::path::Path;
use std::time::Duration;

use serde_json::{json, Value};

use crate::error::{ApiError, ApiResult};
use crate::store::Store;

/// Answers per upload request; the server accepts at most 500.
pub const UPLOAD_BATCH: usize = 500;

#[derive(Clone, Debug, PartialEq)]
pub struct ServerConfig {
    /// Base URL such as `https://example.com`; `/api/...` is appended.
    pub url: String,
    pub token: String,
}

impl ServerConfig {
    /// Trims and checks user input; the URL must be http(s) without spaces.
    pub fn new(url: &str, token: &str) -> Result<Self, String> {
        let url = url.trim().trim_end_matches('/').to_string();
        let token = token.trim().to_string();
        let host = url.strip_prefix("https://").or_else(|| url.strip_prefix("http://")).unwrap_or_default();
        if host.is_empty() || url.chars().any(char::is_whitespace) {
            return Err("服务器地址必须以 http:// 或 https:// 开头，例如 https://example.com".into());
        }
        if token.is_empty() || token.len() > 500 {
            return Err("请填写访问令牌".into());
        }
        Ok(ServerConfig { url, token })
    }

    /// Reads `server.json` (`{"url": ..., "token": ...}`); a missing file means not configured.
    pub fn load(path: &Path) -> Result<Option<Self>, String> {
        if !path.is_file() {
            return Ok(None);
        }
        let text = std::fs::read_to_string(path).map_err(|e| format!("无法读取 {}：{e}", path.display()))?;
        let value: Value = serde_json::from_str(&text).map_err(|e| format!("{} 不是有效 JSON：{e}", path.display()))?;
        let field = |k: &str| value[k].as_str().unwrap_or_default().to_string();
        Self::new(&field("url"), &field("token")).map(Some).map_err(|e| format!("{}：{e}", path.display()))
    }

    /// Writes `server.json` atomically.
    pub fn save(&self, path: &Path) -> Result<(), String> {
        let failed = |e: std::io::Error| format!("无法保存服务器设置：{e}");
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir).map_err(failed)?;
        }
        let temporary = path.with_extension("json.tmp");
        let text = serde_json::to_string_pretty(&json!({"url": self.url, "token": self.token})).unwrap();
        std::fs::write(&temporary, text).map_err(failed)?;
        std::fs::rename(&temporary, path).map_err(failed)
    }
}

/// The two server calls, abstracted so tests can use an in-memory server.
pub trait Remote: Send + Sync {
    fn vocab(&self) -> Result<Value, String>;
    fn sync(&self, request: &Value) -> Result<Value, String>;
    /// Shown in the sync dialog.
    fn label(&self) -> String {
        "同步服务器".into()
    }
    /// Confirms the address and token before they are saved.
    fn check(&self) -> Result<(), String> {
        match self.vocab()?.get("format").and_then(Value::as_i64) {
            Some(1) => Ok(()),
            _ => Err("该地址不是词间同步服务器".into()),
        }
    }
}

pub struct HttpRemote {
    config: ServerConfig,
    agent: ureq::Agent,
}

impl HttpRemote {
    pub fn new(config: ServerConfig) -> Self {
        let agent = ureq::Agent::config_builder()
            .timeout_global(Some(Duration::from_secs(60)))
            .http_status_as_error(false)
            .build()
            .into();
        HttpRemote { config, agent }
    }

    fn url(&self, path: &str) -> String {
        format!("{}{path}", self.config.url)
    }

    fn read(&self, response: Result<ureq::http::Response<ureq::Body>, ureq::Error>) -> Result<Value, String> {
        let mut response = response.map_err(|e| format!("无法连接同步服务器：{e}"))?;
        let status = response.status().as_u16();
        let body: Value = response.body_mut().with_config().limit(64 * 1024 * 1024).read_json()
            .map_err(|e| format!("同步服务器返回了无效数据（HTTP {status}）：{e}"))?;
        match status {
            200 if body["success"] == true => Ok(body["data"].clone()),
            401 => Err("访问令牌无效，请检查同步设置".into()),
            _ => Err(body["error"].as_str().map_or_else(|| format!("同步服务器错误（HTTP {status}）"), String::from)),
        }
    }
}

impl Remote for HttpRemote {
    fn label(&self) -> String {
        self.config.url.clone()
    }

    fn vocab(&self) -> Result<Value, String> {
        let auth = format!("Bearer {}", self.config.token);
        self.read(self.agent.get(&self.url("/api/vocab")).header("Authorization", &auth).call())
    }

    fn sync(&self, request: &Value) -> Result<Value, String> {
        let auth = format!("Bearer {}", self.config.token);
        self.read(self.agent.post(&self.url("/api/sync")).header("Authorization", &auth).send_json(request))
    }
}

/// Full sync: refresh the vocabulary, upload unsent answers, merge the server log.
/// Network calls run without holding the store lock, so practice continues.
pub fn sync_all(store: &Store, remote: &dyn Remote) -> ApiResult<Value> {
    let failed = |e: String| ApiError::BadRequest(e);
    // Manual and background syncs must not interleave their cursor updates.
    let _running = store.sync_running.try_lock().map_err(|_| failed("正在同步，请稍候".into()))?;
    let snapshot = remote.vocab().map_err(failed)?;
    store.import_server_vocabulary(&snapshot)?;
    let device_id = store.device_id()?;
    let mut cursor = store.sync_cursor()?;
    let (mut uploaded, mut merged) = (0, 0);
    // Each round either uploads pending answers or advances the cursor, so it ends.
    loop {
        let pending = store.pending_uploads(UPLOAD_BATCH)?;
        let response = remote.sync(&json!({"device_id": device_id, "cursor": cursor, "attempts": pending})).map_err(failed)?;
        let attempts = response["attempts"].as_array().map_or(&[][..], Vec::as_slice);
        let next = response["next_cursor"].as_i64().filter(|n| *n >= cursor)
            .ok_or_else(|| failed("同步服务器返回了无效的游标".into()))?;
        merged += store.merge_remote(&pending, attempts, next)?;
        uploaded += pending.len();
        cursor = next;
        if pending.is_empty() && response["more"] != true {
            break;
        }
    }
    let message = format!("词库已更新；上传 {uploaded} 条作答，合并其他设备 {merged} 条");
    Ok(json!({"success": true, "message": message,
              "uploaded_attempts": uploaded, "merged_attempts": merged}))
}
