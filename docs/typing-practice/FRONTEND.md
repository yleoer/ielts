# 打字练习前端说明

这是 `typing-practice` 前端的知识库说明。

## 入口文件

- `typing-practice/frontend/index.html`：练习页
- `typing-practice/frontend/stats.html`：统计页

## 主要脚本

- `typing-practice/frontend/src/app.js`：练习流程、输入处理、判分、会话提交
- `typing-practice/frontend/src/stats.js`：图表数据加载和交互

## 运行依赖

前端通过 CDN 加载这些库：

- Vue 3
- Axios
- Tailwind CSS
- 统计页使用的 ECharts

没有前端构建步骤。

## 练习页行为

- 从 `/api/words` 获取练习单词。
- 先显示中文含义和词性。
- 只接受英文输入。
- 每题答案在前端本地校验，不再逐题请求后端。
- Enter 用于提交或进入下一题。
- 空输入时，Space 用于跳过。
- Esc 用于退出练习。
- 完成后把会话统计提交到 `/api/stats/sessions`。

## 统计页行为

- 从 `/api/stats/*` 加载概览数据和图表数据。
- 单词掌握度和错误类型图表支持点击查看明细。
- 低调模式会切换页面配色。
- 窗口大小变化时图表会自适应。

## 主题模式

练习页和统计页都支持低调的灰白模式，选择会保存在 `localStorage`。

## 开发说明

- 正式运行时，静态文件由后端托管。
- 也可以直接打开页面做轻量静态调试。
- 当练习接口失败时，`app.js` 会回退到模拟数据，方便本地前端开发。

## 相关文档

- [系统概览](SPEC.md)
- [统计页说明](statistics/FRONTEND.md)
