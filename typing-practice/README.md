# typing-practice

`typing-practice` 是桌面端“词间”（[typing-desktop](../typing-desktop/README.md)）的精简同步服务，基于 Python Flask + SQLite。它只做三件事：

- 只读读取 Anki `collection.anki2`，通过 `GET /api/vocab` 提供 Word Atlas 词库快照；
- 通过 `POST /api/sync` 保存各设备上传的作答，并按游标返回完整作答日志；
- 定时从 anki-sync-server 的数据目录复制最新 `collection.anki2`。

练习页、统计页、插图、FSRS 调度与参数优化都在桌面端运行，服务端不再提供页面、媒体或统计接口。接口与数据见 [服务概览](../docs/typing-practice/SPEC.md)。

## 本地 Python 运行

需要 Python 3.12 或更高版本，依赖只有 Flask、PyYAML、python-dotenv。在仓库根目录：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r typing-practice\backend\requirements.txt

$env:ANKI_DB_PATH = "$env:APPDATA\Anki2\User 1\collection.anki2"
$env:STATS_DB_PATH = (Join-Path (Get-Location) 'typing-practice\data\stats\stats.db')
$env:ACCESS_TOKEN = '自己的令牌'

.\.venv\Scripts\python.exe typing-practice\backend\app.py
```

默认监听 <http://127.0.0.1:8080>。默认读取 `Word Atlas` 牌组（生成时 ID `1958430017`），优先按名称解析实际导入后的牌组和子牌组；只支持 Word Atlas 的 22 字段结构。`ANKI_DECK_NAME` / `ANKI_DECK_ID` 可覆盖。

配置来自 `backend/config/config.yaml`、`typing-practice/.env` 和进程环境变量，环境变量优先：

| 变量 | 说明 |
| --- | --- |
| `SERVER_HOST` / `SERVER_PORT` | 监听地址，默认 `localhost:8080` |
| `ANKI_DB_PATH` | 读取的 `collection.anki2`；留空时查找 `%APPDATA%\Anki2` 下的配置文件 |
| `ANKI_DECK_NAME` / `ANKI_DECK_ID` | 词库牌组 |
| `STATS_DB_PATH` | 作答日志数据库，沿用旧统计库路径，默认 `data/stats.db` |
| `ACCESS_TOKEN` | 访问令牌；留空时沿用旧的 `ACCESS_PASSWORD`，两者都为空则不校验 |
| `ANKI_SYNC_SOURCE_DIR` / `ANKI_SYNC_TARGET` | 同时设置才启用定时复制 Anki 数据库 |
| `ANKI_SYNC_INTERVAL_SECONDS` / `ANKI_SYNC_INITIAL_WAIT_SECONDS` / `ANKI_SYNC_STABLE_SECONDS` | 复制间隔（默认 300）、首次等待（默认 60）、源文件稳定等待（默认 2） |

## 访问令牌

除 `/api/health` 外，请求需带 `Authorization: Bearer <ACCESS_TOKEN>`，否则返回 401（`code: authentication_required`）。`ACCESS_TOKEN` 为空时使用旧的 `ACCESS_PASSWORD`，升级后不会意外开放；两者都为空时不校验，启动日志会给出警告。原网页登录页与 Cookie 凭证已移除，`.access-secret` 不再使用。公网部署应通过 HTTPS 访问。

桌面端首次启动时填写本服务的地址和 `ACCESS_TOKEN`（也可用 `CIJIAN_SERVER_URL` / `CIJIAN_SERVER_TOKEN` 预先指定），见 [typing-desktop/README.md](../typing-desktop/README.md)。

## 从本地同步目录读取

同步源目录下需要有 `collection.anki2`；服务会把它及 SQLite 附属文件复制到目标路径后再读取。

```powershell
$root = (Get-Location).Path
$env:ANKI_SYNC_SOURCE_DIR = Join-Path $root 'typing-practice\data\anki-sync'
$env:ANKI_SYNC_TARGET = Join-Path $root 'typing-practice\data\anki-cache\collection.anki2'
$env:ANKI_DB_PATH = $env:ANKI_SYNC_TARGET
$env:ANKI_SYNC_INITIAL_WAIT_SECONDS = '0'
$env:ANKI_SYNC_STABLE_SECONDS = '0'
$env:STATS_DB_PATH = Join-Path $root 'typing-practice\data\stats\stats.db'

.\.venv\Scripts\python.exe typing-practice\backend\app.py
```

本地 Python 进程不会启动 `anki-sync` 容器。需要 Anki 客户端通过同步协议上传数据时使用 Docker Compose。

## 启动检查

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/health
$headers = @{ Authorization = "Bearer $env:ACCESS_TOKEN" }
(Invoke-RestMethod http://127.0.0.1:8080/api/vocab -Headers $headers).data.words.Count
```

`/api/health` 应返回 `status: ok`。`/api/vocab` 返回 503 表示 Anki 数据库不可读；词数为 0 时检查 `ANKI_DECK_NAME`、`ANKI_DECK_ID` 是否与数据库中的牌组一致。

## 网页版历史

首次启动时，若 `STATS_DB_PATH` 中存在网页版的 `word_reviews` 表，会一次性导入作答日志（设备 `web`，迁移记录 `web-history-v1`），桌面端同步后按日志重放得到记忆状态。旧表原样保留，不会删除。

## 本地测试

在仓库根目录运行；选择方法见 [测试范围](../docs/typing-practice/TESTING.md)：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

## Docker

标准部署使用 `docker-compose.yml`，本地构建使用 `docker-compose.local-build.yml`，见 [Docker 部署](../docs/typing-practice/DOCKER-DEPLOY.md)。两份 Dockerfile 自动复制后端 `*.py`（`.dockerignore` 排除测试文件），构建时导入应用检查依赖。镜像检查统一通过 SSH 在 `typetest` 执行 `scripts/check_image.py`，见 [镜像验证](../docs/typing-practice/IMAGE-CHECK.md)。GitHub Actions 只负责构建、推送多架构镜像和部署。
