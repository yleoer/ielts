# 同步服务概览

`typing-practice/backend` 是桌面端“词间”的精简同步服务（Python 3.12+、Flask、SQLite）。它只读读取 Anki `collection.anki2` 提供词库，保存多设备共享的只追加作答日志，并定时从 anki-sync-server 复制数据库。判题、FSRS 调度、统计、参数优化、页面和插图都在桌面端，见 [桌面端设计](../typing-desktop/DESIGN.md)。

## 模块

| 文件 | 职责 |
| --- | --- |
| `app.py` | 路由、错误处理、后台复制 Anki 数据库、Waitress 启动入口 |
| `anki.py` | 只读解析 Word Atlas 22 字段笔记，生成词库快照 |
| `ledger.py` | 作答日志表、上传校验、去重与分页、网页版历史导入 |
| `auth.py` | Bearer 访问令牌 |
| `sync.py` | 选择并复制最新的 `collection.anki2` 及 SQLite 附属文件 |
| `config.py` | YAML、`.env` 与环境变量配置 |

依赖为 Flask、Waitress、PyYAML、python-dotenv；不再安装 `fsrs[optimizer]` 或 PyTorch。`python app.py` 通过 Waitress 启动生产 WSGI 服务，沿用现有监听配置、后台复制任务与退出时的数据库关闭流程。

## API

所有响应为 `{success, data}` 或 `{success:false, error}`。

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 公开健康检查，返回 `status: ok` |
| `GET /api/vocab` | Word Atlas 词库完整快照；Anki 数据库不可用时返回 503 |
| `POST /api/sync` | 上传作答并按游标读取作答日志 |

其他路径（包括原 `/`、`/stats.html`、`/api/stats/*`、`/api/media/*`）返回 404。

### 词库快照

`GET /api/vocab` 返回 `{"format":1,"generated_at","deck_name","words":[...]}`。`words` 包含配置牌组及子牌组的全部有效词条，每项带 `learned`（Anki 中是否已学习）和 `illustration_file`（保留兼容的插图文件名）。桌面端按 `source_id` 查询自行导入的独立资源包清单读取插图和音频，不依赖服务端文件名，见 [独立媒体资源包](../typing-desktop/MEDIA.md)。词条字段沿用 Word Atlas 映射：`id`（Anki note_id）、`source_id`、`word`、`phonetic`、`part_of_speech`、`chinese_meaning`、`chinese_senses`、`example_en` / `example_cn`、`category`（Topic）、`cefr`。HTML 先去标签再解码实体，不返回音频。每次返回完整快照，没有增量游标。

词库读取精确标签 `word_atlas::excluded`，将这些笔记从完整快照排除，包含已学和暂停的重复项；普通暂停或 leech 不改变原同步规则。若过滤项已学，`word_atlas::canonical::<SourceId>` 指定的保留项 `learned=true`，只继承进入练习池的资格，不改写 Anki 卡片状态，不合并既有作答或 FSRS 历史。词头修订沿用原 `source_id`，接口格式和字段保持不变。

### 作答日志

请求体为 `{"device_id", "cursor", "attempts":[...]}`，每次最多上传 500 条。每条作答包含：

| 字段 | 说明 |
| --- | --- |
| `attempt_id` | 全局唯一，去重依据 |
| `word_key` | `word-atlas:<SourceId>` |
| `word` / `chinese_meaning` / `category` / `user_input` | 作答时的词条快照与输入 |
| `is_correct` | 布尔值 |
| `rating` | 1–4 |
| `reviewed_at` | 带时区的时间，统一存为 UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ` |
| `duration_ms` / `first_input_ms` | 非负有限数，`first_input_ms` 可为空 |

任一条无效时返回 400，整批不写入。有效作答写入只追加的 `attempts` 表，按 `attempt_id` 去重，先到的一份生效。响应为 `{"accepted","duplicates","attempts","next_cursor","more"}`：`attempts` 是 `cursor` 之后最多 500 条日志（含本次上传的作答），`next_cursor` 为本页最后一行的服务端行号（递增、可能不连续），`more` 表示还有后续页。客户端循环请求直到 `more` 为假。

服务端不调度卡片；桌面端合并后按 `reviewed_at, attempt_id` 重放受影响词条。

## 访问令牌

除 `/api/health` 外需要 `Authorization: Bearer <ACCESS_TOKEN>`，否则返回 401（`code: authentication_required`）。`ACCESS_TOKEN` 为空时沿用旧的 `ACCESS_PASSWORD`，两者都为空则不校验。

## 数据与迁移

作答日志保存在 `STATS_DB_PATH`（沿用旧统计库路径）。首次启动时，若同一数据库中存在网页版的 `word_reviews` 表，按 `reviewed_at` 顺序一次性导入 `attempts`（`device_id` 为 `web`），并在 `ledger_migrations` 记录 `web-history-v1`；之后不再导入。旧网页版的表原样保留，不会删除。

配置来自 `backend/config/config.yaml`、`typing-practice/.env` 和进程环境变量，环境变量优先；变量列表见 [typing-practice/README.md](../../typing-practice/README.md)。设置 `ANKI_SYNC_SOURCE_DIR` 与 `ANKI_SYNC_TARGET` 后，后台线程在首次等待后按间隔复制最新数据库并重新打开读取器。

Python 单元测试在本机按改动范围运行，镜像冒烟检查统一在 SSH 测试机 `typetest` 运行；GitHub Actions 只负责构建、发布和部署。详见 [测试范围](TESTING.md)、[镜像验证](IMAGE-CHECK.md)、[部署](DOCKER-DEPLOY.md)。
