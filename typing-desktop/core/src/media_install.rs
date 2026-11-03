//! Personal resource packages: import a ZIP, then activate it.
use std::fs::File;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, RwLock};

use serde_json::{json, Value};
use uuid::Uuid;

use crate::error::{ApiError, ApiResult};
use crate::media::Media;

pub const CHUNK_SIZE: usize = 4 * 1024 * 1024;

struct Job {
    phase: &'static str,
    id: String,
    done: u64,
    total: Option<u64>,
    error: String,
    upload: Option<File>,
}

impl Default for Job {
    fn default() -> Self {
        Self {
            phase: "idle",
            id: String::new(),
            done: 0,
            total: None,
            error: String::new(),
            upload: None,
        }
    }
}

pub struct MediaManager {
    root: Option<PathBuf>,
    current: RwLock<Arc<Media>>,
    job: Mutex<Job>,
}

fn failure(e: impl std::fmt::Display) -> ApiError {
    ApiError::Unavailable(format!("资源导入失败：{e}。请重新选择资源包"))
}

impl Job {
    fn busy(&self) -> bool {
        matches!(self.phase, "uploading" | "installing")
    }
}

impl MediaManager {
    pub fn new(root: Option<&Path>) -> Arc<Self> {
        let load = || -> ApiResult<Media> {
            let Some(root) = root else {
                return Ok(Media::default());
            };
            let pointer = root.join("active.json");
            if !pointer.is_file() {
                return Ok(Media::default());
            }
            let name: String = serde_json::from_slice(&std::fs::read(pointer).map_err(failure)?)
                .map_err(failure)?;
            Media::load_package(&root.join(name))
        };
        let (media, error) = match load() {
            Ok(media) => (media, String::new()),
            Err(error) => (Media::default(), error.to_string()),
        };
        Arc::new(Self {
            root: root.map(Path::to_path_buf),
            current: RwLock::new(Arc::new(media)),
            job: Mutex::new(Job {
                error,
                ..Job::default()
            }),
        })
    }

    pub fn current(&self) -> Arc<Media> {
        self.current.read().unwrap().clone()
    }

    pub fn status(&self) -> Value {
        let job = self.job.lock().unwrap();
        let counts = self.current().counts();
        json!({"installed": counts["files"].as_u64().unwrap_or(0) > 0, "counts": counts,
            "phase": job.phase, "id": job.id,
            "done": job.done, "total": job.total, "error": job.error,
            "busy": job.busy()})
    }

    pub fn begin_upload(&self, size: u64) -> ApiResult<Value> {
        if size == 0 {
            return Err(ApiError::bad("请选择非空 ZIP 资源包"));
        }
        let root = self
            .root
            .as_ref()
            .ok_or_else(|| ApiError::bad("未配置资源保存目录"))?;
        let mut job = self.job.lock().unwrap();
        if job.busy() {
            return Err(ApiError::bad("已有资源任务正在进行"));
        }
        std::fs::create_dir_all(root).map_err(failure)?;
        let id = Uuid::new_v4().to_string();
        let path = root.join(format!("{id}.part"));
        let file = File::create(&path).map_err(failure)?;
        *job = Job {
            phase: "uploading",
            id: id.clone(),
            total: Some(size),
            upload: Some(file),
            ..Job::default()
        };
        Ok(json!({"id": id, "chunk_size": CHUNK_SIZE}))
    }

    pub fn append(&self, id: &str, offset: u64, bytes: &[u8]) -> ApiResult<()> {
        let mut job = self.job.lock().unwrap();
        if job.phase != "uploading" || job.id != id || job.done != offset {
            return Err(ApiError::bad("导入进度不匹配，请重新选择资源包"));
        }
        job.upload
            .as_mut()
            .unwrap()
            .write_all(bytes)
            .map_err(failure)?;
        job.done += bytes.len() as u64;
        Ok(())
    }

    pub fn cancel_upload(&self, id: &str) -> ApiResult<()> {
        let mut job = self.job.lock().unwrap();
        if job.id != id || job.phase != "uploading" {
            return Err(ApiError::bad("该导入任务已结束"));
        }
        job.upload.take();
        if let Some(root) = &self.root {
            let _ = std::fs::remove_file(root.join(format!("{id}.part")));
        }
        *job = Job::default();
        Ok(())
    }

    pub fn finish_upload(&self, id: &str) -> ApiResult<()> {
        {
            let mut job = self.job.lock().unwrap();
            if job.id != id || job.phase != "uploading" || Some(job.done) != job.total {
                return Err(ApiError::bad("资源包尚未完整导入"));
            }
            job.upload.take();
            job.phase = "installing";
        }
        let path = self.root.as_ref().unwrap().join(format!("{id}.part"));
        let result = self.install(&path, id);
        if let Err(error) = &result {
            self.failed(error);
        }
        result
    }

    fn failed(&self, error: &ApiError) {
        let mut job = self.job.lock().unwrap();
        job.upload.take();
        job.phase = "error";
        job.error = error.to_string();
        if let Some(root) = &self.root {
            let _ = std::fs::remove_file(root.join(format!("{}.part", job.id)));
        }
    }

    fn install(&self, path: &Path, id: &str) -> ApiResult<()> {
        // Close the candidate ZIP before renaming it on Windows.
        drop(Media::load_package(path)?);
        let root = self.root.as_ref().unwrap();
        let name = format!("{id}.zip");
        let target = root.join(&name);
        std::fs::rename(path, &target).map_err(failure)?;
        let media = Arc::new(Media::load_package(&target)?);
        let pointer = root.join("active.json");
        let temporary = root.join("active.json.tmp");
        std::fs::write(&temporary, serde_json::to_vec(&name).unwrap()).map_err(failure)?;
        std::fs::rename(temporary, pointer).map_err(failure)?;
        let previous = std::mem::replace(&mut *self.current.write().unwrap(), media);
        let previous_version = previous.version().to_string();
        drop(previous);
        if !previous_version.is_empty() {
            let _ = std::fs::remove_file(root.join(format!("{previous_version}.zip")));
        }
        self.job.lock().unwrap().phase = "ready";
        Ok(())
    }
}
