# IELTS 打字练习 - 前端

这是 IELTS 单词打字练习系统的前端部分，使用 Vue 3 + Tailwind CSS 构建。

## 功能特性

- ✅ 显示中文含义和词性
- ✅ 实时输入反馈
- ✅ 正确/错误视觉提示
- ✅ 进度条和统计
- ✅ 键盘快捷键支持
- ✅ 错题回顾
- ✅ 响应式设计

## 文件结构

```
frontend/
├── index.html              # 主页面
├── src/
│   ├── app.js             # Vue 应用主逻辑
│   └── api/
│       └── client.js      # API 客户端
└── assets/
    └── style.css          # 自定义样式
```

## 快速开始

### 1. 直接打开（推荐用于开发测试）

由于使用了 CDN 引入依赖，可以直接在浏览器中打开 `index.html`：

```bash
# 使用默认浏览器打开
start index.html

# 或使用 Python 启动本地服务器
python -m http.server 3000
# 然后访问 http://localhost:3000
```

### 2. 使用 Live Server（VS Code）

如果使用 VS Code，安装 Live Server 插件后：
- 右键点击 `index.html`
- 选择 "Open with Live Server"

## 依赖说明

所有依赖通过 CDN 引入，无需本地安装：

- **Vue 3.4.21**: 前端框架
- **Axios 1.6.7**: HTTP 客户端
- **Tailwind CSS 3.x**: CSS 框架

## 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 提交答案 |
| `Space` | 跳过当前单词 |
| `Esc` | 退出练习 |

## 模拟数据模式

当后端服务不可用时，前端会自动切换到模拟数据模式，使用 5 个示例单词进行测试。

## API 端点

前端默认连接到 `http://localhost:8080/api`，包含以下端点：

- `GET /api/words?limit=20` - 获取单词列表
- `POST /api/check` - 检查拼写
- `POST /api/stats` - 提交统计
- `GET /api/config` - 获取配置

## 自定义配置

修改 `src/app.js` 中的 `apiBaseUrl`：

```javascript
data() {
    return {
        apiBaseUrl: 'http://localhost:8080/api' // 修改为你的后端地址
    };
}
```

## 浏览器兼容性

- Chrome 90+
- Firefox 88+
- Edge 90+
- Safari 14+

## 开发说明

### 添加新功能

1. **添加音频播放**：在 `currentWord` 显示区域添加播放按钮
2. **计时功能**：在 `mounted()` 中添加 `startTime`，在 `finishPractice()` 中计算时长
3. **难度筛选**：在 API 调用中添加 `difficulty` 参数

### 样式定制

修改 `assets/style.css` 或直接在 HTML 中使用 Tailwind 类名。

### 调试模式

打开浏览器控制台查看 API 请求日志：

```
[API] GET /api/words
[API] Response: {success: true, data: [...]}
```

## 截图

### 练习界面
```
┌─────────────────────────────────┐
│   IELTS 打字练习                │
│   通过打字强化单词记忆          │
├─────────────────────────────────┤
│   进度: 5/20    正确率: 80%     │
│   ████████░░░░░░░░░░             │
├─────────────────────────────────┤
│                                 │
│      大气层；氛围                │
│         (n.)                    │
│                                 │
│   ┌─────────────────────────┐  │
│   │ atmosphere              │  │
│   └─────────────────────────┘  │
│                                 │
│   ✓ 正确！                      │
└─────────────────────────────────┘
```

### 结果界面
```
┌─────────────────────────────────┐
│   ✓ 练习完成！                  │
├─────────────────────────────────┤
│   总题数: 20                    │
│   正确: 18                      │
│   错误: 2                       │
│   正确率: 90%                   │
├─────────────────────────────────┤
│   错题回顾:                     │
│   - catastrophic (你输入: catastrofic) │
│   - phenomenon (你输入: phenominon)    │
├─────────────────────────────────┤
│   [重新开始]                    │
└─────────────────────────────────┘
```

## 下一步

前端已完成，接下来需要：

1. ✅ 前端界面（已完成）
2. ⏳ 后端 API（Golang）
3. ⏳ Anki 数据库读取
4. ⏳ 集成测试

## 许可证

MIT
