# 词间桌面端设计（Tauri 2 + Rust）

把 `typing-practice` 从“浏览器 + Flask”改为“桌面客户端 + 精简同步服务”。分支：`desktop-tauri`。

## 分工

| 部分 | 位置 | 职责 |
| --- | --- | --- |
| 桌面端 | `typing-desktop/`（Tauri 2，Rust 后端 + 现有 Vue 页面） | 判题、FSRS 调度与参数优化、统计查询、本地 SQLite、本地资源包中的插图与音频 |
| 服务端 | `typing-practice/backend`（最小 Python 同步服务） | 默认每小时从 anki-sync-server 复制并检查 `collection.anki2`，提供词库快照与统一新增词历史；保存只追加的作答日志；访问令牌 |

服务端不再运行 FSRS、不提供页面和媒体，运行依赖为 Flask、Waitress、PyYAML、python-dotenv，通过 Waitress 提供生产 WSGI 服务。网页版已下线。

## 桌面端

- **开机自启动**：`app/src/autostart.rs` 通过 `winreg` 管理当前用户的 Windows 登录启动项（`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`），名称固定为 `Cijian`，命令指向当前程序；默认不注册，开启后按正常方式打开主窗口。`desktop.rs` 的 `get_autostart` / `set_autostart` 供共享设置页即时读取及切换，不在本地 JSON 复制系统状态、不参与同步，不需要管理员权限。命令完整引用程序路径以支持空格；读取任务管理器的 `StartupApproved\Run` 禁用状态，重新开启时清除此禁用覆盖。正式安装后开启可保证路径稳定；注册表单元测试使用独立临时键，真实窗口测试使用临时数据并备份、恢复原启动项。
- **窗口**：隐藏系统标题栏，两页共用左侧边栏（练习、统计、同步、设置）与 48px 标题栏（页面名、状态、贴边窗口按钮），只有内容区滚动；标题栏空白可拖动，双击最大化／还原；窄窗口侧栏收成图标栏。Ctrl+1／Ctrl+2、Ctrl+,、F5 等桌面快捷键由 workspace.js 统一处理。开发时 CIJIAN_DEVTOOLS_PORT 开启 WebView2 远程调试。Tauri 开启全局窗口 API，`app/capabilities/main-window.json` 授权主窗口的控制与状态监听；`frontend/src/window-controls.js` 为两页共用逻辑，两页使用共享 `frontend/src/workspace.js` 与 `_workspace_dialogs.html` 提供设置、资源导入和同步弹窗，统计页同步后在原页刷新数据并复用图表容器，避免整体重新挂载导致图表空白。视觉规范见仓库根目录 `DESIGN.md`。
- **前端**：`typing-desktop/frontend`（由网页版迁入，删除登录页）。`scripts/build_frontend.py` 用 Jinja 模板渲染到 `dist/`，CDN 脚本替换为 `vendor/` 中的固定版本，编译时内嵌。
- **Windows 安装包**：NSIS 安装器与卸载器固定使用简体中文，图标与程序共用 `app/icons/icon.ico`。`app/tauri.conf.json` 的 `productName` 为英文 `Cijian`，安装包名为 `Cijian_<版本>_x64-setup.exe`，当前用户默认安装目录为 `%LOCALAPPDATA%\Cijian`；窗口与页面品牌继续为“词间”，应用标识仍为 `com.yleoer.cijian`。
- **发布与更新**：版本统一来自 Cargo 工作区；`scripts/version.py` 更新版本及本地包锁记录、校验 `desktop-v<版本>` 标签。独立 Windows Actions 生成签名 NSIS 包，普通分支构建保存 artifact，正式标签发布 GitHub Release 与 `latest.json`。Tauri updater 直接访问公开 Release，不经过同步服务器；两页后台检查，设置中确认下载安装，NSIS 完成后重启。签名私钥只在本机用户目录与 Actions secrets 中，应用只内嵌公钥。详见 [发布流程](RELEASING.md)。
- **托盘与关闭偏好**：`app/src/desktop.rs` 管理系统托盘和本地 `desktop.json`，默认关闭时隐藏主窗口；常规设置可即时改为直接退出。单击图标或菜单恢复窗口，菜单“退出”直接结束进程。正式队列汇总每 30 秒、鼠标移入及作答／同步后刷新；原生线程每秒按缓存时间更新倒计时及颜色，不依赖 WebView 的后台定时器。`app/src/tray_indicator.rs` 计算最后 10 分钟的线性进度并从上到下染成赭橙色（`#f6ad43`），保留透明度、白色书页和图案明暗；已到期词数优先于下一到期时间，到期即整枚切换为砖红色（`#d84c3e`），无需等待汇总刷新。完成后按新计划恢复，仅有新词不变色。缓存及原生图标更新在主线程串行执行，仅在进度／提示变化时调用原生 setter；读取失败恢复原图标及不可用提示。偏好不参与同步。
- **接口**：Tauri 注册 `cijian://` 自定义协议（Windows 上为 `http://cijian.localhost/`）。练习、统计与同步请求按 `location.origin + "/api"` 交给 `core/src/api.rs`，路径、状态码与 JSON 与 Flask 一致（409 `practice_conflict`、400、503）；仅桌面关闭偏好通过 Tauri `invoke` 的 `get_close_to_tray` / `set_close_to_tray` 命令读写。
- **FSRS**：`typing-desktop/core`（`cijian-core`）逐行移植 py-fsrs 6.3.2 `Scheduler`，与 `srs.py` 行为一致，包括学习步骤 1/10 分钟、重学 10 分钟、保持率 0.9、6/20 秒评分阈值；Card JSON 与 py-fsrs `to_dict()` 兼容，可直接读取现有 `card_json`。原 `srs.py` 保留为 `scripts/srs_reference.py`，只供基准生成使用。
- **参数优化**：`core/src/optimize.rs` 移植 `optimize_fsrs.py` 与 `optimizer_service.py`，表结构（`fsrs_optimization_runs`、`fsrs_optimizer_state`）、状态值与接口 JSON 不变。训练改用 fsrs-rs 6.6.2 `compute_parameters`（纯 Rust，无 PyTorch），每张卡取前 64 次作答，以“距上次作答整天数 > 0”的作答为训练目标。验收规则不变：有效间隔复习满 1000 条后每月评估一次，前 80% 作答训练、后 20% 留出验证，候选的 log loss 低于现用与默认参数且 Brier 不升高才启用；启用后新参数在下一次作答时重放该词日志生效，不改已有到期时间。训练在桌面端后台线程运行（启动时检查，此后每天一次），应用退出导致未完成的记录在下次启动时标为“任务中断”并立即重新评估，取代原来的进程租约。
- **对照基准**：`typing-desktop/scripts/gen_fsrs_fixtures.py` 用 py-fsrs 生成 `typing-desktop/fixtures/fsrs-golden.json`（关闭 fuzz，300 条随机复习序列共 2258 次复习、评分边界、答案归一化）。`core/tests/golden.rs` 逐条比对 state、step、due、last_review，以及 stability、difficulty、回忆概率（相对误差 ≤ 1e-9），当前全部通过。修改评分或调度规则时同时改 `srs_reference.py` 与 Rust 实现，并重新生成。
- **fuzz**：取 SHA-256(`attempt_id`) 前 53 位作为 `[0, 1)` 随机数，重放同一日志得到相同计划；fuzz 区间算法与 py-fsrs 相同，不在基准中比对。
- **统计**：`core/src/stats.rs` 移植 `stats.py`、`activity.py`、`vocabulary.py` 及 `memory.py` 的日历与词库查询：概览与连续天数、近 30 天、学习日历（前 6 个月至后 5 个月，北京时间）、日历单日词表、词库进度与分组明细、单词错误记录，均为只读查询，路径、参数校验与 JSON 与 Flask 一致。
- **存储**：`core/src/store.rs` 移植 `memory.py` 的出题、提交与汇总，本地 SQLite 沿用 `srs_configs`、`word_memory`、`practice_items`、`word_reviews` 结构，另有 `vocabulary`（词库快照）、`sync_history`（服务器新增词历史缓存）、`sync_state`（设备 ID、服务端游标、本机上次同步时间及服务器上次检查 Anki 时间）与 `synced_attempts`（服务端已有的作答）。`practice_items` 只在本地使用，不同步。
- **词库**：服务端 `GET /api/vocab` 返回 JSON 快照（全部词条 + `learned` + 插图文件名，`AnkiReader.snapshot()`）。桌面端必须连接服务器，没有离线导入词库的方式；已同步的词库和作答保存在本地，断网时照常练习。
- **媒体**：个人自用，插图与英、美单词读音（不含例句朗读）单独分发为 `cijian-media.zip`。服务器配置位于同步面板，资源 ZIP 在设置中导入或更换；没有下载功能。`media.rs` 按 SourceId 直接读取 ZIP，`media_install.rs` 管理分块复制与切换；不逐文件校验 SHA，不做成员扫描、多实例锁、后台安装线程或旧散文件兼容。保留基本解析和失败保留原包，详见 [独立媒体资源包](MEDIA.md)。

