# My IELTS Tools

这是一个围绕 Anki 搭建的个人 IELTS 词汇工具仓库。

仓库包含两个相互独立的小项目：

- `apkg-generator`：从本地词表、音频和可选 AI 补充内容生成 Anki 牌组包。
- `typing-practice`：读取 Anki `collection.anki2`，提供浏览器打字练习和学习统计。

English README: [README.md](README.md)

## 项目动机

Anki 是我的词汇数据源。这个仓库把周边流程放在一起：生成牌组、同步到服务器、在浏览器里练拼写、查看学习统计。

整体设计偏向自用和可维护：本地开发简单，服务器部署使用 Docker Compose，练习服务可以直接拉取预构建镜像。

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

### 打字练习

用于拼写练习和学习统计。

应用从 Anki 读取已学习单词，通过 py-fsrs 安排拼写记忆，到期复习优先于新词。后端逐题判分，并在单个 SQLite 事务中保存记忆与练习记录。

主要能力：

- 中文释义提示，英文拼写输入。
- 根据正误与可配置的 6/20 秒阈值自动评分 Again、Hard、Good、Easy。
- 正确答案快速动画后自动进入下一题。
- 自动保存草稿与待提交答案，刷新、重试不重复计分。
- 结束后可对本轮错词重练，错词重练不写入历史统计。
- 没有到期词时显示下次复习时间，并可自由练习。
- 默认模型参数直接可用，累计 1,000 条有效间隔复习后后台自动优化，随后按月评估。

首次启用 FSRS 会清空旧练习统计一次，从新作答累计；Anki 数据、媒体、同步历史和访问凭证保留。

关键路径：

- `typing-practice/backend/`
- `typing-practice/frontend/`
- `typing-practice/docker-compose.yml`
- `typing-practice/data/`

相关文档：

- [打字练习概览](docs/typing-practice/SPEC.md)
- [前端说明](docs/typing-practice/FRONTEND.md)
- [选词算法](docs/typing-practice/WORD-SELECTION.md)
- [FSRS 配置与参数优化](docs/typing-practice/SRS-PLAN.md)
- [Docker 部署](docs/typing-practice/DOCKER-DEPLOY.md)
- [统计功能总结](docs/typing-practice/statistics/SUMMARY.md)

## 文档

文档会尽量保持知识库风格：说明项目约定、边界和排障入口，不堆砌完整脚本或重复教程。

- [文档索引](docs/README.zh-CN.md)
- [英文文档索引](docs/README.md)

## 仓库边界

- Anki 导出产物放在 `apkg-generator/anki_export/`。
- 打字练习运行数据放在 `typing-practice/data/`。
- 部署配置放在 `typing-practice/`。
- 长期设计说明放在 `docs/`。
