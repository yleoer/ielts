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

镜像只安装 Flask、PyYAML、python-dotenv，不再下载 PyTorch，也没有 `TORCH_INDEX_URL` 构建参数；镜像约 219MB。运行冒烟检查的容器由脚本设为 `--network none`。

需要实际切换现有服务时，才通过 `docker-compose.local-build.yml` 覆盖同步服务的构建方式。Compose 会使用现有数据挂载并重建服务，不用于隔离冒烟检查。

## 运行约定

- 这条路径用于测试，不是正式发布流程
- 若使用 Compose 切换了服务，测试完成后切回标准 `docker-compose.yml`
- 本地构建文件应尽量保持精简

## 相关文档

- [Docker 部署](DOCKER-DEPLOY.md)
- [自动部署](AUTO-DEPLOY.md)
