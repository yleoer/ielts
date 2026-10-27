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

这种方式不启动 Anki 同步服务，只读取已有的 `collection.anki2`。如果使用当前同步库中的牌组，牌组名称和 ID 应设置为 `IELTS` 与 `1793085454896`；其他数据库请改成实际牌组信息。

```powershell
$env:ANKI_DB_PATH = "$env:APPDATA\Anki2\User 1\collection.anki2"
$env:ANKI_DECK_NAME = 'IELTS'
$env:ANKI_DECK_ID = '1793085454896'
$env:STATS_DB_PATH = (Join-Path (Get-Location) 'typing-practice\data\stats\stats.db')

.\.venv\Scripts\python.exe typing-practice\backend\app.py
```

默认访问 <http://127.0.0.1:8080>。页面、静态文件和 API 都由同一个 Flask 进程提供，不需要单独启动前端开发服务器。

### 从本地同步目录读取

如果希望使用页面上的“同步 Anki”按钮，必须同时配置同步源和目标路径。同步源目录下需要存在 `collection.anki2`；Python 服务会把它复制到缓存目录后再读取。

```powershell
$root = (Get-Location).Path
$env:ANKI_SYNC_SOURCE_DIR = Join-Path $root 'typing-practice\data\anki-sync'
$env:ANKI_SYNC_TARGET = Join-Path $root 'typing-practice\data\anki-cache\collection.anki2'
$env:ANKI_DB_PATH = $env:ANKI_SYNC_TARGET
$env:ANKI_DECK_NAME = 'IELTS'
$env:ANKI_DECK_ID = '1793085454896'
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

## Docker

标准部署仍使用 `docker-compose.yml`；本地构建使用 `docker-compose.local-build.yml`。应用和页面在同一个 Flask 进程中运行，不需要单独启动前端开发服务器。

