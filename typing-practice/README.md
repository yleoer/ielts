# typing-practice

`typing-practice` 是一个 Python Flask 单体应用。Flask/Jinja2 负责页面和接口，SQLite 保存练习统计，Python 内置 `sqlite3` 只读读取 Anki `collection.anki2`。

## 本地 Python 部署

应用需要 Python 3.12 或更高版本。在仓库根目录创建虚拟环境并安装依赖：

```powershell
cd D:\workshop\ielts
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r typing-practice\backend\requirements.txt
```

### 直接读取 Anki 数据库

这种方式不启动 Anki 同步服务，只读取已有的 `collection.anki2`。默认读取 `Word Atlas` 牌组，生成时的牌组 ID 为 `1958430017`；会优先按名称解析实际导入后的牌组和子牌组。只支持 Word Atlas 的 22 字段结构。

```powershell
$env:ANKI_DB_PATH = "$env:APPDATA\Anki2\User 1\collection.anki2"
$env:ANKI_DECK_NAME = 'Word Atlas'
$env:ANKI_DECK_ID = '1958430017'
$env:STATS_DB_PATH = (Join-Path (Get-Location) 'typing-practice\data\stats\stats.db')

.\.venv\Scripts\python.exe typing-practice\backend\app.py
```

默认访问 <http://127.0.0.1:8080>。页面、静态文件和 API 都由同一个 Flask 进程提供，不需要单独启动前端开发服务器。

### 插图与发音

卡片依次显示 200px 圆角插图、同一行的词性与中文含义、播放发音按钮，然后显示输入框。发音只在点击按钮时播放，优先英音 `AudioUK`，为空时使用美音 `AudioUS`；切换单词或退出练习会停止播放。插图缺失或加载失败时隐藏，音频字段为空时按钮禁用，播放失败时给出提示。

直接读取 Anki 时，媒体目录默认为数据库旁的 `collection.media/`。如数据库是复制的缓存，需指定原始媒体目录，例如：

```powershell
$env:ANKI_MEDIA_DIR = "$env:APPDATA\Anki2\账户 1\collection.media"
```

也可以在 YAML 的 `anki.media_dir` 设置路径；环境变量优先。媒体通过受访问密码保护的 `/api/media/<note_id>/illustration` 和 `/api/media/<note_id>/audio` 提供，只返回该笔记引用的本地图片或音频，不执行字段内的 HTML。

### 首次访问密码

复制 `typing-practice/.env.example` 为同目录下的 `.env`，设置 `ACCESS_PASSWORD` 为自己的访问密码。Python 启动时自动读取该文件，Docker Compose 也使用同一文件；进程已有环境变量优先。`.env` 不提交到 Git。也可以在启动 Python 前设置 `$env:ACCESS_PASSWORD = '自己的密码'`。留空表示关闭访问验证。

设置后，首次打开练习页或统计页会进入密码界面。验证成功后自动返回原页面，并用有效期 10 年的 HttpOnly Cookie 在浏览器本地保存凭证，不保存明文密码；同一浏览器后续访问无需再次输入。换浏览器、清除站点 Cookie 或使用无痕窗口时需要重新验证。

修改密码并重启服务后，旧凭证会失效。服务会在统计数据库同目录生成私有 `.access-secret` 文件，需与数据库一起保留，保证重启后仍记住浏览器；删除该文件也会让已有凭证失效。该文件不提交到 Git。

业务 API 未验证时返回 HTTP 401（`code: authentication_required`），外部脚本需先向 `/login` 提交 `password` 表单并保留响应 Cookie。`/api/health` 保持公开供容器健康检查使用。HTTPS 访问会为登录 Cookie 设置 Secure；公网部署应通过 HTTPS 访问。

### 从本地同步目录读取

如果希望使用页面上的“同步 Anki”按钮，必须同时配置同步源和目标路径。同步源目录下需要存在 `collection.anki2`；Python 服务会把它复制到缓存目录后再读取。

