# IELTS 单词打字练习系统 - 技术规格文档

## 项目概述

为 IELTS 词汇学习者提供一个打字练习工具，通过读取 Anki 数据库中已学习的单词，在 Web 界面显示中文含义，要求用户手敲英文单词，以强化记忆和拼写能力。

## 核心需求

### 功能需求
1. **数据源**：直接读取 Anki SQLite 数据库，获取已学习的单词
2. **练习模式**：显示中文含义和词性，用户输入英文单词
3. **实时反馈**：即时检查拼写正确性（不自动跳转，需手动确认）
4. **进度跟踪**：显示当前练习进度和统计信息
5. **摸鱼模式**：提供低调的灰白色 UI，适合在工作场合使用

### 非功能需求
- 界面现代化、简洁
- 响应速度快（< 100ms）
- 支持键盘快捷键操作（全键盘操作）
- 支持本地开发运行，也支持服务器 Docker Compose 部署
- 支持主题切换（彩色模式 / 摸鱼模式）

## 技术栈

### 后端
- **语言**：Golang 1.21+
- **Web 框架**：Gin（轻量高性能）
- **数据库驱动**：`github.com/mattn/go-sqlite3`
- **CORS 支持**：`github.com/gin-contrib/cors`

### 前端
- **框架**：Vue 3 (Composition API)
- **UI 库**：Tailwind CSS
- **HTTP 客户端**：Axios
- **构建方式**：当前使用 CDN 静态页面，由 Go 后端直接托管

## 项目结构

```
my-ielts/
├── typing-practice/
│   ├── backend/
│   │   ├── main.go                 # 入口文件
│   │   ├── go.mod                  # Go 依赖管理
│   │   ├── go.sum
│   │   ├── Dockerfile              # 练习服务镜像构建
│   │   ├── config/
│   │   │   └── config.go           # 配置管理（Anki 路径等）
│   │   ├── anki/
│   │   │   └── reader.go           # Anki 数据库读取逻辑
│   │   ├── handlers/
│   │   │   ├── api.go              # 练习 API 处理器
│   │   │   └── stats.go            # 统计 API 处理器
│   │   └── stats/                  # 统计数据模型、存储和查询
│   ├── frontend/
│   │   ├── index.html              # 主页面
│   │   ├── stats.html              # 统计页面
│   │   ├── src/
│   │   │   ├── app.js              # 练习页逻辑
│   │   │   ├── stats.js            # 统计页逻辑
│   │   │   └── api/
│   │   │       └── client.js       # API 客户端
│   │   └── assets/
│   │       └── style.css           # 自定义样式
│   ├── docker-compose.yml          # anki-sync + typing-practice 部署
│   ├── .env.example                # Compose 环境变量示例
│   └── data/                       # Compose 运行时数据目录
└── docs/
    └── typing-practice/
        └── SPEC.md                 # 本文档
```

## 数据模型

### Anki 数据库结构
Anki 使用 SQLite 存储，主要表：
- `notes`：存储笔记内容（包含单词字段）
- `cards`：存储卡片状态（学习进度）
- `col`：存储集合配置（包含字段定义）

### 查询已学习单词的 SQL
```sql
SELECT 
    n.flds AS fields,
    c.type AS card_type,
    c.queue AS card_queue
FROM cards c
JOIN notes n ON c.nid = n.id
WHERE c.did = ? -- deck_id (IELTS Vocabulary deck)
  AND (c.type >= 1 OR c.queue >= 2) -- 已学习的卡片
ORDER BY RANDOM()
LIMIT ?;
```

**字段解析**：
- `n.flds`：用 `\x1f` 分隔的字段值（Word, Phonetic, PartOfSpeech, ChineseMeaning, ...）
- `c.type`：0=新卡片, 1=学习中, 2=复习中
- `c.queue`：-1=暂停, 0=新卡片, 1=学习中, 2=复习中, 3=预习

### Word 数据模型（Go）
```go
type Word struct {
    ID             int64  `json:"id"`
    Word           string `json:"word"`
    Phonetic       string `json:"phonetic"`
    PartOfSpeech   string `json:"part_of_speech"`
    ChineseMeaning string `json:"chinese_meaning"`
    ExampleEN      string `json:"example_en,omitempty"`
    ExampleCN      string `json:"example_cn,omitempty"`
    Category       string `json:"category,omitempty"`
}
```

## API 设计

### 基础路径
`http://localhost:8080/api`

### 端点列表

#### 1. 获取练习单词列表
```
GET /api/words?limit=20&category=all
```

**Query 参数**：
- `limit`（可选）：返回单词数量，默认 20
- `category`（可选）：单词分类筛选，默认 `all`

