//! 词间桌面壳：`cijian://` 自定义协议把页面和 `/api/*` 请求交给 `cijian-core`。
//!
//! 现有前端按 `location.origin + "/api"` 调用接口，因此无需改动 JS。
//! 页面与脚本来自内嵌的 `dist/`；接口、插图与音频由本地 SQLite 与媒体清单提供。
//! 后台线程每天检查一次是否需要优化 FSRS 参数（见 `cijian_core::optimize`）；
//! 配置了同步服务器时，启动后及每隔一段时间自动同步作答日志（见 `cijian_core::remote`）；
//! 未配置时页面在首次启动时要求填写服务器地址与访问令牌（保存到数据目录的 `server.json`）。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod desktop;

use std::path::PathBuf;
use std::sync::Arc;

use cijian_core::api::{App, AppConfig, Request, ServerSource};
use cijian_core::optimize::{evaluate_with_fsrs_rs, OptimizationConfig};
use cijian_core::remote::{sync_all, ServerConfig};
use cijian_core::srs::MemoryConfig;
use cijian_core::store::Store;
use tauri::http::{header::CONTENT_TYPE, Response};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

const SCHEME: &str = "cijian";

fn env_path(name: &str) -> Option<PathBuf> {
    std::env::var_os(name).filter(|v| !v.is_empty()).map(PathBuf::from)
}

fn open_app(handle: &tauri::AppHandle) -> Result<App, Box<dyn std::error::Error>> {
    // CIJIAN_DATA_DIR moves the database and server.json together (development, testing).
    let data_dir = match env_path("CIJIAN_DATA_DIR") {
        Some(dir) => dir,
        None => handle.path().app_data_dir()?,
    };
    std::fs::create_dir_all(&data_dir)?;
    let db_path = env_path("CIJIAN_DB_PATH").unwrap_or_else(|| data_dir.join("cijian.db"));
    let store = Store::open(&db_path, MemoryConfig::default(), Box::new(chrono::Utc::now))?;
    let config = AppConfig {
        dist_dir: PathBuf::new(),
        media_dir: Some(env_path("CIJIAN_MEDIA_DIR").unwrap_or_else(|| data_dir.join("media"))),
        server_file: Some(data_dir.join("server.json")),
    };
    let optimization = OptimizationConfig {
        enabled: std::env::var("CIJIAN_OPTIMIZATION").map_or(true, |v| v != "0"),
        ..OptimizationConfig::default()
    };
    let server_file = config.server_file.clone().unwrap_or_default();
    let app = App::new(store, config, optimization);
    // Environment variables win; otherwise the file saved by the first-run dialog.
    let from_env = std::env::var("CIJIAN_SERVER_URL").ok().filter(|v| !v.trim().is_empty());
    if let Some(url) = from_env {
        let server = ServerConfig::new(&url, &std::env::var("CIJIAN_SERVER_TOKEN").unwrap_or_default())?;
        app.set_server(server, ServerSource::Environment);
    } else {
        match ServerConfig::load(&server_file) {
            Ok(Some(server)) => app.set_server(server, ServerSource::File),
            Ok(None) => {}
            // A damaged file is reported and the setup dialog asks again.
            Err(error) => eprintln!("cijian: ignoring server settings: {error}"),
        }
    }
    eprintln!("cijian: db={} media={:?} server={}", db_path.display(), app.config.media_dir,
              app.remote().map_or("none".into(), |r| r.label()));
    Ok(app)
}

/// Checks at startup and then every `check_interval_seconds`; training runs on this
/// thread so practice requests are never blocked by it.
fn start_optimizer(app: Arc<App>) {
    if !app.optimization.enabled {
        return;
    }
    let spawned = std::thread::Builder::new().name("fsrs-optimizer".into()).spawn(move || loop {
        match app.store.check_optimization(&app.optimization, &evaluate_with_fsrs_rs) {
            Ok(Some(run)) => eprintln!("cijian: FSRS evaluation {} {}", run["id"], run["status"]),
            Ok(None) => {}
            Err(error) => eprintln!("cijian: FSRS evaluation check failed: {error}"),
        }
        std::thread::sleep(std::time::Duration::from_secs(app.optimization.check_interval_seconds));
    });
    if let Err(error) = spawned {
        eprintln!("cijian: could not start the optimizer: {error}");
    }
}

/// Syncs at startup and then every `CIJIAN_SYNC_MINUTES` (default 10) while a server
/// is configured. Failures, e.g. while offline, are only logged; practice keeps working.
fn start_sync(app: Arc<App>) {
    let minutes = std::env::var("CIJIAN_SYNC_MINUTES").ok().and_then(|v| v.parse::<u64>().ok()).filter(|m| *m > 0).unwrap_or(10);
    let spawned = std::thread::Builder::new().name("log-sync".into()).spawn(move || loop {
        if let Some(remote) = app.remote() {
            match sync_all(&app.store, remote.as_ref()) {
                Ok(status) => eprintln!("cijian: {}", status["message"].as_str().unwrap_or_default()),
                Err(error) => eprintln!("cijian: sync skipped: {error}"),
            }
        }
        std::thread::sleep(std::time::Duration::from_secs(minutes * 60));
    });
    if let Err(error) = spawned {
        eprintln!("cijian: could not start sync: {error}");
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![desktop::get_close_to_tray, desktop::set_close_to_tray])
        .on_window_event(desktop::on_window_event)
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
            let state = Arc::new(open_app(app.handle())?);
            let settings_path = state.config.server_file.as_ref().unwrap().with_file_name("desktop.json");
            app.manage(desktop::DesktopSettings::load(settings_path));
            start_optimizer(state.clone());
            start_sync(state.clone());
            app.manage(state);
            // Windows WebView2 maps custom schemes to http://<scheme>.localhost.
            let url = if cfg!(windows) { "http://cijian.localhost/" } else { "cijian://localhost/" };
            let mut window = WebviewWindowBuilder::new(app, "main", WebviewUrl::CustomProtocol(url.parse()?))
                .title("词间")
                .decorations(false)
                .inner_size(1100.0, 780.0)
                .min_inner_size(760.0, 560.0);
            // Tauri passes its own WebView2 arguments, which replace WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS;
            // repeat Tauri's defaults and add the debugging port for scripts/cdp.mjs.
            if let Some(port) = std::env::var("CIJIAN_DEVTOOLS_PORT").ok().filter(|v| v.parse::<u16>().is_ok()) {
                window = window.additional_browser_args(&format!(
                    "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection --autoplay-policy=no-user-gesture-required --remote-debugging-port={port}"
                ));
            }
            window.build()?;
            desktop::setup(app.handle())?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running 词间");
}
