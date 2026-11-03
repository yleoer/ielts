# 词间桌面端设计（Tauri 2 + Rust）

把 `typing-practice` 从“浏览器 + Flask”改为“桌面客户端 + 精简同步服务”。分支：`desktop-tauri`。

## 分工

| 部分 | 位置 | 职责 |
| --- | --- | --- |
| 桌面端 | `typing-desktop/`（Tauri 2，Rust 后端 + 现有 Vue 页面） | 判题、FSRS 调度与参数优化、统计查询、本地 SQLite、内置插图与音频 |
| 服务端 | `typing-practice/backend`（精简后的 Python） | 读取 Anki `collection.anki2` 提供已学习词条；作答日志同步；访问令牌 |

服务端不再运行 FSRS、不提供页面和媒体，去掉 `fsrs[optimizer]` / PyTorch 依赖。

## 桌面端

- **前端**：与网页版共用 `typing-practice/frontend`，JS 不改。`scripts/build_frontend.py` 用相同 Jinja 模板渲染到 `dist/`，CDN 脚本替换为 `vendor/` 中的固定版本，编译时内嵌。
- **接口**：Tauri 注册 `cijian://` 自定义协议（Windows 上为 `http://cijian.localhost/`）。页面按 `location.origin + "/api"` 发出的请求由 `core/src/api.rs` 处理，路径、状态码与 JSON 与 Flask 一致（409 `practice_conflict`、400、503），不使用 `invoke`。
- **FSRS**：`typing-desktop/core`（`cijian-core`）逐行移植 py-fsrs 6.3.2 `Scheduler`，与 `srs.py` 行为一致，包括学习步骤 1/10 分钟、重学 10 分钟、保持率 0.9、6/20 秒评分阈值；Card JSON 与 py-fsrs `to_dict()` 兼容，可直接读取现有 `card_json`。
- **参数优化**：`core/src/optimize.rs` 移植 `optimize_fsrs.py` 与 `optimizer_service.py`，表结构（`fsrs_optimization_runs`、`fsrs_optimizer_state`）、状态值与接口 JSON 不变。训练改用 fsrs-rs 6.6.2 `compute_parameters`（纯 Rust，无 PyTorch），每张卡取前 64 次作答，以“距上次作答整天数 > 0”的作答为训练目标。验收规则不变：有效间隔复习满 1000 条后每月评估一次，前 80% 作答训练、后 20% 留出验证，候选的 log loss 低于现用与默认参数且 Brier 不升高才启用；启用后新参数在下一次作答时重放该词日志生效，不改已有到期时间。训练在桌面端后台线程运行（启动时检查，此后每天一次），应用退出导致未完成的记录在下次启动时标为“任务中断”并立即重新评估，取代原来的进程租约。
- **对照基准**：`typing-desktop/scripts/gen_fsrs_fixtures.py` 用 py-fsrs 生成 `typing-desktop/fixtures/fsrs-golden.json`（关闭 fuzz，300 条随机复习序列共 2258 次复习、评分边界、答案归一化）。`core/tests/golden.rs` 逐条比对 state、step、due、last_review，以及 stability、difficulty、回忆概率（相对误差 ≤ 1e-9），当前全部通过。修改 `srs.py` 评分或调度规则后需重新生成。
- **fuzz**：取 SHA-256(`attempt_id`) 前 53 位作为 `[0, 1)` 随机数，重放同一日志得到相同计划；fuzz 区间算法与 py-fsrs 相同，不在基准中比对。
- **统计**：`core/src/stats.rs` 移植 `stats.py`、`activity.py`、`vocabulary.py` 及 `memory.py` 的日历与词库查询：概览与连续天数、近 30 天、学习日历（前 6 个月至后 5 个月，北京时间）、日历单日词表、词库进度与分组明细、单词错误记录，均为只读查询，路径、参数校验与 JSON 与 Flask 一致。
- **存储**：`core/src/store.rs` 移植 `memory.py` 的出题、提交与汇总，本地 SQLite 沿用 `srs_configs`、`word_memory`、`practice_items`、`word_reviews` 结构，另有 `vocabulary`（词库快照）与 `sync_history`。`practice_items` 只在本地使用，不同步。
- **词库（离线阶段）**：`scripts/export_vocab.py` 复用 `anki.py` 从 Anki 数据库导出 JSON 快照（全部词条 + `learned` + 插图文件名）；页面“同步”按钮重新导入快照并记录新增词。后续 `/api/vocab` 返回同一格式。
- **媒体**：插图与音频随安装包放入 Tauri 资源目录，按 `SourceId` 建 manifest（文件名 + 哈希），由 `apkg-generator` 生成；通过自定义协议读取，不经过服务端。

## 同步

同步对象是**只追加的作答日志**，不是卡片状态。

- `GET /api/vocab?since=<游标>`：增量获取已学习词条（SourceId、词面、释义、话题、CEFR 等，不含媒体）。
- `POST /api/sync`：上传本地新增作答（以 `attempt_id` 去重），并按服务端游标返回其他设备的作答。
- 客户端合并后按 `reviewed_at, attempt_id` 顺序重放受影响词条的日志，得到卡片状态；fuzz 可复现保证多设备结果一致。
- 离线时照常练习，联网后再同步。鉴权使用长期访问令牌，替代浏览器 Cookie。

## 实施顺序

1. FSRS 对照基准（已完成）。
2. Rust 实现判题与 FSRS 并通过基准测试（已完成，`cijian-core`）；搭建 Tauri 2 工程。
3. 前端迁入，实现练习相关接口，先做纯离线版本（已完成：练习页在真实窗口中验证出题、判题、FSRS 写库与插图）。
4. 迁移统计查询，接入本地参数优化（已完成：统计页全部接口与参数优化记录在 `cijian-core` 中实现）。
5. 精简服务端，增加 `/api/vocab`、`/api/sync`，把现有 `stats.db` 作答导入服务端作为初始日志。
6. 媒体打包与 manifest；安装包构建与发布流程。

## 本机环境

Windows 构建需要：

- Rust 稳定版工具链，使用 `x86_64-pc-windows-msvc` 目标
- Visual Studio 2022 Build Tools，包含 C++ 构建工具和 Windows SDK
- WebView2（Windows 11 已自带）
- Node.js

首次安装 Rust 和 MSVC，在 PowerShell 中执行：

```powershell
# 先安装 C++ 工作负载及推荐组件（含 Windows SDK），按提示允许管理员授权
winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity --override "--wait --quiet --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"

# 再安装 rustup 及 Rust 稳定版
winget install --id Rustlang.Rustup --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity --override "-y --default-host x86_64-pc-windows-msvc --default-toolchain stable --profile default"
```

只安装 Build Tools 主程序不会自动安装 C++ 工作负载，必须保留 `--add Microsoft.VisualStudio.Workload.VCTools`。已安装 Build Tools 时，可在 Visual Studio Installer 中修改现有安装，补齐 C++ 构建工具和 Windows SDK。

安装后重新打开终端（Codex 中的终端可能需要重启应用才能继承新的 `PATH`），检查：

```powershell
rustup show
rustc --version
cargo --version
```

默认工具链应为 `stable-x86_64-pc-windows-msvc`。Cargo 会自动查找 MSVC 和 Windows SDK，无需把 `cl.exe` 永久加入 `PATH`。按 [构建与运行](../../typing-desktop/README.md#构建与运行) 的步骤准备前端后，可运行 `cargo build -p cijian` 验证桌面端构建。
