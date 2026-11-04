# 测试范围与执行方式

日常改动按影响范围执行本机单元测试，发布前运行全量并检查实际 Docker 镜像。Docker 镜像测试统一使用 SSH 测试机 `typetest`，见 [镜像验证](IMAGE-CHECK.md)。GitHub Actions 负责构建、推送和部署，没有独立测试任务。

## 保留有业务意义的覆盖

测试包含函数用例、临时 SQLite 回归和 Flask 接口流程：

| 文件 | 覆盖 |
| --- | --- |
| `test_anki.py` | Word Atlas 22 字段映射、全部中文义项、HTML 清理、插图引用、子牌组与外部提交后的缓存刷新；真实 APKG 用例在本地完整包不存在时跳过 |
| `test_sync.py` | 复制 `collection.anki2` 及 SQLite 附属文件 |
| `test_app.py` | 仅保留三条路由、词库快照、作答去重与游标分页、大日志分页、非法请求不写入、网页版历史一次性导入 |
| `test_auth.py` | 健康检查公开、令牌校验、`ACCESS_TOKEN` 读取与旧 `ACCESS_PASSWORD` 回退 |

删除实现时同步删除只绑定该内部接口的断言，避免把测试数量本身当作覆盖目标。防御性代码的取舍见 [防御性代码审计](../DEFENSIVE-PROGRAMMING.md)。判题、FSRS、统计与参数优化已移到桌面端，由 `typing-desktop` 的 `cargo test` 与 Node 测试覆盖，见 [typing-desktop/README.md](../../typing-desktop/README.md)。

## 根据改动选择测试

以下是选取起点。结合实际调用关系补充接口测试；变更影响不清楚时运行全量。

| 改动 | 执行范围 |
| --- | --- |
| 纯文档 | 核对内容、链接和命令，不运行代码测试或重建镜像 |
| 桌面端前端 `app.js` / `stats.js` | 对应 `app.test.cjs` / `stats.test.cjs`；接口契约也改变时补 `cargo test` |
| `auth.py` | `test_auth` |
| `ledger.py` | `test_app` |
| `anki.py` / `sync.py` | `test_anki` / `test_sync`，以及 `test_app` 的词库快照测试；字段身份规则改变时运行全量 |
| 单个测试文件 | 该文件；共用夹具变化时包含所有调用方 |
| `app.py`、`config.py`、数据库结构/迁移、依赖、启动配置、多模块或影响不明 | 全量 Python 测试 |
| 发布前 | 全量单元测试，以及实际 Docker 镜像检查 |

同一轮改动完成后执行一次；已有结果通过且相关内容未再改变时，无需在每次回复、暂存或普通提交前重复跑。失败后修复、新增相关改动或仍有未解决问题时再运行。

## 在仓库根目录运行

全量 Python 测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

仅验证作答日志与路由：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_app.py'
```

按名称选择单项，例如网页版历史导入：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_app.py' -k test_web_history_is_imported_once_as_the_initial_log
```

桌面端前端单元测试：

```powershell
node --test typing-desktop/frontend/src/app.test.cjs typing-desktop/frontend/src/stats.test.cjs
```

`-k` 的名称应对应实际用例，检查运行结果中的测试数量，避免拼写错误导致零项通过。无需新增测试环境配置或自动选择测试的脚本。

## 何时检查 Docker 镜像

新增/删除后端模块、调整导入或依赖、修改 Dockerfile / `.dockerignore`、镜像打包范围或启动/部署配置，以及发布前，构建并用 `scripts/check_image.py` 检查实际镜像。日常仅调整现有函数内部逻辑时按上表运行相关单元测试，发布前再做镜像验证；源码测试通过不能代替镜像验证。

先按 [连接检查](IMAGE-CHECK.md#连接检查) 验证 `typetest` 的 SSH。连接失败立即报告原始错误并停止镜像流程，不自动改用其他主机、本机 Docker 或历史验证结果。连接成功且 Python / Docker 可用后再开始传输、构建与检查。

只修改工作流编排或验证文档，且镜像文件、依赖和启动方式没有变化时，校验 YAML 与命令即可，复用本轮对相同镜像内容已经通过的验证。无需重复下载依赖或重建镜像；最终回复说明复用了哪次结果。每次验证后清理临时目录、容器与本次专用镜像，不清理共享 Docker 缓存。

GitHub Actions 不自动运行这些检查。生产容器的部署健康检查与失败回滚继续保留，详见 [自动部署](AUTO-DEPLOY.md)。
