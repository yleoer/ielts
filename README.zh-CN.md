# IELTS Anki 牌组生成器

这个仓库用于根据雅思词汇表和本地发音音频生成 Anki 牌组包
（`.apkg`）。

## 文件说明

- `anki-card-template.md` - 卡片设计方案和模板参考。
- `scripts/generate_anki_import.py` - 生成 TSV 和 APKG 的脚本。
- `data/vocabulary.txt` - 词汇源文件，来自
  [`hefengxian/my-ielts`](https://github.com/hefengxian/my-ielts) 项目。
- `data/audio/` - 本地单词发音音频。
- `anki_export/cache/` - 音标和 AI 生成内容缓存。

生成结果会输出到：

- `anki_export/ielts_vocabulary.tsv`
- `anki_export/ielts_vocabulary.apkg`

## 来源说明

词汇源文件 `data/vocabulary.txt` 来自
[`hefengxian/my-ielts`](https://github.com/hefengxian/my-ielts) 项目。

## 环境要求

- Python 3.11+
- 可访问网络，用于查询音标和调用 AI
- OpenAI 兼容的 chat completions 接口

安装 Python 依赖：

```powershell
pip install requests
```

## 环境变量

AI 翻译例句和生成词根说明需要配置：

```powershell
$env:OPENAI_API_KEY='你的 API Key'
$env:OPENAI_API_BASE='http://localhost:8317/v1'
```

可选配置：

```powershell
$env:OPENAI_MODEL='gpt-5.5'
$env:AI_REQUEST_DELAY='0.05'
$env:DICTIONARY_WORKERS='8'
$env:ANKI_PROGRESS_EVERY='10'
```

说明：

- `OPENAI_MODEL`：使用的模型名称。
- `AI_REQUEST_DELAY`：每次 AI 请求后的等待时间。
- `DICTIONARY_WORKERS`：音标查询并发数。
- `ANKI_PROGRESS_EVERY`：每隔多少条显示一次进度。

## 生成预览牌组

建议先生成 20 个单词的预览包检查效果：

```powershell
python scripts\generate_anki_import.py --limit 20
```

输出文件：

```text
anki_export/ielts_vocabulary.apkg
```

## 生成完整牌组

```powershell
python scripts\generate_anki_import.py
```

脚本会显示音标查询、AI 调用、卡片构建和音频打包进度。

也可以选择本次只生成哪一类 AI 字段：

```powershell
python scripts\generate_anki_import.py --ai-task translations
python scripts\generate_anki_import.py --ai-task etymologies
python scripts\generate_anki_import.py --ai-task all
```

`translations` 会优先补例句翻译；`etymologies` 会补词源/词根说明；
`all` 是默认值，两者都会补。

## 只根据现有 AI 缓存生成

如果 AI 服务暂时不可用，可以先生成一份临时牌组，只包含已经有 AI 例句翻译缓存的单词：

```powershell
python scripts\generate_anki_import.py --cached-ai-only
```

这个模式不会发起新的 AI 请求。没有 AI 翻译缓存的单词会被跳过；
词根说明如果已有缓存就使用，没有缓存则留空。

## 中断后继续生成

脚本可以中断后重新运行。

- 音标缓存：`anki_export/cache/phonetics.json`
- AI 翻译和词根缓存：`anki_export/cache/ai_enrichment.json`
- 每条 API 结果完成后都会立即写入缓存。

如果脚本中途停止，重新运行时会复用已经完成的缓存，只继续生成缺失内容。
通常只有“停止瞬间正在请求的那一条”可能会重复调用一次。

## Anki 学习配置

生成的牌组默认适合每天学习 10 个单词。由于每个单词包含正向和反向卡片，
所以每天新卡数为 20 张。

- 每天新卡：`20`
- 学习步骤：`15m 4h 8h`
- 毕业间隔：`1d`
- 简单间隔：`3d`
- 重新学习步骤：`15m 4h`
- 每天复习上限：`200`

推荐学习节奏：

- 早上地铁：先熟悉 10 个新单词。
- 中午吃饭：再记忆一遍。
- 晚上下班地铁：强化复习。
- 睡前：查漏补缺，清理当天到期卡片。
- 上班期间有碎片时间，可以额外打开 Anki 看几张。

## 导入 Anki

1. 打开 Anki。
2. 选择 `文件 -> 导入`。
3. 选择 `anki_export/ielts_vocabulary.apkg`。
4. 导入牌组。
5. 导入后检查牌组选项，尤其是每天新卡数量和 FSRS 设置。

## 常用命令

只刷新音标缓存：

```powershell
python scripts\generate_anki_import.py --phonetics-only
```

缺失 AI 字段时跳过 AI，直接生成：

```powershell
python scripts\generate_anki_import.py --skip-ai
```

只生成已有 AI 翻译缓存的单词：

```powershell
python scripts\generate_anki_import.py --cached-ai-only
```

只生成某一类 AI 字段：

```powershell
python scripts\generate_anki_import.py --ai-task translations
python scripts\generate_anki_import.py --ai-task etymologies
```

调整进度显示频率：

```powershell
$env:ANKI_PROGRESS_EVERY='25'
python scripts\generate_anki_import.py
```
