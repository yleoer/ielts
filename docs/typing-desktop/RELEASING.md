# Windows 版本发布与更新

## 版本号

桌面端唯一的版本来源是 `typing-desktop/Cargo.toml` 中的 `[workspace.package].version`。壳、core、Tauri 安装包和程序显示均使用该值；不要另在 `tauri.conf.json` 或 `package.json` 添加版本。

使用正式版三段数字（如 `0.1.0`、`0.1.1`）。发布标签固定为 `desktop-v<版本>`，与后端镜像分开。工作流在打包前核对标签与工作区版本，不一致就停止。

在仓库根目录更新版本：

```powershell
.\.venv\Scripts\python.exe typing-desktop\scripts\version.py --set 0.4.0
```

脚本同时通过 `cargo update --workspace --offline` 刷新 `Cargo.lock` 的本地包版本，不升级第三方依赖。需已安装 Rust 并下载过当前依赖。只读取版本可省略 `--set`。

当前发布版本为 `0.4.0`，主题是练习模式与同步改进：

- 新增“退出练习”按钮，点击或在输入框按 Esc 直接退出；保留已保存作答，未答词不计错。
- 新增“难点突破”和“久未练习”，分别选取最多 20 个历史错词和最久没练的词；两种模式不影响 FSRS、统计或下次复习时间。
- 托盘提醒在到期前 10 分钟由上向下逐渐填充橙色，到期后整枚变红。
- 同步历史统一由服务器每小时检查 Anki 后记录，桌面端缓存最近 50 批；升级时清空旧本机同步历史，保留作答与 FSRS 记录。
- 服务器地址和访问令牌移到“同步”面板；“设置”只管理启动与窗口、资源包和软件更新。

先升级同步服务器，再升级桌面端。服务器检查间隔默认改为 3600 秒，客户端升级本身不会更新服务端。安装包不包含独立插图与音频资源包，已有媒体无需重新导入。

本次发布经用户确认跳过 `typetest` 镜像检查，原因是本机无法解析该 SSH 主机名。同步服务已由 GitHub Actions 完成构建与部署。

## GitHub Actions

`.github/workflows/windows-desktop.yml` 使用 Windows x64 runner 构建简体中文 NSIS 安装包。构建只需 Rust、Node、Python 和 Jinja2，不包含媒体资源，不运行独立测试任务；测试在本机完成。

| 触发方式 | 结果 |
| --- | --- |
| 任意分支上桌面代码或工作流变化 | 构建签名安装包，保存 Actions artifact，保留 14 天 |
| Actions 页面手动运行 | 对所选 ref 构建 artifact，不发布 Release |
| 推送 `desktop-v*` 标签 | 核对版本、构建、创建 Release 草稿、上传安装包/签名/`latest.json`，全部成功后发布并设为 latest |

桌面与现有 Docker 工作流独立。只有正式标签发布会更新应用的下载源；普通提交不会让已安装程序升级。失败构建留下的草稿不会成为公开更新。

发布前先按 [桌面 README](../../typing-desktop/README.md#测试) 完成本轮相关测试，然后提交代码与版本，再对该提交打标签。例如：

```powershell
git add <本次相关文件>
git commit -m "发布桌面新版"
git tag desktop-v0.4.0
git push origin HEAD
git push origin desktop-v0.4.0
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

在“设置 → 软件更新”中查看当前版本，手动检查、查看新版说明，点击“下载并重启”。下载展示进度，校验签名后启动安装器，应用退出，安装完成自动启动。安装过程使用 NSIS 的 passive 模式，无需逐步点击。失败保留当前程序，可重试。还有答案未保存时禁止安装，安装前保存当前练习草稿；更新只替换程序文件，数据库、服务器设置和已导入媒体仍保存在原数据目录。

软件更新只在设置窗口展示，首次连接服务器的同步面板不展示更新区。软件更新固定来自 GitHub，与词库同步服务器及资源包导入无关。尚未发布首个 Release 时，自动检查安静失败，手动检查提示失败；发布第一个正式版后更新源才可用。

更新链路为：`GitHub Release latest.json → 检查版本 → 下载 NSIS → 验证签名 → 安装并重启`。发布后检查 Release 同时存在 `.exe`、`.sig` 与 `latest.json`，再用上一版实际升级验证；本机打包成功不代表远程 Actions 已运行。
