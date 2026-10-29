# 打字练习系统概览

“词间”使用 Python 3.12+、Flask/Jinja2、Vue 3 和 SQLite。Anki collection.anki2 只读提供 Word Atlas 完整词库用于统计，已学习词条用于练习，py-fsrs 独立管理中文提示下的英文拼写记忆。

## 数据与界面

只支持 Word Atlas 的固定 22 字段结构。Word、UK/US、PartOfSpeech、MeaningZH、ExampleEN/ExampleZH、CEFR、Topic、Illustration、SourceId 分别提供词面、音标、词性、释义、例句、等级、分类、插图和稳定身份。文本先去除 HTML 标签再解码实体；媒体接口只提供插图，不返回音频。

页面沿用纸色与墨绿、系统字体、本地 CSS/SVG；Vue、Axios、ECharts 通过既有 CDN 加载。页面、静态资源和 API 由同一 Flask 进程提供。

## 练习流程

页面优先恢复待提交答案及草稿，否则请求到期队列。Enter 提交英文，空输入 Space 看答案，Esc 退出；答错后订正，正确输入后自动切题。正式作答由后端判分，并在单个 SQLite 事务中保存复习日志与新卡片状态。保存成功后继续下一题，结束时无需再批量提交。

同一次提交的编号和内容不变时重复请求返回原结果。多标签页的旧卡片版本返回 409，不会重复推进记忆。网络失败保留待提交答案并提供重试。正式练习按当前可练数量动态进行；自由练习随机抽取最多 20 个不同词，包含未到期词，首次作答同样计入历史统计并更新 FSRS 与下次复习时间。自由练习冲突题目跳过后继续本轮剩余词。订正和结果页错词重练不重复计分。

## API

| 接口 | 用途 |
| --- | --- |
| GET /api/health | 公开健康检查 |
| GET /api/config | 配置和词库状态 |
| GET /api/words | 只读词库列表 |
| GET /api/practice/queue | 到期队列或自由练习词条 |
| POST /api/practice/attempts | 逐题事务保存 |
| GET /api/memory/summary | 当前词池的记忆状态、到期数量、未开始词数和下次到期时间 |
| GET /api/media/<note_id>/illustration | 受访问密码保护的插图 |
| GET /api/sync/status、POST /api/sync/now | 同步状态和执行同步 |
| GET /api/stats/overview、heatmap、accuracy-trend | 正式作答汇总 |
| GET /api/stats/word-errors | 按 SourceId 分页查询每次答错记录与答对/总次数 |
| GET /api/stats/vocabulary-progress、vocabulary-words | 完整词库 CEFR / 话题进度与状态筛选分页明细 |
| GET /api/memory/optimization、optimization/runs、optimization/runs/<id> | 自动参数优化进度、历史分页与完整评估记录 |

旧 POST /api/stats/sessions 返回 410，要求旧页面刷新。已移除旧记忆分布和错误分类接口（mastery-distribution、mastery-words、error-types、error-type-words），这些路径返回 404。未提供 speed-trend、daily-duration、streak 或 milestones 路由。

## 数据切换与运行

首次启用 FSRS 时，删除退役的 practice_sessions、word_attempts、word_mastery 表并写入迁移标记，后续不再创建这些表。Anki、媒体、同步历史和访问凭证保留。新复习数据使用 word_memory / word_reviews 保存，重启不会清理。启动时自动移除旧 word_reviews.error_type 列，新作答不再计算错误分类；已有作答、卡片和旧提交的幂等响应保留，详见 [统计迁移](statistics/SPEC.md#废弃分类字段迁移)。

配置来自 backend/config/config.yaml、typing-practice/.env 和进程环境变量；环境变量优先。正式部署继续使用缓存 Anki 数据库与持久化统计目录。测试全部在本地运行。

详见 [选词](WORD-SELECTION.md)、[前端](FRONTEND.md)、[统计](statistics/SPEC.md)、[FSRS 参数与优化](SRS-PLAN.md)、[部署](DOCKER-DEPLOY.md)。
