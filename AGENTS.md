# Codex 项目规范

## 通用规则

- 每次修改代码、脚本、配置、生成流程或用户可见行为时，必须同步更新相关文档。
- 如果本次修改确实不需要改文档，需要在最终回复中简短说明原因。
- 用户说“git commit”时，默认含义是：暂存本次相关修改，并使用简短中文提交信息提交。
- 提交信息保持短句，不使用英文长句，例如：`改用本地音标`、`修复统计查询`、`更新部署文档`。
- 提交前检查 `git status --short`，只提交与本次任务相关的文件，不混入无关改动。

## Codex 环境配置

- 每次涉及测试、构建或运行服务前，先检查仓库根目录是否存在 `CODEX_ENV.md`。
- `CODEX_ENV.md` 是本地私有配置，不提交到 Git；配置格式参考 `CODEX_ENV.example.md`。
- 支持的 `test_mode` 只有两种：`local-gcc` 和 `ssh-server`。
- `test_mode` 仍只支持 `local-gcc` 和 `ssh-server`；Python 测试不需要 gcc，可直接在当前 Python 环境运行。
- `ssh-server` 仍可用于需要在本地服务器上验证 Docker 或服务运行的场景。

## typing-practice 测试规则

- 任何涉及 `typing-practice/` 的修改都必须运行测试。
- `typing-practice` 当前是 Python Flask + SQLite 应用，运行依赖见 `typing-practice/backend/requirements.txt`。
- 后端测试目录默认是 `typing-practice/backend`，默认命令：

```powershell
python -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

- `local-gcc` 模式下在本机运行上述 Python 测试命令；当前测试不需要 gcc。
- `ssh-server` 模式下通过 SSH 在服务器仓库目录运行同等测试命令。
- 如果测试因环境缺失失败，需要说明缺失项、已尝试的命令，以及需要的 `CODEX_ENV.md` 配置项；不要只写“未测试”。

## typing-practice 环境差异

- 本地环境：运行 Python 单元测试；Python 内置 sqlite3 不需要 gcc。
- 本地服务器环境：如涉及部署或容器配置，除 Python 测试外，再额外运行对应的 Docker/服务验证。
- 涉及 SQLite 读取、Anki 数据库读取、统计存储时，必须在 Python 测试或服务环境中验证。
