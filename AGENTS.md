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
- `local-gcc` 表示当前机器安装了 64 位 gcc，可以直接运行需要 CGO 的 Go 测试。
- `local-gcc` 可以配置 `gcc_path`；运行测试前应把该目录加入当前命令的 `Path`。
- `ssh-server` 表示当前机器不直接跑测试，必须通过 SSH 到配置好的本地服务器执行测试。
- 不再支持纯 Go SQLite 回退路径，也不要使用 `CGO_ENABLED=0` 作为测试替代。

## typing-practice 测试规则

- 任何涉及 `typing-practice/` 的修改都必须运行测试。
- `typing-practice` 后端只支持 `github.com/mattn/go-sqlite3`，因此测试环境必须支持 CGO 和 gcc。
- 后端测试目录默认是 `typing-practice/backend`，默认命令：

```powershell
go test ./...
```

- 当 `CODEX_ENV.md` 设置 `test_mode: local-gcc` 时，在本机后端目录运行 `go test ./...`。
- 如果 `local-gcc` 配置了 `gcc_path`，先临时加入 `Path`，例如 `$env:Path = '<gcc_path>;' + $env:Path`。
- 当 `CODEX_ENV.md` 设置 `test_mode: ssh-server` 时，通过 SSH 在服务器仓库目录运行同等测试命令。
- 如果没有 `CODEX_ENV.md`，先尝试本机 `gcc --version` 和 `go test ./...`；本机缺 gcc 时，需要让用户补充服务器配置，不要改用 `CGO_ENABLED=0`。
- 如果测试因环境缺失失败，需要说明缺失项、已尝试的命令，以及需要的 `CODEX_ENV.md` 配置项；不要只写“未测试”。

## typing-practice 环境差异

- 有本地 gcc 的环境：使用本机 `local-gcc` 模式运行 `go test ./...`。
- 无本地 gcc 的环境：使用 `ssh-server` 模式，在本地服务器工作区运行 `go test ./...`。
- 本地服务器环境：如涉及部署或容器配置，除后端测试外，再额外运行对应的 Docker/服务验证。
- 涉及 SQLite 读取、Anki 数据库读取、统计存储时，必须在支持 CGO/gcc 的环境中验证。
