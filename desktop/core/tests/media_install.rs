mod common;

use std::io::Write;
use std::sync::Arc;

use cijian_core::api::{App, AppConfig, Request};
use cijian_core::media_install::MediaManager;
use serde_json::{json, Value};

fn package(image: &[u8]) -> Vec<u8> {
    versioned(image, json!("2026.11.19"))
}

/// A one-word package whose manifest carries `version` (`null` for a pre-versioning package).
fn versioned(image: &[u8], version: Value) -> Vec<u8> {
    let mut archive = zip::ZipWriter::new(std::io::Cursor::new(Vec::new()));
    let mut manifest = json!({"format": 1, "words": {"library": {"illustration": {
        "file": "wa_library_img.webp"}}}});
    if !version.is_null() {
        manifest["version"] = version;
    }
    for (name, body) in [
        ("manifest.json", manifest.to_string().into_bytes()),
        ("CONTENT_LICENSE.md", b"CC BY 4.0".to_vec()),
        ("ATTRIBUTION.txt", b"Word Atlas contributors".to_vec()),
        ("wa_library_img.webp", image.to_vec()),
    ] {
        archive
            .start_file(name, zip::write::SimpleFileOptions::default())
            .unwrap();
        archive.write_all(&body).unwrap();
    }
    archive.finish().unwrap().into_inner()
}

fn upload(manager: &Arc<MediaManager>, bytes: &[u8]) -> cijian_core::error::ApiResult<()> {
    let session = manager.begin_upload(bytes.len() as u64).unwrap();
    let id = session["id"].as_str().unwrap();
    for (i, chunk) in bytes.chunks(113).enumerate() {
        manager.append(id, (i * 113) as u64, chunk).unwrap();
    }
    manager.finish_upload(id)
}

#[test]
fn importing_switches_live_and_persists_while_bad_replacement_keeps_previous_package() {
    let dir = tempfile::tempdir().unwrap();
    let manager = MediaManager::new(Some(dir.path()));
    assert_eq!(manager.status()["installed"], false);
    upload(&manager, &package(b"first")).unwrap();
    assert_eq!(manager.status()["phase"], "ready");
    assert_eq!(
        manager.current().read("library", "illustration").unwrap().1,
        b"first"
    );
    let old = manager.current(); // in-flight readers may keep the old ZIP open on Windows.
    upload(&manager, &package(b"second")).unwrap();
    assert_eq!(manager.status()["phase"], "ready");
    assert_eq!(old.read("library", "illustration").unwrap().1, b"first");
    assert_eq!(
        manager.current().read("library", "illustration").unwrap().1,
        b"second"
    );
    for bytes in [b"not zip".to_vec(), b"PK incomplete archive".to_vec()] {
        assert!(upload(&manager, &bytes).is_err());
        let status = manager.status();
        assert_eq!(status["phase"], "error");
        assert_eq!(status["installed"], true);
        assert!(!status["error"].as_str().unwrap().is_empty());
        assert_eq!(
            manager.current().read("library", "illustration").unwrap().1,
            b"second"
        );
    }
    let reopened = MediaManager::new(Some(dir.path()));
    assert_eq!(
        reopened
            .current()
            .read("library", "illustration")
            .unwrap()
            .1,
        b"second"
    );
}

#[test]
fn upload_requires_order_and_full_size_and_can_be_cancelled_or_retried() {
    let dir = tempfile::tempdir().unwrap();
    let manager = MediaManager::new(Some(dir.path()));
    assert!(manager.begin_upload(0).is_err());
    let session = manager.begin_upload(10).unwrap();
    let id = session["id"].as_str().unwrap();
    assert!(manager.begin_upload(1).is_err());
    assert!(manager.append("wrong", 0, b"abc").is_err());
    assert!(manager.append(id, 1, b"abc").is_err());
    manager.append(id, 0, b"abc").unwrap();
    assert!(manager.finish_upload(id).is_err());
    manager.cancel_upload(id).unwrap();
    assert!(!std::fs::read_dir(dir.path()).unwrap().any(|p| p
        .unwrap()
        .path()
        .extension()
        .is_some_and(|s| s == "part")));
    upload(&manager, &package(b"retry")).unwrap();
    assert_eq!(manager.status()["phase"], "ready");
}

