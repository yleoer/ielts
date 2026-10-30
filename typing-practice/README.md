# typing-practice

`typing-practice` 是一个 Python Flask 单体应用。Flask/Jinja2 负责页面和接口，SQLite 保存 FSRS 记忆与逐题练习统计，Python 内置 `sqlite3` 只读读取 Anki `collection.anki2`。

## 本地 Python 部署

应用需要 Python 3.12 或更高版本。在仓库根目录创建虚拟环境并安装依赖：

```powershell
cd D:\workshop\ielts
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r typing-practice\backend\requirements.txt
```

### 直接读取 Anki 数据库

这种方式不启动 Anki 同步服务，只读取已有的 `collection.anki2`。默认读取 `Word Atlas` 牌组，生成时的牌组 ID 为 `1958430017`；会优先按名称解析实际导入后的牌组和子牌组。只支持 Word Atlas 的 22 字段结构。

```powershell
$env:ANKI_DB_PATH = "$env:APPDATA\Anki2\User 1\collection.anki2"
$env:ANKI_DECK_NAME = 'Word Atlas'
$env:ANKI_DECK_ID = '1958430017'
$env:STATS_DB_PATH = (Join-Path (Get-Location) 'typing-practice\data\stats\stats.db')

.\.venv\Scripts\python.exe typing-practice\backend\app.py
```

默认访问 <http://127.0.0.1:8080>。页面、静态文件和 API 都由同一个 Flask 进程提供，不需要单独启动前端开发服务器。

### 插图

卡片依次显示 200px 圆角插图、同一行的词性与中文含义，然后显示输入框。插图缺失或加载失败时隐藏。浏览器练习页不提供发音按钮、不加载音频；Word Atlas 音频字段保留在原始 22 字段结构中，但练习接口不读取或返回它们。

练习即时反馈拼写，保存期间可订正；服务器确认后才计数和切题，并直接返回下一题。插图提前加载并按文件版本使用浏览器私有缓存，Anki 词库缓存随数据库变化自动刷新。访问验证、动态到期优先和逐题可靠保存继续保留，详见 [前端流程](../docs/typing-practice/FRONTEND.md) 与 [接口说明](../docs/typing-practice/SPEC.md)。

直接读取 Anki 时，媒体目录默认为数据库旁的 `collection.media/`。如数据库是复制的缓存，需指定原始媒体目录，例如：

```powershell
$env:ANKI_MEDIA_DIR = "$env:APPDATA\Anki2\账户 1\collection.media"
```

也可以在 YAML 的 `anki.media_dir` 设置路径；环境变量优先。插图通过受访问密码保护的 `/api/media/<note_id>/illustration` 提供，只返回该笔记引用的本地图片，不执行字段内的 HTML。音频媒体路径返回 404。

### 首次访问密码

复制 `typing-practice/.env.example` 为同目录下的 `.env`，设置 `ACCESS_PASSWORD` 为自己的访问密码。Python 启动时自动读取该文件，Docker Compose 也使用同一文件；进程已有环境变量优先。`.env` 不提交到 Git。也可以在启动 Python 前设置 `$env:ACCESS_PASSWORD = '自己的密码'`。留空表示关闭访问验证。

设置后，首次打开练习页或统计页会进入密码界面。验证成功后自动返回原页面，并用有效期 10 年的 HttpOnly Cookie 在浏览器本地保存凭证，不保存明文密码；同一浏览器后续访问无需再次输入。换浏览器、清除站点 Cookie 或使用无痕窗口时需要重新验证。

修改密码并重启服务后，旧凭证会失效。服务会在统计数据库同目录生成私有 `.access-secret` 文件，需与数据库一起保留，保证重启后仍记住浏览器；删除该文件也会让已有凭证失效。该文件不提交到 Git。

业务 API 未验证时返回 HTTP 401（`code: authentication_required`），外部脚本需先向 `/login` 提交 `password` 表单并保留响应 Cookie。`/api/health` 保持公开供容器健康检查使用。HTTPS 访问会为登录 Cookie 设置 Secure；公网部署应通过 HTTPS 访问。

