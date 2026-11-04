# 独立媒体资源包

这是个人自用项目。插图和音频单独分发为 `cijian-media.zip`，不随桌面安装包。首次启动的“首次设置”中，填写同步服务器地址、访问令牌，并可选导入本地 ZIP；之后从练习页“设置”或同步窗口的“设置”更换资源包。没有资源包也能先练习文字，不提供网络下载功能。

同步服务器只提供词库和作答日志。资源按 Word Atlas 的稳定 `SourceId` 定位，导入不会修改学习记录。练习的中文释义、显示后的英文答案与错题回顾，以及统计词库/日历明细中的单词可点击播放读音：先英音，结束后间隔 500 毫秒再播美音。可播放文字不显示下划线或悬停读音提示。只在点击时读取音频，再次点击重新播放；缺少一种口音时只播已有口音，无读音时不提供播放。切题、关闭统计明细、隐藏或离开页面时停止。

## 生成

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 apkg-generator/scripts/export_desktop_media.py --source D:/me/word-atlas-main
```

默认只生成 `typing-desktop/media/cijian-media.zip`，可用 `--output` 指定目录。源项目需要 `data/word-atlas.json`、`dist/atlas/index.json`、`dist/atlas/img/`、`dist/atlas/audio/{uk,us}/` 和 `CONTENT_LICENSE.md`。导出复用 Anki 生成器的选择与命名规则，不需要 genanki 或生成 APKG。

完整数据包含 7,298 个 SourceId、21,894 个媒体：插图、英音、美音各 7,298 个。不打包日常或雅思例句朗读；Anki APKG 保留原有全部音频。缺少某类媒体时省略该项。ZIP 使用固定时间戳与排序，临时文件组装完成后替换成品；再次导出直接重建，不做哈希缓存，不生成 `.sha256` 文件。

## 清单与授权

ZIP 包含 `manifest.json`、媒体和 `CONTENT_LICENSE.md`、`ATTRIBUTION.txt`。清单只记录资源类型及文件名，不含逐文件 SHA：

```json
{
  "format": 1,
  "words": {
    "library": {
      "illustration": {"file": "wa_library_img.webp"},
      "audio_uk": {"file": "wa_library_uk.mp3"}
    }
  }
}
```

仅使用 `illustration`、`audio_uk`、`audio_us`；导入旧包时忽略额外的例句音频，不生成对应 URL，也不计入安装数量。资源署名为 **Word Atlas contributors — CC BY 4.0**；内容不改写，只改文件名。

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

首次设置沿用既有纸色、墨绿和系统字体，服务器字段与可选资源导入合并在一个窗口。资源区显示未导入/数量、导入进度、选择或更换资源包；不添加独立资源窗口和下载链接。打开设置暂停练习计时，关闭后恢复；导入只刷新媒体，保留当前题目、输入和作答状态。

```powershell
# 仓库根目录
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s apkg-generator/tests -p test_desktop_media.py -v
node --test typing-desktop/frontend/src/app.test.cjs typing-desktop/frontend/src/stats.test.cjs typing-desktop/frontend/src/pronunciation.test.cjs
cd typing-desktop
cargo test
npm run tauri -- build
```

测试关注英美顺序、500 毫秒间隔、重复点击与停止、媒体缺失与重试、SourceId 映射、无哈希清单、安装与重启读取、失败保留旧包、当前题目可继续提交，以及首次设置与分块导入。构建只需要前端，不需要 Word Atlas 源仓库；Windows 安装包在 `target/release/bundle/nsis/`。模板改动后在真实窗口检查首次设置、导入和窄窗口布局。