#[test]
fn resource_api_keeps_queue_attempts_and_updates_media_urls_after_import() {
    let env = common::Env::new(
        common::at(2026, 11, 3, 1, 0, 0),
        vec![common::word("library", 41, true)],
    );
    let dir = tempfile::tempdir().unwrap();
    let app = App::new(
        env.reopen(),
        AppConfig {
            dist_dir: dir.path().into(),
            media_dir: Some(dir.path().join("media")),
            server_file: None,
        },
        Default::default(),
    );
    assert_eq!(
        app.handle(&Request::new("POST", "/api/resources/download", vec![]))
            .status,
        404
    );
    let call = |method: &str, path: &str, body: Vec<u8>| {
        let response = app.handle(&Request::new(method, path, body));
        assert_eq!(
            response.status,
            200,
            "{}",
            String::from_utf8_lossy(&response.body)
        );
        serde_json::from_slice::<Value>(&response.body).unwrap()["data"].clone()
    };
    let queue = call(
        "GET",
        "/api/practice/queue?session_id=media&limit=1",
        vec![],
    );
    assert_eq!(queue["items"][0]["illustration_url"], "");
    let bytes = package(b"api image");
    let id = call(
        "POST",
        "/api/resources/upload",
        json!({"size": bytes.len()}).to_string().into_bytes(),
    )["id"]
        .as_str()
        .unwrap()
        .to_string();
    call(
        "POST",
        &format!("/api/resources/chunk?id={id}&offset=0"),
        bytes,
    );
    call("POST", &format!("/api/resources/finish?id={id}"), vec![]);
    assert_eq!(
        call("GET", "/api/resources/status", vec![])["phase"],
        "ready"
    );
    let urls = call(
        "POST",
        "/api/resources/urls",
        json!({"ids": [41]}).to_string().into_bytes(),
    );
    assert!(urls[0]["illustration_url"]
        .as_str()
        .unwrap()
        .starts_with("/api/media/source/library/illustration"));
    assert_eq!(
        app.handle(&Request::new("GET", "/api/media/41/illustration", vec![]))
            .body,
        b"api image"
    );
    // Resource management does not reissue or expire the question currently being answered.
    let result = app.store.submit(&json!({"attempt_id": queue["items"][0]["attempt_id"], "session_id": "media", "user_input": "library", "duration_ms": 1000, "reviewed_at": "2026-11-03T01:00:01Z"}));
    assert!(result.is_ok(), "{result:?}");
}

#[test]
fn damaged_install_record_does_not_prevent_text_practice() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("active.json"), "\"../outside.zip\"").unwrap();
    let manager = MediaManager::new(Some(dir.path()));
    assert_eq!(manager.status()["installed"], false);
    assert!(!manager.status()["error"].as_str().unwrap().is_empty());
    upload(&manager, &package(b"repaired")).unwrap();
    assert_eq!(manager.status()["phase"], "ready");
}

#[test]
fn accepts_resource_packages_with_extra_personal_notes() {
    let dir = tempfile::tempdir().unwrap();
    let manager = MediaManager::new(Some(dir.path()));
    let mut archive = zip::ZipWriter::new_append(std::io::Cursor::new(package(b"image"))).unwrap();
    archive
        .start_file("README.txt", zip::write::SimpleFileOptions::default())
        .unwrap();
    archive.write_all(b"my resource notes").unwrap();
    upload(&manager, &archive.finish().unwrap().into_inner()).unwrap();
    assert_eq!(manager.status()["phase"], "ready");
    assert_eq!(
        manager.current().read("library", "illustration").unwrap().1,
        b"image"
    );
}

#[test]
fn imports_need_a_version_no_older_than_the_installed_package() {
    let dir = tempfile::tempdir().unwrap();
    let manager = MediaManager::new(Some(dir.path()));
    let image = |m: &Arc<MediaManager>| m.current().read("library", "illustration").unwrap().1;
    let error = upload(&manager, &versioned(b"legacy", Value::Null)).unwrap_err().to_string();
    assert!(error.contains("缺少版本号"), "{error}");
    assert_eq!(manager.status()["installed"], false);
    assert!(upload(&manager, &versioned(b"bad", json!("2026-11-19"))).is_err(), "only dotted numbers are versions");

    upload(&manager, &versioned(b"november", json!("2026.11.19"))).unwrap();
    assert_eq!(manager.status()["version"], "2026.11.19");
    let error = upload(&manager, &versioned(b"october", json!("2026.10.30"))).unwrap_err().to_string();
    assert!(error.contains("低于已安装的 2026.11.19"), "{error}");
    assert_eq!(manager.status()["phase"], "error");
    assert_eq!(image(&manager), b"november", "the installed package stays active");
    assert_eq!(std::fs::read_dir(dir.path()).unwrap().filter(|e| e.as_ref().unwrap().path().extension().is_some_and(|x| x == "zip")).count(), 1,
               "the rejected ZIP is removed");

    upload(&manager, &versioned(b"rebuilt", json!("2026.11.19"))).unwrap();
    assert_eq!(image(&manager), b"rebuilt", "the same version can be reinstalled");
    upload(&manager, &versioned(b"second build", json!("2026.11.19.2"))).unwrap();
    upload(&manager, &versioned(b"december", json!("2026.12.1"))).unwrap();
    assert_eq!(MediaManager::new(Some(dir.path())).status()["version"], "2026.12.1", "the version survives a restart");
}

#[test]
fn a_package_installed_before_versioning_keeps_working_until_replaced() {
    let dir = tempfile::tempdir().unwrap();
    // Write the install record directly, as an older app did, since imports now need a version.
    std::fs::write(dir.path().join("old.zip"), versioned(b"legacy", Value::Null)).unwrap();
    std::fs::write(dir.path().join("active.json"), "\"old.zip\"").unwrap();
    let manager = MediaManager::new(Some(dir.path()));
    let status = manager.status();
    assert_eq!((status["installed"].clone(), status["version"].clone()), (json!(true), Value::Null));
    assert_eq!(manager.current().read("library", "illustration").unwrap().1, b"legacy");
    upload(&manager, &versioned(b"any", json!("2026.1.1"))).unwrap();
    assert_eq!(manager.status()["version"], "2026.1.1");
    assert!(!dir.path().join("old.zip").exists());
}
