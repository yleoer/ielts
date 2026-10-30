# 测试范围与执行方式

日常改动按影响范围执行本机单元测试，发布前运行全量并检查实际 Docker 镜像。Docker 镜像测试统一使用 SSH 测试机 `typetest`，见 [镜像验证](IMAGE-CHECK.md)。GitHub Actions 负责构建、推送和部署，没有独立测试任务。

## 85 项是否过多

当前 85 项分布在 9 个测试文件中，既有函数测试，也有使用临时 SQLite 和 Flask 测试客户端的回归测试。2026-10-30 在本机仓库 `.venv` 测量，85 项全部通过，总耗时约 20.9 秒，其中加载约 0.5 秒。下表是该次全量运行中各组的耗时，单独执行还会有加载开销，耗时会随机器和磁盘变化。

| 测试文件 | 数量 | 约耗时 | 主要覆盖 |
| --- | ---: | ---: | --- |
| `test_activity.py` | 7 | 1.88 秒 | 北京时间、自然月、日历、连续学习、历史明细 |
| `test_anki.py` | 10 | 0.57 秒 | 22 字段、HTML/媒体解析、牌组读取、配置与真实 APKG |
| `test_app.py` | 8 | 6.27 秒 | Flask 页面/API、完整练习流程、媒体、同步、存储错误 |
| `test_auth.py` | 8 | 1.51 秒 | 登录、凭证持久化、密码变更、重定向与访问控制 |
| `test_memory.py` | 28 | 4.09 秒 | FSRS、幂等、并发冲突、事务回滚、迁移与记忆身份 |
| `test_optimizer.py` | 3 | 0.04 秒 | 有效复习数量、时间切分、候选评估 |
| `test_optimizer_service.py` | 11 | 3.50 秒 | 训练门槛、调度、失败重试、租约与参数恢复 |
| `test_sync.py` | 1 | 0.02 秒 | 数据库及 SQLite 侧文件复制、旧侧文件清理 |
| `test_vocabulary.py` | 9 | 2.52 秒 | 完整词库、分组、分页、稳定身份与逐次错答记录 |

最慢单项是 `test_app.FlaskAppTest.test_scheduled_practice_uses_the_entire_pool_without_session_or_daily_quotas`，约 4.1 秒。它逐题完成 125 次 API 作答，超过只读接口的 100 条批量上限，并检查最终队列清空；这部分是有明确业务目的的回归覆盖。其他单项基本在半秒以内。优化器测试使用模拟训练器，不会每次运行真实 PyTorch 训练。

这些用例保护不同的边界，不建议为了减少数量删除事务、并发、迁移或接口测试。部分行为同时在存储层和 API 层检查，分别验证业务规则与接口连接，不能仅凭主题相同认定重复。真实 APKG 用例在本地完整包不存在时会跳过；其余字段/数据库测试继续运行。

可以随相关功能改动复核一些实现细节断言，例如页面测试固定检查 `vue@3.4.21`；升级 CDN 版本时，它可能造成与业务行为无关的失败。这类断言影响维护成本，但不是本次运行耗时的主要来源。

主要调整是执行范围：文档或前端局部改动无需全量后端回归；共享核心和发布前保留完整覆盖。之前镜像验证的长时间等待主要来自基础镜像与训练依赖下载，与这 85 项本机测试不是同一开销。

## 根据改动选择测试

以下是选取起点。结合实际调用关系补充接口或调用方测试；变更影响不清楚时运行全量。

| 改动 | 执行范围 |
| --- | --- |
| 纯文档 | 核对内容、链接和命令，不运行代码测试或重建镜像 |
| 前端 `app.js` / `stats.js` | 对应 `app.test.cjs` / `stats.test.cjs` 单元测试；后端契约也改变时补后端测试 |
| HTML 模板、CSS、图标等静态资源 | `test_app.FlaskAppTest.test_health_and_jinja_rendered_pages`；登录模板还需 `test_auth` |
| `auth.py` | `test_auth`，以及 `test_app` 中的媒体访问控制测试 |
| `vocabulary.py` | `test_vocabulary`，其用例通过 API 验证词库和筛选行为 |
| `activity.py` | `test_activity`、`test_memory` 的日历测试、`test_app` 的单词/统计 API 测试 |
| `anki.py` / `sync.py` | `test_anki` / `test_sync`，补 `test_app` 的相关读取、同步或媒体接口测试；字段身份规则改变时运行全量 |
| `optimize_fsrs.py` / `optimizer_service.py` | `test_optimizer`、`test_optimizer_service`、`test_app` 的优化历史 API 测试 |
| 单个测试文件 | 该文件；共用夹具变化时包含所有调用方 |
| `app.py`、`config.py`、`srs.py`、`memory.py`、`stats.py`、数据库结构/迁移、依赖、启动配置、多模块或影响不明 | 全量 Python 测试 |
| 发布前 | 全量单元测试，以及实际 Docker 镜像检查 |

同一轮改动完成后执行一次；已有结果通过且相关内容未再改变时，无需在每次回复、暂存或普通提交前重复跑。失败后修复、新增相关改动或仍有未解决问题时再运行。

## 在仓库根目录运行

全量 Python 测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

仅验证词库模块的 9 项测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_vocabulary.py'
```

仅验证页面渲染的 1 项测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_app.py' -k test_health_and_jinja_rendered_pages
```

验证优化相关的 15 项测试，使用多个 `-k` 按名称匹配，任一匹配即纳入：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_*.py' -k test_optimizer -k test_optimization_history_api_and_invalid_cursors
```

前端按文件选择单元测试；全量前端测试为：

```powershell
node --test typing-practice/frontend/src/app.test.cjs typing-practice/frontend/src/stats.test.cjs
```

`-k` 的名称应对应实际用例，检查运行结果中的测试数量，避免拼写错误导致零项通过。无需新增测试环境配置或自动选择测试的脚本。

## 何时检查 Docker 镜像

新增/删除后端模块、调整导入或依赖、修改 Dockerfile / `.dockerignore`、镜像打包范围或启动/部署配置，以及发布前，构建并用 `scripts/check_image.py` 检查实际镜像。日常仅调整现有函数内部逻辑时按上表运行相关单元测试，发布前再做镜像验证；源码测试通过不能代替镜像验证。

先按 [连接检查](IMAGE-CHECK.md#连接检查) 验证 `typetest` 的 SSH。连接失败立即报告原始错误并停止镜像流程，不自动改用其他主机、本机 Docker 或历史验证结果。连接成功且 Python / Docker 可用后再开始传输、构建与检查。

只修改工作流编排或验证文档，且镜像文件、依赖和启动方式没有变化时，校验 YAML 与命令即可，复用本轮对相同镜像内容已经通过的验证。无需重复下载依赖或重建镜像；最终回复说明复用了哪次结果。每次验证后清理临时目录、容器与本次专用镜像，不清理共享 Docker 缓存。

GitHub Actions 不自动运行这些检查。生产容器的部署健康检查与失败回滚继续保留，详见 [自动部署](AUTO-DEPLOY.md)。
