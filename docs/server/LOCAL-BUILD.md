# 本地构建说明

当你想直接验证同步服务，但不想等待 Docker Hub 镜像时，可以用这份说明。镜像测试在本机 Docker 执行，先按 [镜像验证](IMAGE-CHECK.md#docker-检查) 确认 Docker 可用；不可用时立即报错并停止。

## 适用场景

- 在服务器上直接验证代码改动
- 不想等 GitHub Actions 构建完成
- 想先做一次发布前检查

## 工作方式

Docker 检查通过后，在仓库根目录构建，再用临时容器检查，不需要启动整套 Compose：

```bash
docker build --network host -f server/backend/Dockerfile.local -t ielts-typing-practice:check typing-practice
python3 server/scripts/check_image.py ielts-typing-practice:check
docker image rm ielts-typing-practice:check
```

正式 Dockerfile 使用 Debian 官方源，`Dockerfile.local` 使用阿里云 Debian 源；应用文件和依赖一致。验证正式打包时将上述 `-f` 改为 `server/backend/Dockerfile`（发布前的检查用它，见 [镜像验证](IMAGE-CHECK.md#检查当前源码)）。`--network host` 的原因同见镜像验证。

镜像只安装 Flask、Waitress、PyYAML、python-dotenv，不再下载 PyTorch，也没有 `TORCH_INDEX_URL` 构建参数。应用通过 Waitress 启动，冒烟检查确认实际 HTTP 响应来自 Waitress；检查容器由脚本设为 `--network none`。

需要实际切换现有服务时，才通过 `docker-compose.local-build.yml` 覆盖同步服务的构建方式。Compose 会使用现有数据挂载并重建服务，不用于隔离冒烟检查。

## 运行约定

- 这条路径用于测试，不是正式发布流程
- 若使用 Compose 切换了服务，测试完成后切回标准 `docker-compose.yml`
- 本地构建文件应尽量保持精简

## 相关文档

- [Docker 部署](DOCKER-DEPLOY.md)
- [自动部署](AUTO-DEPLOY.md)
