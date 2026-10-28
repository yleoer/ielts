# Word Atlas Anki 牌组

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

使用 Anki 复习雅思词汇的中文学习者；使用者已确认卡片设计，并要求完整牌组命名为 Word Atlas。

## Product Purpose

把本地 Word Atlas 的 7,298 个词条及媒体转换为完整、含插画的离线 Anki 牌组。

## Operating Context

词库：`D:/me/word-atlas-main/data/word-atlas.json`；格式：同仓库 `docs/dataset.md`；媒体：`dist/atlas/`。使用 `D:/me/genanki` 的 Python 源码生成 APKG。卡片使用本目录的 Anki 模板和样式。

## Capabilities and Constraints

7,298 个词条、每词正反两张卡，共 14,596 张，按源 JSON 顺序生成。英美音频文件分开；不显示不存在的媒体。英→中正面只给词头与读音，中→英正面给中文释义、词性和插画，不显示英文答案或发音。话题与难度融入卡片主体，不单独设顶部栏或横线；其他义项直接可见。卡面不显示引导语、页脚和品牌标题，背面不展示词族、近反义词和补充说明。授权署名保留在随包许可和项目文档中。牌组及选项组均名为 Word Atlas，牌组描述为空；保留话题/CEFR 标签，每天新卡 20 张，音频按需播放。

学习节奏：07:00 先复习到期旧卡，再学新卡；17:00 与 23:00 继续当天的学习卡。步骤 `1m 10h 6h` 按实际答题时刻计时，新卡以“良好”推进可对应两个通勤/睡前间隔。复习上限 9,999、新卡放在复习后、按位置顺序引入；既有学习记录与媒体保留。

## Brand Commitments

参考 Word Atlas 的现有插画、Fraunces 字体和纸色基础，按用户指定的 Impeccable 规范设计 Anki 前端。

## Evidence on Hand

7,298 个原始词条；所有词有插画、英音、美音和第一例句音频；1,011 个词有第二例句音频。媒体实际存在性与索引一起校验。

## 最终选择

用户确认维持有插画的完整牌组。保留完整 APKG、校验值、构建报告、授权和生成源码；删除网页、示例牌组及其生成入口，默认只生成完整词库。
