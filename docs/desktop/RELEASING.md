# Windows 版本发布与更新

## 版本号

桌面端唯一的版本来源是 `desktop/Cargo.toml` 中的 `[workspace.package].version`。壳、core、Tauri 安装包和程序显示均使用该值；不要另在 `tauri.conf.json` 或 `package.json` 添加版本。

使用正式版三段数字（如 `0.1.0`、`0.1.1`）：新增功能或改变使用方式时升第二段，只改样式或修复问题时升第三段。发布标签固定为 `desktop-v<版本>`，与后端镜像分开，由发布时自动创建，不手动打标签。

## 一个 PR 一次发布

每个改动桌面端的 PR 就是一次版本更新，PR 里同时带上：

1. 新版本号。在仓库根目录运行：

   ```powershell
   .\.venv\Scripts\python.exe desktop\scripts\version.py --set 0.7.1
   ```

   脚本同时通过 `cargo update --workspace --offline` 刷新 `Cargo.lock` 的本地包版本，不升级第三方依赖。需已安装 Rust 并下载过当前依赖。只读取版本可省略 `--set`。

2. 更新说明。在 [`desktop/CHANGELOG.md`](../../desktop/CHANGELOG.md) 最上面加一节 `## <版本号>`，写给使用者看。这一节就是 GitHub Release 的正文，也是程序内“设置 → 软件更新”显示的新版说明；那里按纯文本显示，所以只用列表，不加粗、不加标题。

推送前可在本机核对：`python3 desktop/scripts/version.py --check-release` 会对照远程已发布的 `desktop-v*` 标签，打印版本、是否为新版本（`new=true`）以及读到的更新说明。版本低于已发布的最新版，或新版本在 CHANGELOG 中没有对应一节时直接报错。

发布前先按 [桌面端测试](TESTING.md) 完成本轮相关测试，包括 Linux 上的真实窗口测试和 Windows 上的手工检查。PR 的 Windows 构建通过后合并到 master，同一工作流随即构建并发布，不需要再开升版本号的 PR，也不需要手动打标签。

只改同步服务器或仓库其他部分、不触及 `desktop/` 的 PR 不会触发桌面工作流，也就不需要升版本。

## GitHub Actions

`.github/workflows/windows-desktop.yml` 使用 Windows x64 runner 构建简体中文 NSIS 安装包。构建只需 Rust、Node、Python 和 Jinja2，不包含媒体资源，不运行独立测试任务；测试在本机完成。安装器与卸载器固定使用简体中文（NSIS `SimpChinese`），图标复用程序的 `app/icons/icon.ico`，由 `app/tauri.conf.json` 的 `bundle.windows.nsis` 配置。

工作流先运行 `version.py --check-release`：版本高于所有已发布的 `desktop-v*` 标签即为新版本，并读出 CHANGELOG 中这一版的说明。

| 触发方式 | 结果 |
| --- | --- |
| 分支上桌面代码或工作流变化（PR 构建） | 构建签名安装包，保存 Actions artifact，保留 14 天；版本号仍是已发布的版本时，最后一步失败，提示升版本号 |
| 合并到 master，且版本是新版本 | 构建、创建 Release 草稿（正文为 CHANGELOG 这一节，后附自动生成的 PR 链接），上传安装包、签名与 `latest.json`，全部成功后发布并设为 latest；发布时在该提交上创建 `desktop-v<版本>` 标签 |
| 合并到 master，但版本已发布 | 只构建 artifact，不发布 |
| Actions 页面手动运行 | 与所选分支推送时相同；在 master 上运行可重试一次失败的发布 |

桌面与现有 Docker 工作流独立。只有发布成功才会更新应用的下载源；分支构建不会让已安装程序升级。失败构建留下的草稿不会成为公开更新，也不会创建标签，修好后在 Actions 页面重新运行 master 的那次构建即可。

首个已发布版本为 `0.1.0`，标签为 `desktop-v0.1.0`；0.7.1 起改为合并即发布，此前的版本靠手动推送标签发布。每次发布递增版本；不要重新打包覆盖已经公开的同版本安装包。

## 更新签名

程序使用 Tauri updater 的签名验证，公钥写在 `app/tauri.conf.json`。安装包签名与媒体清单校验是两件事；媒体仍直接导入 ZIP。

仓库已配置两个 Actions secrets：`TAURI_SIGNING_PRIVATE_KEY` 和 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`。当前机器的备份保存在 `%USERPROFILE%\.tauri\cijian.key`、`cijian.key.pub` 与 `cijian-password.txt`，均在仓库之外。保留私钥与密码的备份，后续版本继续使用同一密钥，旧版程序才能验证新版。

本机生成带更新签名的安装包，在 `desktop` 目录执行：

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
