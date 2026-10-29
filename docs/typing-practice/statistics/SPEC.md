# 统计模型与接口

## 数据源

word_reviews 是正式作答的追加日志，保存作答 ID、会话 ID、稳定词条标识、答案、评分、错误类型、有效耗时、首次输入时间、答案长度、实际作答时间、接收时间、前后卡片状态与配置版本。word_memory 保存当前 FSRS 卡片状态；srs_configs 保存历史调度配置；practice_items 保存带版本的正式题目，有效期 7 天。

practice_sessions、word_attempts、word_mastery 是退役表，切换 FSRS 时删除，后续不再创建；schema_migrations 记录切换状态。anki_sync_history、anki_sync_added_words、访问凭证及新的 FSRS 复习数据保留。

## 汇总口径

- 只统计成功提交的正式复习；同一词再次到期作答算新一次。
- 会话数是日志中 session_id 的去重数，包括中途退出但已有作答的会话。
- 准确率由后端判题结果计算；有效时长按 duration_ms 求和。
- 日历、趋势、新词额度和连续天数统一按北京时间。跨午夜的一轮会按每题实际时间分别计入两天。
- 同一词面但不同 SourceId 不合并；同一 SourceId 的 note_id 改变不会产生新记忆。
- 未开始、学习中、已掌握按当前 Anki 练习池计算；已掌握需要 Review 状态且 stability >= 21。待复习是独立状态，不互斥于已掌握。
- 错误类型为 spelling、missing_letter、extra_letter、completely_wrong、skipped，支持答案变体。

## 接口

POST /api/practice/attempts 是唯一正式练习写入入口。attempt_id 幂等，完全相同的重试返回第一次保存的结果；修改已提交内容或提交过期卡片版本返回 409。事务失败时卡片与日志一起回滚。

GET /api/stats/overview、heatmap、accuracy-trend、mastery-distribution、mastery-words、error-types、error-type-words 提供汇总和明细。mastery-words 的 level 支持 new、learning、mastered、due。GET /api/memory/summary 提供待复习数量、新词额度、下一次到期时间和 `due_forecast`。

`due_forecast` 固定返回按北京时间排列的今天及后六天，例如 `[{"date":"2026-10-29","count":12}, ...]`，没有待复习词的日期补零。根据当前词池内已有 FSRS 卡片的 `due` 日期计数，今天桶还包含所有逾期词和今天稍后到期的词；学习、重学、长期复习均计入，未开始的词不计入。同一稳定词条仅计一次，不预测未来作答导致的重复复习或新词安排，不修改卡片、作答日志或到期时间。

`GET /api/memory/forecast-words?date=YYYY-MM-DD` 返回所选日期的全部待复习单词，放在 `data` 数组中；每项包含当前词条信息及 `due`、`state`、`status`、`is_due` 等记忆字段，按到期时间和 SourceId 排序，不截断结果。日期必须是北京时间今天及后六天内的有效日期，否则返回 400。今天包含逾期与今天稍后到期的词；其他日期只包含当天到期词，与 `due_forecast` 共用日期分桶规则，不写入练习记录。

旧 POST /api/stats/sessions 返回 410，不允许旧客户端重新污染统计。无 daily-duration、speed-trend、streak 或 milestones 独立路由。

## 参数优化

完整日志保留用于服务端后台优化，订正、自由练习和立即错词重练不产生 ReviewLog。累计 1,000 条有效间隔复习触发首次训练，随后按自然月、有新增至少 100 条有效记录时评估。独立进程只读日志快照；验证改善后由协调线程启用参数，保留所有到期计划和原始日志。

`fsrs_optimization_runs` 保存所有运行、启用、拒绝、跳过、失败、中断及配置变更结果，包含训练范围、快照 ID、数据量、验证指标、原用/候选权重和配置版本。`fsrs_optimizer_state` 保存进度、下次评估时间和当前启用指针；`srs_configs` 保存启用的调度配置。

只读 API 均返回标准 `{success:true,data:...}` 并沿用访问认证：`GET /api/memory/optimization` 返回配置与进度；`GET /api/memory/optimization/runs?before_id=0&limit=20` 返回 `{items,next_before_id}`（每页最多 100 条，非法游标返回 400）；`GET /api/memory/optimization/runs/<id>` 返回完整记录（不存在返回 404）。服务启动时检查一次，后台检查周期默认 24 小时，进度反映最近一次检查；首次门槛与月度计划在下一次日常检查中触发。详见 [FSRS 实施说明](../SRS-PLAN.md)。
