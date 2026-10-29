# Docker 部署

这是 `typing-practice` 的标准 Docker Compose 部署说明。

## 服务

- `anki-sync`：接收 Anki 客户端同步数据
- `typing-practice`：提供练习页面和统计接口

练习服务使用 Docker Hub 上的预构建镜像，镜像内运行 Python Flask 单体应用。

## 运行文件

- `typing-practice/.env.example`
- `typing-practice/docker-compose.yml`
- `typing-practice/data/anki-sync/`
- `typing-practice/data/anki-cache/`
- `typing-practice/data/anki-media/`：从 Anki `collection.media/` 复制的插图，保留原文件名；只读挂载到 `/app/anki-media`
- `typing-practice/data/stats/`

## 运行模型

- Anki 数据先进入同步服务。
- 练习服务再把同步结果复制到本地缓存。
- 统计数据保存在 SQLite 中，容器重启后不丢失。
- Flask 同时提供 Jinja2 页面、静态资源和 `/api` 接口。
- `ANKI_MEDIA_DIR=/app/anki-media` 提供 Word Atlas 的插图，不需要复制音频。数据库同步不会自动复制媒体文件，需单独维护 `data/anki-media/`；媒体不提交 Git。

## FSRS 配置

Compose 从 .env 传入 FSRS_DESIRED_RETENTION（默认 0.9）、FSRS_DAILY_NEW（20）、FSRS_EASY_SECONDS（6）、FSRS_HARD_SECONDS（20）和 FSRS_PARAMETERS_PATH（空，使用默认模型）。参数配置变化需重建容器。

镜像包含 `fsrs[optimizer]==6.3.2` 与 CPU 版 PyTorch。启动时检查一次，之后默认每天检查一次；累计 1,000 条有效间隔复习后在下一次检查中后台训练，留出较新数据验证，误差改善才启用；后续按自然月评估，默认至少新增 100 条有效记录。训练使用独立 CPU 子进程，答案接口不执行训练。Compose 还传入 `FSRS_AUTO_OPTIMIZE=true`、`FSRS_OPTIMIZER_CHECK_SECONDS=86400`、`FSRS_OPTIMIZER_MIN_NEW_REVIEWS=100`、`FSRS_OPTIMIZER_TIMEOUT_SECONDS=3600`。实际 `.env` 如果还配置旧值 `300`，需改为 `86400` 或删除该覆盖项，再重建容器。

评估记录和启用指针存于原统计数据库；参数 JSON 与进程日志存于 `data/stats/fsrs-optimization/`（容器 `/app/stats/fsrs-optimization/`），随现有 stats 挂载持久化。统计页底部可查询历史。重启自动恢复已接受参数，原到期时间保留，下次正式复习应用新参数。回退时设置 `FSRS_AUTO_OPTIMIZE=false`，将 `FSRS_PARAMETERS_PATH` 指向旧已接受 JSON 或 baseline JSON 后重建容器；清空路径则使用默认权重。备份时保留整个 stats 目录。详见 [FSRS 实施说明](SRS-PLAN.md)。

## 常用接口

- `GET /api/config`
- `GET /api/sync/status`
- `POST /api/sync/now`

## 常见检查

- 确认同步服务已有数据
- 确认缓存里的 `collection.anki2` 存在
- 确认 `data/anki-media/` 中有笔记引用的 `wa_*.webp` 等原始插图文件，不需要音频
- 确认练习容器能读到缓存和统计路径
- 确认 `.env` 里的镜像标签是目标版本

## 从旧版升级到词间 / Word Atlas

本版本使用 Word Atlas 固定 22 字段笔记与 py-fsrs 6.3.2。镜像包含 memory.py / srs.py、自动优化模块和训练依赖；首次启用 FSRS 会在原统计数据库中创建 FSRS 表，清空旧练习会话、作答与掌握度一次并记录迁移标记。Anki、媒体、同步记录和访问凭证保留，后续重启不再清理。已经启用 FSRS 的数据库只新增优化表，保留现有正式复习历史。

首次升级需要在实际部署目录完成以下准备：

1. 同步最新版 `docker-compose.yml`。如果服务器将服务合并在其他 Compose 文件中，只补充练习服务的 `./data/anki-media:/app/anki-media:ro` 挂载及 `ANKI_MEDIA_DIR: /app/anki-media` 环境变量，路径以服务器部署目录为准。
2. 创建 `data/anki-media/`，把 Anki `collection.media/` 中笔记引用的插图按原文件名复制进去。应用同步任务仅复制数据库及 SQLite 侧文件，不会复制插图；后续新增插图也需另行更新此目录。缺图时页面隐藏插画，仍可答题。
3. 在 Anki 导入并同步 Word Atlas 牌组，确认其中已有学习过的卡片。旧 IELTS Vocabulary 字段布局不兼容本版本；如服务器自行覆盖了牌组名称或 ID，应一并调整为实际 Word Atlas 牌组。只导入全新卡片但尚未学习时，练习列表可能为空。
4. 等待目标版本镜像构建完成，再设置部署目录 `.env` 中的 `TYPING_PRACTICE_IMAGE_TAG`。自动部署会填写提交 SHA；手动部署可填写已发布的 SHA 或 `latest`。旧 SHA 不会自动指向新版本。

在包含 Compose 文件和 `.env` 的目录中执行：

```bash
mkdir -p data/anki-media
docker compose config --quiet
docker compose pull typing-practice
docker compose up -d --no-deps typing-practice
docker compose ps typing-practice
docker compose logs --tail=100 typing-practice
```

先完成插图复制和 Compose 配置更新，再启动新容器。此操作只更新练习服务；无需重启 `anki-sync`，无需清空缓存或统计目录。仅执行 `restart` 不会应用新的镜像、挂载或环境变量。

GitHub Actions 自动部署仅修改镜像标签、拉取镜像和重建练习容器，**不会同步服务器 Compose 文件、插图或 Anki 牌组**；以上首次准备需单独完成。仓库本地合并不会触发部署，推送到远端 `master` 后才会触发镜像构建，并在部署密钥已配置时执行部署。

部署后检查容器健康状态、实际练习词条及插图。健康接口不验证 Word Atlas 数据和插图是否齐全，因此容器健康也需继续检查页面。旧网页图标若仍被浏览器缓存，可强制刷新页面。

## 排障

- 正式队列为空可能是没有到期词或新词额度已用完；/api/memory/summary 可区分。词库为空时检查 Anki 学习与同步状态。
- 统计数据缺失，通常是统计库路径或挂载不对。
- 同步延迟，通常只是容器内的初始等待时间还没过。

## 相关文档

- [系统概览](SPEC.md)
- [自动部署](AUTO-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
