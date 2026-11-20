# 镜像验证

本机 Python 测试验证源码逻辑，Docker 冒烟检查验证实际镜像的文件、依赖与启动行为。发布前两者都要执行，日常改动按 [测试范围](TESTING.md) 选择验证项。镜像检查在本机 Docker 执行，使用 `typing-practice/scripts/check_image.py`；GitHub Actions 不执行独立测试任务。

`check_image.py` 是手动 Docker 镜像检查入口，与 CI 无关，继续保留。它负责临时容器的启动、HTTP 检查、失败日志和清理；Dockerfile 的 `import app` 只检查构建时导入，不能替代实际启动与接口验证。

## 需要的环境

| 验证内容 | 需要安装 |
| --- | --- |
| Python 单元测试、SQLite / Anki 业务逻辑 | 仓库 `.venv` 与应用依赖 |
| 构建 Linux 镜像、检查实际镜像 | Docker（当前用户可直接运行 `docker`）、Python 3.9+ |

检查脚本只用 Python 标准库，应用始终使用镜像内的 Python 3.12 和依赖，因此不用为镜像检查安装应用依赖或维护 `.env.test`。默认只验证本机原生架构（当前为 AMD64），跨架构检查需 Docker 已配置 QEMU。

## Docker 检查

每次开始镜像测试前，先确认 Docker 可用：

```bash
docker info >/dev/null && python3 --version
```

失败时报告原始错误并停止镜像流程，不用源码测试或历史结果代替本次验证。

## 本机单元测试

在仓库根目录运行；日常改动的定向命令见 [测试范围](TESTING.md)：

```bash
.venv/bin/python -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

## 检查当前源码

在仓库根目录构建 CI 使用的正式 Dockerfile，用唯一的临时标签检查，结束后删除该标签：

```bash
tag="ielts-typing-practice:check-$(date +%s)"
docker build --network host -f typing-practice/backend/Dockerfile -t "$tag" typing-practice \
  && python3 typing-practice/scripts/check_image.py "$tag"
docker image rm "$tag"
```

`--network host` 只作用于构建步骤：本机 DNS 走本地代理（`127.0.0.53` → `127.0.0.1:1053`），默认 bridge 网络里的构建容器访问不到，`apt-get update` 会报 `Temporary failure resolving 'deb.debian.org'`。检查容器仍由脚本设为 `--network none`。构建缓存是共享的，不需要清理。

## 检查已发布镜像

把镜像摘要换成待验证的真实值；也可使用提交 SHA 标签，避免使用可能变化的 `latest`：

```bash
python3 typing-practice/scripts/check_image.py 'yleoer/ielts-typing-practice@sha256:替换为真实摘要' --pull
```

使用 `--pull` 时由 Docker 联网拉取镜像；检查容器自身没有外网。检查完成后可用 `docker image rm` 删除拉取的镜像。

## 检查范围与隔离

脚本使用镜像原本的 CMD / ENTRYPOINT 启动应用，不额外挂载源码，能发现 `ledger.py`、`auth.py` 等文件漏打包的问题。两份 Dockerfile 都自动复制后端 `*.py`，通过 `.dockerignore` 排除 `test_*.py`，并在构建时执行 `import app` 提前发现导入错误。

每次检查创建随机命名的容器，使用 `--network none`，不映射端口、不挂载宿主目录。通过 `docker exec` 从容器内访问回环地址；作答日志写入 `/tmp/image-check/stats.db`，Anki 路径指向不存在的临时文件，`ACCESS_TOKEN` 为空，Anki 定时复制关闭，不读取生产 `.env`。

检查项包括：

- 默认 60 秒内 `/api/health` 返回 `success: true`、`status: ok`，且 `Server` 响应头为 `waitress`，确认镜像默认入口使用生产服务器。
- 没有 Anki 数据库时 `/api/vocab` 返回 503。
- 在容器临时目录构造最小 Anki SQLite，检查带 `word_atlas::excluded` 的暂停词被过滤，且已学变体可让其保留项进入练习池；不读取真实 Anki 数据。
- 确认打包后的 `vocabulary.py` 可用：`/api/vocab` 返回空的 `sync_history` 基线。行为细节由本机单元测试覆盖。
- `/api/sync` 接受一条作答并在日志中返回，再次上传同一 `attempt_id` 记为重复，验证临时 SQLite 初始化与读写。
- 已退役的 `/`、`/stats.html`、`/api/stats/overview` 返回 404。
- 镜像中未安装 `fsrs` 与 `torch`。

失败返回非零退出码并输出容器末尾日志。成功或失败都会尝试删除本次容器；清理失败也返回非零码并给出容器名。检查不会自动修改部署标签或重启已有服务。

这套检查不验证真实 Word Atlas 牌组、反向代理、令牌配置或生产目录权限。需要验证这些内容时，在本机使用脱敏数据和独立目录做集成检查，发布后按 [Docker 部署](DOCKER-DEPLOY.md) 检查词库接口。

## 发布顺序

发布前完成本机单元测试，确认 Docker 可用，再在本机构建当前源码并执行镜像检查，通过后再推送。GitHub Actions 构建并推送 AMD64 / ARM64 的 `latest` 和提交 SHA 镜像，随后执行 SSH 部署；工作流没有独立测试门禁。本机默认只验证原生架构，不能据此认定另一架构已经验证。部署后的健康检查与回滚继续保留。
