# 同步服务概览

`typing-practice/backend` 是桌面端“词间”的精简同步服务（Python 3.12+、Flask、SQLite）。它只读读取 Anki `collection.anki2` 提供词库，保存多设备共享的只追加作答日志，并定时从 anki-sync-server 复制数据库。判题、FSRS 调度、统计、参数优化、页面和插图都在桌面端，见 [桌面端设计](../typing-desktop/DESIGN.md)。

## 模块

| 文件 | 职责 |
| --- | --- |
| `app.py` | 路由、错误处理、后台复制并检查 Anki 数据库、Waitress 启动入口 |
| `anki.py` | 只读解析 Word Atlas 22 字段笔记，生成词库快照 |
| `ledger.py` | 作答日志表、上传校验、去重与分页、网页版历史导入 |
| `vocabulary.py` | 持久化最近成功词库快照、已发现的已学 SourceId 和新增词批次 |
| `auth.py` | Bearer 访问令牌 |
| `sync.py` | 选择并复制最新的 `collection.anki2` 及 SQLite 附属文件 |
| `config.py` | YAML、`.env` 与环境变量配置 |

依赖为 Flask、Waitress、PyYAML、python-dotenv；不再安装 `fsrs[optimizer]` 或 PyTorch。`python app.py` 通过 Waitress 启动生产 WSGI 服务，沿用现有监听配置、后台复制任务与退出时的数据库关闭流程。

## API

所有响应为 `{success, data}` 或 `{success:false, error}`。

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 公开健康检查，返回 `status: ok` |
| `GET /api/vocab` | 最近成功检查的完整词库快照、最近 50 批新增历史；尚无快照时返回 503 |
| `POST /api/sync` | 上传作答并按游标读取作答日志 |

其他路径（包括原 `/`、`/stats.html`、`/api/stats/*`、`/api/media/*`）返回 404。

### 词库快照

`GET /api/vocab` 返回 `{"format":1,"generated_at","last_anki_sync_at","deck_name","words":[...],"sync_history":[...]}`。`generated_at` 与 `last_anki_sync_at` 均为最近成功检查的 UTC 时间，接口读取不触发 Anki 扫描或写库。`words` 包含配置牌组及子牌组的全部有效词条，每项带 `learned`（Anki 中是否已学习）和 `illustration_file`（保留兼容的插图文件名）。桌面端按 `source_id` 查询自行导入的独立资源包清单读取插图和音频，不依赖服务端文件名，见 [独立媒体资源包](../typing-desktop/MEDIA.md)。词条字段沿用 Word Atlas 映射：`id`（Anki note_id）、`source_id`、`word`、`phonetic`、`part_of_speech`、`chinese_meaning`、`chinese_senses`、`example_en` / `example_cn`、`category`（Topic）、`cefr`。HTML 先去标签再解码实体，不返回音频。每次返回完整快照，没有增量游标。

`sync_history` 按服务器批次 ID 倒序返回最近 50 批：每批包含 `id`、`synced_at`、`before_words`、`after_words`、`added_words`、`added_word_list`。词表保存发现时的 `id/source_id/word/chinese_meaning/category`，后续词头或释义修改不会改写历史。只有首次进入服务器已发现集合的已学 SourceId 产生新增批次；无新增、重复检查、note_id 变化、移出后重新进入或重置后再学习都不重复计数。`before_words/after_words` 是前后快照的当前已学词数，新增数不一定等于两者之差。

首次成功检查只建立基线，即使词池为空也完成初始化，不产生新增历史。服务器保留全部历史，只限制接口返回条数。词库快照、已发现集合和新增批次在同一事务提交，检查失败不更新快照或检查时间，已有快照仍可读取。历史记录服务器发现时间，不能还原真实 Anki 首次学习时间。

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

词库数据同样保存在 `STATS_DB_PATH`：`vocabulary_snapshot` 保存最新成功快照及检查时间，`anki_learned_words` 保存曾经发现过的已学 SourceId，`vocabulary_sync_history` 保存新增批次。

配置来自 `backend/config/config.yaml`、`typing-practice/.env` 和进程环境变量，环境变量优先；变量列表见 [typing-practice/README.md](../../typing-practice/README.md)。启动时先检查已有数据库，后台线程首次等待默认 60 秒、检查间隔默认 3600 秒。设置 `ANKI_SYNC_SOURCE_DIR` 与 `ANKI_SYNC_TARGET` 后，每次先复制最新数据库再检查；否则直接检查 `ANKI_DB_PATH`。部署时先升级服务器，再升级桌面端。

Python 单元测试在本机按改动范围运行，镜像冒烟检查统一在 SSH 测试机 `typetest` 运行；GitHub Actions 只负责构建、发布和部署。详见 [测试范围](TESTING.md)、[镜像验证](IMAGE-CHECK.md)、[部署](DOCKER-DEPLOY.md)。
