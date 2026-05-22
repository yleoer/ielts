# IELTS 打字练习 - 统计图表功能规格文档

## 当前实现补充（2026-05-22）

当前代码已完成后端统计存储、查询接口和前端统计页。前端实际展示 7 个核心图表：学习热力图、正确率趋势、单词掌握度分布、错误单词 Top 10、每日练习时长、分类掌握度、错误类型分布。

“打字速度趋势”和“里程碑时间轴”后端接口仍保留，但当前统计页不再展示这两个图表。学习连续性仍用于概览中的连续学习天数。

新增两个图表明细接口，用于点击饼图后弹窗展示具体单词：

```text
GET /api/stats/mastery-words?level=weak&limit=500
GET /api/stats/error-type-words?type=spelling&limit=500
```

顶部导航入口使用纯图标按钮展示，文字说明通过 `title` 和 `aria-label` 保留。

## 项目概述

为 IELTS 打字练习系统添加完整的数据统计和可视化功能。当前前端聚焦展示 7 个核心图表，覆盖学习进度、掌握情况、错误分布和练习投入。

## 功能列表

### 当前展示的 7 个核心图表

1. **GitHub 风格热力图** - 学习习惯可视化
2. **正确率趋势折线图** - 学习效果趋势
3. **单词掌握度分布饼图** - 整体掌握情况
4. **错误单词 Top 10 排行榜** - 薄弱点识别
5. **每日练习时长柱状图** - 学习投入监控
6. **单词分类掌握雷达图** - 主题掌握情况
7. **错误类型分析饼图** - 错误原因分析

后端仍保留打字速度、连续学习和里程碑相关接口，便于后续重新展示或扩展。

## 技术栈

### 前端
- **图表库**：ECharts 5.x（功能强大、中文文档完善）
- **备选**：Chart.js（轻量）、D3.js（高度自定义）
- **框架**：Vue 3 + Tailwind CSS
- **HTTP 客户端**：Axios

### 后端
- **语言**：Golang 1.21+
- **框架**：Gin
- **数据库**：SQLite（存储练习记录）
- **ORM**：GORM（可选）

## 数据模型设计

### 1. 练习会话表（practice_sessions）

```sql
CREATE TABLE practice_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,           -- UUID
    user_id TEXT DEFAULT 'default',            -- 用户标识（未来扩展）
    start_time DATETIME NOT NULL,              -- 开始时间
    end_time DATETIME,                         -- 结束时间
    total_words INTEGER NOT NULL,              -- 总单词数
    correct_words INTEGER NOT NULL,            -- 正确数
    incorrect_words INTEGER NOT NULL,          -- 错误数
    accuracy REAL NOT NULL,                    -- 正确率（百分比）
    duration_seconds INTEGER,                  -- 练习时长（秒）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2. 单词练习记录表（word_attempts）

```sql
CREATE TABLE word_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,                  -- 关联 practice_sessions
    word TEXT NOT NULL,                        -- 单词
    chinese_meaning TEXT,                      -- 中文含义
    category TEXT,                             -- 分类（如：自然地理）
    user_input TEXT NOT NULL,                  -- 用户输入
    is_correct BOOLEAN NOT NULL,               -- 是否正确
    time_spent REAL,                           -- 输入耗时（秒）
    error_type TEXT,                           -- 错误类型
    attempt_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES practice_sessions(session_id)
);
```

### 3. 单词掌握度表（word_mastery）

```sql
CREATE TABLE word_mastery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE NOT NULL,                 -- 单词
    total_attempts INTEGER DEFAULT 0,          -- 总尝试次数
    correct_attempts INTEGER DEFAULT 0,        -- 正确次数
    incorrect_attempts INTEGER DEFAULT 0,      -- 错误次数
    mastery_level TEXT DEFAULT 'new',          -- 掌握等级
    last_attempt_time DATETIME,                -- 最后练习时间
    average_time REAL,                         -- 平均输入时间
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**掌握等级定义**：
- `new`：从未练习
- `weak`：错误次数 > 正确次数
- `learning`：正确 1-2 次
- `familiar`：正确 3-5 次
- `mastered`：正确 6 次以上

### 4. 学习里程碑表（milestones）

```sql
CREATE TABLE milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_type TEXT NOT NULL,              -- 里程碑类型
    milestone_name TEXT NOT NULL,              -- 名称
    description TEXT,                          -- 描述
    achieved_at DATETIME NOT NULL,             -- 达成时间
    metadata TEXT                              -- JSON 格式的额外数据
);
```

