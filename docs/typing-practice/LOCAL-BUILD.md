# 本地服务器构建测试

正式部署使用 Docker Hub 镜像：

```bash
docker compose pull
docker compose up -d
```

如果要在本地服务器 `172.0.14.17` 上直接验证改动，可以叠加 `docker-compose.local-build.yml`，只本地构建 `typing-practice` 服务，不等待 GitHub Actions 和 Docker Hub。

本地构建使用 `backend/Dockerfile.local`，它会把 Debian apt 源切到阿里云镜像，并设置 `GOPROXY=https://goproxy.cn,direct`，用于国内网络下更快完成测试镜像构建。正式发布镜像仍使用 `backend/Dockerfile`。

## 首次启动

```bash
ssh root@172.0.14.17
cd /root/me/ielts/typing-practice
cp .env.example .env

docker compose up -d anki-sync
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build typing-practice
```

访问：

```text
http://172.0.14.17:8080/
http://172.0.14.17:8080/stats.html
```

## 每次代码改动后测试

在服务器拉取最新代码后，重新构建并替换练习服务：

```bash
cd /root/me/ielts
git pull

cd typing-practice
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build --no-deps typing-practice
docker compose logs -f typing-practice
```

`--no-deps` 会避免重启 `anki-sync`，已有同步数据和统计数据都保留在：

```text
typing-practice/data/anki-sync/
typing-practice/data/anki-cache/
typing-practice/data/stats/
```

## 回到正式镜像

本地测试结束后，如果要切回 Docker Hub 的正式镜像：

```bash
cd /root/me/ielts/typing-practice
docker compose pull typing-practice
docker compose up -d --no-deps --force-recreate typing-practice
```

这条命令只使用 `docker-compose.yml`，不会读取本地 build override。

## 常用命令

```bash
# 只构建镜像，不启动容器
docker compose -f docker-compose.yml -f docker-compose.local-build.yml build typing-practice

# 构建并重启练习服务
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build --no-deps typing-practice

# 查看练习服务日志
docker compose logs -f typing-practice

# 查看当前使用的镜像
docker compose ps
docker inspect ielts-typing-practice --format '{{.Config.Image}}'
```
