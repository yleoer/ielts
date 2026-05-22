# 统计页面实现说明

## 当前状态

统计页由 `stats.html` 和 `src/stats.js` 实现，使用 Vue 3、Axios、ECharts 和 Tailwind CSS。页面会从后端 `/api/stats/*` 接口加载真实练习数据。

当前保留 5 个核心图表，已移除“错误单词 Top 10”和“分类掌握度”的前端面板及后端接口；“打字速度趋势”和“里程碑时间轴”暂不展示：

1. 学习热力图
2. 正确率趋势
3. 单词掌握度分布
4. 错误类型分布
5. 每日练习时长

“错误单词 Top 10”和“分类掌握度”不再展示，也不再提供对应后端接口。

## 页面布局

- 第一行保持学习热力图和正确率趋势。
- 第二行展示单词掌握度分布和错误类型分布。
- 最后一行展示每日练习时长，并占满整行宽度。

## 交互说明

- “单词掌握度分布”饼图支持点击扇区，弹窗展示该掌握等级下的具体单词、正确次数、总次数和正确率。
- “错误类型分布”饼图支持点击扇区，弹窗展示该错误类型下的具体单词、中文含义、分类、错误次数和最近一次错误输入。
- 顶部工具按钮使用纯图标展示，说明文字保留在 `title` 和 `aria-label` 中。
- 摸鱼模式会切换为低调灰白配色，并保存到 `localStorage`。

## 关键前端方法

```javascript
loadAllData()          // 加载概览数据并初始化图表
reloadAllCharts()      // 摸鱼模式切换后销毁并重建图表
openMasteryWords()     // 打开掌握度单词明细弹窗
openErrorTypeWords()   // 打开错误类型单词明细弹窗
renderMasteryPie()     // 渲染掌握度饼图并绑定点击事件
renderErrorTypes()     // 渲染错误类型饼图并绑定点击事件
```

## 后端接口依赖

统计页主要依赖以下接口：

```text
GET /api/stats/overview
GET /api/stats/heatmap
GET /api/stats/accuracy-trend
GET /api/stats/mastery-distribution
GET /api/stats/mastery-words?level=weak&limit=500
GET /api/stats/daily-duration
GET /api/stats/error-types
GET /api/stats/error-type-words?type=spelling&limit=500
```

`apiBaseUrl` 会优先使用当前页面 origin：

```javascript
apiBaseUrl: window.location.origin && window.location.origin.startsWith('http')
    ? `${window.location.origin}/api`
    : 'http://localhost:8080/api'
```

因此推荐通过后端访问 `http://localhost:8080/stats.html`，这样前端静态文件和 API 会走同一个服务。

## 测试清单

1. 打开 `http://localhost:8080/stats.html`
2. 确认 5 个图表正常渲染
3. 点击“单词掌握度分布”的非空扇区，确认弹窗展示具体单词
4. 点击“错误类型分布”的非空扇区，确认弹窗展示具体单词和最近输入
5. 切换摸鱼模式，确认图表颜色和顶部图标按钮正常
6. 缩放窗口，确认图表会自动 resize

## 相关文件

- `stats.html`：统计页结构、概览卡片、图表容器、详情弹窗
- `src/stats.js`：数据加载、图表渲染、摸鱼模式、图表点击弹窗逻辑
- `../backend/handlers/stats.go`：统计 API 路由和 handler
- `../backend/stats/queries.go`：统计查询和图表明细查询
