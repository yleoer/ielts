# 测试范围与执行方式

日常改动按影响范围执行本机单元测试，发布前运行全量并检查实际 Docker 镜像。Docker 镜像测试统一使用 SSH 测试机 `typetest`，见 [镜像验证](IMAGE-CHECK.md)。GitHub Actions 负责构建、推送和部署，没有独立测试任务。

## 保留有业务意义的覆盖

测试包含函数用例、临时 SQLite 回归和 Flask 接口流程。事务、并发、迁移和接口测试保护不同边界；存储层与 API 层出现相似主题时，分别验证业务规则和接口连接，不能仅凭名称相近认定重复。真实 APKG 用例在本地完整包不存在时会跳过，优化器测试使用模拟训练器，不执行真实 PyTorch 训练。

删除实现时同步删除只绑定该内部接口或重复运行时自校验的断言。页面依赖版本等实现细节断言应随相关改动复核，避免把测试数量本身当作覆盖目标。防御性代码的取舍见 [防御性代码审计](../DEFENSIVE-PROGRAMMING.md)。

日常效率主要通过选择执行范围控制：文档或前端局部改动无需全量后端回归，共享核心和发布前保留完整覆盖。镜像验证的耗时主要来自基础镜像与训练依赖下载，与本机单元测试不是同一开销。

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

### 全部中文义项回归

- `test_anki.py`：首义项与 MoreSenses 的顺序、词性、空字段、HTML 实体与换行、英文解释排除及外部更新。
- `test_app.py`：只读词库、正式/自由队列及 `next_queue` 的完整义项契约，展开区在输入框之后。
- `test_memory.py`：义项变化时拒绝旧题且不写入记忆，升级前题目仍可提交。
- `app.test.cjs`：义项分区、展开/收起、换词重置、完整草稿恢复与旧草稿回退、错词重练不重复计分，以及鼠标回焦与键盘原生焦点。

浏览器检查桌面和窄屏的居中排版、长文本换行、词性/词义配色、44px 展开按钮、输入框展开前后位置，以及输入、订正和换词。图片尺寸夹具只验证布局，不代表真实词义插画或真实手机软键盘；读屏和系统软键盘需在相应设备中验证。

此功能涉及 `memory.py` 作答校验，完整改动按共享核心规则执行全量本机 Python 测试；后续仅改前端时按上表缩小范围。未改变应用依赖、运行时导入、后端模块、打包或启动方式，无需单独重建镜像。

## 在仓库根目录运行

全量 Python 测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

仅验证词库模块（含易错优先排序、筛选与分页）的测试：

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
