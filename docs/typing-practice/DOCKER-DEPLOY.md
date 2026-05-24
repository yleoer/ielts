# Docker 部署

这是 `typing-practice` 的标准 Docker Compose 部署说明。

## 服务

- `anki-sync`：接收 Anki 客户端同步数据
- `typing-practice`：提供练习页面和统计接口

练习服务使用 Docker Hub 上的预构建镜像。

## 运行文件

- `typing-practice/.env.example`
- `typing-practice/docker-compose.yml`
- `typing-practice/data/anki-sync/`
- `typing-practice/data/anki-cache/`
- `typing-practice/data/stats/`

## 运行模型

- Anki 数据先进入同步服务。
- 练习服务再把同步结果复制到本地缓存。
- 统计数据保存在 SQLite 中，容器重启后不丢失。

## 常用接口

- `GET /api/config`
- `GET /api/sync/status`
- `POST /api/sync/now`

## 常见检查

- 确认同步服务已有数据
- 确认缓存里的 `collection.anki2` 存在
- 确认练习容器能读到缓存和统计路径
- 确认 `.env` 里的镜像标签是目标版本

## 排障

- 单词列表为空，通常是同步源还没就绪。
- 统计数据缺失，通常是统计库路径或挂载不对。
- 同步延迟，通常只是容器内的初始等待时间还没过。

## 相关文档

- [系统概览](SPEC.md)
- [自动部署](AUTO-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