**里程碑类型**：
- `first_practice`：首次练习
- `word_count_100`：累计 100 个单词
- `accuracy_90`：首次正确率 90%+
- `streak_7`：连续学习 7 天
- `total_1000`：完成 1000 次练习

## API 设计

### 基础路径
`http://localhost:8080/api/stats`

### 1. 提交练习记录
```
POST /api/stats/sessions
```

**请求体**：
```json
{
  "session_id": "uuid-v4",
  "start_time": "2026-05-21T10:00:00Z",
  "end_time": "2026-05-21T10:05:00Z",
  "total_words": 20,
  "correct_words": 18,
  "incorrect_words": 2,
  "accuracy": 90.0,
  "duration_seconds": 300,
  "word_attempts": [
    {
      "word": "atmosphere",
      "chinese_meaning": "大气层；氛围",
      "category": "自然地理",
      "user_input": "atmosphere",
      "is_correct": true,
      "time_spent": 3.2,
      "error_type": null
    },
    {
      "word": "catastrophic",
      "chinese_meaning": "灾难性的",
      "category": "自然地理",
      "user_input": "catastrofic",
      "is_correct": false,
      "time_spent": 5.1,
      "error_type": "spelling"
    }
  ]
}
```

**响应**：
```json
{
  "success": true,
  "message": "Session saved successfully",
  "session_id": "uuid-v4"
}
```

### 2. 获取热力图数据
```
GET /api/stats/heatmap?start_date=2026-01-01&end_date=2026-12-31
```

**响应**：
```json
{
  "success": true,
  "data": [
    {
      "date": "2026-05-21",
      "count": 3,
      "accuracy": 85.5
    },
    {
      "date": "2026-05-22",
      "count": 2,
      "accuracy": 92.0
    }
  ]
}
```

### 3. 获取正确率趋势
```
GET /api/stats/accuracy-trend?days=30
```

**响应**：
```json
{
  "success": true,
  "data": [
    {
      "date": "2026-05-01",
      "accuracy": 75.0,
      "total_words": 20
    },
    {
      "date": "2026-05-02",
      "accuracy": 80.0,
      "total_words": 25
    }
  ]
}
```

### 4. 获取单词掌握度分布
```
GET /api/stats/mastery-distribution
```

**响应**：
```json
{
  "success": true,
  "data": {
    "mastered": 150,
    "familiar": 80,
    "learning": 50,
    "weak": 20,
    "new": 200
  }
}
```

### 5. 获取错误单词 Top 10
```
GET /api/stats/top-errors?limit=10
```

**响应**：
```json
{
  "success": true,
  "data": [
    {
      "word": "catastrophic",
      "error_count": 8,
      "total_attempts": 10,
      "chinese_meaning": "灾难性的"
    }
  ]
}
```

### 6. 获取打字速度趋势
```
GET /api/stats/speed-trend?days=30
```

**响应**：
```json
{
  "success": true,
  "data": [
    {
      "date": "2026-05-01",
      "average_time": 4.5,
      "word_count": 20
    }
  ]
}
```

### 7. 获取每日练习时长
```
GET /api/stats/daily-duration?days=30
```

**响应**：
```json
{
  "success": true,
  "data": [
    {
      "date": "2026-05-21",
      "duration_minutes": 25,
      "session_count": 3
    }
  ]
}
```

### 8. 获取分类掌握度（雷达图）
```
GET /api/stats/category-mastery
```

**响应**：
```json
{
  "success": true,
  "data": [
    {
      "category": "自然地理",
      "accuracy": 85.5,
      "word_count": 50
    },
    {
      "category": "商业经济",
      "accuracy": 78.0,
      "word_count": 30
    }
  ]
}
```

### 9. 获取学习连续性
```
GET /api/stats/streak
```

**响应**：
```json
{
  "success": true,
  "data": {
    "current_streak": 7,
    "longest_streak": 15,
    "total_days": 45,
    "practice_dates": [
      "2026-05-15",
      "2026-05-16",
      "2026-05-17"
    ]
  }
}
```

### 10. 获取错误类型分布
```
GET /api/stats/error-types
```

**响应**：
```json
{
  "success": true,
  "data": {
    "spelling": 45,
    "missing_letter": 20,
    "extra_letter": 15,
    "completely_wrong": 10,
    "skipped": 5
  }
}
```

### 11. 获取里程碑列表
```
GET /api/stats/milestones
```

**响应**：
```json
{
  "success": true,
  "data": [
    {
      "milestone_type": "first_practice",
      "milestone_name": "首次练习",
      "description": "开始你的学习之旅",
      "achieved_at": "2026-04-01T10:00:00Z"
    },
    {
      "milestone_type": "word_count_100",
      "milestone_name": "百词斩",
      "description": "累计练习 100 个单词",
      "achieved_at": "2026-04-15T14:30:00Z"
    }
  ]
}
```

