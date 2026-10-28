---
name: Word Atlas Anki
description: 已确认的完整牌组卡片设计
colors:
  atlas-ink: '#253d34'
  atlas-accent: '#a4442d'
  atlas-paper: '#fbf8f0'
  atlas-background: '#e9ede4'
  atlas-secondary: '#58675c'
  atlas-rule: '#d9ddd0'
  atlas-soft: '#f0f1e6'
  selection: '#dccca8'
  word-mark: '#b7c4a3'
  night-paper: '#202f29'
  night-ink: '#eef0df'
  night-secondary: '#b7c4b7'
  night-rule: '#435348'
  night-accent: '#edb298'
  night-soft: '#34463a'
  night-background: '#17251e'
typography:
  display:
    fontFamily: '"Atlas Fraunces", Georgia, serif'
    fontSize: clamp(34px, 5.8vw, 60px)
    fontWeight: 500
    lineHeight: 1.12
    letterSpacing: -.035em
  recall:
    fontFamily: '"Atlas Fraunces", Georgia, serif'
    fontSize: clamp(38px, 7.4vw, 76px)
    fontWeight: 500
    lineHeight: 1.12
    letterSpacing: -.035em
  chinese-prompt:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: clamp(27px, 4vw, 38px)
    fontWeight: 500
    lineHeight: 1.6
  title:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: 21px
    fontWeight: 600
    lineHeight: 1.55
  body:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.65
  sentence:
    fontFamily: Georgia, "Microsoft YaHei", serif
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.65
  translation:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.8
  label:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1.65
    letterSpacing: .04em
  section:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: 13px
    fontWeight: 700
    lineHeight: 1.65
    letterSpacing: .04em
rounded:
  small: 3px
  card: 5px
  circle: 50%
spacing:
  '8': 8px
  '10': 10px
  '12': 12px
  '15': 15px
  '22': 22px
  '24': 24px
  '30': 30px
  '36': 36px
components:
  card:
    backgroundColor: '{colors.atlas-paper}'
    textColor: '{colors.atlas-ink}'
    rounded: '{rounded.card}'
    padding: 26px 38px 18px
    typography: '{typography.body}'
  audio-button:
    backgroundColor: transparent
    textColor: '{colors.atlas-ink}'
    rounded: '{rounded.circle}'
    padding: 4px
    size: 28px
---

# Word Atlas 卡片设计

此设计适用于完整 Word Atlas Anki 牌组：7,298 个词、14,596 张卡。用户已确认保留插画。独立的 typing-practice 应用与旧生成器不受本规范影响。

## 颜色与字体

纸色卡面、墨绿正文与赭红强调，颜色及字体层级见上方 token。离线字体 `_wa_fraunces.woff2` 用于英文词头，中文与正文使用 Segoe UI、Microsoft YaHei、PingFang SC 和 sans-serif；例句使用 Georgia 配 Microsoft YaHei。卡片不依赖网络字体。

深色模式使用 `night-*` 对应值，CSS 识别 Anki 的 `nightMode` 与 `night_mode` 类。正文与辅助文字保留清晰层级；词性、读音标签和语境名称使用强调色。

## 卡面内容

英→中正面显示词头、英美音标与原生声音字段。中→英正面显示中文首义项、词性和插画；不显示英文词头与发音，插画替代文本为“词义插画”。

两种方向共用答案面，展示词头、读音、插画、全部义项、双语例句、搭配与用法提醒。其他义项为普通 section，无需展开。目标词在例句中加粗并加下划线，不铺高亮色块。

话题与 CEFR 融入主体：背面与词头同组，采用可换行水平布局；正面位于读音或中文释义下方。卡面没有独立品牌标题、顶部横线、引导语、署名页脚或“再多学一点”。词族、近反义词与补充说明保留为稳定字段，不在卡面显示。

## 布局

Anki 外层留白 24px；卡片居中，最大宽度 960px，内边距 26px 38px 18px。卡片为 5px 圆角，轻阴影 `0 8px 30px #213a3010`。

答案上区为弹性文字列与 210px 插画列，间距 30px；图片保持完整比例，上限 230px。无图片时文字占满。下区例句与搭配为 1.3:1 双列，间距 36px，用 1px 细线与释义区分开。

话题与等级间距 10px；词头组允许换行，列间距 18px、行间距 10px。回忆区最小高度 350px，垂直居中；中文题面最大宽度 18em。中→英插画位于释义下方，宽度不超过 200px 或回忆区的 65%，上方间距 26px。

640px 以下，外层留白 10px，卡面内边距 21px 22px 16px；释义旁插画列缩至 108px，间距 15px；答案词头 35px，主释义 18px，读音纵排。例句与搭配改为单列分区，搭配内部为两列；回忆区最小高度 340px，中→英插画上限 180px。

390px 以下，答案插画移至释义下方，上限 150px；搭配改为单列。

## 声音与离线资源

使用 `[sound:...]`，由 Anki 客户端生成原生播放控件。CSS 为原生 `.replay-button` / `.soundLink` 设置圆形控件，通常 28px，640px 以下为 32px；焦点为强调色 2px 外轮廓，外移 4px。

模型模板不依赖 JavaScript。图片、声音、字体和授权在 APKG 内离线打包，授权署名保留在随包许可与项目文档；牌组描述为空。

## 使用约定

- 保留原插画完整比例、本地字体和内容署名。
- 保持模型字段、模型/牌组 ID 与按源词条生成的 GUID 稳定。
- 中→英题面与图片替代文本不包含英文答案。
- 用户已完成 Anki 导入；Anki Desktop、AnkiDroid、AnkiMobile 之间的控件显示差异尚未逐客户端验证。
