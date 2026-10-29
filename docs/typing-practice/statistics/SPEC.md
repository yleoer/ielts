# 统计模型与接口

## 数据源

word_reviews 保存正式练习和自由练习首次作答的追加日志，包含作答 ID、会话 ID、稳定词条标识、答案、评分、有效耗时、首次输入时间、答案长度、实际作答时间、接收时间、前后卡片状态与配置版本。word_memory 保存当前 FSRS 卡片状态；srs_configs 保存历史调度配置；practice_items 保存带版本和模式的题目，有效期 7 天。

practice_sessions、word_attempts、word_mastery 是退役表，切换 FSRS 时删除，后续不再创建；schema_migrations 记录切换状态。anki_sync_history、anki_sync_added_words、访问凭证及新的 FSRS 复习数据保留。

## 汇总口径

- 统计成功提交的正式练习与自由练习首次作答，自由练习允许未到期词，更新历史统计和 FSRS；同一词下一次独立作答算新一次，订正与结果页错词重练不重复统计。
- 会话数是日志中 session_id 的去重数，包括中途退出但已有作答的会话。
- 准确率由后端判题结果计算；有效时长按 duration_ms 求和。
- 日历、趋势、当天新词计数和连续天数统一按北京时间。跨午夜的一轮会按每题实际时间分别计入两天。
- 同一词面但不同 SourceId 不合并；同一 SourceId 的 note_id 改变不会产生新记忆。
- 等级进度和话题进度以配置牌组及子牌组的全部有效 Word Atlas 词条为分母，按 SourceId 去重；总数不受 Anki 学习状态限制。网站存在 word_memory 记录即为已学；Review 且 stability >= 21 的词显示“已掌握”（内部 status=mastered），其余已学词为学习中。未开始指尚无网站 FSRS 记录。待复习仍仅统计原练习池，与已掌握不互斥。
- 后端仅判定正误并自动评分，支持答案变体；不再计算或保存错误分类。输入中的差异由前端按当时答案对齐着色。

## 接口

POST /api/practice/attempts 是唯一正式练习写入入口。attempt_id 幂等，完全相同的重试返回第一次保存的结果；修改已提交内容或提交过期卡片版本返回 409。事务失败时卡片与日志一起回滚。

GET /api/stats/overview、heatmap、accuracy-trend 提供作答汇总，vocabulary-progress、vocabulary-words 提供完整词库进度与明细，word-errors 提供逐次答错记录。GET /api/memory/summary 提供待复习数量、全部未开始词数（`new_available`）、当天已引入新词数（`new_today`）、下一次到期时间和 `due_forecast`，不设每日新词上限。

`due_forecast` 固定返回按北京时间排列的今天及后六天，例如 `[{"date":"2026-10-29","count":12}, ...]`，没有待复习词的日期补零。根据当前词池内已有 FSRS 卡片的 `due` 日期计数，今天桶还包含所有逾期词和今天稍后到期的词；学习、重学、长期复习均计入，未开始的词不计入。同一稳定词条仅计一次，不预测未来作答导致的重复复习或新词安排，不修改卡片、作答日志或到期时间。

`GET /api/memory/forecast-words?date=YYYY-MM-DD` 返回所选日期的全部待复习单词，放在 `data` 数组中；每项包含当前词条信息及 `due`、`state`、`status`、`is_due` 等记忆字段，按到期时间和 SourceId 排序，不截断结果。日期必须是北京时间今天及后六天内的有效日期，否则返回 400。今天包含逾期与今天稍后到期的词；其他日期只包含当天到期词，与 `due_forecast` 共用日期分桶规则，不写入练习记录。

旧 POST /api/stats/sessions 返回 410，不允许旧客户端重新污染统计。无 daily-duration、speed-trend、streak 或 milestones 独立路由。

## 完整词库进度接口

`GET /api/stats/vocabulary-progress` 返回 `{overall,levels,topics}`。每个分组含 `value,label,total,learned,new,learning,mastered`；`learned=learning+mastered`，`total=new+learning+mastered`。页面按“学习中 / 已掌握 / 总单词数”依次展示 `learning / mastered / total`，不将 learned 当作学习中。levels 始终按 A1、A2、B1、B2、C1、C2 排列，包含零值；异常或空 CEFR 汇入“未分级”，有词时追加该组。CEFR 去 HTML、去空格并大写；话题取 Topic（接口字段 category），空值归入“未分类”，按首次出现顺序输出。

