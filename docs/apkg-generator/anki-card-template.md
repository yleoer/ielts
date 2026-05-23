# Anki 卡片设计说明

这是 `apkg-generator` 使用的卡片设计说明，重点只保留结构和取舍。

## 卡片字段

核心字段：

- `Word`
- `Phonetic`
- `PartOfSpeech`
- `ChineseMeaning`
- `ExampleEN`
- `ExampleCN`
- `Audio`
- `Category`

补充字段：

- `Etymology`
- `Tags`
- `Notes`

## 卡片角色

- 正向卡片：先看英文单词，再回忆中文释义。
- 反向卡片：先看中文释义，再回忆英文单词。

## 布局原则

- 正面保持简洁。
- 释义、例句和补充说明放在背面。
- 音频作为内联提示展示，不做主视觉。
- 分类和标签只做元数据，不抢主内容。

## 内容策略

- 例句用于帮助回忆，不用于堆信息。
- 词源信息只在有价值时出现。
- 备注要短，尽量直接。
- 设计目标是高频复习，不是阅读长文。

## 牌组行为

- 导出的牌组包含正向和反向卡片。
- 学习参数写入生成的牌组配置。
- 生成器会保留音标和 AI 补全缓存。

## 相关路径

- `apkg-generator/scripts/generate_anki_import.py`
- `apkg-generator/data/vocabulary.txt`
- `apkg-generator/data/audio/`
- `apkg-generator/anki_export/cache/`
