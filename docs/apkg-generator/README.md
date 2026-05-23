# IELTS Anki 牌组生成器

这是 `apkg-generator` 的概览文档，说明如何生成可导入 Anki 的牌组包。

打字练习应用位于 `typing-practice/`。

## 输出

- `apkg-generator/anki_export/ielts_vocabulary.tsv`
- `apkg-generator/anki_export/ielts_vocabulary.apkg`

## 输入

- `apkg-generator/data/vocabulary.txt`：词汇源文件
- `apkg-generator/data/audio/`：本地发音音频
- `apkg-generator/anki_export/cache/`：音标和 AI 补全缓存

词汇源来自 [`hefengxian/my-ielts`](https://github.com/hefengxian/my-ielts)。

## 运行要求

- Python 3.11+
- `requests`
- 可访问网络，用于音标查询和 AI 补全
- 需要 AI 字段时，必须提供 OpenAI 兼容接口

## 配置项

生成器会读取这些环境变量：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` 或 `OPENAI_API_BASE`
- `OPENAI_MODEL`
- `OPENAI_TEMPERATURE`
- `AI_REQUEST_DELAY`
- `DICTIONARY_WORKERS`
- `ANKI_PROGRESS_EVERY`

## 生成模式

- 完整导出：生成全部牌组内容。
- 预览导出：用 `--limit` 生成少量样本。
- 只刷新音标：`--phonetics-only`
- 缺失 AI 字段时跳过：`--skip-ai`
- 只使用缓存 AI：`--cached-ai-only`
- 指定 AI 字段：`--ai-task translations|etymologies|all`

## 运行约定

- 缓存会跨运行复用。
- AI 翻译和词源缓存分开保存。
- 脚本支持中断后重新运行。
- 导出的牌组包含正向和反向卡片。

## 相关文档

- [Anki 卡片设计说明](anki-card-template.md)
- [文档索引](../README.md)