### 12. 获取综合统计概览
```
GET /api/stats/overview
```

**响应**：
```json
{
  "success": true,
  "data": {
    "total_sessions": 45,
    "total_words_practiced": 1523,
    "overall_accuracy": 85.5,
    "total_time_minutes": 680,
    "current_streak": 7,
    "mastered_words": 150,
    "weak_words": 20
  }
}
```

## 前端图表实现

### 图表库选择：ECharts 5.x

**引入方式**：
```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
```

### 1. GitHub 风格热力图

**数据格式**：
```javascript
const heatmapData = [
  ['2026-05-21', 3, 85.5],  // [日期, 练习次数, 正确率]
  ['2026-05-22', 2, 92.0]
];
```

**ECharts 配置**：
```javascript
const option = {
  title: { text: '学习热力图' },
  tooltip: {
    formatter: function(params) {
      return `${params.value[0]}<br/>练习次数: ${params.value[1]}<br/>正确率: ${params.value[2]}%`;
    }
  },
  visualMap: {
    min: 0,
    max: 5,
    calculable: true,
    orient: 'horizontal',
    left: 'center',
    bottom: '15%',
    inRange: {
      color: ['#ebedf0', '#c6e48b', '#7bc96f', '#239a3b', '#196127']
    }
  },
  calendar: {
    range: '2026',
    cellSize: ['auto', 13]
  },
  series: [{
    type: 'heatmap',
    coordinateSystem: 'calendar',
    data: heatmapData
  }]
};
```

### 2. 正确率趋势折线图

**ECharts 配置**：
```javascript
const option = {
  title: { text: '正确率趋势' },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: ['2026-05-01', '2026-05-02', '2026-05-03']
  },
  yAxis: {
    type: 'value',
    min: 0,
    max: 100,
    axisLabel: { formatter: '{value}%' }
  },
  series: [
    {
      name: '正确率',
      type: 'line',
      data: [75, 80, 85],
      smooth: true,
      itemStyle: { color: '#5470c6' }
    },
    {
      name: '移动平均',
      type: 'line',
      data: [75, 77.5, 80],
      smooth: true,
      lineStyle: { type: 'dashed' },
      itemStyle: { color: '#91cc75' }
    }
  ]
};
```

### 3. 单词掌握度分布饼图

**ECharts 配置**：
```javascript
const option = {
  title: { text: '单词掌握度分布' },
  tooltip: { trigger: 'item' },
  legend: { orient: 'vertical', left: 'left' },
  series: [{
    type: 'pie',
    radius: '50%',
    data: [
      { value: 150, name: '已掌握', itemStyle: { color: '#67C23A' } },
      { value: 80, name: '熟悉', itemStyle: { color: '#409EFF' } },
      { value: 50, name: '学习中', itemStyle: { color: '#E6A23C' } },
      { value: 20, name: '薄弱', itemStyle: { color: '#F56C6C' } },
      { value: 200, name: '未学习', itemStyle: { color: '#909399' } }
    ],
    emphasis: {
      itemStyle: {
        shadowBlur: 10,
        shadowOffsetX: 0,
        shadowColor: 'rgba(0, 0, 0, 0.5)'
      }
    }
  }]
};
```

### 4. 错误单词 Top 10 排行榜

**ECharts 配置**：
```javascript
const option = {
  title: { text: '错误单词 Top 10' },
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'value' },
  yAxis: {
    type: 'category',
    data: ['catastrophic', 'phenomenon', 'atmosphere']
  },
  series: [{
    type: 'bar',
    data: [8, 6, 5],
    itemStyle: { color: '#F56C6C' }
  }]
};
```

### 5. 打字速度曲线图（后端保留，当前页面未展示）

**ECharts 配置**：
```javascript
const option = {
  title: { text: '打字速度趋势' },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: ['第1天', '第2天', '第3天']
  },
  yAxis: {
    type: 'value',
    name: '平均时间(秒)',
    inverse: true  // 反转Y轴，时间越短越好
  },
  series: [{
    type: 'line',
    data: [5.2, 4.8, 4.3],
    smooth: true,
    areaStyle: { opacity: 0.3 },
    itemStyle: { color: '#5470c6' }
  }]
};
```

### 6. 每日练习时长柱状图（当前页面最后一行全宽展示）

