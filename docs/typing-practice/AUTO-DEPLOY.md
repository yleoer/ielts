# 自动部署

这是基于 GitHub Actions 的自动部署说明。

## 流程

1. 通过 QEMU 和 Buildx 构建 `linux/amd64`、`linux/arm64` 两种 `typing-practice` 镜像。
2. 同时推送 `latest` 和提交 SHA 标签的 Docker Hub 多架构镜像。
3. 通过 SSH 登录服务器。
4. 更新部署镜像标签。
5. 只重启练习服务。
6. 检查生产容器健康状态。
7. 健康失败时回滚。

工作流不运行单元测试或独立镜像冒烟任务。发布前按 [测试范围](TESTING.md) 在本机运行单元测试，并在 `typetest` 验证实际镜像，通过后再推送触发自动构建和部署。镜像测试前先检查 SSH 连接，连接失败立即报告错误并停止。Dockerfile 自身保留构建时的应用导入检查。

## 范围

- 只更新练习服务。
- 同步服务和其他组件保持不动。
- 只有文档改动时会跳过构建和部署。
- `latest` 和提交 SHA 标签都同时支持 AMD64 与 ARM64；服务器执行 `docker compose pull` 时会自动拉取与本机架构匹配的镜像。
- 单元测试与 Docker 镜像检查独立于 GitHub Actions 执行。镜像检查使用 `typetest` 的临时容器，见 [镜像验证](IMAGE-CHECK.md)。只修改仓库的检查脚本不会触发镜像重建和部署。
- 工作流不执行服务器仓库的 `git pull`，也不复制 Compose 文件、插图或 Anki 数据。首次升级词间 / Word Atlas 前，需先完成 [Docker 部署](DOCKER-DEPLOY.md#从旧版升级到词间--word-atlas) 中的配置与数据准备；健康检查成功不代表练习词条和插图已就绪。

## 需要的密钥

- Docker Hub 凭据
- SSH 主机、用户和密钥
- 服务器上的部署目录

## 回滚方式

工作流会保留上一个镜像标签；如果新容器没有变成健康状态，就恢复旧标签并重新启动。

## 相关文档

- [Docker 部署](DOCKER-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
