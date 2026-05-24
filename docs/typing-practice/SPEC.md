# 打字练习系统概览

这是 `typing-practice` 的知识库说明，记录系统边界、接口和运行约定。

## 它是什么

`typing-practice` 是一个基于 Anki 的浏览器拼写练习系统。

它从 Anki 读取已学习单词，先显示中文，再要求用户输入英文单词。普通练习结果会写入 SQLite，用于统计和后续选词；临时巩固类练习只在前端完成。

## 组成部分

- 后端：Go + Gin
- 练习数据源：Anki `collection.anki2`
- 统计存储：SQLite
- 前端：Vue 3 + Tailwind CSS，由后端直接托管

## 当前路由

练习和工具接口：

- `GET /api/health`
- `GET /api/words`
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
2. 页面优先恢复本地草稿；没有可用草稿时，向 `/api/words` 请求练习单词。
3. 用户根据中文含义输入英文单词。
4. 前端直接用已返回的单词数据做本地校验，不逐词请求后端。
5. 答对后播放快速过渡动画并自动进入下一题。
6. 答错或跳过时展示正确答案，并记录本轮错误。
7. 普通练习结束后提交会话统计。
8. 如果本轮存在错词，可以从结果页进入错词重练。

## 前端状态

- `data: []` 且 `success: true` 时，页面进入“暂无可练习单词”状态。
- 输入内容、题号、错误展示、统计进度和练习模式会保存为本地草稿。
- 草稿保存在浏览器 `localStorage`，有效期为 7 天。
- 练习完成、重新开始、重新拉词时会清理草稿。
- 正确答案的自动跳转期间会提前保存下一题位置，刷新后不会重复上一题。

## 错词重练

- 错词重练来源于本轮答错或跳过的单词。
- 错词去重后直接在前端开启新一轮练习，不重新请求后端。
- 错词重练保留正常的输入、判分、动画和草稿能力。
- 错词重练不提交到 `/api/stats/sessions`，不会影响历史统计和后续选词权重。

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

- 前后端作为同一个应用一起打包和部署，不保留旧接口兼容层。
- 前端依赖当前后端接口；接口不可用时展示错误或空状态，不回退到模拟数据。
- 正式部署时，应用读取缓存的 Anki 数据库，而不是直接访问 Anki 客户端。
- 统计库应当在容器重启后继续保留。

## 相关文档

- [前端说明](FRONTEND.md)
- [Docker 部署](DOCKER-DEPLOY.md)
- [自动部署](AUTO-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
- [统计功能总结](statistics/SUMMARY.md)
