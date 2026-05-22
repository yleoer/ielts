# 统计功能实现总结

## 已完成内容

### 后端

- 新增统计数据表：`practice_sessions`、`word_attempts`、`word_mastery`、`milestones`
- 新增统计 API 路由，统一挂载在 `/api/stats`
- 支持保存练习会话和单词尝试记录
- 支持根据 `word_attempts` 重建单词掌握度，保证重复提交同一个 session 时统计不会翻倍
- 支持错误类型分析：拼写错误、漏字母、多字母、完全错误、跳过
- 支持图表明细查询：
  - `GET /api/stats/mastery-words?level=weak&limit=500`
  - `GET /api/stats/error-type-words?type=spelling&limit=500`

### 前端

- 新增统计页面 `frontend/stats.html`
- 新增统计逻辑 `frontend/src/stats.js`
- 练习页和统计页顶部工具按钮改为纯图标展示
- 统计页保留 5 个核心图表：
  - 学习热力图
  - 正确率趋势
  - 单词掌握度分布
  - 每日练习时长
  - 错误类型分布
- “错误单词 Top 10”和“分类掌握度”已移除前端面板及后端接口
- “单词掌握度分布”和“错误类型分布”支持点击扇区打开单词明细弹窗
- 摸鱼模式支持图表和页面配色切换，并保存到 `localStorage`
- 当前统计页布局：
  - 第一行：学习热力图、正确率趋势
  - 第二行：单词掌握度分布、错误类型分布
  - 最后一行：每日练习时长，横向占满整行

## 当前统计接口

```text
POST /api/stats/sessions
GET  /api/stats/heatmap
GET  /api/stats/accuracy-trend
GET  /api/stats/mastery-distribution
GET  /api/stats/mastery-words
GET  /api/stats/speed-trend
GET  /api/stats/daily-duration
GET  /api/stats/streak
GET  /api/stats/error-types
GET  /api/stats/error-type-words
GET  /api/stats/milestones
GET  /api/stats/overview
```

说明：`speed-trend`、`streak`、`milestones` 后端仍保留，当前统计页 UI 暂不展示这些图表或列表。

## 关键文件

```text
typing-practice/
├── backend/
│   ├── handlers/stats.go
│   └── stats/
│       ├── schema.go
│       ├── models.go
│       ├── store.go
│       ├── queries.go
│       └── error_analyzer.go
└── frontend/
    ├── index.html
    ├── stats.html
    └── src/
        ├── app.js
        └── stats.js

docs/typing-practice/statistics/
├── SPEC.md
├── SUMMARY.md
└── FRONTEND.md
```

## 验证方式

本地开发：

```bash
cd typing-practice/backend
go test ./...
go build ./...
go run .
```

Docker 部署：

```bash
cd typing-practice
docker compose pull
docker compose up -d
docker compose logs -f typing-practice
```

然后访问：

```text
http://localhost:8080/stats.html
```

手动验证：

1. 统计页可以正常加载概览卡片和 5 个图表
2. 点击掌握度饼图扇区，会弹出对应等级的单词列表
3. 点击错误类型饼图扇区，会弹出对应错误类型的单词列表
4. 顶部“返回练习”“查看统计”“摸鱼模式”入口均为纯图标，悬停仍有提示
