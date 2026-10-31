# 打字练习系统概览

“词间”使用 Python 3.12+、Flask/Jinja2、Vue 3 和 SQLite。Anki collection.anki2 只读提供 Word Atlas 完整词库用于统计，已学习词条用于练习，py-fsrs 独立管理中文提示下的英文拼写记忆。

## 数据与界面

只支持 Word Atlas 的固定 22 字段结构。Word、UK/US、PartOfSpeech、MeaningZH、ExampleEN/ExampleZH、CEFR、Topic、Illustration、SourceId 分别提供词面、音标、词性、释义、例句、等级、分类、插图和稳定身份。文本先去除 HTML 标签再解码实体；媒体接口只提供插图，不返回音频。

词条新增 `chinese_senses` 列表，每项为 `{part_of_speech, chinese_meaning}`：先取 PartOfSpeech / MeaningZH 首义项，再按原顺序读取 MoreSenses 的 `atlas-sense` 块。其他义项仅提取词性与中文文本，排除 `lang="en"`（含 en-*）解释、脚本与样式，解码实体并保留换行；空中文义项略过，不将原始 HTML 交给页面渲染。旧 `part_of_speech` / `chinese_meaning` 仍表示首义项，统计与同步历史展示不变。列表随只读词库、正式/自由练习队列及保存后的 `next_queue` 返回。

练习提示默认显示首义项及前两条其他义项，剩余在输入框下方展开，全部居中；具体排版与交互见 [前端说明](FRONTEND.md)。折叠仅影响展示，接口、草稿与题目快照始终保留完整列表。提交时检测完整中文义项（含词性与顺序）变化，发生变化返回 409，要求重新取题；升级前没有列表的题目继续按原首义项字段校验。无需迁移数据库或重置 FSRS 状态。Anki 词池返回独立的义项列表及条目，调用方修改不会污染缓存。

页面沿用纸色与墨绿、系统字体、本地 CSS/SVG；Vue、Axios、ECharts 通过既有 CDN 加载。页面、静态资源和 API 由同一 Flask 进程提供。

## 练习流程

页面优先恢复待提交答案及草稿，否则请求到期队列。Enter 提交英文，空输入 Space 看答案，Esc 退出；提交后立即给出本地拼写反馈，保存期间可订正。正式作答仍由后端复核，并在单个 SQLite 事务中保存复习日志与新卡片状态；确认后才计数和切题。正确反馈间隔与提交等待重叠。保存响应可直接带回重新选择的下一题，结束时无需再批量提交。

网页请求三道正式候选，仅第一道进入当前练习，其余用于插图预加载；每题保存后重新选择，不固定做完候选批次。下一题缓冲最多复用五秒，出现新到期词或手动同步后刷新。队列插图 URL 带文件版本，匹配版本的图片使用浏览器私有长期缓存。Anki 完整词库与已学词池按 SQLite `data_version` 缓存解析结果；外部提交（包括 WAL）自动失效，同步重建读取器时重新加载。

同一次提交的编号和内容不变时重复请求返回原结果。多标签页的旧卡片版本返回 409，不会重复推进记忆。网络失败保留待提交答案并提供重试。正式练习按当前可练数量动态进行；自由练习随机抽取最多 20 个不同词，包含未到期词，首次作答同样计入历史统计并更新 FSRS 与下次复习时间。自由练习冲突题目跳过后继续本轮剩余词。订正和结果页错词重练不重复计分。

## API

| 接口 | 用途 |
| --- | --- |
| GET /api/health | 公开健康检查 |
| GET /api/config | 配置和词库状态 |
| GET /api/words | 只读词库列表 |
| GET /api/practice/queue | 到期队列或自由练习词条 |
| POST /api/practice/attempts | 逐题事务保存 |
| GET /api/memory/summary | 当前词池总数、到期数量、可用新词、当天引入新词和下次到期时间 |
| GET /api/media/<note_id>/illustration | 受访问密码保护的插图 |
| GET /api/sync/status、POST /api/sync/now | 同步状态和执行同步 |
| GET /api/stats/overview | 累计作答、连续天数和有效时长汇总 |
| GET /api/stats/calendar、calendar-words | 以当月居中的一年学习记录、待复习安排与日期单词列表 |
| GET /api/stats/monthly-activity | 北京时间自然月逐日作答量与正确率 |
| GET /api/stats/word-errors | 按 SourceId 分页查询每次答错记录与答对/总次数 |
| GET /api/stats/vocabulary-progress、vocabulary-words | 完整词库 CEFR / 话题进度与状态筛选分页明细 |
| GET /api/memory/optimization、optimization/runs、optimization/runs/<id> | 自动参数优化进度、历史分页与完整评估记录 |

旧 POST /api/stats/sessions 返回 410，要求旧页面刷新。已移除旧记忆分布、错误分类、旧日历、滚动趋势和七天预报接口（mastery-distribution、mastery-words、error-types、error-type-words、heatmap、accuracy-trend、memory/forecast-words），这些路径返回 404。未提供 speed-trend、daily-duration、streak 或 milestones 路由。

`POST /api/practice/attempts` 可选查询参数 `next_limit=0..3`，默认 `0` 保持原响应。大于零时在保存成功后返回顶层 `next_queue`（结构同队列接口的 `data`），使用同一词池快照重新选择正式候选；幂等重试只保存一次作答，但可重新选择候选。下一题选择失败时仍确认已保存的作答，客户端回退到 GET 队列。该扩展不改变作答请求内容与幂等校验。

## 数据切换与运行

首次启用 FSRS 时，删除退役的 practice_sessions、word_attempts、word_mastery 表并写入迁移标记，后续不再创建这些表。Anki、媒体、同步历史和访问凭证保留。新复习数据使用 word_memory / word_reviews 保存，重启不会清理。启动时自动移除旧 word_reviews.error_type 列，新作答不再计算错误分类；已有作答、卡片和旧提交的幂等响应保留，详见 [统计迁移](statistics/SPEC.md#废弃分类字段迁移)。

配置来自 backend/config/config.yaml、typing-practice/.env 和进程环境变量；环境变量优先。正式部署继续使用缓存 Anki 数据库与持久化统计目录。Python 单元测试在本机按改动范围运行，镜像冒烟检查统一在 SSH 测试机 `typetest` 运行，连接失败立即报错并停止镜像流程；GitHub Actions 只负责构建、发布和部署，不运行测试。详见 [测试范围](TESTING.md) 与 [镜像验证](IMAGE-CHECK.md)。

详见 [选词](WORD-SELECTION.md)、[前端](FRONTEND.md)、[统计](statistics/SPEC.md)、[FSRS 参数与优化](SRS-PLAN.md)、[部署](DOCKER-DEPLOY.md)。
