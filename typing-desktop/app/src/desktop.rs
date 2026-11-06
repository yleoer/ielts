//! Local window preferences and the system tray; these stay on this device.

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use chrono::{TimeDelta, Utc};
use serde_json::{json, Value};
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent};

use cijian_core::api::App;
use cijian_core::time::{parse_time, Time};

const TRAY_ID: &str = "main";

struct TrayState {
    original: Image<'static>,
    summary: Option<Value>,
    last_read: Instant,
    level: Option<u16>,
    tooltip: String,
}

pub struct DesktopSettings {
    path: PathBuf,
    close_to_tray: AtomicBool,
}

impl DesktopSettings {
    pub fn load(path: PathBuf) -> Self {
        let close_to_tray = match std::fs::read(&path) {
            Ok(bytes) => match serde_json::from_slice::<Value>(&bytes)
                .and_then(|v| serde_json::from_value::<bool>(v["close_to_tray"].clone()))
            {
                Ok(value) => value,
                Err(error) => {
                    eprintln!("cijian: ignoring desktop settings: {error}");
                    true
                }
            },
            Err(error) => {
                if error.kind() != std::io::ErrorKind::NotFound {
                    eprintln!("cijian: could not read desktop settings: {error}");
                }
                true
            }
        };
        Self {
            path,
            close_to_tray: AtomicBool::new(close_to_tray),
        }
    }

    fn save(&self, enabled: bool) -> Result<(), String> {
        std::fs::write(&self.path, json!({"close_to_tray": enabled}).to_string())
            .map_err(|error| format!("无法保存关闭设置：{error}"))?;
        self.close_to_tray.store(enabled, Ordering::Relaxed);
        Ok(())
    }
}

#[tauri::command]
pub fn get_close_to_tray(settings: State<'_, DesktopSettings>) -> bool {
    settings.close_to_tray.load(Ordering::Relaxed)
}

#[tauri::command]
pub fn set_close_to_tray(
    enabled: bool,
    settings: State<'_, DesktopSettings>,
) -> Result<(), String> {
    settings.save(enabled)
}

#[tauri::command]
pub fn get_autostart() -> Result<bool, String> {
    crate::autostart::is_enabled().map_err(|error| format!("无法读取开机自启动：{error}"))
}

#[tauri::command]
pub fn set_autostart(enabled: bool) -> Result<(), String> {
    crate::autostart::set_enabled(enabled).map_err(|error| format!("无法修改开机自启动：{error}"))
}

pub fn on_window_event(window: &tauri::Window, event: &WindowEvent) {
    if let WindowEvent::CloseRequested { api, .. } = event {
        if window.label() == "main"
            && window
                .state::<DesktopSettings>()
                .close_to_tray
                .load(Ordering::Relaxed)
        {
            api.prevent_close();
            if let Err(error) = window.emit("cijian-window-hidden", ()) {
                eprintln!("cijian: could not notify window hide: {error}");
            }
            if let Err(error) = window.hide() {
                eprintln!("cijian: could not hide window: {error}");
            }
        }
    }
}

fn show_window(handle: &AppHandle) {
    if let Some(window) = handle.get_webview_window("main") {
        if let Err(error) = window
            .show()
            .and_then(|_| window.unminimize())
            .and_then(|_| window.set_focus())
        {
            eprintln!("cijian: could not restore window: {error}");
        } else if let Err(error) = window.emit("cijian-window-shown", ()) {
            eprintln!("cijian: could not notify window restore: {error}");
        }
    }
}

fn tooltip(summary: &Value, now: Time) -> Result<String, String> {
    let due = summary["due_count"].as_u64().unwrap_or(0);
    let message = if due > 0 {
        format!("有 {due} 个单词待复习")
    } else if let Some(next) = summary["next_due"].as_str() {
        let remaining = parse_time(next)? - now;
        if remaining <= TimeDelta::zero() {
            "已有单词到期，可以复习了".into()
        } else if remaining < TimeDelta::minutes(1) {
            "距下次复习不足 1 分钟".into()
        } else {
            let minutes = (remaining.num_milliseconds() + 59999) / 60000;
            let days = minutes / 1440;
            let hours = minutes % 1440 / 60;
            let minutes = minutes % 60;
            let mut parts = Vec::new();
            if days > 0 {
                parts.push(format!("{days} 天"));
            }
            if hours > 0 {
                parts.push(format!("{hours} 小时"));
            }
            if minutes > 0 {
                parts.push(format!("{minutes} 分钟"));
            }
            format!("距下次复习 {}", parts.join(" "))
        }
    } else {
        let fresh = summary["new_available"].as_u64().unwrap_or(0);
        if fresh > 0 {
            format!("暂无待复习单词，可学 {fresh} 个新词")
        } else {
            "暂无复习计划".into()
        }
    };
    Ok(format!("词间\n{message}"))
}

