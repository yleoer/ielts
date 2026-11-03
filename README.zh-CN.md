# My IELTS Tools

这是一个围绕 Anki 搭建的个人 IELTS 词汇工具仓库。

仓库包含三个相关项目：

- `apkg-generator`：从本地词表、音频和可选 AI 补充内容生成 Anki 牌组包。
- `typing-desktop`：桌面端“词间”（Tauri + Rust），提供拼写练习、FSRS 调度和学习统计。
- `typing-practice`：精简同步服务，为桌面端提供 Anki 词库快照和多设备共享的作答日志。

English README: [README.md](README.md)

## 项目动机

Anki 是我的词汇数据源。这个仓库把周边流程放在一起：生成牌组、同步到服务器、在桌面端练拼写、查看学习统计。

整体设计偏向自用和可维护：桌面端可离线练习，同步服务使用 Docker Compose 部署，可直接拉取预构建镜像。

## 子项目

### APKG 生成器

用于在词表或卡片内容变化后，重新生成可导入 Anki 的牌组包。

两套生成器均只生成英→汉卡片，每词一张；Word Atlas 完整牌组包含 7,298 词、7,298 张卡。

关键路径：

- `apkg-generator/scripts/generate_anki_import.py`
- `apkg-generator/data/`
- `apkg-generator/anki_export/`

相关文档：

- [APKG 生成器说明](docs/apkg-generator/README.zh-CN.md)
- [Anki 卡片设计说明](docs/apkg-generator/anki-card-template.md)
- [Word Atlas：完整 Anki 牌组](docs/apkg-generator/word-atlas.md)

### 桌面端（词间）

用于拼写练习和学习统计。调度（py-fsrs 6.3.2 的 Rust 移植）、统计、参数优化、页面和插图都在本地 SQLite 上运行；作答经同步服务汇总，各设备合并后按日志重放。

主要能力：

- 中文释义提示，英文拼写输入。
- 根据正误与 6/20 秒阈值自动评分 Again、Hard、Good、Easy。
- 自动保存草稿与待提交答案，重试不重复计分。
- 结束后可对本轮错词重练，错词重练不写入历史统计。
- 没有到期词时显示下次复习时间，并可自由练习。
- 累计 1,000 条有效间隔复习后后台自动优化参数，随后按月评估。
- 离线可练，启动时、每 10 分钟及手动“立即同步”时与服务器同步。

关键路径：

- `typing-desktop/core/`
- `typing-desktop/app/`
- `typing-desktop/frontend/`

相关文档：

- [桌面端说明](typing-desktop/README.md)
- [桌面端设计](docs/typing-desktop/DESIGN.md)
- [前端说明](docs/typing-desktop/FRONTEND.md)
- [选词算法](docs/typing-desktop/WORD-SELECTION.md)
- [FSRS 与参数优化](docs/typing-desktop/SRS-PLAN.md)
- [统计功能总结](docs/typing-desktop/statistics/SUMMARY.md)

### 同步服务（typing-practice）

精简的 Flask 服务：`GET /api/vocab` 返回从 Anki 读取的 Word Atlas 词库快照，`POST /api/sync` 保存并分页返回只追加的作答日志，后台定时从 anki-sync-server 复制 `collection.anki2`。使用 Bearer 访问令牌，不再提供页面、媒体、FSRS 或统计。

关键路径：

- `typing-practice/backend/`
- `typing-practice/docker-compose.yml`
- `typing-practice/data/`

相关文档：

- [同步服务概览](docs/typing-practice/SPEC.md)
- [Docker 部署](docs/typing-practice/DOCKER-DEPLOY.md)

## 文档

文档会尽量保持知识库风格：说明项目约定、边界和排障入口，不堆砌完整脚本或重复教程。

- [文档索引](docs/README.zh-CN.md)
- [英文文档索引](docs/README.md)

## 仓库边界

- Anki 导出产物放在 `apkg-generator/anki_export/`。
- 同步服务运行数据放在 `typing-practice/data/`。
- 同步服务部署配置放在 `typing-practice/`。
- 长期设计说明放在 `docs/`。