`GET /api/stats/vocabulary-words?dimension=cefr&value=A1&status=all&offset=0&limit=100` 返回 `{items,total,next_offset}`。dimension 支持 `cefr/topic`，value 为进度接口的原分组值，status 支持 `all/new/learning/mastered`。每词提供现有词条字段（含 cefr/category）、记忆状态、FSRS 到期字段（如有），以及 `correct_attempts/total_attempts`（无网站作答记录时均为 0），按英文词面和 SourceId 排序。total 为当前筛选匹配数，next_offset 为下一页偏移，无后续数据时为 null；不静默截断整个分组。offset 必须为非负整数，limit 为 1–200，默认为 100；非法参数返回 400。两接口只读，不签发题目、不写入记忆或作答日志；数据源不可用返回 503。

已移除不再使用的 mastery-distribution/mastery-words、error-types/error-type-words 接口及其统计查询，旧路径返回 404。原练习队列、自由练习、待复习预报及 `/api/words` 仍使用 Anki 已学习词池。

## 单词答错记录接口

`GET /api/stats/word-errors?source_id=...&before_id=0&limit=50` 按稳定 SourceId 读取网站作答日志，返回 `{items,correct_attempts,total_attempts,next_before_id}`，两个 attempts 字段为全部作答的正确/总次数；items 仅含 `is_correct=0` 的逐次记录，每项包含 `id,word,user_input,reviewed_at`，保留当时答案与原始输入，按 id 倒序排列。前端仅显示时间和输入；word 用于定位输入的错写、多写与漏写位置，不另行展示正确答案或错误类型。默认每页 50 条，最多 200 条；有后续记录时 next_before_id 为本页最后一条 id，否则为 null。游标只限制分页记录，不改变答对/总次数；相同词面、不同 SourceId 不混用历史。同一提交幂等重试不增加次数，订正和即时错词重练不计入。

source_id 不可为空，before_id 必须为非负整数，limit 为 1–200，非法参数返回 400。没有作答历史或只有正确作答时返回空 items 与对应计数；数据查询只读并受既有访问认证保护。`/api/memory/forecast-words` 同样追加 `correct_attempts/total_attempts`，使所有单词明细弹窗展示一致。

## 废弃分类字段迁移

新建的 word_reviews 不再包含 error_type，正式作答响应不再生成该字段。启动时在同一事务内检查旧表；存在 error_type 时执行 DROP COLUMN，并记录 `remove-error-type-v1`。迁移可重复执行，保留其余复习日志、卡片 ID、到期时间、待提交题目、优化配置和作答次数，不重建或清空历史。旧 response_json 原样保留，以确保历史 attempt_id 重试仍返回首次保存的结果；新作答和逐次答错接口均不携带错误分类。

答错记录接口同时去掉已不使用的总错误次数和单次耗时字段；原始作答日志中的 duration_ms 继续用于有效时长与 FSRS 参数优化。

## 参数优化

正式练习与自由练习的首次作答均产生 ReviewLog，完整保留用于服务端后台优化；订正与结果页立即错词重练不产生。累计 1,000 条有效间隔复习触发首次训练，随后按自然月、有新增至少 100 条有效记录时评估；同一词相邻复习间隔不足 24 小时的记录不计入有效复习门槛。独立进程只读日志快照；验证改善后由协调线程启用参数，保留所有到期计划和原始日志。

`fsrs_optimization_runs` 保存所有运行、启用、拒绝、跳过、失败、中断及配置变更结果，包含训练范围、快照 ID、数据量、验证指标、原用/候选权重和配置版本。`fsrs_optimizer_state` 保存进度、下次评估时间和当前启用指针；`srs_configs` 保存启用的调度配置。

只读 API 均返回标准 `{success:true,data:...}` 并沿用访问认证：`GET /api/memory/optimization` 返回配置与进度；`GET /api/memory/optimization/runs?before_id=0&limit=20` 返回 `{items,next_before_id}`（每页最多 100 条，非法游标返回 400）；`GET /api/memory/optimization/runs/<id>` 返回完整记录（不存在返回 404）。服务启动时检查一次，后台检查周期默认 24 小时，进度反映最近一次检查；首次门槛与月度计划在下一次日常检查中触发。详见 [FSRS 实施说明](../SRS-PLAN.md)。