### 从本地同步目录读取

如果希望使用页面上的“同步 Anki”按钮，必须同时配置同步源和目标路径。同步源目录下需要存在 `collection.anki2`；Python 服务会把它复制到缓存目录后再读取。

```powershell
$root = (Get-Location).Path
$env:ANKI_SYNC_SOURCE_DIR = Join-Path $root 'typing-practice\data\anki-sync'
$env:ANKI_SYNC_TARGET = Join-Path $root 'typing-practice\data\anki-cache\collection.anki2'
$env:ANKI_DB_PATH = $env:ANKI_SYNC_TARGET
$env:ANKI_DECK_NAME = 'Word Atlas'
$env:ANKI_DECK_ID = '1958430017'
$env:ANKI_SYNC_STABLE_SECONDS = '0'
$env:STATS_DB_PATH = Join-Path $root 'typing-practice\data\stats\stats.db'

.\.venv\Scripts\python.exe typing-practice\backend\app.py
```

可以先关闭 Anki，再把数据库复制到同步目录：

```powershell
Copy-Item `
  "$env:APPDATA\Anki2\User 1\collection.anki2" `
  'typing-practice\data\anki-sync\collection.anki2'
```

本地 Python 进程不会启动 `anki-sync` 容器。如果需要 Anki 客户端通过同步协议上传数据，仍需使用 Docker Compose；同步完成后，Python 服务读取 `typing-practice/data/anki-sync/` 中的数据库。

### 启动检查

