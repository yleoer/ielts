# IELTS 打字练习 - Docker 部署指南

打字练习现在使用单容器部署：Go 后端负责 API，同时托管 `frontend/` 下的静态页面。Docker Compose 只需要启动 `backend` 一个服务，并暴露 `8080` 端口。

## 快速开始

### 1. 准备 Anki 数据库

先把 Anki 的 `collection.anki2` 复制到项目目录：

```powershell
New-Item -ItemType Directory -Force -Path "typing-practice\backend\data"
Copy-Item "$env:APPDATA\Anki2\User 1\collection.anki2" -Destination "typing-practice\backend\data\collection.anki2"
```

如果你的 Anki profile 不是 `User 1`，请把源路径换成真实 profile 下的 `collection.anki2`。

### 2. 启动服务

```bash
cd typing-practice
docker compose up -d --build
docker compose logs -f backend
```

停止服务：

```bash
docker compose down
```

## 访问地址

```text
http://localhost:8080/
http://localhost:8080/stats.html
http://localhost:8080/api/config
```

## Compose 结构

`typing-practice/docker-compose.yml` 做了三件关键的事：

```yaml
ports:
  - "8080:8080"

volumes:
  - ./backend/data:/app/data:ro
  - stats-data:/app/stats

environment:
  SERVER_HOST: 0.0.0.0
  SERVER_PORT: 8080
  ANKI_DB_PATH: /app/data/collection.anki2
  STATS_DB_PATH: /app/stats/stats.db
```

- `./backend/data:/app/data:ro`：只读挂载 Anki 数据库，避免容器修改 Anki 原始数据。
- `stats-data:/app/stats`：使用 Docker volume 保存练习统计数据，容器重建后不会丢失。
- `SERVER_HOST=0.0.0.0`：让服务监听容器网卡，否则宿主机可能无法通过端口映射访问。

## 更新 Anki 数据

当 Anki 数据有变化时，重新复制数据库并重启容器：

```powershell
Copy-Item "$env:APPDATA\Anki2\User 1\collection.anki2" -Destination "typing-practice\backend\data\collection.anki2" -Force
cd typing-practice
docker compose restart backend
```

## 服务器部署思路

在服务器上运行时，可以把本地 Anki 数据同步到服务器的 `typing-practice/backend/data/collection.anki2`：

```bash
scp collection.anki2 user@server:/path/to/my-ielts/typing-practice/backend/data/collection.anki2
ssh user@server "cd /path/to/my-ielts/typing-practice && docker compose up -d --build"
```

如果需要定期同步，可以用 `rsync`、计划任务或 CI/CD 把 `collection.anki2` 推到服务器，然后执行：

```bash
docker compose restart backend
```

## 常见问题

### 访问不了 `localhost:8080`

检查容器状态和日志：

```bash
docker compose ps
docker compose logs backend
```

确认 `SERVER_HOST` 是 `0.0.0.0`，并且端口映射是 `"8080:8080"`。

### `/api/words` 没有单词

确认数据库文件存在：

```bash
docker compose exec backend ls -l /app/data/collection.anki2
```

如果文件不存在，重新复制 `collection.anki2` 到 `typing-practice/backend/data/`。

### 统计数据是否会丢失

不会。统计库写入 Docker volume `stats-data`。如果要备份：

```bash
docker compose exec backend cp /app/stats/stats.db /tmp/stats.db
docker cp ielts-typing-backend:/tmp/stats.db ./stats-backup.db
```

删除统计数据需要显式删除 volume：

```bash
docker compose down -v
```

## 常用命令

```bash
docker compose up -d --build
docker compose logs -f backend
docker compose restart backend
docker compose down
docker compose down -v
```