**响应示例**：
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "word": "atmosphere",
      "phonetic": "/ˈætməsfɪə(r)/",
      "part_of_speech": "n.",
      "chinese_meaning": "大气层；氛围"
    }
  ],
  "total": 20
}
```

#### 2. 检查拼写
```
POST /api/check
```

**请求体**：
```json
{
  "word_id": 1,
  "user_input": "atmosphere"
}
```

**响应示例**：
```json
{
  "success": true,
  "correct": true,
  "expected": "atmosphere",
  "user_input": "atmosphere"
}
```

#### 3. 提交练习统计
```
POST /api/stats
```

**请求体**：
```json
{
  "session_id": "uuid-v4",
  "total": 20,
  "correct": 18,
  "duration_seconds": 180,
  "errors": [
    {
      "word": "catastrophic",
      "user_input": "catastrofic"
    }
  ]
}
```

**响应示例**：
```json
{
  "success": true,
  "message": "Statistics saved"
}
```

#### 4. 获取 Anki 配置
```
GET /api/config
```

**响应示例**：
```json
{
  "success": true,
  "anki_path": "C:\\Users\\yleoer\\AppData\\Roaming\\Anki2\\User 1\\collection.anki2",
  "deck_name": "IELTS Vocabulary",
  "total_learned": 1523
}
```

## 前端界面设计

### 主界面布局

#### 正常模式（彩色）
```
┌────────────────────────────────────────────┐
│  🕶️ 摸鱼模式                    [右上角]   │
│  IELTS 打字练习                            │
│  通过打字强化单词记忆                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                            │
│              进度: 5 / 20                  │
│              正确率: 80%                   │
│              ████████░░░░░░░░░░            │
│                                            │
│  ┌────────────────────────────────────┐   │
│  │                                    │   │
│  │         大气层；氛围                │   │
│  │            (n.)                    │   │
│  │                                    │   │
│  │  ┌──────────────────────────────┐ │   │
│  │  │  atmosphere                  │ │   │
│  │  └──────────────────────────────┘ │   │
│  │                                    │   │
│  │  ✓ 正确！                          │   │
│  │  [下一题 (Enter)]                  │   │
│  └────────────────────────────────────┘   │
│                                            │
│  提示：Enter 提交/下一题 | Space 跳过      │
│                                            │
└────────────────────────────────────────────┘
```

#### 摸鱼模式（灰白）
```
┌────────────────────────────────────────────┐
│  👔 工作模式                    [右上角]   │
│  English Vocabulary Practice               │
│  Professional English Training System      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                            │
│              Progress: 5 / 20              │
│              Accuracy: 80%                 │
│              ████████░░░░░░░░░░            │
│                                            │
│  ┌────────────────────────────────────┐   │
│  │                                    │   │
│  │         大气层；氛围                │   │
│  │            (n.)                    │   │
│  │                                    │   │
│  │  ┌──────────────────────────────┐ │   │
│  │  │  atmosphere                  │ │   │
│  │  └──────────────────────────────┘ │   │
│  │                                    │   │
│  │  ✓ 正确！                          │   │
│  │  [下一题 (Enter)]                  │   │
│  └────────────────────────────────────┘   │
│                                            │
│  Shortcuts: Enter Submit/Next | Space Skip│
│                                            │
└────────────────────────────────────────────┘
```

### 交互流程
1. 页面加载 → 调用 `/api/words` 获取单词列表
2. 显示第一个单词的中文含义和词性
3. 用户输入 → 实时显示字符
4. 按 Enter → 调用 `/api/check` 验证
5. 显示结果（✓ 或 ✗）+ 显示"下一题"按钮
6. **按 Enter 或点击按钮** → 进入下一题（不自动跳转）
7. 完成所有单词 → 显示统计页面

### 选词策略

`/api/words` 使用“分桶 + 加权随机”算法：优先覆盖薄弱词、学习中词和到期复习词，同时保留随机词保证覆盖面。详细规则见 [选词算法说明](WORD-SELECTION.md)。

### 键盘快捷键
- `Enter`：提交答案 / 进入下一题（根据当前状态）
- `Space`：跳过当前单词
- `Esc`：退出练习
- `Ctrl + R`：重新开始

### 视觉反馈

#### 正常模式
- **正确**：绿色边框 + ✓ 图标 + 绿色背景
- **错误**：红色边框 + ✗ 图标 + 红色背景 + 显示正确答案
- **输入中**：蓝色边框 + 实时字符计数
- **进度条**：靛蓝色渐变

#### 摸鱼模式（低调风格）
- **正确**：灰色边框 + ✓ 图标 + 浅灰背景
- **错误**：深灰边框 + ✗ 图标 + 灰色背景 + 显示正确答案
- **输入中**：灰色边框
- **进度条**：深灰色
- **整体配色**：灰白色调，无彩色元素
- **界面文字**：英文为主，看起来像企业培训系统

### 主题切换功能
- **切换按钮**：固定在右上角
  - 正常模式：🕶️ 摸鱼模式（靛蓝色按钮）
  - 摸鱼模式：👔 工作模式（灰白色按钮）
- **持久化**：使用 localStorage 保存用户选择
- **自动加载**：页面刷新后保持上次选择的模式
- **全局切换**：一键切换所有界面元素（背景、按钮、文字、进度条）

## 配置管理

### 配置文件（`backend/config/config.yaml`）
```yaml
server:
  port: 8080
  host: localhost

