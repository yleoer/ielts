# 统计功能总结

这是打字练习统计模块的简要说明。

## 作用

统计模块负责三件事：

- 记录练习会话
- 汇总单词级尝试
- 为统计页和选词策略提供数据

## 当前数据区

- 练习会话
- 单词尝试
- 单词掌握状态
- 里程碑
- Anki 同步历史

## 当前统计页

当前统计页保留五个核心视图：

- 学习热力图
- 正确率趋势
- 单词掌握度分布
- 错误类型分布
- 每日练习时长

其中掌握度和错误类型图表支持点击查看明细。

## 当前接口

写入接口：

- `POST /api/stats/sessions`

读取接口：

- `GET /api/stats/overview`
- `GET /api/stats/heatmap`
- `GET /api/stats/accuracy-trend`
- `GET /api/stats/mastery-distribution`
- `GET /api/stats/mastery-words`
- `GET /api/stats/daily-duration`
- `GET /api/stats/error-types`
- `GET /api/stats/error-type-words`
- `GET /api/stats/speed-trend`
- `GET /api/stats/streak`
- `GET /api/stats/milestones`

部分读取接口保留给后端完整能力，当前页面未全部展示。

## 关键文件

- `typing-practice/backend/handlers/stats.go`
- `typing-practice/backend/stats/`
- `typing-practice/frontend/stats.html`
- `typing-practice/frontend/src/stats.js`

## 维护要点

- 会话使用 `session_id` 做幂等覆盖。
- 重复提交同一个会话不会重复累计。
- 错误类型可以由前端提供，也可以由后端推断。
- 单词掌握状态可以由尝试记录重新计算。
