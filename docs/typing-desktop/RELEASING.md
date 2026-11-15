# Windows 版本发布与更新

## 版本号

桌面端唯一的版本来源是 `typing-desktop/Cargo.toml` 中的 `[workspace.package].version`。壳、core、Tauri 安装包和程序显示均使用该值；不要另在 `tauri.conf.json` 或 `package.json` 添加版本。

使用正式版三段数字（如 `0.1.0`、`0.1.1`）：新增功能或改变使用方式时升第二段，只改样式或修复问题时升第三段。发布标签固定为 `desktop-v<版本>`，与后端镜像分开。工作流在打包前核对标签与工作区版本，不一致就停止。

在仓库根目录更新版本：

```powershell
.\.venv\Scripts\python.exe typing-desktop\scripts\version.py --set 0.4.1
```

脚本同时通过 `cargo update --workspace --offline` 刷新 `Cargo.lock` 的本地包版本，不升级第三方依赖。需已安装 Rust 并下载过当前依赖。只读取版本可省略 `--set`。

当前发布版本为 `0.4.1`，主题是界面样式调整：

- 窗口改为纸色底加一张内容卡片，侧栏、标题栏与内容之间不再画分隔线；练习和统计内容直接排在卡片上，不再卡片套卡片。
- 按钮去掉边框，次按钮改为浅底；输入框聚焦只保留一圈边框；导航选中只用浅底表示。
- 设置改为分组卡片：关闭窗口行为用分段选择，开机自启动用开关，去掉多余的“完成”按钮。
- 前端接口改用相对路径 `/api`，桌面端也能在 Linux 上编译运行，用于开发调试。

同步服务器未改动，无需升级。安装包不包含独立插图与音频资源包，已有媒体无需重新导入。

这批改动曾以 `0.5.0` 发布，因只涉及样式，随即撤回并改以 `0.4.1` 重新发布；已删除 `desktop-v0.5.0` 的 Release 与标签。

## GitHub Actions

`.github/workflows/windows-desktop.yml` 使用 Windows x64 runner 构建简体中文 NSIS 安装包。构建只需 Rust、Node、Python 和 Jinja2，不包含媒体资源，不运行独立测试任务；测试在本机完成。安装器与卸载器固定使用简体中文（NSIS `SimpChinese`），图标复用程序的 `app/icons/icon.ico`，由 `app/tauri.conf.json` 的 `bundle.windows.nsis` 配置。

| 触发方式 | 结果 |
| --- | --- |
| 任意分支上桌面代码或工作流变化 | 构建签名安装包，保存 Actions artifact，保留 14 天 |
| Actions 页面手动运行 | 对所选 ref 构建 artifact，不发布 Release |
| 推送 `desktop-v*` 标签 | 核对版本、构建、创建 Release 草稿、上传安装包/签名/`latest.json`，全部成功后发布并设为 latest |

桌面与现有 Docker 工作流独立。只有正式标签发布会更新应用的下载源；普通提交不会让已安装程序升级。失败构建留下的草稿不会成为公开更新。

发布前先按 [桌面端测试](TESTING.md) 完成本轮相关测试，包括 Linux 上的真实窗口测试和 Windows 上的手工检查。功能改动与版本号放在同一个分支、同一个 PR：最后一个提交只更新版本号和本文的“当前发布版本”。PR 的 Windows 构建通过后合并到 master，再对 master 的最新提交打标签触发发布：

```powershell
git switch master
git pull --ff-only
git tag -a desktop-v0.4.1 -m "词间 v0.4.1"
git push origin desktop-v0.4.1
```

首个已发布版本为 `0.1.0`，标签为 `desktop-v0.1.0`。之后每次发布递增版本；不要重新打包覆盖已经公开的同版本安装包。工作流需在标签指向的提交中存在；Actions 页面手动运行还需工作流已进入默认分支。

## 更新签名

程序使用 Tauri updater 的签名验证，公钥写在 `app/tauri.conf.json`。安装包签名与媒体清单校验是两件事；媒体仍直接导入 ZIP。

仓库已配置两个 Actions secrets：`TAURI_SIGNING_PRIVATE_KEY` 和 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`。当前机器的备份保存在 `%USERPROFILE%\.tauri\cijian.key`、`cijian.key.pub` 与 `cijian-password.txt`，均在仓库之外。保留私钥与密码的备份，后续版本继续使用同一密钥，旧版程序才能验证新版。

本机生成带更新签名的安装包，在 `typing-desktop` 目录执行：

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY = Join-Path $env:USERPROFILE '.tauri\cijian.key'
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = [IO.File]::ReadAllText((Join-Path $env:USERPROFILE '.tauri\cijian-password.txt'))
npm ci
npm run tauri -- build --bundles nsis -- --locked
```

产物为 `target/release/bundle/nsis/Cijian_<版本>_x64-setup.exe` 及同名 `.sig`。`latest.json` 由 `tauri-apps/tauri-action` 在发布时生成，包含版本、安装包地址和签名。开发时直接 `cargo run -p cijian` 不生成安装包，不需要签名私钥。

## 程序内更新

每次打开练习页或统计页会后台检查 GitHub 的最新正式 Release；检查失败不打断练习。有更新时设置图标显示小圆点，辅助名称提示有可用更新。

在“设置 → 软件更新”中查看当前版本，手动检查、查看新版说明，点击“下载并重启”。下载展示进度，校验签名后启动安装器，应用退出，安装完成自动启动。安装过程使用 NSIS 的 passive 模式，无需逐步点击。失败保留当前程序，可重试。还有答案未保存时禁止安装；更新只替换程序文件，数据库、服务器设置和已导入媒体仍保存在原数据目录。

软件更新只在设置窗口展示，首次连接服务器的同步面板不展示更新区。软件更新固定来自 GitHub，与词库同步服务器及资源包导入无关。尚未发布首个 Release 时，自动检查安静失败，手动检查提示失败；发布第一个正式版后更新源才可用。

更新链路为：`GitHub Release latest.json → 检查版本 → 下载 NSIS → 验证签名 → 安装并重启`。发布后检查 Release 同时存在 `.exe`、`.sig` 与 `latest.json`，再用上一版实际升级验证；本机打包成功不代表远程 Actions 已运行。
