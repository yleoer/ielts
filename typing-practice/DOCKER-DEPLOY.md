# IELTS 打字练习 - Docker 部署指南

## 快速开始

### 1. 准备 Anki 数据库文件

**在本地电脑操作**：

```bash
# Windows
# 找到 Anki 数据库文件
# 路径：C:\Users\yleoer\AppData\Roaming\Anki2\User 1\collection.anki2

# 复制到项目目录
mkdir typing-practice\backend\data
copy "%APPDATA%\Anki2\User 1\collection.anki2" typing-practice\backend\data\
```

**或使用 PowerShell**：
```powershell
# 创建数据目录
New-Item -ItemType Directory -Force -Path "typing-practice\backend\data"

# 复制 Anki 数据库
Copy-Item "$env:APPDATA\Anki2\User 1\collection.anki2" -Destination "typing-practice\backend\data\"
```

### 2. 启动 Docker 容器

```bash
# 进入项目目录
cd typing-practice

# 构建并启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 3. 访问应用

打开浏览器访问：http://localhost:8080
## 文件结构

```
typing-practice/
├── docker-compose.yml          # Docker Compose 配置
├── nginx.conf                  # Nginx 配置
├── backend/
│   ├── Dockerfile             # 后端 Dockerfile
│   ├── data/
│   │   └── collection.anki2   # Anki 数据库（需手动复制）
│   ├── main.go
│   ├── go.mod
│   └── ...
└── frontend/
    ├── index.html
    ├── src/
    └── assets/
```

## 环境变量

可以在 `docker-compose.yml` 中修改：

```yaml
environment:
  - ANKI_DB_PATH=/root/data/collection.anki2  # Anki 数据库路径
  - SERVER_PORT=8080                          # 后端端口
  - GIN_MODE=release                          # Gin 运行模式
```

## 端口映射

- **8080**：后端 API 服务

如需修改端口，编辑 `docker-compose.yml`：

```yaml
ports:
  - "8080:8080" # 改为 "9090:8080" 则后端运行在 9090
```

## 数据同步方案

### 方案 A：手动同步（简单）

每次 Anki 学习新单词后，手动复制数据库文件：

```bash
# 停止容器
docker-compose down

# 复制最新的 Anki 数据库
copy "%APPDATA%\Anki2\User 1\collection.anki2" typing-practice\backend\data\

# 重启容器
docker-compose up -d
```

### 方案 B：定时同步脚本（推荐）

创建 `sync-anki.bat`：

```batch
@echo off
echo Syncing Anki database...

REM 复制 Anki 数据库
copy "%APPDATA%\Anki2\User 1\collection.anki2" "D:\Code\Github\my-ielts\typing-practice\backend\data\" /Y

REM 重启 Docker 容器
cd D:\Code\Github\my-ielts\typing-practice
docker-compose restart backend

echo Sync completed!
pause
```

使用 Windows 任务计划程序设置每天自动运行。

### 方案 C：使用 rsync 远程同步（服务器部署）

如果服务器在远程，使用 rsync 或 scp：

```bash
# 从本地同步到服务器
rsync -avz --progress \
  "%APPDATA%\Anki2\User 1\collection.anki2" \
  user@server:/path/to/typing-practice/backend/data/

# SSH 到服务器重启容器
ssh user@server "cd /path/to/typing-practice && docker-compose restart backend"
```

## 常见问题

### 1. 后端无法读取数据库

**检查文件权限**：
```bash
# 进入容器
docker exec -it ielts-typing-backend sh

# 检查文件是否存在
ls -la /root/data/collection.anki2

# 检查文件权限
chmod 644 /root/data/collection.anki2
```

### 2. 前端无法连接后端

**检查 API 地址**：
- 确保 `frontend/src/app.js` 中 `apiBaseUrl` 设置为 `/api`
- 检查 Nginx 配置是否正确代理到后端

**测试后端连接**：
```bash
curl http://localhost:8080/api/config
```

### 3. 容器启动失败

**查看日志**：
```bash
docker-compose logs backend
docker-compose logs frontend
```

**重新构建**：
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 4. 数据库文件过大

Anki 数据库可能包含大量媒体文件，如果只需要单词数据：

```bash
# 使用 SQLite 导出纯文本数据
sqlite3 collection.anki2 ".dump notes cards" > anki_data.sql
```

## 生产环境部署

### 使用 HTTPS（推荐）

1. 安装 Certbot
2. 获取 SSL 证书
3. 修改 `nginx.conf` 添加 SSL 配置

### 使用域名

修改 `nginx.conf`：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    # ... 其他配置
}
```

### 性能优化

在 `docker-compose.yml` 中添加资源限制：

```yaml
services:
  backend:
    # ... 其他配置
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
```

## 备份和恢复

### 备份数据

```bash
# 备份 Anki 数据库
cp typing-practice/backend/data/collection.anki2 backup/collection_$(date +%Y%m%d).anki2

# 备份 Docker 镜像
docker save ielts-typing-backend > ielts-typing-backend.tar
```

### 恢复数据

```bash
# 恢复 Anki 数据库
cp backup/collection_20260521.anki2 typing-practice/backend/data/collection.anki2

# 重启容器
docker-compose restart backend
```

## 监控和日志

### 查看实时日志

```bash
# 所有服务
docker-compose logs -f

# 仅后端
docker-compose logs -f backend

# 仅前端
docker-compose logs -f frontend
```

### 日志持久化

修改 `docker-compose.yml` 添加日志配置：

```yaml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 卸载

```bash
# 停止并删除容器
docker-compose down

# 删除镜像
docker rmi ielts-typing-backend nginx:alpine

# 删除数据（可选）
rm -rf typing-practice/backend/data/collection.anki2
```

## 技术支持

- **GitHub Issues**: https://github.com/yleoer/my-ielts/issues
- **文档**: typing-practice-spec.md

---

**最后更新**: 2026-05-21  
**Docker 版本**: 20.10+  
**Docker Compose 版本**: 2.0+