anki:
  # Windows 默认路径
  db_path: "C:\\Users\\yleoer\\AppData\\Roaming\\Anki2\\User 1\\collection.anki2"
  deck_name: "IELTS Vocabulary"
  deck_id: 2055274336

practice:
  default_limit: 20
  max_limit: 100
  enable_audio: false  # 未来功能

stats:
  db_path: "data/stats.db"
```

### 环境变量支持
```bash
# 覆盖 Anki 数据库路径
export ANKI_DB_PATH="/path/to/collection.anki2"

# 覆盖服务器端口
export SERVER_PORT=9090

# 覆盖统计数据库路径
export STATS_DB_PATH="/path/to/stats.db"
```

Docker Compose 部署时，常用变量集中在 `typing-practice/.env.example`，包括服务端口、Anki 同步账号和同步间隔。

## 实现步骤

### Phase 1: 后端基础（优先级：高）✅ 已完成
1. ✅ 初始化 Go 项目，安装依赖
2. ✅ 实现 Anki 数据库读取逻辑
3. ✅ 实现 `/api/words` 端点
4. ✅ 实现 `/api/check` 端点
5. ✅ 添加 CORS 支持

### Phase 2: 前端基础（优先级：高）✅ 已完成
1. ✅ 创建 HTML 模板，引入 Vue 3 + Tailwind CSS（CDN）
2. ✅ 实现单词显示组件
3. ✅ 实现输入框组件
4. ✅ 连接后端 API（含模拟数据模式）
5. ✅ 实现基础交互逻辑

### Phase 3: 增强功能（优先级：中）✅ 已完成
1. ✅ 添加进度条和统计显示
2. ✅ 实现错题本功能
3. ✅ 添加键盘快捷键（全键盘操作）
4. ✅ 优化动画和视觉反馈
5. ✅ 添加本地存储（LocalStorage）保存主题选择
6. ✅ **新增：摸鱼模式**（灰白色低调 UI）
7. ✅ **新增：手动确认下一题**（取消自动跳转）

### Phase 4: 高级功能（优先级：低）⏳ 待开发
1. ⏳ 音频播放支持（复用 `data/audio/`）
2. ⏳ 难度分级（根据单词长度/复杂度）
3. ✅ 练习历史记录和趋势图表
4. ⏳ 导出错题列表到 Anki

## 技术细节

### Anki 字段分隔符
Anki 使用 `\x1f`（ASCII 31，Unit Separator）分隔字段值。

**Go 解析示例**：
```go
fields := strings.Split(rawFields, "\x1f")
word := Word{
    Word:           fields[0],
    Phonetic:       fields[1],
    PartOfSpeech:   fields[2],
    ChineseMeaning: fields[3],
    // ...
}
```

### 拼写检查逻辑
```go
func CheckSpelling(expected, input string) bool {
    // 1. 转小写
    expected = strings.ToLower(strings.TrimSpace(expected))
    input = strings.ToLower(strings.TrimSpace(input))
    
    // 2. 精确匹配
    return expected == input
}
```

**未来增强**：
- 容错匹配（Levenshtein 距离 ≤ 2）
- 忽略连字符/空格差异（如 `co-operate` vs `cooperate`）

### 前端状态管理
使用 Vue 3 Composition API + `ref`/`reactive`：

```javascript
const state = reactive({
  words: [],
  currentIndex: 0,
  userInput: '',
  score: { correct: 0, total: 0 },
  isChecking: false,
  stealthMode: false  // 摸鱼模式开关
});
```

### 主题切换实现
```javascript
// 切换摸鱼模式
toggleStealthMode() {
    this.stealthMode = !this.stealthMode;
    localStorage.setItem('stealthMode', this.stealthMode);
},

// 加载保存的主题
loadStealthMode() {
    const saved = localStorage.getItem('stealthMode');
    if (saved !== null) {
        this.stealthMode = saved === 'true';
    }
}
```

### Enter 键智能处理
```javascript
// 根据当前状态决定 Enter 键行为
@keyup.enter="showAnswer ? nextWord() : submitAnswer()"
```

- **未提交时**：`submitAnswer()` - 提交答案并显示反馈
- **已显示答案后**：`nextWord()` - 进入下一题

## 部署和运行

### 开发环境
```bash
# 后端
cd typing-practice/backend
go mod tidy
go run .

