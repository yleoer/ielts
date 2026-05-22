# IELTS 打字练习 - Docker 部署指南

当前部署使用 Docker Compose 启动两个服务：

- `anki-sync`：Anki 同步服务器，接收 Anki 客户端同步过来的数据。
- `typing-practice`：打字练习服务，直接从 Docker Hub 拉取镜像，定时把同步数据复制到自己的缓存目录后读取。

因此服务器上不再需要每次执行 `docker compose build`。

## 快速开始

### 1. 准备环境变量

复制示例配置：

```bash
cd typing-practice
cp .env.example .env
```

按需修改 `.env`：

```dotenv
ANKI_SYNC_PORT=8081
ANKI_SYNC_USER=ielts
ANKI_SYNC_PASSWORD=ielts
TYPING_PRACTICE_PORT=8080
ANKI_SYNC_INTERVAL_SECONDS=300
ANKI_SYNC_INITIAL_WAIT_SECONDS=60
```

两个镜像在 `docker-compose.yml` 中固定：

- `afrima/anki-sync-server:latest`
- `yleoer/ielts-typing-practice:latest`

### 2. 启动服务

```bash
cd typing-practice
docker compose pull
docker compose up -d
```

查看状态和日志：

```bash
docker compose ps
docker compose logs -f anki-sync
docker compose logs -f typing-practice
```

停止服务：

```bash
docker compose down
```

## 访问地址

默认端口：

```text
打字练习：http://localhost:8080/
统计页面：http://localhost:8080/stats.html
健康检查：http://localhost:8080/api/config
Anki 同步：http://localhost:8081/
```

服务器部署时，把 `localhost` 换成服务器 IP 或域名。

## Anki 客户端同步

Anki 客户端需要连接到 `anki-sync` 服务。默认账号来自 `.env`：

```text
用户名：ielts
密码：ielts
端口：8081
```

同步成功后，`typing-practice` 会从共享目录中定时复制最新的 `collection.anki2` 到：

```text
/app/anki-cache/collection.anki2
```

第一次启动会等待 `ANKI_SYNC_INITIAL_WAIT_SECONDS` 秒后尝试复制，之后按 `ANKI_SYNC_INTERVAL_SECONDS` 周期刷新。

## Compose 结构

`typing-practice/docker-compose.yml` 的关键结构：

```yaml
services:
  anki-sync:
    image: afrima/anki-sync-server:latest
    ports:
      - "${ANKI_SYNC_PORT:-8081}:8080"
    volumes:
      - ./data/anki-sync:/data
    environment:
      SYNC_USER1: "${ANKI_SYNC_USER:-ielts}:${ANKI_SYNC_PASSWORD:-ielts}"

  typing-practice:
    image: yleoer/ielts-typing-practice:latest
    user: "0:0"
    ports:
      - "${TYPING_PRACTICE_PORT:-8080}:8080"
    volumes:
      - ./data/anki-sync:/app/anki-sync:ro
      - ./data/anki-cache:/app/anki-cache
      - ./data/stats:/app/stats
    environment:
      ANKI_DB_PATH: /app/anki-cache/collection.anki2
      STATS_DB_PATH: /app/stats/stats.db
```

- `./data/anki-sync`：保存 Anki 同步服务器的数据，同时只读挂载给练习服务。
- `./data/anki-cache`：保存练习服务复制出来的 `collection.anki2`。
- `./data/stats`：保存练习统计 SQLite 数据库，容器重建后不会丢失。

`typing-practice` 服务在 Compose 中使用 `user: "0:0"`，这样在服务器用 root 拉取仓库时，容器可以直接写入这些相对路径数据目录。

## 更新镜像

GitHub Actions 会构建 `yleoer/ielts-typing-practice:latest` 并推送到 Docker Hub。服务器更新时执行：

```bash
cd typing-practice
docker compose pull typing-practice
docker compose up -d typing-practice
```

如需同时更新 Anki 同步服务器镜像：

```bash
docker compose pull
docker compose up -d
```

## 统计数据备份

统计数据保存在 `typing-practice/data/stats/stats.db`。备份示例：

```bash
cp data/stats/stats.db ./stats-backup.db
```

删除所有运行数据：

```bash
docker compose down
rm -rf data/anki-sync/* data/anki-cache/* data/stats/*
```

## 常见问题

### 访问不了打字练习页面

检查容器状态和日志：

```bash
docker compose ps
docker compose logs typing-practice
```

确认 `.env` 中的 `TYPING_PRACTICE_PORT` 没有和服务器上其他服务冲突。

### `/api/words` 没有单词

先确认 Anki 同步服务已经收到客户端数据，再检查练习服务缓存：

```bash
docker compose logs anki-sync
docker compose exec typing-practice ls -l /app/anki-cache/collection.anki2
```

如果缓存文件不存在，通常是客户端还没有同步成功，或等待时间还没到。

### 不想等待定时复制

可以重启练习服务触发启动复制流程：

```bash
docker compose restart typing-practice
```

## 常用命令

```bash
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f typing-practice
docker compose logs -f anki-sync
docker compose restart typing-practice
docker compose down
```
