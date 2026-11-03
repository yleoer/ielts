# typing-desktop

“词间”桌面端（Tauri 2 + Rust），开发中。设计见 [docs/typing-desktop/DESIGN.md](../docs/typing-desktop/DESIGN.md)。

| 目录 | 内容 |
| --- | --- |
| `core/` | `cijian-core`：判题、FSRS、本地 SQLite（`store.rs`）、统计查询（`stats.rs`）、参数优化（`optimize.rs`）、与 Flask 同路径同 JSON 的路由（`api.rs`） |
| `app/` | Tauri 2 壳：`cijian://` 协议转发到 `core`，页面来自内嵌的 `dist/` |
| `vendor/` | 固定版本的 Vue 3.4.21、axios 1.6.7、ECharts 5.4.3 及许可证，替代 CDN |
| `scripts/` | 前端打包、词库导出、FSRS 基准生成、CDP 调试脚本 |
| `fixtures/` | py-fsrs 对照基准 |

当前已实现练习页（正式/自由练习、提交、汇总、插图、同步弹窗）和统计页（概览、学习日历、近 30 天、词库进度与明细、错误记录、参数优化记录）。FSRS 参数优化在后台线程运行：启动时检查一次，此后每天一次，有效间隔复习满 1000 条后每月最多训练一次。

## 构建与运行

需要 Rust 工具链、MSVC 生成工具和 Node.js（见设计文档“本机环境”）。在仓库根目录：

```powershell
# 1. 用 typing-practice 的模板渲染前端到 typing-desktop/dist（需要 Jinja2，.venv 已带）
.\.venv\Scripts\python.exe typing-desktop\scripts\build_frontend.py

# 2. 从 Anki 数据库导出词库快照（只读，复用 typing-practice/backend/anki.py）
.\.venv\Scripts\python.exe typing-desktop\scripts\export_vocab.py `
    --db "$env:APPDATA\Anki2\User 1\collection.anki2" --out "$env:APPDATA\com.yleoer.cijian\vocab.json"

# 3. 编译并启动
cd typing-desktop
npm install
cargo run -p cijian
```

首次启动后点右上角“同步”导入词库。前端模板或脚本修改后需重新执行第 1 步再编译，页面在编译时内嵌。

环境变量（均可选）：

| 变量 | 默认 |
| --- | --- |
| `CIJIAN_DB_PATH` | `%APPDATA%\com.yleoer.cijian\cijian.db` |
| `CIJIAN_VOCAB_PATH` | `%APPDATA%\com.yleoer.cijian\vocab.json` |
| `CIJIAN_MEDIA_DIR` | 安装目录下的 `media/`；开发时指向 Anki 的 `collection.media` |
| `CIJIAN_OPTIMIZATION` | 设为 `0` 关闭自动参数优化（已启用的参数保留）；默认开启 |

例如使用仓库内 demo 数据：`CIJIAN_MEDIA_DIR=typing-practice\data\local-demo\collection.media`，词库从 `typing-practice\data\local-demo\collection.anki2` 导出。

### 调试真实窗口

设置 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333` 后启动，可用：

```powershell
node typing-desktop\scripts\cdp.mjs eval "document.title"
node typing-desktop\scripts\cdp.mjs shot practice.png
```

## FSRS 对照基准

在仓库根目录用 py-fsrs 生成 Rust 实现的比对数据（输出可复现）：

```powershell
.\.venv\Scripts\python.exe typing-desktop\scripts\gen_fsrs_fixtures.py
```

输出 `fixtures/fsrs-golden.json`。修改 `typing-practice/backend/srs.py` 的评分或调度规则后需重新生成并提交。

## 测试

在 `typing-desktop` 目录运行：

```powershell
cargo test
```

- `core/tests/golden.rs`：逐条比对 Rust 调度、评分与答案归一化结果。
- `core/tests/store.rs`：移植 `test_memory.py` / `test_app.py` 的练习用例（学习/重学/掌握、重试幂等、多标签冲突、自由练习、队列顺序、北京时间新词计数、过期与非法时间、参数变更重放、路由路径与 JSON）。
- `core/tests/stats.rs`：移植 `test_activity.py` / `test_vocabulary.py`（日历窗口与北京时间边界、到期分布、移出词库后的历史、近 30 天、连续天数、词库进度与平滑错误率排序、分页与参数校验、错误记录），并确认统计查询不写库。
- `core/tests/optimize.rs`：移植 `test_optimizer.py` / `test_optimizer_service.py`（有效复习计数、时间留出不泄漏、1000 条门槛、每月跳过、启用后保留到期时间并接受未提交题目、重启恢复、失败与异常一天后重试、无效结果、退出中断恢复、接口），另用 fsrs-rs 实际训练一次合成数据。

`Cargo.toml` 对 `fsrs`、`ndarray` 在开发构建中开启优化，否则训练测试会慢很多。