```powershell
$root = (Get-Location).Path
$env:ANKI_SYNC_SOURCE_DIR = Join-Path $root 'typing-practice\data\anki-sync'
$env:ANKI_SYNC_TARGET = Join-Path $root 'typing-practice\data\anki-cache\collection.anki2'
$env:ANKI_DB_PATH = $env:ANKI_SYNC_TARGET
$env:ANKI_DECK_NAME = 'Word Atlas'
$env:ANKI_DECK_ID = '1958430017'
$env:ANKI_SYNC_STABLE_SECONDS = '0'
$env:STATS_DB_PATH = Join-Path $root 'typing-practice\data\stats\stats.db'

.\.venv\Scripts\python.exe typing-practice\backend\app.py
```

可以先关闭 Anki，再把数据库复制到同步目录：

```powershell
Copy-Item `
  "$env:APPDATA\Anki2\User 1\collection.anki2" `
  'typing-practice\data\anki-sync\collection.anki2'
```

本地 Python 进程不会启动 `anki-sync` 容器。如果需要 Anki 客户端通过同步协议上传数据，仍需使用 Docker Compose；同步完成后，Python 服务读取 `typing-practice/data/anki-sync/` 中的数据库。

### 启动检查

启动后可以执行以下命令：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/health
Invoke-RestMethod http://127.0.0.1:8080/api/config
Invoke-RestMethod http://127.0.0.1:8080/api/sync/status
Invoke-RestMethod 'http://127.0.0.1:8080/api/words?limit=20'
```

`/api/health` 应返回 `status: ok`。如果同步接口提示 `Anki sync source is not configured`，说明启动进程没有同时设置 `ANKI_SYNC_SOURCE_DIR` 和 `ANKI_SYNC_TARGET`。如果同步成功但单词列表为空，请检查 `ANKI_DECK_NAME`、`ANKI_DECK_ID` 是否与数据库中的牌组一致，以及牌组中是否有已学习卡片。

如果进程中已有旧的 `ANKI_DECK_NAME` / `ANKI_DECK_ID`，需更新为 Word Atlas 配置；环境变量会覆盖默认 YAML。刚导入但还未在 Anki 学习的卡片不会进入练习池。

## Word Atlas 字段

按 Word Atlas 的固定 22 字段顺序读取，不兼容旧词表牌组格式：

| Word Atlas 字段 | 练习接口字段 |
| --- | --- |
| `Word` | `word` |
| `UK`（为空时使用 `US`） | `phonetic` |
| `PartOfSpeech` | `part_of_speech` |
| `MeaningZH` | `chinese_meaning` |
| `ExampleEN` / `ExampleZH` | `example_en` / `example_cn` |
| `Topic` | `category` |
| `Illustration` 的 `<img src>` | `illustration_url` |
| `AudioUK`（为空时使用 `AudioUS`）的 `[sound:...]` | `audio_url` |

词条文字中的 HTML 排版会转换为纯文本。页面去掉可见的“IELTS 打字练习”标题；浏览器标签分别为“打字练习”和“学习统计”。插图、词性与释义、发音按钮按参考卡片顺序排列，保留现有页面配色和答题流程。

正式版草稿使用 `typingPracticeDraftSession:wordAtlas:v2`，保留媒体链接，避免恢复缺少媒体字段的旧草稿及本地演示数据；历史统计保留。测试命令为：

```powershell
python -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

## Docker

标准部署仍使用 `docker-compose.yml`；本地构建使用 `docker-compose.local-build.yml`。应用和页面在同一个 Flask 进程中运行，不需要单独启动前端开发服务器。

Compose 将 `typing-practice/data/anki-media/` 只读挂载到 `/app/anki-media`。把 Anki 的 `collection.media/` 文件复制到该目录，保留原文件名；媒体文件不提交 Git。当前数据库同步只复制 `collection.anki2` 及其 SQLite 附属文件，不自动复制媒体目录；新增媒体需要同步更新该目录。

