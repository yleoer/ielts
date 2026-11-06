# typing-desktop

“词间”桌面端（Tauri 2 + Rust），开发中。设计见 [docs/typing-desktop/DESIGN.md](../docs/typing-desktop/DESIGN.md)。

| 目录 | 内容 |
| --- | --- |
| `core/` | `cijian-core`：判题、FSRS、本地 SQLite（`store.rs`）、统计查询（`stats.rs`）、参数优化（`optimize.rs`）、作答日志同步（`sync.rs`、`remote.rs`）、与原 Flask 同路径同 JSON 的路由（`api.rs`） |
| `frontend/` | Vue 页面模板、脚本与样式（由网页版迁入） |
| `app/` | Tauri 2 壳：`cijian://` 协议转发到 `core`，页面来自内嵌的 `dist/` |
| `vendor/` | 固定版本的 Vue 3.4.21、axios 1.6.7、ECharts 5.4.3 及许可证，替代 CDN |
| `scripts/` | 前端打包、FSRS 基准生成（含参考实现 `srs_reference.py`）、CDP 调试脚本 |
| `fixtures/` | py-fsrs 对照基准 |
| `media/` | 独立分发的 `cijian-media.zip` （生成产物，不入 Git） |

当前已实现练习页（正式/自由练习、提交、汇总、插图、同步弹窗）和统计页（概览、学习日历、近 30 天、词库进度与明细、错误记录、参数优化记录）。FSRS 参数优化在后台线程运行：启动时检查一次，此后每天一次，有效间隔复习满 1000 条后每月最多训练一次。