## 同步

同步对象是**只追加的作答日志**，不是卡片状态。服务端实现在 `typing-practice/backend/ledger.py`，客户端在 `core/src/sync.rs`（本地合并）与 `core/src/remote.rs`（HTTP 与流程）。

- **鉴权**：请求头 `Authorization: Bearer <令牌>`，令牌是服务端的 `ACCESS_TOKEN`（未设置时沿用旧的 `ACCESS_PASSWORD`，两者都为空则不鉴权）。`/api/health` 不需要令牌。
- `GET /api/vocab`：完整词库快照 `{"format": 1, "generated_at", "last_anki_sync_at", "deck_name", "words", "sync_history"}`。服务器默认每小时检查 Anki，首次成功检查建立已有已学 SourceId 基线，之后持久化首次发现的新增批次。接口仅返回最近成功快照及最近 50 批，不因客户端请求而扫描 Anki。客户端在同一事务替换词库、历史缓存与检查时间，不自行计算新增词；升级时一次性清空旧的本机历史表。
- `POST /api/sync`：请求 `{"device_id", "cursor", "attempts"}`，每次最多上传 500 条；服务端以 `attempt_id` 去重（先到为准），返回游标之后最多 500 条日志 `{"accepted", "duplicates", "attempts", "next_cursor", "more"}`。游标是服务端行号，递增但可能不连续。
- **作答字段**：`attempt_id`、`word_key`（`word-atlas:<SourceId>`）、`word`、`chinese_meaning`、`category`、`user_input`、`is_correct`、`rating`、`reviewed_at`（UTC 微秒 `Z`）、`duration_ms`、`first_input_ms`。评分在作答设备上确定，重放直接使用记录的评分。
- **流程**（`remote::sync_all`）：先刷新词库；再循环“上传未确认的本地作答 + 取回游标后的日志”，直到没有待上传作答且 `more` 为假。网络请求不持有存储锁，练习不受影响；同一时间只允许一次同步。
- **合并**：每批返回的日志在一个事务里处理：记录已确认的作答，插入本机没有的作答，按 `reviewed_at, attempt_id` 重放受影响词条的完整日志并重写卡片（`version + 1`，该词未提交的题目会提示已在其他设备完成复习），最后保存游标。fuzz 由 `attempt_id` 决定，在 FSRS 参数相同时多台设备得到相同计划（参数优化暂不同步，见 [SRS 待办](SRS-PLAN.md#待办多设备参数优化同步)）；`card_id` 是本地行号，各设备不同，不影响调度。服务端返回无效作答时整批拒绝，本地不变。
- **服务器配置**：同步面板在已配置时只展示地址，点击“修改”才展开地址与令牌表单，可取消恢复原值；保存成功后自动收起，失败则保留输入。首次启动时页面调用 `GET /api/settings/server`，未配置则自动打开同步面板，连接成功前不可关闭。`POST /api/settings/server` 先用填写的令牌请求 `/api/vocab` 验证，地址错误或令牌无效都不保存；通过后原子写入数据目录的 `server.json`，页面同步并加载练习。以后仍在同步面板“保存并同步”，令牌留空保留原值，成功后清空输入但不关闭面板、不重置已有练习。配置从桌面 core 内存读取，本页首次需要时加载，保存后使用返回值更新；保存或同步期间禁止重复操作。`CIJIAN_SERVER_URL` / `CIJIAN_SERVER_TOKEN` 优先于 `server.json`，此时只展示地址，不提供修改入口。侧栏“设置”（`Ctrl+,`）仅管理资源、启动与窗口、软件更新，不再读取服务器配置。
- **触发**：启动时及每隔 `CIJIAN_SYNC_MINUTES`（默认 10）分钟自动同步（未设置服务器时跳过），另可点“立即同步”。离线时照常练习，联网后补传；失败只记录日志。
- **初始日志**：服务端首次启动时把同一数据库中网页版的 `word_reviews` 一次性导入 `attempts`（`device_id` 为 `web`，记录在 `ledger_migrations`），旧表保留不删。新设备首次同步即可得到全部历史与统计。

## 实施顺序

1. FSRS 对照基准（已完成）。
2. Rust 实现判题与 FSRS 并通过基准测试（已完成，`cijian-core`）；搭建 Tauri 2 工程。
3. 前端迁入，实现练习相关接口，先做纯离线版本（已完成：练习页在真实窗口中验证出题、判题、FSRS 写库与插图）。
4. 迁移统计查询，接入本地参数优化（已完成：统计页全部接口与参数优化记录在 `cijian-core` 中实现）。
5. 精简服务端，增加 `/api/vocab`、`/api/sync`，把现有 `stats.db` 作答导入服务端作为初始日志（已完成：服务端只保留词库、作答日志与令牌；桌面端同步在真实窗口中验证上传与合并，镜像在 `typetest` 检查通过）。
6. 独立媒体资源包的生成、本地导入与 NSIS 安装包构建（已实现）；Windows Actions、统一版本和程序内更新已接入，正式 Release 由标签触发。

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
