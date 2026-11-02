//! 词间桌面壳：`cijian://` 自定义协议把页面和 `/api/*` 请求交给 `cijian-core`。
//!
//! 现有前端按 `location.origin + "/api"` 调用接口，因此无需改动 JS。
//! 页面与脚本来自内嵌的 `dist/`；接口、插图由本地 SQLite 与媒体目录提供。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::Arc;

use cijian_core::api::{App, AppConfig, Request};
use cijian_core::srs::MemoryConfig;
use cijian_core::store::Store;
use tauri::http::{header::CONTENT_TYPE, Response};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

const SCHEME: &str = "cijian";

fn env_path(name: &str) -> Option<PathBuf> {
    std::env::var_os(name).filter(|v| !v.is_empty()).map(PathBuf::from)
}

fn open_app(handle: &tauri::AppHandle) -> Result<App, Box<dyn std::error::Error>> {
    let data_dir = handle.path().app_data_dir()?;
    std::fs::create_dir_all(&data_dir)?;
    let db_path = env_path("CIJIAN_DB_PATH").unwrap_or_else(|| data_dir.join("cijian.db"));
    let store = Store::open(&db_path, MemoryConfig::default(), Box::new(chrono::Utc::now))?;
    let resource_media = handle.path().resource_dir().ok().map(|d| d.join("media")).filter(|d| d.is_dir());
    let config = AppConfig {
        dist_dir: PathBuf::new(),
        media_dir: env_path("CIJIAN_MEDIA_DIR").or(resource_media),
        vocab_path: env_path("CIJIAN_VOCAB_PATH").or_else(|| Some(data_dir.join("vocab.json"))),
    };
    eprintln!("cijian: db={} media={:?} vocab={:?}", db_path.display(), config.media_dir, config.vocab_path);
    Ok(App { store, config })
}

fn main() {
    tauri::Builder::default()
        .register_uri_scheme_protocol(SCHEME, |ctx, request| {
            let handle = ctx.app_handle();
            let uri = request.uri().to_string();
            let req = Request::new(request.method().as_str(), &uri, request.body().clone());
            let (status, content_type, body) = if req.path.starts_with("/api/") {
                let app = handle.state::<Arc<App>>();
                let r = app.handle(&req);
                (r.status, r.content_type, r.body)
            } else {
                // Static pages are embedded; unknown pages fall back to the practice page.
                let resolver = handle.asset_resolver();
                let path = match req.path.as_str() {
                    "/" => "/index.html",
                    p => p,
                };
                match resolver.get(path.to_string()).or_else(|| resolver.get("/index.html".into())) {
                    Some(asset) => (200, asset.mime_type, asset.bytes),
                    None => (404, "text/plain".into(), b"not found".to_vec()),
                }
            };
            Response::builder().status(status).header(CONTENT_TYPE, content_type).body(body).unwrap()
        })
        .setup(|app| {
            let state = open_app(app.handle())?;
            app.manage(Arc::new(state));
            // Windows WebView2 maps custom schemes to http://<scheme>.localhost.
            let url = if cfg!(windows) { "http://cijian.localhost/" } else { "cijian://localhost/" };
            WebviewWindowBuilder::new(app, "main", WebviewUrl::CustomProtocol(url.parse()?))
                .title("词间")
                .inner_size(1100.0, 780.0)
                .min_inner_size(420.0, 560.0)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running 词间");
}
