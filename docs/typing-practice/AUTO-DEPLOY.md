# 打字练习自动部署

本文说明 GitHub Actions 构建镜像成功后，自动登录云服务器更新 `typing-practice` 服务，并在健康检查失败时回滚到上一个镜像 tag。

只有影响 Docker 镜像内容的文件变化才会触发构建和部署：

- `typing-practice/backend/**`
- `typing-practice/frontend/**`
- `typing-practice/.dockerignore`

只修改文档、compose、`.env.example` 或 GitHub Actions 部署脚本时，workflow 会跳过镜像构建和云服务器部署。

## 整体流程

```text
push master
  -> 检查是否修改了镜像相关文件
  -> GitHub Actions 构建 Docker 镜像
  -> 推送 yleoer/ielts-typing-practice:latest
  -> 推送 yleoer/ielts-typing-practice:<commit-sha>
  -> SSH 登录云服务器
  -> 写入 TYPING_PRACTICE_IMAGE_TAG=<commit-sha>
  -> docker compose pull typing-practice
  -> docker compose up -d --no-deps typing-practice
  -> 等待容器 healthcheck
  -> 失败则恢复旧 tag 并重新启动
```

自动部署只更新 `typing-practice` 一个服务，不会 `docker compose down`，也不会重启 nginx、Anki 同步服务器或其他服务。

## 项目侧改动

`typing-practice/docker-compose.yml` 中的镜像使用可配置 tag：

```yaml
services:
  typing-practice:
    image: yleoer/ielts-typing-practice:${TYPING_PRACTICE_IMAGE_TAG:-latest}
```

`.env` 中可以手动指定当前运行版本：

```dotenv
TYPING_PRACTICE_IMAGE_TAG=latest
```

GitHub Actions 自动部署时会把它改成当前 commit sha，例如：

```dotenv
TYPING_PRACTICE_IMAGE_TAG=7439930f0f...
```

## GitHub Secrets

进入仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

需要配置：

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
DEPLOY_HOST
DEPLOY_USER
DEPLOY_SSH_KEY
DEPLOY_APP_DIR
```

说明：

```text
DOCKERHUB_USERNAME  Docker Hub 用户名
DOCKERHUB_TOKEN     Docker Hub access token
DEPLOY_HOST         云服务器 IP 或域名
DEPLOY_USER         SSH 用户，例如 root
DEPLOY_SSH_KEY      GitHub Actions 专用 SSH 私钥
DEPLOY_APP_DIR      云服务器 compose 文件所在目录，例如 /root/all-in-one
```

`DEPLOY_APP_DIR` 可以不填，workflow 默认使用：

```text
/root/all-in-one
```

## 创建 SSH Key

在本地电脑生成 GitHub Actions 专用 key：

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy-ielts" -f ./github_actions_deploy
```

把公钥加入云服务器：

```bash
ssh root@你的服务器IP "mkdir -p ~/.ssh && chmod 700 ~/.ssh"
cat github_actions_deploy.pub | ssh root@你的服务器IP "cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

把私钥完整内容写入 GitHub Secret：

```bash
cat github_actions_deploy
```

Secret 名称：

```text
DEPLOY_SSH_KEY
```

私钥内容需要包含头尾：

```text
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

不要把私钥提交到 git。

## 服务器准备

云服务器 compose 目录需要有 `.env` 文件。没有也可以创建空文件：

```bash
cd /root/all-in-one
touch .env
```

如果你本地路径不是 `/root/all-in-one`，把实际路径写入 GitHub Secret：

```text
DEPLOY_APP_DIR=/你的/compose/目录
```

确认手动命令可用：

```bash
cd /root/all-in-one
docker compose pull typing-practice
docker compose up -d --no-deps typing-practice
docker inspect -f '{{.State.Health.Status}}' ielts-typing-practice
```

健康状态应该变为：

```text
healthy
```

## 回滚机制

workflow 部署前会读取服务器 `.env` 中的旧值：

```dotenv
TYPING_PRACTICE_IMAGE_TAG=<old-tag>
```

新版本启动后，脚本会最多等待 60 秒检查容器健康状态：

```bash
docker inspect -f '{{.State.Health.Status}}' ielts-typing-practice
```

如果不是 `healthy`，会自动：

1. 把 `.env` 恢复为旧 tag。
2. `docker compose pull typing-practice`
3. `docker compose up -d --no-deps typing-practice`

## 手动回滚

如果需要人工回滚，直接改 `.env`：

```bash
cd /root/all-in-one
sed -i '/^TYPING_PRACTICE_IMAGE_TAG=/d' .env
echo 'TYPING_PRACTICE_IMAGE_TAG=上一个commit-sha' >> .env
docker compose pull typing-practice
docker compose up -d --no-deps typing-practice
```

查看当前运行镜像：

```bash
docker inspect -f '{{.Config.Image}}' ielts-typing-practice
```