**ECharts 配置**：
```javascript
const option = {
  title: { text: '每日练习时长' },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  },
  yAxis: {
    type: 'value',
    name: '时长(分钟)'
  },
  series: [{
    type: 'bar',
    data: [25, 30, 20, 35, 28, 40, 32],
    itemStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: '#83bff6' },
        { offset: 1, color: '#188df0' }
      ])
    },
    markLine: {
      data: [{ type: 'average', name: '平均值' }]
    }
  }]
};
```

### 7. 单词分类掌握雷达图

**ECharts 配置**：
```javascript
const option = {
  title: { text: '分类掌握度' },
  tooltip: {},
  radar: {
    indicator: [
      { name: '自然地理', max: 100 },
      { name: '商业经济', max: 100 },
      { name: '科技创新', max: 100 },
      { name: '社会文化', max: 100 },
      { name: '教育学习', max: 100 }
    ]
  },
  series: [{
    type: 'radar',
    data: [{
      value: [85.5, 78.0, 92.0, 80.5, 88.0],
      name: '正确率',
      areaStyle: { opacity: 0.3 }
    }]
  }]
};
```

### 8. 学习连续性日历（后端保留，当前页面未展示）

**ECharts 配置**：
```javascript
const option = {
  title: { text: '学习连续性' },
  tooltip: {},
  calendar: {
    range: ['2026-05-01', '2026-05-31'],
    cellSize: ['auto', 20]
  },
  series: [{
    type: 'scatter',
    coordinateSystem: 'calendar',
    data: [
      ['2026-05-21', 1],
      ['2026-05-22', 1],
      ['2026-05-23', 1]
    ],
    symbolSize: 15,
    itemStyle: { color: '#67C23A' }
  }]
};
```

### 9. 错误类型分析饼图

**ECharts 配置**：
```javascript
const option = {
  title: { text: '错误类型分析' },
  tooltip: { trigger: 'item' },
  series: [{
    type: 'pie',
    radius: ['40%', '70%'],
    avoidLabelOverlap: false,
    data: [
      { value: 45, name: '拼写错误' },
      { value: 20, name: '遗漏字母' },
      { value: 15, name: '多余字母' },
      { value: 10, name: '完全错误' },
      { value: 5, name: '跳过' }
    ]
  }]
};
```

### 10. 进步里程碑时间轴（后端保留，当前页面未展示）

**ECharts 配置**：
```javascript
const option = {
  title: { text: '学习里程碑' },
  tooltip: { trigger: 'item' },
  xAxis: {
    type: 'time',
    splitLine: { show: false }
  },
  yAxis: {
    type: 'category',
    data: ['里程碑'],
    axisLabel: { show: false }
  },
  series: [{
    type: 'scatter',
    symbolSize: 20,
    data: [
      ['2026-04-01', 0, '首次练习'],
      ['2026-04-15', 0, '百词斩'],
      ['2026-05-01', 0, '正确率90%'],
      ['2026-05-21', 0, '连续7天']
    ],
    label: {
      show: true,
      formatter: function(params) {
        return params.data[2];
      },
      position: 'top'
    }
  }]
};
```

## 前端页面结构

### 统计页面路由
```
/stats - 统计仪表盘主页
```

### 页面布局（HTML）
```html
<div class="stats-dashboard">
  <!-- 顶部概览卡片 -->
  <div class="overview-cards grid grid-cols-4 gap-4 mb-8">
    <div class="card bg-white rounded-lg shadow p-6">
      <h3 class="text-gray-500 text-sm">总练习次数</h3>
      <p class="text-3xl font-bold text-indigo-600">45</p>
    </div>
    <div class="card bg-white rounded-lg shadow p-6">
      <h3 class="text-gray-500 text-sm">总单词数</h3>
      <p class="text-3xl font-bold text-green-600">1523</p>
    </div>
    <div class="card bg-white rounded-lg shadow p-6">
      <h3 class="text-gray-500 text-sm">整体正确率</h3>
      <p class="text-3xl font-bold text-blue-600">85.5%</p>
    </div>
    <div class="card bg-white rounded-lg shadow p-6">
      <h3 class="text-gray-500 text-sm">连续学习</h3>
      <p class="text-3xl font-bold text-orange-600">7天</p>
    </div>
  </div>

  <!-- 图表网格 -->
  <div class="charts-grid grid grid-cols-2 gap-6">
    <div class="chart-container bg-white rounded-lg shadow p-6" id="heatmap"></div>
    <div class="chart-container bg-white rounded-lg shadow p-6" id="accuracy-trend"></div>
    <div class="chart-container bg-white rounded-lg shadow p-6" id="mastery-pie"></div>
    <div class="chart-container bg-white rounded-lg shadow p-6" id="error-types"></div>
    <div class="chart-container bg-white rounded-lg shadow p-6" id="category-radar"></div>
    <div class="chart-container bg-white rounded-lg shadow p-6" id="top-errors"></div>
    <div class="chart-container bg-white rounded-lg shadow p-6 col-span-2" id="daily-duration"></div>
  </div>
</div>
```

