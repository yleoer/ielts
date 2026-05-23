# 统计模型和接口说明

这是统计子系统的简明参考。

## 作用

统计系统主要服务三件事：

- 用户可见的图表
- 会话历史
- 选词策略所需的信号

## 存储模型

统计库会记录：

- `practice_sessions`：每次完整练习会话
- `word_attempts`：每个单词的尝试记录
- `word_mastery`：按单词汇总的掌握状态
- `milestones`：进度里程碑
- `anki_sync_history`：同步事件
- `anki_sync_added_words`：同步新增单词

## 会话结构

完整会话包括：

- 会话 ID
- 开始和结束时间
- 总数、正确数、错误数
- 正确率
- 耗时
- 单词级尝试明细

单词尝试包括：

- 期望单词
- 中文含义
- 分类
- 用户输入
- 是否正确
- 耗时
- 错误类型

## 掌握等级

当前掌握等级：

- `new`
- `weak`
- `learning`
- `familiar`
- `mastered`

后端会结合尝试次数、正确率、最近行为和耗时来计算等级。

## 错误类型

当前错误类型：

- `spelling`
- `missing_letter`
- `extra_letter`
- `completely_wrong`
- `skipped`

## 接口分组

写入接口：

- `POST /api/stats/sessions`

图表接口：

- `GET /api/stats/overview`
- `GET /api/stats/heatmap`
- `GET /api/stats/accuracy-trend`
- `GET /api/stats/mastery-distribution`
- `GET /api/stats/daily-duration`
- `GET /api/stats/error-types`

明细接口：

- `GET /api/stats/mastery-words`
- `GET /api/stats/error-type-words`

保留但当前页面不展示的接口：

- `GET /api/stats/speed-trend`
- `GET /api/stats/streak`
- `GET /api/stats/milestones`

## 相关文件

- `typing-practice/backend/stats/schema.go`
- `typing-practice/backend/stats/store.go`
- `typing-practice/backend/stats/queries.go`
- `typing-practice/backend/stats/error_analyzer.go`
- `typing-practice/backend/handlers/stats.go`

## 运行约定

- 统计库路径是可配置的。
- 同一个 `session_id` 的重复提交应当覆盖旧内容。
- 汇总数据都属于派生数据，必要时可以根据尝试记录重建。
- 前端要能处理空图表数据。
