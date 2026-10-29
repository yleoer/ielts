# Codex 项目规范

## 通用规则

- 每次修改代码、脚本、配置、生成流程或用户可见行为时，必须同步更新相关文档。
- 如果本次修改确实不需要改文档，需要在最终回复中简短说明原因。
- 用户说“git commit”时，默认含义是：暂存本次相关修改，并使用简短中文提交信息提交。
- 提交信息保持短句，不使用英文长句，例如：`改用本地音标`、`修复统计查询`、`更新部署文档`。
- 提交前检查 `git status --short`，只提交与本次任务相关的文件，不混入无关改动。

## 测试环境

- 测试在本机执行，不使用单独的测试环境配置文件或 SSH 测试模式。
- Python 测试优先使用仓库根目录的 `.venv`；没有虚拟环境时使用本机 Python，并按对应项目的依赖文件安装依赖。
- 当前 Python 测试不需要 gcc；Python 内置 `sqlite3` 可直接使用。

## typing-practice 测试规则

- 任何涉及 `typing-practice/` 的修改都必须运行测试。
- `typing-practice` 当前是 Python Flask + SQLite 应用，运行依赖见 `typing-practice/backend/requirements.txt`。
- 在仓库根目录运行，测试目录是 `typing-practice/backend`。激活本地 Python 虚拟环境后执行：

```powershell
python -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

- Windows 下也可直接使用 `.\.venv\Scripts\python.exe` 替代命令中的 `python`，无需激活虚拟环境。
- 如果测试因环境缺失失败，需要说明缺失项、已尝试的命令和本机安装或配置步骤；不要只写“未测试”。

## typing-practice 验证范围

- 运行本地 Python 单元测试。
- 如涉及部署或容器配置，除 Python 测试外，再额外运行本地 Docker/服务验证；缺少运行条件时明确说明。
- 涉及 SQLite 读取、Anki 数据库读取、统计存储时，必须在本地 Python 测试或服务环境中验证。
