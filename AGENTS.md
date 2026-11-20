# Codex 项目规范

## 通用规则

- 这是个人自用项目，优先简单直接的实现；按实际使用场景保留必要检查，不为假设的攻击、多实例或极端数据增加防御层和兼容分支。

- 每次修改代码、脚本、配置、生成流程或用户可见行为时，必须同步更新相关文档。
- 如果本次修改确实不需要改文档，需要在最终回复中简短说明原因。
- 用户说“git commit”时，默认含义是：暂存本次相关修改，并使用简短中文提交信息提交。
- 提交信息保持短句，不使用英文长句，例如：`改用本地音标`、`修复统计查询`、`更新部署文档`。
- 提交前检查 `git status --short`，只提交与本次任务相关的文件，不混入无关改动。

## 测试环境

- Python 单元测试在本机执行，不使用单独的测试环境配置文件。
- 镜像构建和冒烟检查在本机 Docker 执行，复用 `typing-practice/scripts/check_image.py`，不另建测试逻辑或测试配置文件；镜像检查只需 Docker 和 Python 3，不需要安装应用依赖。命令见 `docs/typing-practice/IMAGE-CHECK.md`。
- 开始镜像测试前，先执行 `docker info` 确认 Docker 可用。不可用时立即报告原始错误并停止镜像测试流程；不得以源码测试或历史结果代替本次验证。
- 构建使用 `docker build --network host`：本机 DNS 走代理，默认网络下构建容器无法解析软件源。
- 镜像检查使用独立临时容器，不挂载生产数据、不占用服务端口、不修改部署目录或重启现有服务。完成后清理本次的容器和临时镜像标签，不清理共享构建缓存。
- Python 测试优先使用仓库根目录的 `.venv`；没有虚拟环境时使用本机 Python，并按对应项目的依赖文件安装依赖。
- 当前 Python 测试不需要 gcc；Python 内置 `sqlite3` 可直接使用。

## typing-practice 测试规则

- `typing-practice/` 的代码、脚本和配置改动按影响范围验证，不再每次默认运行全量测试；纯文档改动只核对内容、链接和命令。
- 局部改动执行相关模块测试及直接调用它的接口测试。
- 修改 `app.py`、`config.py`、`ledger.py` 等共享核心、数据库结构/迁移、应用依赖或启动配置，跨多个业务模块或无法确定影响范围时，运行全量 Python 测试。发布前也运行全量；普通提交本身不要求全量。
- 修改单个测试文件时运行该文件；修改共用测试夹具时覆盖其调用方。同一轮改动完成后验证一次；只有新增相关改动、测试失败或存在未解决问题时才重复执行。
- 具体选取方法与耗时分析见 `docs/typing-practice/TESTING.md`。
- `typing-practice` 当前是供桌面端使用的最小同步服务（Python Flask + SQLite：词库快照、作答日志、访问令牌），运行依赖见 `typing-practice/backend/requirements.txt`。
- 在仓库根目录运行，测试目录是 `typing-practice/backend`。以下是全量命令；定向执行可替换 `-p` 文件名或使用 `-k` 选择测试：

```powershell
python -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

- Windows 下也可直接使用 `.\.venv\Scripts\python.exe` 替代命令中的 `python`，无需激活虚拟环境。
- 如果测试因环境缺失失败，需要说明缺失项、已尝试的命令和本机安装或配置步骤；不要只写“未测试”。

## typing-desktop 测试规则

- 桌面端 Rust 测试在 `typing-desktop` 目录运行 `cargo test`；只改某个模块时可用 `cargo test -p cijian-core --test <文件名>` 定向执行。
- 只改前端逻辑时运行 `node --test typing-desktop/frontend/src/*.test.cjs`。
- 改模板、样式、页面流程（焦点、键盘、结果页与等待页、统计页加载）、协议处理（`app/src/main.rs`）或 Tauri 配置时，在 Linux 上运行 `python3 typing-desktop/e2e/run.py`：它会自动构建，并在 Xvfb 里通过 tauri-driver 驱动真实窗口，不占用桌面的键鼠。发布前也运行一次。分层、命令与仍需手工检查的项目见 `docs/typing-desktop/TESTING.md`。
- 修改同步协议（`typing-practice/backend/ledger.py` 或 `typing-desktop/core/src/sync.rs`、`remote.rs`）时，两端测试都要运行。

## typing-practice 验证范围

- 按上述范围运行本机单元测试，最终说明执行了哪些测试；不以用例数量作为覆盖充分的依据。
- 新增/删除后端模块、改变导入/依赖、修改 Dockerfile、`.dockerignore`、镜像打包范围或启动/部署配置，以及发布前，还需在本机 Docker 构建并检查实际镜像；缺少运行条件时说明已尝试的命令与缺失项，不能用源码测试通过代替镜像验证。
- 只改工作流编排或验证文档且镜像内容、依赖和启动方式未变化时，核对工作流语法与命令，复用本轮已通过的镜像验证，不重复构建；最终说明复用情况。
- GitHub Actions 不运行独立测试任务；单元测试和 Docker 镜像检查都在本机执行。
- 涉及 SQLite 读取、Anki 数据库读取、统计存储时，必须在本地 Python 测试或服务环境中验证。
