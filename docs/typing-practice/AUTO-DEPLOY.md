# 自动部署

这是基于 GitHub Actions 的自动部署说明。

## 流程

1. 通过 QEMU 和 Buildx 构建 `linux/amd64`、`linux/arm64` 两种 `typing-practice` 镜像。
2. 推送包含两种架构的 Docker Hub 多架构清单。
3. 通过 SSH 登录服务器。
4. 更新部署镜像标签。
5. 只重启练习服务。
6. 检查健康状态。
7. 健康失败时回滚。

## 范围

- 只更新练习服务。
- 同步服务和其他组件保持不动。
- 只有文档改动时会跳过构建和部署。
- `latest` 和提交 SHA 标签都同时支持 AMD64 与 ARM64；服务器执行 `docker compose pull` 时会自动拉取与本机架构匹配的镜像。

## 需要的密钥

- Docker Hub 凭据
- SSH 主机、用户和密钥
- 服务器上的部署目录

## 回滚方式

工作流会保留上一个镜像标签；如果新容器没有变成健康状态，就恢复旧标签并重新启动。

## 相关文档

- [Docker 部署](DOCKER-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
