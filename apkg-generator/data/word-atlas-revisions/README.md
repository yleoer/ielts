# Word Atlas 本地修订

`revisions.json` 是运行时使用的唯一修订表：31 条重复项标记并暂停，48 条保留原 SourceId 改写词头。核对依据和暂保留项见 [核对清单](../../../docs/apkg-generator/word-atlas-variant-audit.md)。原始 `D:/me/word-atlas-main` 不修改。

`generate_word_atlas.py` 和 `export_desktop_media.py` 在读取源词库后共同应用本表。改写同步处理词头、英文例句、搭配、词族及提示；保留中文义项，处理已双写 l 的屈折形式，保留 Scotch whisky 的地区拼法。

重复项保留笔记、GUID 和卡片，添加 `word_atlas::excluded` 及 `word_atlas::canonical::<保留项 SourceId>`。生成的新卡 `queue=-1`；更新已有 Anki 集合必须运行更新器，不能依赖 APKG 导入修改旧卡的暂停状态。服务器按标签排除，不按所有暂停卡统一排除。

## 修订录音

`maths`、`ladybird`、`anticlockwise`、`windscreen` 改词头会改变读音。`media/` 中提供 12 条替代录音：每词的美音、日常例句和第二例句。英音暂不提供，导出时移除这四词的旧英音引用；其他词继续保留原英美音频。

录音于 2026-11-06 使用本机 Windows `System.Speech.Synthesis.SpeechSynthesizer` 生成，声音 `Microsoft Zira Desktop`，语言 `en-US`，速率 `-1`，不作为 Word Atlas 原始录音署名。输入是应用修订表后的词头和两条英文例句；WAV 通过 FFmpeg 的 `libmp3lame -q:a 3` 转为 MP3。音频是可直接导出的生成资产，构建牌组或资源 ZIP 不需要 TTS、FFmpeg、联网或额外依赖。

替代录音使用 `wa_<原 SourceId>_<类型>_revised.mp3`，保留稳定资源索引，同时避免覆盖旧录音和 Anki 对同名不同内容媒体的自动改名。插图复用原文件。

## 更新已有 Anki

`scripts/apply_word_atlas_revisions.py` 使用 Anki 官方集合 API。先预检词头和 SourceId，创建官方集合备份，记录原笔记字段与标签，再批量更新和暂停；检查 GUID、卡片调度数据和全部复习日志不变。只更新修订导致变化的字段，保留其他字段及个人标签。重复运行不会重复修改已完成的笔记。

在 Anki 主窗口按 `Ctrl+Shift+;` 打开调试控制台，输入下列命令后用 `Ctrl+Enter` 执行：

```python
import sys; sys.path.insert(0, r"D:\me\ielts\apkg-generator\scripts"); import apply_word_atlas_revisions; apply_word_atlas_revisions.run_in_anki(mw)
```

也可在安装了 Anki Python 包的运行环境中调用命令行，须先正常关闭 Anki：

```powershell
python apkg-generator/scripts/apply_word_atlas_revisions.py --collection "原集合路径/collection.anki2" --report-dir "备份与报告目录"
```

默认只预览；添加 `--apply` 才备份并应用。仓库 `.venv` 不需要安装 Anki 依赖来生成牌组或运行其他测试。更新报告、原字段和 `.colpkg` 备份保存在 `apkg-generator/anki_export/word-atlas/updates/`；恢复整个集合使用该目录中 `backups/` 的官方备份。
