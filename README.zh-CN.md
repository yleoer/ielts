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

关键路径：

- `apkg-generator/scripts/generate_anki_import.py`
- `apkg-generator/data/`
- `apkg-generator/anki_export/`

相关文档：

- [APKG 生成器说明](docs/apkg-generator/README.zh-CN.md)
- [Anki 卡片设计说明](docs/apkg-generator/anki-card-template.md)

### 打字练习

用于拼写练习和学习统计。

应用从 Anki 读取已学习单词，通过加权策略选词，完成拼写检查，并把练习会话写入 SQLite。

关键路径：

- `typing-practice/backend/`
- `typing-practice/frontend/`
- `typing-practice/docker-compose.yml`
- `typing-practice/data/`

相关文档：

- [打字练习概览](docs/typing-practice/SPEC.md)
- [前端说明](docs/typing-practice/FRONTEND.md)
- [选词算法](docs/typing-practice/WORD-SELECTION.md)
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