### Vue 组件结构
```javascript
// stats.js
const { createApp } = Vue;

createApp({
  data() {
    return {
      overview: {},
      charts: {}
    };
  },
  methods: {
    async loadOverview() {
      const response = await axios.get('/api/stats/overview');
      this.overview = response.data.data;
    },
    
    async initCharts() {
      await this.loadHeatmap();
      await this.loadAccuracyTrend();
      await this.loadMasteryPie();
      await this.loadErrorTypes();
      await this.loadCategoryRadar();
      await this.loadTopErrors();
      await this.loadDailyDuration();
    },
    
    async loadHeatmap() {
      const response = await axios.get('/api/stats/heatmap', {
        params: { start_date: '2026-01-01', end_date: '2026-12-31' }
      });
      const chart = echarts.init(document.getElementById('heatmap'));
      chart.setOption(/* 热力图配置 */);
    }
    
    // ... 其他图表加载方法
  },
  
  mounted() {
    this.loadOverview();
    this.initCharts();
  }
}).mount('#app');
```

## 后端实现要点

### 1. 数据库初始化

**创建表的 SQL 脚本**：
```go
// db/schema.go
const schema = `
CREATE TABLE IF NOT EXISTS practice_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    user_id TEXT DEFAULT 'default',
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    total_words INTEGER NOT NULL,
    correct_words INTEGER NOT NULL,
    incorrect_words INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    duration_seconds INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS word_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    word TEXT NOT NULL,
    chinese_meaning TEXT,
    category TEXT,
    user_input TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    time_spent REAL,
    error_type TEXT,
    attempt_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES practice_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS word_mastery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE NOT NULL,
    total_attempts INTEGER DEFAULT 0,
    correct_attempts INTEGER DEFAULT 0,
    incorrect_attempts INTEGER DEFAULT 0,
    mastery_level TEXT DEFAULT 'new',
    last_attempt_time DATETIME,
    average_time REAL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_type TEXT NOT NULL,
    milestone_name TEXT NOT NULL,
    description TEXT,
    achieved_at DATETIME NOT NULL,
    metadata TEXT
);

CREATE INDEX idx_session_id ON word_attempts(session_id);
CREATE INDEX idx_word ON word_attempts(word);
CREATE INDEX idx_attempt_time ON word_attempts(attempt_time);
CREATE INDEX idx_mastery_level ON word_mastery(mastery_level);
`;
```

### 2. 错误类型判断逻辑

**Go 实现**：
```go
// utils/error_analyzer.go
func AnalyzeErrorType(expected, input string) string {
    if input == "" {
        return "skipped"
    }
    
    expected = strings.ToLower(strings.TrimSpace(expected))
    input = strings.ToLower(strings.TrimSpace(input))
    
    if expected == input {
        return ""  // 正确
    }
    
    // 计算编辑距离
    distance := levenshteinDistance(expected, input)
    
    if distance == 1 {
        if len(input) < len(expected) {
            return "missing_letter"
        } else if len(input) > len(expected) {
            return "extra_letter"
        } else {
            return "spelling"
        }
    } else if distance <= 3 {
        return "spelling"
    } else {
        return "completely_wrong"
    }
}

func levenshteinDistance(s1, s2 string) int {
    // 标准 Levenshtein 距离算法实现
    // ...
}
```

### 3. 掌握度等级更新逻辑

**Go 实现**：
```go
// services/mastery_service.go
func UpdateWordMastery(word string, isCorrect bool, timeSpent float64) error {
    var mastery WordMastery
    
    // 查询或创建记录
    db.FirstOrCreate(&mastery, WordMastery{Word: word})
    
    // 更新统计
    mastery.TotalAttempts++
    if isCorrect {
        mastery.CorrectAttempts++
    } else {
        mastery.IncorrectAttempts++
    }
    
    // 更新平均时间
    if mastery.AverageTime == 0 {
        mastery.AverageTime = timeSpent
    } else {
        mastery.AverageTime = (mastery.AverageTime + timeSpent) / 2
    }
    
    // 计算掌握等级
    mastery.MasteryLevel = calculateMasteryLevel(mastery)
    mastery.LastAttemptTime = time.Now()
    
    return db.Save(&mastery).Error
}

func calculateMasteryLevel(m WordMastery) string {
    if m.TotalAttempts == 0 {
        return "new"
    }
    
    if m.IncorrectAttempts > m.CorrectAttempts {
        return "weak"
    }
    
    if m.CorrectAttempts >= 6 {
        return "mastered"
    } else if m.CorrectAttempts >= 3 {
        return "familiar"
    } else if m.CorrectAttempts >= 1 {
        return "learning"
    }
    
    return "weak"
}
```

