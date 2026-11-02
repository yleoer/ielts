//! 词间桌面端核心逻辑。
//!
//! - [`answer`]：答案归一化与判题，与 `srs.py` / 前端 `normalizeAnswer` 一致。
//! - [`fsrs`]：py-fsrs 6.3.2 `Scheduler` 的逐行移植。
//! - [`srs`]：应用评分规则（6/20 秒阈值）与调度配置。

pub mod answer;
pub mod fsrs;
pub mod srs;
pub mod time;
