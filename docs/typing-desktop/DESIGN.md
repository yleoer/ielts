# 词间桌面端设计（Tauri 2 + Rust）

把 `typing-practice` 从“浏览器 + Flask”改为“桌面客户端 + 精简同步服务”。分支：`desktop-tauri`。

## 分工

| 部分 | 位置 | 职责 |
| --- | --- | --- |
| 桌面端 | `typing-desktop/`（Tauri 2，Rust 后端 + 现有 Vue 页面） | 判题、FSRS 调度与参数优化、统计查询、本地 SQLite、内置插图与音频 |
| 服务端 | `typing-practice/backend`（精简后的 Python） | 读取 Anki `collection.anki2` 提供已学习词条；作答日志同步；访问令牌 |

服务端不再运行 FSRS、不提供页面和媒体，去掉 `fsrs[optimizer]` / PyTorch 依赖。

## 桌面端

- **前端**：沿用 `app.js` / `stats.js` / `style.css`。Jinja 模板改为静态 HTML；Vue、ECharts 改为本地文件；axios 调用改为 `invoke` 同名命令，命令返回结构与现有 `/api/*` JSON 保持一致，以便复用前端和 Node 测试。
- **FSRS**：`typing-desktop/core`（`cijian-core`）逐行移植 py-fsrs 6.3.2 `Scheduler`，与 `srs.py` 行为一致，包括学习步骤 1/10 分钟、重学 10 分钟、保持率 0.9、6/20 秒评分阈值；Card JSON 与 py-fsrs `to_dict()` 兼容，可直接读取现有 `card_json`。参数优化使用 fsrs-rs 的 `compute_parameters`，在本地后台线程运行，验收规则沿用现有优化服务（时间留出验证、误差改善才启用）。
- **对照基准**：`typing-desktop/scripts/gen_fsrs_fixtures.py` 用 py-fsrs 生成 `typing-desktop/fixtures/fsrs-golden.json`（关闭 fuzz，300 条随机复习序列共 2258 次复习、评分边界、答案归一化）。`core/tests/golden.rs` 逐条比对 state、step、due、last_review，以及 stability、difficulty、回忆概率（相对误差 ≤ 1e-9），当前全部通过。修改 `srs.py` 评分或调度规则后需重新生成。
- **fuzz**：取 SHA-256(`attempt_id`) 前 53 位作为 `[0, 1)` 随机数，重放同一日志得到相同计划；fuzz 区间算法与 py-fsrs 相同，不在基准中比对。
- **存储**：本地 SQLite 沿用 `word_memory`、`word_reviews` 结构，另存词库缓存和同步游标。`practice_items` 只在本地使用，不同步。
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
3. 前端迁入，实现练习相关命令，先做纯离线版本（词库从本地 Anki 数据库导入）。
4. 迁移统计查询，接入本地参数优化。
5. 精简服务端，增加 `/api/vocab`、`/api/sync`，把现有 `stats.db` 作答导入服务端作为初始日志。
6. 媒体打包与 manifest；安装包构建与发布流程。

## 本机环境

Windows 构建需要：

- Rust 工具链：`winget install Rustlang.Rustup`
- MSVC 生成工具（含“使用 C++ 的桌面开发”工作负载）：`winget install Microsoft.VisualStudio.2022.BuildTools`，或在 Visual Studio Installer 中勾选
- WebView2（Windows 11 已自带）
- Node.js（已有）
