# 统计页说明

这是 `frontend/stats.html` 的前端说明。

## 技术栈

- Vue 3
- Axios
- Tailwind CSS
- ECharts

## 布局

- 顶部概览卡片
- 第一行：热力图、正确率趋势
- 第二行：掌握度分布、错误类型分布
- 最后一行：每日练习时长

## 交互

- 掌握度饼图可以点击，打开单词明细弹窗。
- 错误类型饼图可以点击，打开错误明细弹窗。
- 页面支持和练习页一致的低调模式。
- 窗口变化时图表会自动调整尺寸。

## 数据加载

- 概览数据先加载。
- 各图表独立加载，某个图失败不会阻塞其它图。
- 弹窗有自己的加载状态。

## 后端依赖

- `/api/stats/overview`
- `/api/stats/heatmap`
- `/api/stats/accuracy-trend`
- `/api/stats/mastery-distribution`
- `/api/stats/mastery-words`
- `/api/stats/daily-duration`
- `/api/stats/error-types`
- `/api/stats/error-type-words`

## 相关文件

- `typing-practice/frontend/stats.html`
- `typing-practice/frontend/src/stats.js`
- `typing-practice/backend/handlers/stats.go`
- `typing-practice/backend/stats/queries.go`