### 4. 里程碑自动检测

**Go 实现**：
```go
// services/milestone_service.go
func CheckAndCreateMilestones(sessionID string) error {
    // 检查首次练习
    var count int64
    db.Model(&PracticeSession{}).Count(&count)
    if count == 1 {
        createMilestone("first_practice", "首次练习", "开始你的学习之旅")
    }
    
    // 检查单词数量里程碑
    var totalWords int64
    db.Model(&WordAttempt{}).Distinct("word").Count(&totalWords)
    if totalWords == 100 {
        createMilestone("word_count_100", "百词斩", "累计练习 100 个单词")
    }
    
    // 检查正确率里程碑
    var session PracticeSession
    db.Where("session_id = ?", sessionID).First(&session)
    if session.Accuracy >= 90.0 {
        var exists int64
        db.Model(&Milestone{}).Where("milestone_type = ?", "accuracy_90").Count(&exists)
        if exists == 0 {
            createMilestone("accuracy_90", "正确率达人", "首次正确率达到 90%")
        }
    }
    
    // 检查连续学习天数
    streak := calculateCurrentStreak()
    if streak == 7 {
        createMilestone("streak_7", "坚持不懈", "连续学习 7 天")
    }
    
    return nil
}

func createMilestone(mType, name, desc string) error {
    milestone := Milestone{
        MilestoneType: mType,
        MilestoneName: name,
        Description:   desc,
        AchievedAt:    time.Now(),
    }
    return db.Create(&milestone).Error
}
```

### 5. 连续学习天数计算

**Go 实现**：
```go
// services/streak_service.go
func calculateCurrentStreak() int {
    var sessions []PracticeSession
    db.Order("start_time DESC").Find(&sessions)
    
    if len(sessions) == 0 {
        return 0
    }
    
    streak := 1
    today := time.Now().Truncate(24 * time.Hour)
    lastDate := sessions[0].StartTime.Truncate(24 * time.Hour)
    
    // 如果最后一次练习不是今天或昨天，连续性中断
    if today.Sub(lastDate) > 24*time.Hour {
        return 0
    }
    
    for i := 1; i < len(sessions); i++ {
        currentDate := sessions[i].StartTime.Truncate(24 * time.Hour)
        diff := lastDate.Sub(currentDate)
        
        if diff == 24*time.Hour {
            streak++
            lastDate = currentDate
        } else if diff > 24*time.Hour {
            break
        }
    }
    
    return streak
}
```

## 实现步骤

### Phase 1: 后端数据库和 API（优先级：高）✅ 已完成
1. ✅ 创建数据库表结构
2. ✅ 实现 POST /api/stats/sessions 端点
3. ✅ 实现单词掌握度更新逻辑
4. ✅ 实现统计查询 API
5. ✅ 实现里程碑自动检测
6. ✅ 添加数据库索引优化查询

### Phase 2: 前端统计页面（优先级：高）✅ 已完成
1. ✅ 创建 stats.html 页面
2. ✅ 引入 ECharts 库
3. ✅ 实现概览卡片组件
4. ✅ 实现 7 个核心图表
5. ✅ 连接后端 API
6. ✅ 添加加载状态和错误处理

### Phase 3: 集成到练习流程（优先级：中）✅ 已完成
1. ✅ 修改练习页面，提交时调用统计 API
2. ✅ 添加"查看统计"按钮跳转到统计页面
3. ✅ 实现实时数据更新
4. ✅ 添加导航入口

### Phase 4: 优化和增强（优先级：低）
1. 添加图表交互（点击查看详情）
2. 实现数据导出功能（CSV/Excel）
3. 添加时间范围筛选器
4. 优化移动端显示
5. 添加图表主题切换（配合摸鱼模式）

## 性能优化

### 数据库优化
```sql
-- 添加索引
CREATE INDEX idx_session_start_time ON practice_sessions(start_time);
CREATE INDEX idx_word_category ON word_attempts(category);
CREATE INDEX idx_mastery_word ON word_mastery(word);

-- 定期清理旧数据（可选）
DELETE FROM word_attempts WHERE attempt_time < date('now', '-1 year');
```

