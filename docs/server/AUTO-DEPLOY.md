# 自动部署

这是基于 GitHub Actions 的自动部署说明。

## 流程

1. 通过 QEMU 和 Buildx 构建 `linux/amd64`、`linux/arm64` 两种同步服务镜像（`yleoer/ielts-typing-practice`）。
2. 同时推送 `latest` 和提交 SHA 标签的 Docker Hub 多架构镜像。
3. 通过 SSH 登录服务器。
4. 更新部署镜像标签。
5. 只重建同步服务（`typing-practice`）。
6. 检查生产容器健康状态。
7. 健康失败时回滚。

工作流不运行单元测试或独立镜像冒烟任务。发布前按 [测试范围](TESTING.md) 在本机运行单元测试，并在本机 Docker 验证实际镜像，通过后再推送触发自动构建和部署。镜像测试前先确认 Docker 可用，不可用时立即报告错误并停止。Dockerfile 自身保留构建时的应用导入检查。

## 范围

- 只更新同步服务。
- 同步服务和其他组件保持不动。
- 只有 `server/backend/`、`server/.dockerignore` 或工作流本身改动时才构建和部署；文档和桌面端改动会跳过。
- `latest` 和提交 SHA 标签都同时支持 AMD64 与 ARM64；服务器执行 `docker compose pull` 时会自动拉取与本机架构匹配的镜像。
- 单元测试与 Docker 镜像检查独立于 GitHub Actions 执行。镜像检查使用本机 Docker 的临时容器，见 [镜像验证](IMAGE-CHECK.md)。只修改仓库的检查脚本不会触发镜像重建和部署。
- 工作流不执行服务器仓库的 `git pull`，也不复制 Compose 文件、`.env` 或 Anki 数据。从网页版升级前，需先完成 [Docker 部署](DOCKER-DEPLOY.md#从网页版升级到同步服务) 中的令牌与配置准备；健康检查成功不代表词库已就绪。

## 需要的密钥

| 密钥 | 说明 |
| --- | --- |
| `DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN` | Docker Hub 凭据 |
| `DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY` | SSH 主机、用户和私钥；缺任何一项时跳过远程部署 |
| `DEPLOY_PORT` | 可选，SSH 端口；未填写时使用 `22` |
| `DEPLOY_APP_DIR` | 可选，服务器上的部署目录；未填写时使用 `/root/all-in-one` |

## 回滚方式

工作流会保留上一个镜像标签；如果新容器没有变成健康状态，就恢复旧标签并重新启动。

## 相关文档

- [Docker 部署](DOCKER-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
