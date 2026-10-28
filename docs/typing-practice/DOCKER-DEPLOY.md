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

本次相对旧版 `master` 新增了插画挂载，并改为读取 Word Atlas 固定 22 字段笔记。SQLite 统计结构、端口和访问密码配置不变，不需要数据库迁移或新增 Python 依赖；已有统计继续保存在原 `data/stats/`。

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

- 单词列表为空，通常是同步源还没就绪。
- 统计数据缺失，通常是统计库路径或挂载不对。
- 同步延迟，通常只是容器内的初始等待时间还没过。

## 相关文档

- [系统概览](SPEC.md)
- [自动部署](AUTO-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