### API 缓存策略
```go
// 使用内存缓存减少数据库查询
var cache = make(map[string]interface{})
var cacheMutex sync.RWMutex

func getCachedData(key string, ttl time.Duration, fetchFunc func() interface{}) interface{} {
    cacheMutex.RLock()
    if data, exists := cache[key]; exists {
        cacheMutex.RUnlock()
        return data
    }
    cacheMutex.RUnlock()
    
    data := fetchFunc()
    
    cacheMutex.Lock()
    cache[key] = data
    cacheMutex.Unlock()
    
    // 设置过期时间
    time.AfterFunc(ttl, func() {
        cacheMutex.Lock()
        delete(cache, key)
        cacheMutex.Unlock()
    })
    
    return data
}
```

### 前端优化
```javascript
// 图表懒加载
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      loadChart(entry.target.id);
      observer.unobserve(entry.target);
    }
  });
});

document.querySelectorAll('.chart-container').forEach(el => {
  observer.observe(el);
});
```

## 测试计划

### 单元测试

**后端测试**：
```go
// services/mastery_service_test.go
func TestCalculateMasteryLevel(t *testing.T) {
    tests := []struct {
        name     string
        mastery  WordMastery
        expected string
    }{
        {
            name:     "新单词",
            mastery:  WordMastery{TotalAttempts: 0},
            expected: "new",
        },
        {
            name:     "已掌握",
            mastery:  WordMastery{CorrectAttempts: 6, IncorrectAttempts: 1},
            expected: "mastered",
        },
        {
            name:     "薄弱",
            mastery:  WordMastery{CorrectAttempts: 2, IncorrectAttempts: 5},
            expected: "weak",
        },
    }
    
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            result := calculateMasteryLevel(tt.mastery)
            if result != tt.expected {
                t.Errorf("expected %s, got %s", tt.expected, result)
            }
        })
    }
}
```

### 集成测试

**API 测试**：
```bash
# 提交练习记录
curl -X POST http://localhost:8080/api/stats/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-uuid",
    "start_time": "2026-05-21T10:00:00Z",
    "end_time": "2026-05-21T10:05:00Z",
    "total_words": 20,
    "correct_words": 18,
    "incorrect_words": 2,
    "accuracy": 90.0,
    "duration_seconds": 300,
    "word_attempts": []
  }'

# 获取统计概览
curl http://localhost:8080/api/stats/overview

# 获取热力图数据
curl "http://localhost:8080/api/stats/heatmap?start_date=2026-01-01&end_date=2026-12-31"
```

### 手动测试清单

#### 后端测试
- [ ] 数据库表创建成功
- [ ] 提交练习记录 API 正常
- [ ] 所有统计查询 API 返回正确数据
- [ ] 单词掌握度正确更新
- [ ] 里程碑自动检测触发
- [ ] 连续学习天数计算准确

#### 前端测试
- [ ] 统计页面正常加载
- [ ] 概览卡片显示正确数据
- [ ] 7 个核心图表正常渲染
- [ ] 图表交互功能正常
- [ ] 响应式布局适配移动端
- [ ] 摸鱼模式下图表样式正确

## Docker 部署

当前 Compose 使用相对路径保存统计数据库：

```yaml
services:
  typing-practice:
    volumes:
      - ./data/stats:/app/stats
    environment:
      STATS_DB_PATH: /app/stats/stats.db
```

完整部署方式见 [Docker 部署说明](../DOCKER-DEPLOY.md)。

### 数据备份

**自动备份脚本**：
```bash
#!/bin/bash
# backup-stats.sh

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 备份统计数据库
cp ./data/stats/stats.db $BACKUP_DIR/stats_$DATE.db

# 保留最近 30 天的备份
find $BACKUP_DIR -name "stats_*.db" -mtime +30 -delete

echo "Backup completed: stats_$DATE.db"
```

## 数据迁移

### 从 LocalStorage 迁移到后端

**迁移脚本**：
```javascript
// migrate-to-backend.js
async function migrateLocalStorageData() {
    const historyData = localStorage.getItem('practice_history');
    if (!historyData) {
        console.log('No data to migrate');
        return;
    }
    
    const history = JSON.parse(historyData);
    
    for (const session of history) {
        try {
            await axios.post('/api/stats/sessions', session);
            console.log(`Migrated session: ${session.session_id}`);
        } catch (error) {
            console.error(`Failed to migrate session: ${session.session_id}`, error);
        }
    }
    
    // 迁移完成后清理 LocalStorage
    // localStorage.removeItem('practice_history');
    console.log('Migration completed');
}
```

## 安全考虑

### 1. 数据验证

