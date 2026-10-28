# Word Atlas Anki 牌组

完整牌组使用 `D:/me/word-atlas-main` 的词库与媒体，通过 `D:/me/genanki` 的 Python 源码生成。最终名称为 **Word Atlas**，保留已确认的插画设计。

## 成品

文件：`apkg-generator/anki_export/word-atlas/Word Atlas.apkg`。

- 7,298 个词条、14,596 张卡片，英→中与中→英各一张。
- 7,298 幅插画；英音、美音和日常例句朗读各 7,298 条；雅思例句朗读 1,011 条。
- 字体、完整授权随包提供，共 30,206 个媒体/授权文件。
- 文件大小 593,227,015 字节，约 565.75 MiB。
- 牌组目录另保留 SHA-256 文件、`build-report.json` 和 `CONTENT_LICENSE.md`。

笔记按源 JSON 顺序生成，首词 library，末词 profess。新卡位置设为 1–7,298，同词两张卡共享位置；实际学习顺序受 Anki 调度和同胞卡埋藏设置影响。话题与 CEFR 同时保存为标签。CEFR 是词库估计分级，并非官方雅思分数。

## 数据与卡片

源数据为 `data/word-atlas.json`，格式参考源仓库 `docs/dataset.md`；媒体位于 `dist/atlas/`。`audio/ex2/` 实际有 1,011 条第二例句音频，源格式文档尚未描述，生成器按文件存在性处理。

| 词库字段 | 卡片表现 |
| --- | --- |
| `id` / `w` | 源 id / 词头；GUID 根据源 id 固定，便于更新 |
| `uk` / `us` | 独立音标与 Anki 原生音频控件 |
| `senses` | 首义项突出，其他义项直接展示词性与中英文释义 |
| `ex[0]` / `ex[1]` | 日常 / 雅思双语例句，目标词精确匹配加粗，朗读按媒体有无显示 |
| `col` / `tip` | 常用搭配、中文译文及用法提醒 |
| `fam` / `syn` / `ant` / `note` | 原始数据与稳定字段保留，不在卡面展示 |
| `topic` / `cefr` | 融入词头或题面，不另设顶部栏与横线 |

英→中正面显示词头、英美音标与播放按钮；中→英正面显示首义项、词性和插画，不展示英文词头或发音。背面保留插画、全部义项、双语例句、搭配与用法提醒。卡面移除品牌标题、引导语、页脚及“再多学一点”。

卡片采用离线 Fraunces 字体和响应式 HTML/CSS，不依赖 JavaScript 或联网字体。媒体按 `wa_<id>_uk.mp3`、`wa_<id>_us.mp3`、`wa_<id>_ex.mp3`、`wa_<id>_ex2.mp3`、`wa_<id>_img.webp` 扁平命名，避免 Anki 中相同 basename 覆盖。已文档化媒体同时校验索引位与文件；缺失媒体省略。

## 重新生成

