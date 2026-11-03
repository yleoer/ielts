//! 词间桌面端核心逻辑。
//!
//! - [`answer`]：答案归一化与判题，与 `srs.py` / 前端 `normalizeAnswer` 一致。
//! - [`fsrs`]：py-fsrs 6.3.2 `Scheduler` 的逐行移植。
//! - [`srs`]：应用评分规则（6/20 秒阈值）与调度配置。
//! - [`store`]：本地 SQLite 练习队列、作答记录与卡片（移植 `memory.py`）。
//! - [`stats`]：统计页查询（移植 `stats.py` 与 `memory.py` 的日历、词库进度）。
//! - [`optimize`]：本地参数优化（fsrs-rs 训练 + 时间留出验证，移植 `optimizer_service.py`）。
//! - [`api`]：与 Flask 相同路径和 JSON 的请求路由，供桌面壳的自定义协议调用。

pub mod answer;
pub mod api;
pub mod error;
pub mod fsrs;
pub mod optimize;
pub mod srs;
pub mod stats;
pub mod store;
pub mod time;
pub mod vocab;