窗口隐藏系统标题栏，采用桌面应用布局：左侧边栏放练习、统计入口，底部为同步（显示上次同步时间）和设置；右侧为 48px 标题栏（页面名、当前状态、贴边的最小化／最大化／关闭按钮）和独立滚动的内容区。标题栏空白处可拖动、双击最大化／还原；窗口宽度不超过 960px 时侧栏收成图标栏，最小窗口 760×560。侧栏可用底部按钮或 `Ctrl+B` 折叠为图标栏，状态会被记住。快捷键：`Ctrl+1` / `Ctrl+2` 切换页面，`Ctrl+,` 打开设置，`F5` / `Ctrl+R` 刷新当前页数据（练习页重新获取到期队列，统计页重新读取统计；不弹出同步窗口或发起同步），`Esc` 关闭弹窗；不显示网页右键菜单。刷新保留本轮已保存的作答；待保存答案、订正反馈以及自由／错词练习批次保留，仅更新汇总。弹窗遮罩覆盖整个窗口，窗口按钮仍可操作。统计页同步成功后在原页刷新数据，复用已挂载的图表。首次设置等弹窗打开时仍可操作窗口按钮。当前各设备独立优化 FSRS，参数暂不同步，限制及后续方案见 [SRS 计划](../docs/typing-desktop/SRS-PLAN.md#待办多设备参数优化同步)。

关闭主窗口默认收进系统托盘，后台同步继续运行；在“设置 → 窗口 → 关闭窗口时”可改为“直接退出应用”，选择后自动保存，无需保存或重新验证同步服务器。偏好保存在数据目录的 `desktop.json`，仅在本机生效。单击托盘图标或右键“打开词间”恢复窗口，右键“退出”彻底退出。悬停图标显示距离下次复习的天／小时／分钟（不足一分钟单独提示）；已经到期则显示待复习数量，无复习计划时显示可学新词数或暂无计划。

到期前 10 分钟，托盘图标由上向下逐渐填充赭橙色；到期或存在待复习词时完全变色，完成复习后按下一次到期时间恢复。仅有新词不触发变色，不闪烁或弹窗，也不改变窗口图标。原生线程每秒推进颜色和倒计时，正式队列汇总每 30 秒、鼠标移入及作答／同步后刷新，窗口隐藏时仍运行；读取失败恢复原图标并提示暂时无法读取。

收进托盘会保存练习草稿、停止读音并暂停计时，恢复后继续当前题目，隐藏期间不计入作答耗时。

词库和作答日志通过同步服务器（`typing-practice/backend`）获取与合并。首次启动时页面弹出“首次设置”，要求填写地址和访问令牌：保存前先用令牌请求一次服务器，通过后写入数据目录的 `server.json`，并立即同步。之后启动时和每 10 分钟自动同步；离线时照常练习，联网后补传。同步弹窗或侧栏的“设置”可修改地址或令牌（令牌留空表示不变）。

## 构建与运行

需要 Rust 工具链、MSVC 生成工具和 Node.js（见设计文档“本机环境”）。在仓库根目录：

```powershell
# 1. 准备前端（需要 Jinja2，.venv 已带；不需要媒体源仓库）
node typing-desktop\scripts\prepare.mjs

# 2. 编译并启动
cd typing-desktop
npm install
cargo run -p cijian
```

首次启动按提示填写服务器地址和令牌（本机开发可先运行服务端，见 [typing-practice/README.md](../typing-practice/README.md)）。前端模板或脚本修改后需重新执行 `build_frontend.py` 再编译，页面在编译时内嵌。

在 `typing-desktop` 目录运行 `npm run tauri -- dev` 或 `npm run tauri -- build` 时，Tauri 钩子只准备前端；`build` 生成 Windows NSIS 安装包和更新签名，位于 `target/release/bundle/nsis/`，需设置签名环境变量（见 [发布与更新](../docs/typing-desktop/RELEASING.md)）。媒体独立导出和安装，构建不需要 Word Atlas 源仓库。直接 `cargo run` / `cargo build` 不执行钩子，需要先完成第 1 步。详见 [独立媒体资源包](../docs/typing-desktop/MEDIA.md)。

Windows 安装器与卸载器固定使用简体中文（NSIS `SimpChinese`），图标均复用程序的 `app/icons/icon.ico`。语言和图标由 `app/tauri.conf.json` 的 `bundle.windows.nsis` 配置，重新构建安装包后生效。

`app/tauri.conf.json` 的 `productName` 使用英文 `Cijian`，生成的安装包为 `Cijian_<版本>_x64-setup.exe`，当前用户默认安装目录为 `%LOCALAPPDATA%\Cijian`。程序窗口和页面继续显示“词间”，本地数据仍由应用标识 `com.yleoer.cijian` 定位。覆盖同名安装包后，文件列表可能沿用旧图标缓存，刷新目录可重新读取图标。

GitHub Actions 在任意分支桌面代码变化或手动运行时构建 Windows x64 artifact，推送 `desktop-v<版本>` 标签时发布安装包、签名与 `latest.json`。版本统一来自工作区 `Cargo.toml`，可用 `scripts/version.py --set <版本>` 更新。程序后台检查正式 Release，在“设置 → 软件更新”中下载、安装并自动重启；检测到更新时设置图标显示圆点。发布步骤、签名备份和本机打包命令见 [发布与更新](../docs/typing-desktop/RELEASING.md)。

环境变量（均可选）：

| 变量 | 默认 |
| --- | --- |
| `CIJIAN_DATA_DIR` | `%APPDATA%\com.yleoer.cijian`；数据库、`server.json` 与 `desktop.json` 的默认位置，开发和测试时可指向临时目录 |
| `CIJIAN_DB_PATH` | 数据目录下的 `cijian.db` |
| `CIJIAN_MEDIA_DIR` | 数据目录下的 `media/`；保存用户导入的资源包与 `active.json`，需可写，无需 Anki `collection.media` |
| `CIJIAN_OPTIMIZATION` | 设为 `0` 关闭自动参数优化（已启用的参数保留）；默认开启 |
| `CIJIAN_SERVER_URL` | 同步服务器地址，如 `https://example.com`；设置后跳过首次设置，界面中不可修改 |
| `CIJIAN_SERVER_TOKEN` | 访问令牌，对应服务端的 `ACCESS_TOKEN` |
| `CIJIAN_SYNC_MINUTES` | 自动同步间隔（分钟），默认 `10` |
| `CIJIAN_DEVTOOLS_PORT` | 开发调试用，开启 WebView2 远程调试端口，供 `scripts/cdp.mjs` 使用；默认关闭 |

服务器设置的优先顺序：环境变量 > 数据目录的 `server.json`（`{"url": …, "token": …}`，由首次设置写入）> 首次启动弹窗。`server.json` 损坏时记录日志并重新弹出设置。

桌面端必须连接同步服务器：没有设置服务器时只显示首次设置弹窗，不提供离线导入词库的方式。设置完成后，已同步的词库和作答保存在本地，断网时照常练习。

### 调试真实窗口

设置 `CIJIAN_DEVTOOLS_PORT=9333` 后启动（Tauri 会传入自己的 WebView2 参数，`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 不再生效），可用：

```powershell
node typing-desktop\scripts\cdp.mjs eval "document.title"
node typing-desktop\scripts\cdp.mjs shot practice.png
```

## FSRS 对照基准

在仓库根目录用 py-fsrs 和 `scripts/srs_reference.py`（原网页版 `srs.py`，仅作参考实现）生成 Rust 实现的比对数据（输出可复现；依赖见 `scripts/requirements.txt`，`.venv` 已带）：

```powershell
.\.venv\Scripts\python.exe typing-desktop\scripts\gen_fsrs_fixtures.py
```

输出 `fixtures/fsrs-golden.json`。修改评分或调度规则时，同时修改 `srs_reference.py` 与 Rust 实现，重新生成并提交。

## 测试

在 `typing-desktop` 目录运行：

```powershell
cargo test
```

前端脚本测试在仓库根目录运行：

```powershell
node --test typing-desktop/frontend/src/app.test.cjs typing-desktop/frontend/src/stats.test.cjs typing-desktop/frontend/src/pronunciation.test.cjs typing-desktop/frontend/src/window-controls.test.cjs typing-desktop/frontend/src/updates.test.cjs
.\.venv\Scripts\python.exe -m unittest discover -s typing-desktop/scripts -p test_version.py
```

- `core/tests/golden.rs`：逐条比对 Rust 调度、评分与答案归一化结果。
- `core/tests/store.rs`：移植 `test_memory.py` / `test_app.py` 的练习用例（学习/重学/掌握、重试幂等、多标签冲突、自由练习、队列顺序、北京时间新词计数、过期与非法时间、参数变更重放、路由路径与 JSON）。
- `core/tests/media.rs`：按 SourceId 获取本地插图与英美单词读音（练习和统计明细可点击播放）、Anki note id 变化、缺失媒体、无哈希清单与资源包 URL 版本。
- `core/tests/stats.rs`：移植 `test_activity.py` / `test_vocabulary.py`（日历窗口与北京时间边界、到期分布、移出词库后的历史、近 30 天、连续天数、词库进度与平滑错误率排序、分页与参数校验、错误记录），并确认统计查询不写库。
- `core/tests/sync.rs`：两台设备经内存服务器同步（交错作答收敛为同一重放结果、重复同步不重传、小分页、离线失败不改数据后补传、服务器词库替换本地、合并使未提交题目失效、以及首次设置（地址与令牌校验、错误令牌不保存、保存后同步、只改地址保留令牌、环境变量配置不可修改、损坏的 `server.json`）。
- `frontend/src/app.test.cjs` 与 `stats.test.cjs`：使用共享的 `workspace.js` 验证两页设置、资源与同步，统计页同步后在原页刷新；前者另含首次设置弹窗（未配置时不可关闭、已配置跳过、错误令牌保留弹窗、保存后先同步再加载练习）。
- `frontend/src/window-controls.test.cjs`：窗口按钮调用原生操作，最大化／还原图标与名称随窗口状态更新；拖动、双击、缩放和关闭另在真实桌面窗口验证。
- `app/src/desktop.rs`：关闭偏好默认值、保存后重启、写入失败保留原值，以及托盘倒计时、到期、仅有新词和空计划的提示。真实窗口另检查关闭收进托盘、单击恢复、右键退出、直接退出偏好及隐藏后的练习计时。
- `app/src/tray_indicator.rs`：10 分钟边界、渐变进度、到期保持、完成后恢复、无计划及无效时间；像素测试检查从上到下填充、透明度及白色书页保留。真实托盘另检查正常、半橙、全橙及作答后恢复。
- `frontend/src/updates.test.cjs`：发现新版本、无更新、下载进度、安装前保存草稿、失败重试与未保存答案阻止安装；`scripts/test_version.py` 验证标签匹配、正式版格式与 Cargo 工作区/锁文件版本同步。
- `core/tests/optimize.rs`：移植 `test_optimizer.py` / `test_optimizer_service.py`（有效复习计数、时间留出不泄漏、1000 条门槛、每月跳过、启用后保留到期时间并接受未提交题目、重启恢复、失败与异常一天后重试、无效结果、退出中断恢复、接口），另用 fsrs-rs 实际训练一次合成数据。

`Cargo.toml` 对 `fsrs`、`ndarray` 在开发构建中开启优化，否则训练测试会慢很多。

## 插图与音频资源

安装包不包含大媒体。首次启动在同一窗口配置同步服务器并可选导入 `cijian-media.zip`；之后从“设置”更换。仅支持本地导入，资源包单独生成，不做逐文件 SHA 校验。导入后离线读取，未导入可先练习文字。详见 [独立媒体资源包](../docs/typing-desktop/MEDIA.md)。测试验证导入、失败保留、重启读取以及当前题目和输入保持。
