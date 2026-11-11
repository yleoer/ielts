# Docker 部署

这是 `typing-practice` 同步服务的标准 Docker Compose 部署说明。

## 服务

- `anki-sync`：接收 Anki 客户端同步数据
- `typing-practice`：为桌面端提供词库快照和作答日志同步

同步服务使用 Docker Hub 上的预构建镜像，镜像内只有 Flask、Waitress、PyYAML、python-dotenv，不含 FSRS 或 PyTorch。默认命令仍为 `python app.py`，由 Waitress 提供生产 WSGI 服务，监听地址沿用 `SERVER_HOST` / `SERVER_PORT`。

## 运行文件

- `typing-practice/.env.example`
- `typing-practice/docker-compose.yml`
- `typing-practice/data/anki-sync/`：anki-sync-server 数据，只读挂载到 `/app/anki-sync`
- `typing-practice/data/anki-cache/`：复制出的 `collection.anki2`
- `typing-practice/data/stats/`：作答日志数据库 `stats.db`

## 运行模型

- Anki 数据先进入同步服务。
- 启动时检查已有缓存；后台任务在 `ANKI_SYNC_INITIAL_WAIT_SECONDS`（默认 60）后，每 `ANKI_SYNC_INTERVAL_SECONDS`（默认 3600，即 1 小时）秒把最新 `collection.anki2` 复制到缓存，检查新增已学词并保存历史。首次成功检查建立基线，不把累计已学词记成当天新增。

升级此流程时先升级同步服务器，再升级桌面端。已有 `.env` 若显式设置 `ANKI_SYNC_INTERVAL_SECONDS=300`，需改为 `3600` 才会使用小时周期；部署目录的 Compose 默认值也应同步更新。自动部署不复制 Compose 或 `.env`。服务器新增历史从建立基线后开始，不从旧桌面记录回填；`data/stats/` 继续保留作答、词库快照和服务器新增历史。Anki 检查失败时保留最近成功快照，接口的 `last_anki_sync_at` 可用于判断是否滞后。
- `/api/vocab` 返回缓存中 Word Atlas 的完整词库快照；`/api/sync` 读写 `stats.db` 中的只追加作答日志，容器重启后不丢失。
- 不提供页面、插图、FSRS 或统计；这些在桌面端运行。
- 除 `/api/health` 外需要 `Authorization: Bearer <ACCESS_TOKEN>`。

## 常见检查

- 确认同步服务已有数据，缓存里的 `collection.anki2` 存在
- 确认容器能读写 `/app/stats`
- 确认 `.env` 里的 `ACCESS_TOKEN` 与桌面端配置一致
- 确认 `.env` 里的镜像标签是目标版本

```bash
curl -fsS http://127.0.0.1:8080/api/health
curl -fsS -H "Authorization: Bearer $ACCESS_TOKEN" http://127.0.0.1:8080/api/vocab | head -c 200
```

## 从网页版升级到同步服务

本版本移除了网页练习、统计页、插图接口和服务端 FSRS。在实际部署目录完成以下准备：

1. 在 `.env` 中设置 `ACCESS_TOKEN`（建议使用新的长随机值），并在各桌面端配置相同令牌。未设置时沿用旧的 `ACCESS_PASSWORD`，不会因升级而开放访问。
2. 同步最新版 `docker-compose.yml`，或在自有 Compose 文件中为 `typing-practice` 服务传入 `ACCESS_TOKEN`。`anki-media` 挂载与 `ANKI_MEDIA_DIR`、全部 `FSRS_*` 变量已不再使用，可以删除；保留也会被忽略。`data/anki-media/` 目录可在确认不再需要后自行清理。
3. 保留 `data/stats/`。首次启动时，`stats.db` 中网页版的 `word_reviews` 会一次性导入作答日志（迁移记录 `web-history-v1`），桌面端首次同步后即可得到原有记忆与统计。旧表原样保留，不会删除；`fsrs-optimization/` 与 `.access-secret` 不再使用。
4. 等待目标版本镜像构建完成，再设置 `.env` 中的 `TYPING_PRACTICE_IMAGE_TAG`。自动部署会填写提交 SHA；手动部署可填写已发布的 SHA 或 `latest`。

在包含 Compose 文件和 `.env` 的目录中执行：

```bash
docker compose config --quiet
docker compose pull typing-practice
docker compose up -d --no-deps typing-practice
docker compose ps typing-practice
docker compose logs --tail=100 typing-practice
```

此操作只更新同步服务，无需重启 `anki-sync`。仅执行 `restart` 不会应用新的镜像或环境变量。升级前建议备份整个 `data/stats/`。

GitHub Actions 自动部署仅修改镜像标签、拉取镜像和重建练习容器，**不会同步服务器 Compose 文件或 `.env`**；以上准备需单独完成。推送到远端 `master` 后才会触发镜像构建，并在部署密钥已配置时执行部署。

## 排障

- `/api/vocab` 返回 503：缓存数据库不存在或不可读，检查同步目录与挂载；同步延迟通常只是初始等待时间未过。
- 词数为 0：检查 Anki 中是否已导入并同步 Word Atlas 牌组，以及 `ANKI_DECK_NAME` / `ANKI_DECK_ID`。
- 401：桌面端令牌与 `ACCESS_TOKEN`（或旧 `ACCESS_PASSWORD`）不一致。
- 历史未出现在桌面端：确认 `STATS_DB_PATH` 指向原 `stats.db`，并检查 `ledger_migrations` 表中的 `web-history-v1` 记录（`detail` 含导入条数）。

## 相关文档

- [服务概览](SPEC.md)
- [自动部署](AUTO-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
- [桌面端说明](../../typing-desktop/README.md)
