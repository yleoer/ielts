//! Local resource ZIPs indexed by stable Word Atlas SourceId.
use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::Deserialize;
use serde_json::{json, Value};

use crate::error::{ApiError, ApiResult};

const KINDS: [(&str, &str); 5] = [
    ("illustration", "illustration"),
    ("audio_uk", "audio/uk"),
    ("audio_us", "audio/us"),
    ("audio_example", "audio/example"),
    ("audio_ielts", "audio/ielts"),
];

#[derive(Deserialize)]
struct Asset {
    file: String,
}

#[derive(Deserialize)]
struct Manifest {
    format: u32,
    words: HashMap<String, HashMap<String, Asset>>,
}

#[derive(Default)]
pub struct Media {
    words: HashMap<String, HashMap<String, Asset>>,
    archive: Option<Mutex<zip::ZipArchive<File>>>,
    version: String,
}

impl Media {
    pub fn load_package(path: &Path) -> ApiResult<Self> {
        let load = || -> Result<Self, Box<dyn std::error::Error>> {
            let mut archive = zip::ZipArchive::new(File::open(path)?)?;
            let manifest: Manifest = serde_json::from_reader(archive.by_name("manifest.json")?)?;
            if manifest.format != 1 {
                return Err("不支持的资源包版本".into());
            }
            Ok(Self {
                words: manifest.words,
                archive: Some(Mutex::new(archive)),
                version: path.file_stem().unwrap().to_string_lossy().into_owned(),
            })
        };
        load().map_err(|e| ApiError::Unavailable(format!("无法读取资源包：{e}")))
    }

    pub fn version(&self) -> &str {
        &self.version
    }

    pub fn counts(&self) -> Value {
        let kinds: serde_json::Map<String, Value> = KINDS
            .iter()
            .map(|(kind, _)| {
                (
                    (*kind).into(),
                    self.words
                        .values()
                        .filter(|a| a.contains_key(*kind))
                        .count()
                        .into(),
                )
            })
            .collect();
        json!({"words": self.words.len(), "files": self.words.values().map(|a| a.len()).sum::<usize>(), "kinds": kinds})
    }

    pub fn read(&self, source: &str, route: &str) -> ApiResult<(PathBuf, Vec<u8>)> {
        let assets = self.words.get(source).ok_or(ApiError::NotFound)?;
        let kind = if route == "audio" {
            if assets.contains_key("audio_uk") {
                "audio_uk"
            } else {
                "audio_us"
            }
        } else {
            KINDS
                .iter()
                .find(|(_, r)| *r == route)
                .map(|(k, _)| *k)
                .ok_or(ApiError::NotFound)?
        };
        let asset = assets.get(kind).ok_or(ApiError::NotFound)?;
        let mut archive = self
            .archive
            .as_ref()
            .ok_or(ApiError::NotFound)?
            .lock()
            .unwrap();
        let mut entry = archive
            .by_name(&asset.file)
            .map_err(|_| ApiError::NotFound)?;
        let mut body = Vec::new();
        entry
            .read_to_end(&mut body)
            .map_err(|e| ApiError::Unavailable(format!("无法读取本地媒体：{e}")))?;
        Ok((PathBuf::from(&asset.file), body))
    }

    /// Add only locally known URLs, replacing any media URLs saved by an older app.
    pub fn decorate(&self, value: &mut Value) {
        match value {
            Value::Array(items) => items.iter_mut().for_each(|v| self.decorate(v)),
            Value::Object(object) => {
                object.values_mut().for_each(|v| self.decorate(v));
                if let (Some(source), Some(id)) = (
                    object.get("source_id").and_then(Value::as_str),
                    object.get("id").and_then(Value::as_i64),
                ) {
                    let assets = self.words.get(source);
                    let url = |kind: &str, route: &str| -> String {
                        assets.and_then(|a| a.get(kind)).map_or(String::new(), |_| {
                            format!("/api/media/{id}/{route}?v={}", self.version)
                        })
                    };
                    let illustration = url("illustration", "illustration");
                    let mut audio = serde_json::Map::new();
                    for (kind, route) in KINDS.iter().skip(1) {
                        let value = url(kind, route);
                        if !value.is_empty() {
                            audio
                                .insert(route.strip_prefix("audio/").unwrap().into(), value.into());
                        }
                    }
                    let default_audio = audio
                        .get("uk")
                        .or_else(|| audio.get("us"))
                        .cloned()
                        .unwrap_or(json!(""));
                    object.insert("illustration_url".into(), illustration.into());
                    object.insert("audio_url".into(), default_audio);
                    object.insert("audio_urls".into(), audio.into());
                }
            }
            _ => {}
        }
    }
}