以下命令在本仓库根目录执行；先按 `AGENTS.md` 检查私有 `CODEX_ENV.md`。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r apkg-generator/requirements-word-atlas.txt
.venv/Scripts/python.exe -X utf8 apkg-generator/scripts/generate_word_atlas.py
```

默认即生成完整牌组。`--all` 保留为兼容参数；可通过 `--source`、`--genanki-source`、`--output` 和 `--deck-name` 覆盖输入路径、输出目录和牌组名称。生成不调用 AI，也不修改源仓库。

已有完整文件只更新学习计划、名称和描述时，使用：

```powershell
.venv/Scripts/python.exe -B -X utf8 apkg-generator/scripts/generate_word_atlas.py --update-study-plan
```

该命令只修改 APKG 中的集合元数据，验证笔记和卡片数据未变、媒体及媒体索引的 CRC/大小未变后替换成品，再更新构建报告与 SHA-256。更新过程使用临时目录，不重新复制平铺媒体，也不生成网页。

生成时会复制媒体、词条和 CSS 到输出目录；打包后自动检查 ZIP CRC、SQLite 完整性、所有笔记顺序与 GUID、正反向卡片归属、新卡位置、媒体命名及全部媒体引用。结果记录在 `build-report.json`。已打包的平铺媒体和数据副本可在验证后清理，当前成品目录只保留上述四个文件。

模型 ID、牌组 ID 和 GUID 沿用已经导出的版本，便于更新。如果客户端已导入早期小牌组，可能保留原名称或已存在卡片的位置；可在 Anki 中改名并移动卡片。

## 导入与学习

牌组和选项组均名为 **Word Atlas**，牌组描述为空。音频仍按需播放，名称不附加播放方式。完整授权保留在包内 `_wa_content_license.txt`、输出目录 `CONTENT_LICENSE.md` 和本项目文档中。

学习时间按用户提供的 **07:00、17:00、23:00** 设置：

| 时间 | 学习安排 |
| --- | --- |
| 07:00 早上通勤 | 先完成到期旧卡，再学当天新卡；每天新卡额度保持 20 张 |
| 17:00 下午通勤 | 继续当天新学卡的第一次间隔复习 |
| 23:00 睡前 | 继续当天新学卡的第二次间隔复习，答对后结束短期学习阶段 |

学习步骤为 **`1m 10h 6h`**，对应 `[1, 600, 360]` 分钟。新卡第一次按“良好”后约 10 小时再出现，下午按“良好”后约 6 小时再出现；`1m` 是按“重来”后的短重试间隔。“困难”和“简单”会改变推进方式，因此这个三时段安排以按“良好”推进为例。

步骤按每张卡实际答题时刻计时，不是固定时刻提醒；晚开始会相应顺延，Anki 的时间浮动和提前学习设置也可能使出现时间略有差异。每天早上完成当天新卡额度，下午和睡前即可专注继续当天的学习卡；若早上未完成额度，Anki 后续会话仍可能提供剩余新卡。

旧卡排在新卡前，新卡按位置升序收集、按收集顺序排列。复习上限设为 9,999，作为避免隐藏到期旧卡的高上限，**不是每天的任务量**。同胞卡埋藏仍开启，正反向卡可能分在不同天引入；20 张是卡片额度，不等同于 20 个新词。已毕业的旧卡继续按原有调度复习；遗忘重学步骤保留原配置。

在 Anki 中通过“文件 → 导入”选择更新后的 APKG，并允许导入/更新牌组选项，保留现有学习进度。导入后检查当前牌组是否采用 **Word Atlas** 选项组、学习步骤是否为 `1m 10h 6h`、新卡是否安排在复习后。不同版本对已有选项和牌组描述的导入行为不同；若旧设置仍保留，可在客户端直接设置上述值、把原选项组改名为 Word Atlas，并清空牌组描述。新步骤适用于后续学习，不会把已毕业的卡片重新变为新卡。

排序字段依据 Anki 的 [选项定义](https://github.com/ankitects/anki/blob/main/proto/anki/deck_config.proto) 和 [旧版 JSON 兼容层](https://github.com/ankitects/anki/blob/main/rslib/src/deckconfig/schema11.rs) 写入；同时保留旧调度器的“新卡最后”配置。

## 验证

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest discover -s apkg-generator/tests -p 'test_*.py' -v
```

7 项测试覆盖内容转义、缺失媒体、文件名冲突、完整模式名称及源顺序、实际 APKG/SQLite/模板和媒体引用，以及从旧学习配置升级时保留笔记、卡片数据和全部媒体。包级测试需要本机两个源仓库，缺失时明确 skip。本流程不修改 `typing-practice/`，Python 测试不需要 gcc。

完整成品的 ZIP CRC 与 SQLite 完整性通过；7,298 条笔记、14,596 张卡的顺序、GUID 和新卡位置正确；30,203 个内容媒体全部被引用，缺失引用为 0。用户已确认完成 Anki 导入。

本次学习计划更新另验证了：选项组名为 Word Atlas、牌组描述为空、学习步骤和排序正确；笔记、卡片数据和所有媒体均保持不变。

## 授权与设计

词库、插画与录音：**Word Atlas contributors — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**。原文和媒体未改写，增加 HTML 排版及目标词强调；源项目说明内容由 AI 生成、未经逐条人工审校。Fraunces 使用 SIL OFL 1.1，完整许可随包提供。

前端参考 [Impeccable](https://github.com/pbakaus/impeccable) 的设计规范。卡片设计约定见 [word-atlas-surface.md](word-atlas-surface.md)，实现说明见 [DESIGN.md](../../apkg-generator/templates/word-atlas/DESIGN.md)。