# 访问
http://localhost:8080/
http://localhost:8080/stats.html
```

### Docker Compose 部署
```bash
cd typing-practice
cp .env.example .env
docker compose pull
docker compose up -d
```

Docker Compose 会启动 `anki-sync` 和 `typing-practice` 两个服务。练习服务镜像由 GitHub Actions 构建并推送到 Docker Hub，服务器更新时只需要 `docker compose pull` 和 `docker compose up -d`，不需要本地 build。

详细说明见 [Docker 部署说明](DOCKER-DEPLOY.md)。

## 测试计划

### 单元测试
- Anki 数据库读取逻辑
- 拼写检查函数
- API 端点响应格式

### 集成测试
- 前后端 API 调用
- 完整练习流程

### 手动测试清单

#### 前端功能测试 ✅
- [x] 正确加载模拟数据（后端未启动时）
- [x] 显示中文含义和词性
- [x] 输入正确单词后显示 ✓
- [x] 输入错误单词后显示正确答案
- [x] 键盘快捷键正常工作
  - [x] Enter 提交答案
  - [x] Enter 进入下一题（提交后）
  - [x] Space 跳过单词
  - [x] Esc 退出练习
- [x] 进度和统计正确更新
- [x] 完成后显示错题回顾
- [x] 摸鱼模式切换正常
- [x] 主题选择持久化（刷新后保持）
- [x] 跨浏览器兼容性（Chrome, Firefox, Edge）

#### 后端功能测试 ⏳
- [ ] 正确读取 Anki 已学习单词
- [ ] API 端点正常响应
- [ ] CORS 配置正确
- [ ] 拼写检查逻辑准确
- [ ] 输入正确单词后显示 ✓
- [ ] 输入错误单词后显示正确答案
- [ ] 键盘快捷键正常工作
- [ ] 进度和统计正确更新
- [ ] 跨浏览器兼容性（Chrome, Firefox, Edge）

## 未来扩展

### 短期（1-2 周）
- [ ] 添加音频播放功能
- [ ] 实现错题本重点练习
- [x] 添加练习历史记录和统计图表

### 中期（1-2 月）
- [ ] 支持多用户（登录系统）
- [x] 练习数据可视化（图表）
- [ ] 移动端适配
- [ ] 添加计时功能和速度统计

### 长期（3+ 月）
- [ ] 多语言支持（托福、GRE 词汇）
- [ ] AI 智能推荐薄弱单词
- [ ] 社区功能（排行榜、挑战赛）

## 更新日志

### v1.2 - 2026-05-22
**后端、统计和部署完成**
- ✅ 完成 Go 后端 API 和 Anki SQLite 读取
- ✅ 使用 SQLite 保存练习统计原始数据
- ✅ 新增统计页面和核心图表
- ✅ Docker Compose 使用 `anki-sync` + `typing-practice` 双服务部署
- ✅ 练习服务镜像由 GitHub Actions 构建并推送到 Docker Hub

### v1.1 - 2026-05-21
**前端完成**
- ✅ 实现完整的 Vue 3 + Tailwind CSS 界面
- ✅ 添加摸鱼模式（灰白色低调 UI）
- ✅ 取消自动跳转，改为手动确认下一题
- ✅ 优化 Enter 键智能处理（提交/下一题）
- ✅ 添加主题切换按钮和持久化
- ✅ 实现模拟数据模式用于前端测试
- ✅ 完整的键盘快捷键支持
- ✅ 错题回顾功能
- ✅ 响应式设计

**后续已完成**
- ✅ 后端 Golang API
- ✅ Anki 数据库读取

### v1.0 - 2026-05-21
**初始设计**
- 📝 完成技术规格文档
- 📝 定义 API 接口
- 📝 设计数据模型

## 参考资料

### Anki 数据库文档
- [Anki Database Structure](https://github.com/ankidroid/Anki-Android/wiki/Database-Structure)
- [Anki Manual - File Locations](https://docs.ankiweb.net/files.html)

### 技术文档
- [Gin Web Framework](https://gin-gonic.com/docs/)
- [Vue 3 Documentation](https://vuejs.org/)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [go-sqlite3](https://github.com/mattn/go-sqlite3)

## 附录

### Anki 数据库路径（常见位置）
- **Windows**: `%APPDATA%\Anki2\<用户名>\collection.anki2`
- **macOS**: `~/Library/Application Support/Anki2/<用户名>/collection.anki2`
- **Linux**: `~/.local/share/Anki2/<用户名>/collection.anki2`

### 依赖版本
```
Go: 1.21+
Gin: v1.9.1
go-sqlite3: v1.14.18
Vue: 3.4+
Tailwind CSS: 3.4+
```

---

**文档版本**: v1.0  
**创建日期**: 2026-05-21  
**作者**: yleoer  
**目标受众**: Codex AI / 开发人员
