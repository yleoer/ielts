# 打字练习系统概览

这是 `typing-practice` 的知识库说明，记录系统边界、接口和运行约定。

## 它是什么

`typing-practice` 是一个基于 Anki 的浏览器拼写练习系统。

它从 Anki 读取已学习单词，先显示中文，再要求用户输入英文单词，并把练习结果写入 SQLite，用于统计和选词。

## 组成部分

- 后端：Go + Gin
- 练习数据源：Anki `collection.anki2`
- 统计存储：SQLite
- 前端：Vue 3 + Tailwind CSS，由后端直接托管

## 当前路由

练习和工具接口：

- `GET /api/health`
- `GET /api/words`
- `POST /api/check`
- `POST /api/stats`
- `GET /api/config`
- `GET /api/sync/status`
- `POST /api/sync/now`

统计接口：

- `POST /api/stats/sessions`
- `GET /api/stats/heatmap`
- `GET /api/stats/accuracy-trend`
- `GET /api/stats/mastery-distribution`
- `GET /api/stats/mastery-words`
- `GET /api/stats/speed-trend`
- `GET /api/stats/daily-duration`
- `GET /api/stats/streak`
- `GET /api/stats/error-types`
- `GET /api/stats/error-type-words`
- `GET /api/stats/milestones`
- `GET /api/stats/overview`

## 练习流程

1. 前端加载。
2. 页面向 `/api/words` 请求练习单词。
3. 用户输入英文单词。
4. `/api/check` 校验答案。
5. 前端记录尝试，并手动进入下一题。
6. 练习结束后提交会话统计。

## 选词策略

后端不是简单随机取词，而是结合统计状态对已学习单词做加权选择，让薄弱词和近期错词更常出现。

详细说明见 [WORD-SELECTION.md](WORD-SELECTION.md)。

## 配置来源

运行配置来自：

- `typing-practice/backend/config/config.yaml`
- 环境变量
- Docker Compose 覆盖项

重点配置包括：

- 监听地址
- Anki 数据库路径
- 统计数据库路径
- 练习词数量限制
- 部署模式下的同步源和缓存路径

## 数据边界

- `typing-practice/data/anki-sync/`：同步来的 Anki 源数据
- `typing-practice/data/anki-cache/`：缓存的 `collection.anki2`
- `typing-practice/data/stats/`：学习统计和同步历史

## 前端文件

- `frontend/index.html`：练习页
- `frontend/stats.html`：统计页
- `frontend/src/app.js`：练习逻辑
- `frontend/src/stats.js`：统计图表逻辑

## 运行约定

- 本地开发时，前端可以在后端不可用时回退到模拟数据。
- 正式部署时，应用读取缓存的 Anki 数据库，而不是直接访问 Anki。
- 统计库应当在容器重启后继续保留。

## 相关文档

- [前端说明](FRONTEND.md)
- [Docker 部署](DOCKER-DEPLOY.md)
- [自动部署](AUTO-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
- [统计功能总结](statistics/SUMMARY.md)