启动后可以执行以下命令：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/health
Invoke-RestMethod http://127.0.0.1:8080/api/config
Invoke-RestMethod http://127.0.0.1:8080/api/sync/status
Invoke-RestMethod 'http://127.0.0.1:8080/api/words?limit=20'
```

`/api/health` 应返回 `status: ok`。如果同步接口提示 `Anki sync source is not configured`，说明启动进程没有同时设置 `ANKI_SYNC_SOURCE_DIR` 和 `ANKI_SYNC_TARGET`。如果同步成功但单词列表为空，请检查 `ANKI_DECK_NAME`、`ANKI_DECK_ID` 是否与数据库中的牌组一致，以及牌组中是否有已学习卡片。

如果进程中已有旧的 `ANKI_DECK_NAME` / `ANKI_DECK_ID`，需更新为 Word Atlas 配置；环境变量会覆盖默认 YAML。刚导入但还未在 Anki 学习的卡片不会进入练习池。

## Word Atlas 字段

按 Word Atlas 的固定 22 字段顺序读取，不兼容旧词表牌组格式：

| Word Atlas 字段 | 练习接口字段 |
| --- | --- |
| `Word` | `word` |
| `SourceId` | `source_id`，稳定记忆身份 |
| `UK`（为空时使用 `US`） | `phonetic` |
| `PartOfSpeech` | `part_of_speech` |
| `MeaningZH` | `chinese_meaning` |
| `ExampleEN` / `ExampleZH` | `example_en` / `example_cn` |
| `Topic` | `category` |
| `CEFR` | `cefr`，去空格并大写的词库等级 |
| `Illustration` 的 `<img src>` | `illustration_url` |

词条文字中的 HTML 排版会转换为纯文本。网站名称为“词间”，统一使用纸色、墨绿的中文界面与原色插画，不再提供黑白纯英文模式或读取旧 `stealthMode` 偏好；浏览器标签为“词间 · 练习”和“词间 · 统计”。练习页去掉页首标题、可见输入标签、输入占位提示、提交与看答案按钮，以及底部快捷键提示，只保留进度、插图、词性释义和输入框等必要内容。Enter 提交、空输入 Space 看答案、Esc 退出及订正流程继续保留；统计页以 CEFR 等级进度和话题进度替换原单词记忆、错误类型模块，等级与话题可点击查看明细。

前端样式按 [Impeccable](https://github.com/pbakaus/impeccable) 的 Operate 与 craft-floor 规范重做，设计约束见根目录 `PRODUCT.md` / `DESIGN.md`。样式和 SVG 图标均为本地资源，不再加载 Tailwind CDN；Vue、Axios、统计页 ECharts 仍沿用现有 CDN。网页图标采用纸色底、墨绿双页与赭色书签，和“词间”的衬线品牌字搭配。提供 `frontend/assets/favicon.svg`、多尺寸 `favicon.ico` 和 180px `app-icon.png`，练习、统计与访问密码页共用。

## FSRS 拼写记忆

正式练习每次取一道到期题目或尚未开始的词，答对且小于 6 秒记 Easy，6–20 秒（含边界）记 Good，超过 20 秒记 Hard；答错或看答案记 Again。后台使用 py-fsrs 6.3.2，目标保持率 0.9，学习步骤 1/10 分钟，重学 10 分钟。自由练习使用相同评分、历史统计与 FSRS 更新流程；订正、结果页错词重练不重复推进记忆或写入历史统计。

正式练习数量根据当前词池决定，不设每轮作答数或每日新词上限。已到期的学习/重学词优先，其次长期复习词，最后所有网站未开始的词；每题后重新取队列，同轮中再次到期可继续正式复习，直到当前队列为空。进度总数随可练习单词变化；没有到期项目或新词时显示下次时间，并可选择自由练习。

自由练习每轮从当前全部 Anki 已学习词池随机抽取最多 20 个不同词，包含未到期词；不足 20 个时全部取出。每个词首次作答逐题保存到历史统计，并按实际作答时间更新 FSRS 与下次复习安排；做完本轮词条后结束，不自动追加新词。失效题目跳过后继续本轮剩余词，不重复抽取一批。旧版未记录的自由练习草稿会重新开始一轮，不补写旧作答。

`practice.default_limit` / `practice.max_limit` 控制只读词库或接口批量大小，不限制正式练习总数。正式模式默认每次返回一道题，`mode=free` 默认并最多返回 20 道带作答编号的题，显式 `limit` 只能进一步缩小批量。旧 YAML 的 `memory.daily_new`、环境变量 `FSRS_DAILY_NEW` 和正式练习旧草稿中的每轮上限均已停用，保留旧值也不会截断正式练习。

统计页等级进度和话题进度读取配置的 Word Atlas 牌组及子牌组全部有效词条，包含 Anki 未学习的词，按 SourceId 去重。CEFR A1–C2 以六个相连圆环显示，话题以分段进度条显示；各等级、汇总和话题统一按“学习中 / 已掌握 / 总单词数”展示，数据来自完整词库与网站 FSRS 记录；已掌握沿用 Review 且稳定性至少 21 天的标准。缺失等级和话题分别归入未分级、未分类。点击等级或话题可按全部、未开始、学习中、已掌握筛选明细，每页 100 词并支持加载更多。等级、话题和日历弹窗中的单词统一按“易错优先”排序：已作答词按平滑错误率 `(答错次数 + 1) / (总次数 + 2)` 降序，同分时按答错次数降序，再按英文词面与 SourceId 升序，未作答词放最后；等级和话题先整体排序再分页。答过的词显示“答对次数 / 总次数”，点击可在原词条下展开逐次答错记录，仅显示时间与输入；错写和多写字符用赭红色区分，漏写位置用赭色方框标记，保留原始输入；未答词仅显示不可展开的 `0/0`。答错记录每页 50 条并可加载更早记录。旧错误分类与记忆分布接口及计算已移除，启动时自动去掉废弃 error_type 列，保留作答历史和复习计划；窄屏路线可横向滑动，话题改为单列。练习仍只使用 Anki 已学习词池，完整词库读取不扩大正式或自由练习范围。接口和统计口径详见 [统计规范](../docs/typing-practice/statistics/SPEC.md)。

统计页首行依次显示连续学习、已学习、已掌握、累计时长；已学习和已掌握按完整词库的去重词数计算。第二行是一年学习日历，范围为前六个月、当月、后五个月，跨年及闰年均按北京时间处理；历史学习用绿色，未来待复习用浅灰色，逾期归今天。有学习记录或待复习单词的日期可悬停查看数量、打开当天完整单词列表，支持已学习/待复习切换，保留答对次数及逐次答错查看；空日期不显示悬停提示或描边，也不可打开弹窗。第三行“本月学习”按自然月 28–31 天显示作答次数和正确率。后续依次为等级进度、话题进度、参数优化记录，移除原七天待复习模块，以及无调用的旧日历、滚动 30 天和七天预报接口。练习 summary 只返回进度和选词所需字段；日历与本月图表共用逐日汇总，连续学习使用相同的北京时间日期。日历独立横向滚动，窄屏首次居中到今天；支持方向键导航、Enter/Space 打开及 Esc 返回日期。

每题由后端判分并事务保存，刷新/重试按作答 ID 去重，多标签页旧版本题目返回冲突。浏览器保存独立待提交记录和每会话草稿（`typingPracticePending:fsrs:v1:*` / `typingPracticeDraftSession:fsrs:v1:*`），未确认保存时提供重试，不假报完成。有效耗时排除隐藏页面、同步弹窗、加载、网络和订正时间。跨日统计统一使用北京时间。

**首次启动新版会清空旧练习会话、作答和掌握度数据一次，然后从新作答累计。** Anki、媒体、同步历史和访问凭证保留。后续重启保留新数据，旧草稿不再恢复，旧批量统计接口返回 410。

`memory` YAML 节点和 `.env.example` 提供保持率、6/20 秒阈值及参数文件配置。初始使用默认权重与保持率 0.9；启动时检查一次，之后默认每天检查一次，累计 1,000 条有效间隔复习后在下一次检查中，后台自动在独立 CPU 子进程训练，并按时间留出较新记录验证。只有预测误差改善才启用候选，保留既有到期计划，下次正式复习应用新参数。随后按自然月评估，默认要求新增至少 100 条有效记录；不足会记录跳过，失败 24 小时后重试。服务依赖已包含 `fsrs[optimizer]`，镜像安装 CPU 版 PyTorch，提交答案时不训练。

统计页底部“参数优化记录”可查看进度、计划、训练范围、验证误差、版本及完整记录，并支持查询更早历史。数据库与同目录 `fsrs-optimization/` 持久保存评估报告、参数和进程日志，重启恢复已接受参数。`FSRS_AUTO_OPTIMIZE` 默认开启；可关闭并用 `FSRS_PARAMETERS_PATH` 指向旧参数文件回退。配置与 API 详见 [FSRS 实施说明](../docs/typing-practice/SRS-PLAN.md)。

## 本地测试

在仓库根目录运行，无需额外环境配置文件。以下为全量命令；日常局部改动只运行受影响测试，共享核心、依赖改动或发布前运行全量，选择方法与耗时分析见 [测试范围](../docs/typing-practice/TESTING.md)：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s typing-practice/backend -p 'test_*.py'
node --test typing-practice/frontend/src/app.test.cjs typing-practice/frontend/src/stats.test.cjs
```

## Docker

标准部署仍使用 `docker-compose.yml`；本地构建使用 `docker-compose.local-build.yml`。应用和页面在同一个 Flask 进程中运行，不需要单独启动前端开发服务器。

两份 Dockerfile 自动复制后端 `*.py`（排除测试文件），并在构建时导入应用以检查模块依赖。单元测试在本机执行，Docker 镜像检查统一通过 SSH 在 `typetest` 测试机执行；先检查 SSH 连接，失败时立即报错并停止，不自动换主机。保留 `scripts/check_image.py` 作为实际镜像检查入口，操作见 [镜像验证](../docs/typing-practice/IMAGE-CHECK.md)。GitHub Actions 只负责构建、推送多架构镜像和部署，不运行独立测试任务。无需为测试机维护另一套应用依赖或 `.env`。

Compose 将 `typing-practice/data/anki-media/` 只读挂载到 `/app/anki-media`。把 Anki 的 `collection.media/` 文件复制到该目录，保留原文件名；媒体文件不提交 Git。当前数据库同步只复制 `collection.anki2` 及其 SQLite 附属文件，不自动复制媒体目录；新增媒体需要同步更新该目录。

