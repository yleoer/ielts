# Codex 项目规范

## 通用规则

- 每次修改代码、脚本、配置、生成流程或用户可见行为时，必须同步更新相关文档。
- 如果本次修改确实不需要改文档，需要在最终回复中简短说明原因。
- 用户说“git commit”时，默认含义是：暂存本次相关修改，并使用简短中文提交信息提交。
- 提交信息保持短句，不使用英文长句，例如：`改用本地音标`、`修复统计查询`、`更新部署文档`。
- 提交前检查 `git status --short`，只提交与本次任务相关的文件，不混入无关改动。

## 测试环境

- Python 单元测试在本机执行，不使用单独的测试环境配置文件。
- 镜像构建和冒烟检查统一通过 SSH 在测试机 `typetest` 执行。复用 `typing-practice/scripts/check_image.py`，不另建 SSH 版测试逻辑或测试配置文件；测试机只需 Docker 和 Python 3，不需要安装应用依赖。
- 开始镜像测试前，先执行 `ssh -o BatchMode=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 typetest true`。连接失败时，立即报告 SSH 原始错误并停止镜像测试流程；不得自动换主机、改为本机测试或以历史结果代替本次验证。连接成功后再检查 Python / Docker、传输文件和构建镜像。
- 镜像检查使用独立临时容器，不挂载生产数据、不占用服务端口、不修改部署目录或重启现有服务。测试临时目录和容器在完成后清理。
- Python 测试优先使用仓库根目录的 `.venv`；没有虚拟环境时使用本机 Python，并按对应项目的依赖文件安装依赖。
- 当前 Python 测试不需要 gcc；Python 内置 `sqlite3` 可直接使用。

## typing-practice 测试规则

- `typing-practice/` 的代码、脚本和配置改动按影响范围验证，不再每次默认运行全量测试；纯文档改动只核对内容、链接和命令。
- 局部改动执行相关模块测试及直接调用它的接口测试。只改前端逻辑时运行对应 Node 单元测试；只改模板或静态资源时运行页面渲染测试，无需运行全部 Python 用例。
- 修改 `app.py`、`config.py`、`srs.py`、`memory.py`、`stats.py` 等共享核心、数据库结构/迁移、应用依赖或启动配置，跨多个业务模块或无法确定影响范围时，运行全量 Python 测试。发布前也运行全量；普通提交本身不要求全量。
- 修改单个测试文件时运行该文件；修改共用测试夹具时覆盖其调用方。同一轮改动完成后验证一次；只有新增相关改动、测试失败或存在未解决问题时才重复执行。
- 具体选取方法与耗时分析见 `docs/typing-practice/TESTING.md`。
- `typing-practice` 当前是 Python Flask + SQLite 应用，运行依赖见 `typing-practice/backend/requirements.txt`。
- 在仓库根目录运行，测试目录是 `typing-practice/backend`。以下是全量命令；定向执行可替换 `-p` 文件名或使用 `-k` 选择测试：

```powershell
python -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

- Windows 下也可直接使用 `.\.venv\Scripts\python.exe` 替代命令中的 `python`，无需激活虚拟环境。
- 如果测试因环境缺失失败，需要说明缺失项、已尝试的命令和本机安装或配置步骤；不要只写“未测试”。

## typing-practice 验证范围

- 按上述范围运行本机单元测试，最终说明执行了哪些测试；不以用例数量作为覆盖充分的依据。
- 新增/删除后端模块、改变导入/依赖、修改 Dockerfile、`.dockerignore`、镜像打包范围或启动/部署配置，以及发布前，还需在 `typetest` 构建并检查实际镜像；缺少运行条件时说明已尝试的命令与缺失项，不能用源码测试通过代替镜像验证。
- 只改工作流编排或验证文档且镜像内容、依赖和启动方式未变化时，核对工作流语法与命令，复用本轮已通过的镜像验证，不重复构建；最终说明复用情况。
- GitHub Actions 不运行独立测试任务；单元测试在本机执行，Docker 镜像检查在 `typetest` 执行。
- 涉及 SQLite 读取、Anki 数据库读取、统计存储时，必须在本地 Python 测试或服务环境中验证。
