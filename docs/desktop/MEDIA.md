# 独立媒体资源包

这是个人自用项目。插图和音频单独分发为 `cijian-media.zip`，不随桌面安装包，发布在 GitHub Releases 的 `media-<版本>` 标签下（约 300MB）。服务器地址和令牌直接在“同步”面板配置，资源 ZIP 在“设置 → 插图与音频”中导入或更换。没有资源包也能先练习文字，不提供网络下载功能。资源包仍含插图，但练习页不再显示，避免靠图片记词。

同步服务器只提供词库和作答日志。资源按 Word Atlas 的稳定 `SourceId` 定位，导入不会修改学习记录。练习输入框旁的喇叭按钮（作答前点击即记为忘记，答案仍隐藏，可凭读音再拼一次）、显示后的英文答案与错题回顾，以及统计词库/日历明细中的单词可点击播放读音：先英音，结束后间隔 500 毫秒再播美音。可播放文字不显示下划线或悬停读音提示。只在点击时读取音频，再次点击重新播放；缺少一种口音时只播已有口音，无读音时不提供播放。切题、关闭统计明细、隐藏或离开页面时停止。

## 生成

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 deck/scripts/export_desktop_media.py --source D:/me/word-atlas-main
```

默认只生成 `desktop/media/cijian-media.zip`（已被 Git 忽略），可用 `--output` 指定目录。`--version` 指定资源包版本，默认当天日期，例如 `2026.11.19`；同一天需要再出一版时用 `2026.11.19.2`。

没有 Word Atlas 源项目、只需给已有资源包换版本号时，用 `--repack` 原样复制全部条目，只改清单里的版本：

```bash
.venv/bin/python -X utf8 deck/scripts/export_desktop_media.py --repack cijian-media.zip --version 2026.11.19
```

源项目需要 `data/word-atlas.json`、`dist/atlas/index.json`、`dist/atlas/img/`、`dist/atlas/audio/{uk,us}/` 和 `CONTENT_LICENSE.md`。导出复用 Anki 生成器的选择与命名规则，不需要 genanki 或生成 APKG。

完整数据保留 7,298 个 SourceId，应用 [本地修订表](../../deck/data/word-atlas-revisions/README.md) 后包含 21,890 个媒体：插图 7,298、美音 7,298、英音 7,294。4 个词头改写影响读音，使用新的美音并省略旧英音；其他拼写变体复用原读音，所有资源继续按原 SourceId 定位。不打包日常或雅思例句朗读。缺少某类媒体时省略该项。ZIP 使用固定时间戳与排序，临时文件组装完成后替换成品；再次导出直接重建，不做哈希缓存，不生成 `.sha256` 文件。

已有桌面端在“设置”中重新导入新版 `cijian-media.zip`，无需升级客户端或重置数据库。替代音频采用新的 `_revised.mp3` 文件名；服务器更新词头不会自动更新本地资源包。

## 清单与授权

ZIP 包含 `manifest.json`、媒体和 `CONTENT_LICENSE.md`、`ATTRIBUTION.txt`。清单记录资源包版本、资源类型及文件名，不含逐文件 SHA：

```json
{
  "format": 1,
  "version": "2026.11.19",
  "words": {
    "library": {
      "illustration": {"file": "wa_library_img.webp"},
      "audio_uk": {"file": "wa_library_uk.mp3"}
    }
  }
}
```

仅使用 `illustration`、`audio_uk`、`audio_us`；导入旧包时忽略额外的例句音频，不生成对应 URL，也不计入安装数量。单词、插图与录音来自 [Word Atlas](https://github.com/designfuchen/word-atlas)，资源署名为 **Word Atlas contributors — CC BY 4.0**；内容不改写，只改文件名。

## 版本

`version` 是点分数字，逐段按数值比较（`2026.11.19` < `2026.11.19.2` < `2026.12.1`）。导入时：

- 清单缺少版本号的包拒绝导入，提示从 GitHub Releases 下载新版；格式不对（如 `2026-11-19`）视为无法读取。
- 版本低于已安装的包时拒绝，提示两个版本号，已安装的包保持启用；同版本可以重新导入。
- 版本校验之前导入的旧包没有版本号，照常使用，设置里显示“未标注版本”，之后可换成任何带版本的包。

设置“插图与音频”显示已安装的插图、音频数量及版本（来自 `/api/resources/status` 的 `version`）。版本只用于防止误装回旧包，不参与媒体 URL 的缓存键，缓存键仍是每次安装的 UUID。

旧版桌面端（0.5.0 及以前）忽略清单中的 `version`，也能导入带版本的新包。

## 发布

资源包作为 Release 附件上传，不进 Git 仓库：

```bash
gh release create media-2026.11.19 desktop/media/cijian-media.zip --latest=false \
  --title '资源包 2026.11.19' --notes '桌面端“设置 → 插图与音频”导入，无需解压。'
