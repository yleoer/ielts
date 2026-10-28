# 打字练习系统概览

这是 `typing-practice` 的知识库说明，记录系统边界、接口和运行约定。

## 它是什么

`typing-practice` 是一个基于 Anki 的浏览器拼写练习系统。

它从 Anki 读取已学习单词，先显示中文，再要求用户输入英文单词。普通练习结果会写入 SQLite，用于统计和后续选词；临时巩固类练习只在前端完成。

数据源默认是 `Word Atlas`（生成时 ID `1958430017`），优先按名称解析实际牌组和子牌组。只支持 Word Atlas 的固定 22 字段结构：`Word`、`UK`/`US`、`PartOfSpeech`、`MeaningZH`、`ExampleEN`/`ExampleZH`、`Topic` 分别映射到单词、音标、词性、中文释义、双语例句及分类接口字段。`Illustration`、`AudioUK`/`AudioUS` 提供插图和手动发音，英音优先。字段数量不符的笔记跳过，不按旧牌组布局猜测解析。文字 HTML 先移除真实标签，再解码实体，保留纯文本中的比较符号。

## 组成部分

- 单体应用：Python 3.12 + Flask + Jinja2
- 练习数据源：Anki `collection.anki2`
- 统计存储：Python 内置 `sqlite3` + SQLite
- 页面：Jinja2 模板由 Flask 渲染，交互使用 Vue 3、JavaScript 和 CDN 资源
- 部署：一个 Flask 进程同时提供页面、静态文件和 `/api` 接口

## 当前路由

练习和工具接口：

- `GET /api/health`
- `GET /api/words`
- `GET /api/media/<note_id>/illustration`
- `GET /api/media/<note_id>/audio`
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
3. 页面依次显示插图、同行的词性与中文含义、手动发音按钮，用户在下方输入英文单词。
4. 前端直接用已返回的单词数据做本地校验，不逐词请求后端。
5. 答对后播放快速过渡动画并自动进入下一题。
6. 答错或跳过时展示正确答案，并记录本轮错误。
7. 普通练习结束后提交会话统计。
8. 如果本轮存在错词，可以从结果页进入错词重练。

## 前端状态

- `data: []` 且 `success: true` 时，页面进入“暂无可练习单词”状态。
- 输入内容、题号、错误展示、统计进度和练习模式会保存为本地草稿。
- 草稿保存在浏览器 `localStorage`，有效期为 7 天。
- 正式版草稿键为 `typingPracticeDraftSession:wordAtlas:v2`，保留媒体链接，不恢复缺少媒体字段的旧草稿或本地演示数据；历史练习统计不清空。
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
- Anki 媒体目录（`ANKI_MEDIA_DIR` / `anki.media_dir`，默认数据库旁的 `collection.media/`）
- 统计数据库路径
- 练习词数量限制
- 部署模式下的同步源和缓存路径

## 数据边界

- `typing-practice/data/anki-sync/`：同步来的 Anki 源数据
- `typing-practice/data/anki-cache/`：缓存的 `collection.anki2`
- `typing-practice/data/stats/`：学习统计和同步历史

## 前端文件

- `frontend/templates/index.html`：练习页 Jinja2 模板
- `frontend/templates/stats.html`：统计页 Jinja2 模板
- `frontend/src/app.js`：练习逻辑
- `frontend/src/stats.js`：统计图表逻辑

## 运行约定

- 页面、接口和数据访问作为同一个 Python 应用一起打包和部署，不需要独立前端构建步骤。
- 前端依赖当前后端接口；接口不可用时展示错误或空状态，不回退到模拟数据。
- 正式部署时，应用读取缓存的 Anki 数据库，而不是直接访问 Anki 客户端。
- 统计库应当在容器重启后继续保留。

## 相关文档

- [前端说明](FRONTEND.md)
- [Docker 部署](DOCKER-DEPLOY.md)
- [自动部署](AUTO-DEPLOY.md)
- [本地构建说明](LOCAL-BUILD.md)
- [统计功能总结](statistics/SUMMARY.md)
