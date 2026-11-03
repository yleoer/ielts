use std::io::Write;
use std::path::PathBuf;

use cijian_core::api::{App, AppConfig, Request, Response};
use cijian_core::store::Store;
use cijian_core::vocab::parse_snapshot;
use serde_json::{json, Value};

struct Bundle {
    dir: tempfile::TempDir,
    manifest: Value,
    files: Vec<(String, Vec<u8>)>,
}

impl Bundle {
    fn new() -> Self {
        Self {
            dir: tempfile::tempdir().unwrap(),
            manifest: json!({"format": 1, "words": {"library": {}}}),
            files: vec![],
        }
    }

    fn asset(&mut self, kind: &str, name: &str, body: &[u8]) {
        self.files.retain(|(file, _)| file != name);
        self.files.push((name.into(), body.into()));
        self.manifest["words"]["library"][kind] = json!({"file": name});
    }

    fn write(&self) {
        let name = format!("{}.zip", uuid::Uuid::new_v4());
        let mut archive =
            zip::ZipWriter::new(std::fs::File::create(self.dir.path().join(&name)).unwrap());
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);
        archive.start_file("manifest.json", options).unwrap();
        archive
            .write_all(self.manifest.to_string().as_bytes())
            .unwrap();
        for (file, body) in &self.files {
            archive.start_file(file, options).unwrap();
            archive.write_all(body).unwrap();
        }
        archive.finish().unwrap();
        std::fs::write(
            self.dir.path().join("active.json"),
            serde_json::to_vec(&name).unwrap(),
        )
        .unwrap();
    }

    fn app(&self) -> App {
        self.write();
        let store = Store::with_connection(
            rusqlite::Connection::open_in_memory().unwrap(),
            Default::default(),
            Box::new(chrono::Utc::now),
        )
        .unwrap();
        store.import_vocabulary(words(41, "library")).unwrap();
        App::new(
            store,
            AppConfig {
                dist_dir: PathBuf::new(),
                media_dir: Some(self.dir.path().into()),
                server_file: None,
            },
            Default::default(),
        )
    }
}

fn words(id: i64, source: &str) -> Vec<cijian_core::vocab::Word> {
    parse_snapshot(&json!({"format": 1, "words": [{"id": id, "source_id": source, "word": "library",
        "chinese_meaning": "图书馆", "part_of_speech": "n.", "category": "教育", "learned": true,
        "illustration_file": "unrelated_server_filename.webp", "illustration_url": "https://server/image",
        "audio_url": "https://server/audio", "audio_urls": {"uk": "https://server/uk"}}]}).to_string()).unwrap()
}

fn get(app: &App, path: &str) -> Response {
    app.handle(&Request::new("GET", path, vec![]))
}

fn queue(app: &App) -> Value {
    let response = get(app, "/api/practice/queue?session_id=test&limit=1");
    assert_eq!(response.status, 200);
    serde_json::from_slice::<Value>(&response.body).unwrap()["data"]["items"][0].clone()
}