```

必须带 `--latest=false`：桌面端自动更新读取 `releases/latest/download/latest.json`，资源包 Release 成为“最新版”会使检查更新失败。`media-*` 标签不触发任何工作流。换新版时发布新的标签，旧的 Release 可以删除。

## 导入与读取

- 本地文件按 4 MiB 分块复制到用户数据目录的 `media/<UUID>.part`，避免一次把整个资源包放入请求内存。保留基本的顺序和总大小检查，避免未复制完就启用。
- 复制完成后重命名为 `<UUID>.zip` 并读取清单，失败则删除该文件、保留原包；成功后用临时文件替换 `active.json` 并切换内存索引。无法打开 ZIP 或解析清单时保留原包，界面提示重新选择。
- 导入后立即可用，重启读取 `active.json`。每次安装的 UUID 用作媒体 URL 的 `v` 参数，更新资源时刷新缓存，不依赖文件哈希。
- 启动时读取不到已安装资源只记录错误，仍可进入设置重新导入；应用初始化本身直接返回实例，不增加空的错误传递层。
- 直接读取 ZIP 对应条目，不解压整包，不逐项扫描、计算或验证 SHA。文件缺失返回 404，ZIP 读取错误返回 503；使用 ZIP 库自身的正常解压处理。
- 仅支持此单 ZIP 格式。按自用场景，移除大小分级上限、成员白名单、多实例文件锁、后台安装线程、轮询和旧散文件兼容。没有网络下载，因此也没有断点续传或下载状态。
- 原包切换后尝试删除；若仍被一个请求占用，可能留下旧版本文件。未完成的上传可以取消后重新选择；重启不会继续上次上传。

`CIJIAN_MEDIA_DIR` 可覆盖保存目录，默认在应用数据目录下；`active.json` 是应用自行生成的资源记录。资源与学习数据库独立保存。

## 本地接口

| 接口 | 内容 |
| --- | --- |
| `GET /api/resources/status` | 已安装数量、导入进度及错误 |
| `POST /api/resources/upload` | `{size}` 开始导入，返回 `id/chunk_size` |
| `POST /api/resources/chunk?id=…&offset=…` | 写入二进制分块 |
| `POST /api/resources/finish?id=…` | 完成复制并启用资源 |
| `POST /api/resources/cancel?id=…` | 取消未完成的上传 |
| `POST /api/resources/urls` | `{ids}` 刷新当前词条媒体 URL，不重新出题 |
| `GET /api/media/source/<SourceId>/illustration?v=<版本>` | 本地插图；词条的 `illustration_url` 指向它 |
| `GET /api/media/source/<SourceId>/audio/<类型>?v=<版本>` | `uk/us`，只为存在的类型生成 URL；当前词库外的历史单词也按 SourceId 读取 |
| `GET /api/media/source/<SourceId>/audio` | 默认发音，优先英音，否则美音；原有 note id 媒体路径仍可读取 |

## 界面约定与验证

同步与设置沿用既有纸色、墨绿和系统字体；服务器表单位于同步面板，资源导入位于设置窗口，与启动、窗口及软件更新分区并列。资源区显示未导入/数量、导入进度、选择或更换资源包；不添加独立资源窗口和下载链接。打开设置暂停练习计时，关闭后恢复；导入只刷新媒体，保留当前题目、输入和作答状态。

```powershell
# 仓库根目录
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s deck/tests -p test_desktop_media.py -v
node --test desktop/frontend/src/app.test.cjs desktop/frontend/src/stats.test.cjs desktop/frontend/src/pronunciation.test.cjs
cd desktop
cargo test
npm run tauri -- build
```

测试关注英美顺序、500 毫秒间隔、重复点击与停止、媒体缺失与重试、SourceId 映射、无哈希清单、安装与重启读取、失败保留旧包、当前题目可继续提交，以及服务器配置与资源设置分离、分块导入。构建只需要前端，不需要 Word Atlas 源仓库；Windows 安装包在 `target/release/bundle/nsis/`。模板改动后在真实窗口检查首次连接、设置内资源导入和窄窗口布局。