**后端验证**：
```go
func validateSessionData(session *PracticeSession) error {
    if session.TotalWords <= 0 {
        return errors.New("total_words must be positive")
    }
    
    if session.CorrectWords + session.IncorrectWords != session.TotalWords {
        return errors.New("correct + incorrect must equal total")
    }
    
    if session.Accuracy < 0 || session.Accuracy > 100 {
        return errors.New("accuracy must be between 0 and 100")
    }
    
    if session.DurationSeconds < 0 {
        return errors.New("duration must be non-negative")
    }
    
    return nil
}
```

### 2. SQL 注入防护

使用参数化查询：
```go
// 正确方式
db.Where("word = ?", userInput).Find(&attempts)

// 错误方式（易受 SQL 注入攻击）
// db.Raw("SELECT * FROM word_attempts WHERE word = '" + userInput + "'")
```

### 3. 速率限制

```go
// middleware/rate_limiter.go
func RateLimiter() gin.HandlerFunc {
    limiter := rate.NewLimiter(10, 20) // 每秒 10 个请求，突发 20 个
    
    return func(c *gin.Context) {
        if !limiter.Allow() {
            c.JSON(429, gin.H{"error": "Too many requests"})
            c.Abort()
            return
        }
        c.Next()
    }
}
```

## 监控和日志

### 统计 API 日志

```go
// middleware/logger.go
func StatsLogger() gin.HandlerFunc {
    return func(c *gin.Context) {
        start := time.Now()
        
        c.Next()
        
        duration := time.Since(start)
        
        log.Printf(
            "[STATS] %s %s | Status: %d | Duration: %v",
            c.Request.Method,
            c.Request.URL.Path,
            c.Writer.Status(),
            duration,
        )
    }
}
```

### 性能监控

```go
// 记录慢查询
func logSlowQuery(query string, duration time.Duration) {
    if duration > 1*time.Second {
        log.Printf("[SLOW QUERY] %s took %v", query, duration)
    }
}
```

## 未来扩展

### 短期（1-2 周）
- [ ] 添加图表导出功能（PNG/PDF）
- [ ] 实现数据对比功能（本周 vs 上周）
- [ ] 添加目标设置和进度追踪
- [ ] 实现错误单词专项练习入口

### 中期（1-2 月）
- [ ] 多用户支持和数据隔离
- [ ] 添加社交功能（排行榜、好友对比）
- [ ] 实现数据分析报告生成
- [ ] 添加学习建议和智能推荐

### 长期（3+ 月）
- [ ] AI 驱动的个性化学习路径
- [ ] 语音识别练习模式
- [ ] 移动端 App 开发
- [ ] 多语言支持（托福、GRE）

## 参考资料

### ECharts 文档
- [官方文档](https://echarts.apache.org/zh/index.html)
- [示例库](https://echarts.apache.org/examples/zh/index.html)
- [配置项手册](https://echarts.apache.org/zh/option.html)

### SQLite 文档
- [SQLite 官方文档](https://www.sqlite.org/docs.html)
- [日期时间函数](https://www.sqlite.org/lang_datefunc.html)

### Golang 相关
- [Gin 框架文档](https://gin-gonic.com/docs/)
- [GORM 文档](https://gorm.io/docs/)

## 附录

### 完整的 API 端点列表

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/stats/sessions` | POST | 提交练习记录 |
| `/api/stats/heatmap` | GET | 获取热力图数据 |
| `/api/stats/accuracy-trend` | GET | 获取正确率趋势 |
| `/api/stats/mastery-distribution` | GET | 获取单词掌握度分布 |
| `/api/stats/top-errors` | GET | 获取错误单词 Top 10 |
| `/api/stats/speed-trend` | GET | 获取打字速度趋势 |
| `/api/stats/daily-duration` | GET | 获取每日练习时长 |
| `/api/stats/category-mastery` | GET | 获取分类掌握度 |
| `/api/stats/streak` | GET | 获取学习连续性 |
| `/api/stats/error-types` | GET | 获取错误类型分布 |
| `/api/stats/milestones` | GET | 获取里程碑列表 |
| `/api/stats/overview` | GET | 获取综合统计概览 |

### 数据库表关系图

```
practice_sessions (1) ----< (N) word_attempts
                                    |
                                    | word
                                    v
                              word_mastery (1:1)
```

---

**文档版本**: v1.0  
**创建日期**: 2026-05-21  
**作者**: yleoer  
**目标受众**: Codex AI / 开发人员  
**相关文档**: `docs/typing-practice/SPEC.md`, `docs/typing-practice/DOCKER-DEPLOY.md`