// Serialize cache updates and native setters on the main thread. In particular,
// never hold this mutex on a worker while waiting for a native tray operation.
fn update_tray(handle: &AppHandle, reload: bool) {
    let state = handle.state::<Mutex<TrayState>>();
    let mut state = state.lock().unwrap();
    if reload || state.last_read.elapsed() >= Duration::from_secs(30) {
        state.summary = match handle.state::<Arc<App>>().store.summary() {
            Ok(summary) => Some(summary),
            Err(error) => {
                eprintln!("cijian: could not read tray review time: {error}");
                None
            }
        };
        state.last_read = Instant::now();
    }
    let now = Utc::now();
    let presentation = state.summary.as_ref().map(|summary| {
        tooltip(summary, now)
            .and_then(|text| crate::tray_indicator::level(summary, now).map(|level| (text, level)))
    });
    let (text, level) = match presentation {
        Some(Ok(value)) => value,
        _ => ("词间\n暂时无法读取复习时间".into(), 0),
    };
    if let Some(tray) = handle.tray_by_id(TRAY_ID) {
        if state.level != Some(level) {
            let original = &state.original;
            let icon = Image::new_owned(
                crate::tray_indicator::render(
                    original.rgba(),
                    original.width(),
                    original.height(),
                    level,
                ),
                original.width(),
                original.height(),
            );
            match tray.set_icon(Some(icon)) {
                Ok(()) => state.level = Some(level),
                Err(error) => eprintln!("cijian: could not update tray icon: {error}"),
            }
        }
        if state.tooltip != text {
            match tray.set_tooltip(Some(&text)) {
                Ok(()) => state.tooltip = text,
                Err(error) => eprintln!("cijian: could not update tray tooltip: {error}"),
            }
        }
    }
}

pub fn refresh(handle: &AppHandle) {
    schedule_update(handle, true);
}

fn schedule_update(handle: &AppHandle, reload: bool) {
    let owned = handle.clone();
    if let Err(error) = handle.run_on_main_thread(move || update_tray(&owned, reload)) {
        eprintln!("cijian: could not schedule tray update: {error}");
    }
}

pub fn setup(handle: &AppHandle) -> tauri::Result<()> {
    let icon = handle
        .default_window_icon()
        .expect("bundled application icon");
    let original = Image::new_owned(icon.rgba().to_vec(), icon.width(), icon.height());
    handle.manage(Mutex::new(TrayState {
        original: original.clone(),
        summary: None,
        last_read: Instant::now(),
        level: None,
        tooltip: String::new(),
    }));
    let open = MenuItem::with_id(handle, "open", "打开词间", true, None::<&str>)?;
    let quit = MenuItem::with_id(handle, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(handle, &[&open, &quit])?;
    TrayIconBuilder::with_id(TRAY_ID)
        .icon(original)
        .tooltip("词间")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|handle, event| match event.id.as_ref() {
            "open" => show_window(handle),
            "quit" => handle.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| match event {
            TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } => show_window(tray.app_handle()),
            TrayIconEvent::Enter { .. } => refresh(tray.app_handle()),
            _ => {}
        })
        .build(handle)?;
    update_tray(handle, true);
    let handle = handle.clone();
    std::thread::Builder::new()
        .name("tray-review-time".into())
        .spawn(move || loop {
            std::thread::sleep(Duration::from_secs(1));
            schedule_update(&handle, false);
        })?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use cijian_core::time::time_text;

    #[test]
    fn close_preference_defaults_to_tray_and_survives_restart() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("desktop.json");
        let settings = DesktopSettings::load(path.clone());
        assert!(settings.close_to_tray.load(Ordering::Relaxed));
        settings.save(false).unwrap();
        assert!(!DesktopSettings::load(path.clone())
            .close_to_tray
            .load(Ordering::Relaxed));
        settings.save(true).unwrap();
        assert!(DesktopSettings::load(path)
            .close_to_tray
            .load(Ordering::Relaxed));
    }

    #[test]
    fn failed_save_keeps_the_active_close_preference() {
        let dir = tempfile::tempdir().unwrap();
        let settings = DesktopSettings::load(dir.path().join("missing/desktop.json"));
        assert!(settings.save(false).is_err());
        assert!(settings.close_to_tray.load(Ordering::Relaxed));
    }

    #[test]
    fn tooltip_counts_down_and_becomes_due_at_the_deadline() {
        let now = parse_time("2026-11-04T00:00:00Z").unwrap();
        for (seconds, expected) in [
            (30, "不足 1 分钟"),
            (61, "2 分钟"),
            (3600, "1 小时"),
            (93780, "1 天 2 小时 3 分钟"),
        ] {
            let summary =
                json!({"due_count": 0, "next_due": time_text(now + TimeDelta::seconds(seconds))});
            assert_eq!(
                tooltip(&summary, now).unwrap(),
                format!(
                    "词间\n距下次复习{space}{expected}",
                    space = if seconds < 60 { "" } else { " " }
                )
            );
        }
        let summary = json!({"due_count": 0, "next_due": time_text(now)});
        assert_eq!(
            tooltip(&summary, now).unwrap(),
            "词间\n已有单词到期，可以复习了"
        );
    }

    #[test]
    fn tooltip_distinguishes_due_new_and_empty_plans() {
        let now = Utc::now();
        assert_eq!(
            tooltip(&json!({"due_count": 3, "new_available": 5}), now).unwrap(),
            "词间\n有 3 个单词待复习"
        );
        assert_eq!(
            tooltip(&json!({"due_count": 0, "new_available": 5}), now).unwrap(),
            "词间\n暂无待复习单词，可学 5 个新词"
        );
        assert_eq!(
            tooltip(&json!({"due_count": 0, "new_available": 0}), now).unwrap(),
            "词间\n暂无复习计划"
        );
    }
}
