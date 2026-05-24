# 本地构建说明

当你想在服务器上直接验证 `typing-practice`，但不想等待 Docker Hub 镜像时，可以用这份说明。

## 适用场景

- 在服务器上直接验证代码改动
- 不想等 GitHub Actions 构建完成
- 想先做一次发布前检查

## 工作方式

- 通过 `docker-compose.local-build.yml` 覆盖练习服务的构建方式
- 只在服务器本地重建练习服务
- 同步和统计数据保持不变

## 运行约定

- 这条路径用于测试，不是正式发布流程
- 测试完成后切回标准 `docker-compose.yml`
- 本地构建文件应尽量保持精简

## 相关文档

- [Docker 部署](DOCKER-DEPLOY.md)
- [自动部署](AUTO-DEPLOY.md)
