# 本地构建说明

当你想直接验证 `typing-practice`，但不想等待 Docker Hub 镜像时，可以用这份说明。镜像测试统一在 SSH 测试机 `typetest` 执行，先按 [镜像验证](IMAGE-CHECK.md#连接检查) 检查连接；连接失败立即报错并停止，不传输文件或开始构建。

## 适用场景

- 在服务器上直接验证代码改动
- 不想等 GitHub Actions 构建完成
- 想先做一次发布前检查

## 工作方式

连接与 Python / Docker 检查通过后，在 `typetest` 的独立源码目录中构建，再用临时容器检查，不需要启动整套 Compose：

```bash
docker build -f typing-practice/backend/Dockerfile.local -t ielts-typing-practice:check typing-practice
python3 typing-practice/scripts/check_image.py ielts-typing-practice:check
```

正式 Dockerfile 使用 Debian 官方源，`Dockerfile.local` 使用阿里云 Debian 源；应用文件和依赖一致。验证正式打包时将上述 `-f` 改为 `typing-practice/backend/Dockerfile`。

两份 Dockerfile 的 `TORCH_INDEX_URL` 构建参数默认使用官方 CPU 源 `https://download.pytorch.org/whl/cpu`。如果测试机下载大文件过慢，可用 `--build-arg TORCH_INDEX_URL=可信CPU镜像源地址` 指定缓存或镜像源；保持 CPU wheel 的版本与官方 SHA256 一致。该参数只影响构建下载，不需要为应用另建测试配置。测试机上的临时缓存服务应随验证一起清理。Linux 测试机可在需要访问主机回环缓存服务时加 `--network host`；运行冒烟检查的容器仍由脚本设为 `--network none`。

需要实际切换现有服务时，才通过 `docker-compose.local-build.yml` 覆盖练习服务的构建方式。Compose 会使用现有数据挂载并重建服务，不用于隔离冒烟检查。

## 运行约定

- 这条路径用于测试，不是正式发布流程
- 若使用 Compose 切换了服务，测试完成后切回标准 `docker-compose.yml`
- 本地构建文件应尽量保持精简

## 相关文档

- [Docker 部署](DOCKER-DEPLOY.md)
- [自动部署](AUTO-DEPLOY.md)