#[test]
fn serves_package_variants_by_source_id_without_server_filenames() {
    let mut bundle = Bundle::new();
    bundle.asset("illustration", "wa_library_img.webp", b"picture");
    for (kind, suffix) in [
        ("audio_uk", "uk"),
        ("audio_us", "us"),
        ("audio_example", "example"),
        ("audio_ielts", "ielts"),
    ] {
        bundle.asset(kind, &format!("wa_library_{suffix}.mp3"), suffix.as_bytes());
    }
    let app = bundle.app();
    let item = queue(&app);
    assert!(item["illustration_url"]
        .as_str()
        .unwrap()
        .starts_with("/api/media/source/library/illustration?v="));
    let image = get(&app, item["illustration_url"].as_str().unwrap());
    assert_eq!(
        (
            image.status,
            image.content_type.as_str(),
            image.body.as_slice()
        ),
        (200, "image/webp", b"picture".as_slice())
    );
    assert_eq!(item["audio_urls"].as_object().unwrap().len(), 2);
    for suffix in ["uk", "us"] {
        let url = item["audio_urls"][suffix].as_str().unwrap();
        assert!(url.starts_with(&format!("/api/media/source/library/audio/{suffix}?v=")));
        let audio = get(&app, url);
        assert_eq!(
            (
                audio.status,
                audio.content_type.as_str(),
                audio.body.as_slice()
            ),
            (200, "audio/mpeg", suffix.as_bytes())
        );
    }
    assert_eq!(item["audio_url"], item["audio_urls"]["uk"]);
    assert_eq!(get(&app, "/api/media/41/audio").body, b"uk");
    assert_eq!(get(&app, "/api/media/41/audio/example").status, 404);
    assert_eq!(get(&app, "/api/media/41/audio/ielts").status, 404);
    let status: Value = serde_json::from_slice(&get(&app, "/api/resources/status").body).unwrap();
    assert_eq!(status["data"]["counts"]["files"], 3);
    let active: String = serde_json::from_slice(&std::fs::read(bundle.dir.path().join("active.json")).unwrap()).unwrap();
    let media = cijian_core::media::Media::load_package(&bundle.dir.path().join(active)).unwrap();
    let mut historical = json!({"id": "history-1", "source_id": "library", "word": "library"});
    media.decorate(&mut historical);
    assert_eq!(historical["audio_urls"], item["audio_urls"]);

    let stats: Value = serde_json::from_slice(&get(&app,
        "/api/stats/vocabulary-words?dimension=topic&value=教育&status=all").body).unwrap();
    assert_eq!(stats["data"]["items"][0]["audio_urls"], item["audio_urls"]);

    // Anki note ids may change between snapshots. Stable SourceId still finds the media.
    app.store.import_vocabulary(words(99, "library")).unwrap();
    assert_eq!(get(&app, "/api/media/99/illustration").body, b"picture");
    assert_eq!(get(&app, "/api/media/41/illustration").status, 404);
    app.store
        .import_vocabulary(words(99, "different_source"))
        .unwrap();
    assert_eq!(get(&app, "/api/media/99/illustration").status, 404);
    // Calendar history can retain a SourceId after the word leaves the current vocabulary.
    assert_eq!(get(&app, "/api/media/source/library/audio/uk").body, b"uk");
}

#[test]
fn missing_media_does_not_block_practice_and_audio_defaults_to_available_accent() {
    let mut bundle = Bundle::new();
    bundle.asset("audio_us", "wa_library_us.mp3", b"us");
    let app = bundle.app();
    let item = queue(&app);
    assert_eq!(item["illustration_url"], "");
    assert_eq!(item["audio_urls"].as_object().unwrap().len(), 1);
    assert_eq!(item["audio_url"], item["audio_urls"]["us"]);
    assert_eq!(get(&app, "/api/media/41/audio").body, b"us");
    for path in [
        "/api/media/41/illustration",
        "/api/media/41/audio/uk",
        "/api/media/999/audio/us",
        "/api/media/41/../manifest.json",
        "/api/media/41/audio/../../server.json",
        "/api/media/41/audio/secret",
    ] {
        assert_eq!(get(&app, path).status, 404, "{path}");
    }
    assert_eq!(
        app.handle(&Request::new("POST", "/api/media/41/audio/us", vec![]))
            .status,
        404
    );
}

#[test]
fn reads_media_without_hashes_and_versions_urls_when_package_changes() {
    let mut bundle = Bundle::new();
    bundle.asset("illustration", "wa_library_img.webp", b"original");
    let app = bundle.app();
    let old_url = queue(&app)["illustration_url"].clone();
    assert_eq!(get(&app, old_url.as_str().unwrap()).body, b"original");
    bundle.asset("illustration", "wa_library_img.webp", b"updated");
    let updated = bundle.app();
    let new_url = queue(&updated)["illustration_url"].clone();
    assert_ne!(old_url, new_url);
    assert_eq!(get(&updated, new_url.as_str().unwrap()).body, b"updated");
    assert!(!bundle.dir.path().join("wa_library_img.webp").exists());
}
