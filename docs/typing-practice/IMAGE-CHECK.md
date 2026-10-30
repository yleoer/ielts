# 镜像验证

本机 Python 测试验证源码逻辑，Docker 冒烟检查验证实际镜像的文件、依赖与启动行为。发布前两者都要执行，日常改动按 [测试范围](TESTING.md) 选择验证项。镜像检查统一在 SSH 测试机 `typetest` 执行，使用 `typing-practice/scripts/check_image.py`；GitHub Actions 不执行独立测试任务。

`check_image.py` 是手动 Docker 镜像检查入口，与 CI 无关，继续保留。它负责临时容器的启动、HTTP 检查、失败日志和清理；Dockerfile 的 `import app` 只检查构建时导入，不能替代实际启动与接口验证。

## 两个环境如何配合

| 位置 | 需要安装 | 验证内容 |
| --- | --- | --- |
| 本机 Windows | 仓库 `.venv` 与应用依赖 | Python 单元测试、SQLite / Anki 业务逻辑 |
| `typetest` 测试机 | Docker、Python 3.9+、可用的 SSH 登录 | 构建 Linux 镜像、检查实际镜像 |

测试机的 Python 只执行标准库检查脚本，应用始终使用镜像内的 Python 3.12 和依赖。因此主机 Python 版本和目录结构可以不同；不用复制本机 `.venv`、安装应用依赖或维护 `.env.test`。默认使用测试机原生架构，跨架构检查需 Docker 主机已配置 QEMU。

## 连接检查

每次开始镜像测试前，在 Windows 仓库根目录先执行：

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 typetest true
if ($LASTEXITCODE -ne 0) { throw '无法通过 SSH 连接 typetest，停止镜像测试。' }

ssh -o BatchMode=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 typetest 'python3 --version && docker info >/dev/null'
if ($LASTEXITCODE -ne 0) { throw 'typetest 的 Python 或 Docker 就绪检查失败，停止镜像测试。' }
```

SSH 使用非交互模式、10 秒连接超时且只尝试一次。失败时先报告 SSH 原始错误并停止镜像流程，不自动切换主机、改用本机 Docker 或把历史结果当作本次验证成功。检查通过后再传输文件、拉取或构建镜像。

## 本机单元测试

在仓库根目录运行；日常改动的定向命令见 [测试范围](TESTING.md)：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

## 通过 SSH 检查已发布镜像

先完成上述连接检查，再在 Windows 仓库根目录执行以下 PowerShell 命令。把镜像摘要换成待验证的真实值；也可使用提交 SHA 标签，避免使用可能变化的 `latest`：

```powershell
$image = 'yleoer/ielts-typing-practice@sha256:替换为真实摘要'
Get-Content -Raw -Encoding utf8 typing-practice/scripts/check_image.py |
    ssh -o BatchMode=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 typetest "python3 - '$image' --pull"
if ($LASTEXITCODE -ne 0) { throw '镜像验证失败，停止发布' }
```

脚本通过标准输入发送到测试机，不需要让测试机的仓库、分支或配置与本机保持同步。使用 `--pull` 时由 Docker 主机联网拉取镜像；检查容器自身没有外网。

也可把脚本复制到 `typetest` 后执行：

```bash
python3 check_image.py yleoer/ielts-typing-practice:提交SHA --pull
```

未发布的修改应在连接检查通过后，把当前源码复制到 `typetest` 的独立临时目录，再按 [本地构建说明](LOCAL-BUILD.md) 构建并验证。只发送应用源码和构建文件，不发送 `.env`、`.venv`、Anki、统计数据库或媒体目录。使用唯一临时镜像标签，完成后清理此次创建的目录与镜像。

## 检查范围与隔离

脚本使用镜像原本的 CMD / ENTRYPOINT 启动应用，不额外挂载源码，能发现 `activity.py`、`vocabulary.py` 等文件漏打包的问题。两份 Dockerfile 都自动复制后端 `*.py`，通过 `.dockerignore` 排除 `test_*.py`，并在构建时执行 `import app` 提前发现导入错误。

每次检查创建随机命名的容器，使用 `--network none`，不映射端口、不挂载宿主目录。通过 `docker exec` 从容器内访问回环地址；统计库写入 `/tmp/image-check/stats.db`，Anki 路径指向不存在的临时文件，同步与自动优化关闭，不读取生产 `.env`。

检查项包括：

- 默认 60 秒内 `/api/health` 返回 `success: true`、`status: ok`。
- 练习页、统计页、CSS 与两个前端脚本可读取，响应类型正确。
- 配置接口确认没有 Anki 数据库，统计概览、自然月统计、优化状态接口正常，验证临时 SQLite 初始化与读取。

失败返回非零退出码并输出容器末尾日志。成功或失败都会尝试删除本次容器；清理失败也返回非零码并给出容器名。检查不会自动修改部署标签或重启已有服务。

这套检查不验证真实 Word Atlas 牌组、媒体、反向代理或生产目录权限。需要验证这些内容时，在测试机使用脱敏数据和独立目录做集成检查，发布后继续按 [Docker 部署](DOCKER-DEPLOY.md) 检查词条与插图。

## 发布顺序

发布前完成本机单元测试，先确认 `typetest` 可连接且 Python / Docker 可用，再在该机构建当前源码并执行镜像检查，通过后再推送。GitHub Actions 构建并推送 AMD64 / ARM64 的 `latest` 和提交 SHA 镜像，随后执行 SSH 部署；工作流没有独立测试门禁。`typetest` 默认只验证其原生架构，不能据此认定另一架构已经验证。部署后的健康检查与回滚继续保留。
