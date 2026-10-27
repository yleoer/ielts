# typing-practice

`typing-practice` 是一个 Python Flask 单体应用。Flask/Jinja2 负责页面和接口，SQLite 保存练习统计，Python 内置 `sqlite3` 只读读取 Anki `collection.anki2`。

## 本地运行

在仓库根目录执行：

```powershell
python -m pip install -r typing-practice/backend/requirements.txt
python typing-practice/backend/app.py
```

默认访问 <http://localhost:8080>。可以通过环境变量覆盖 Anki 和统计数据库路径：

```powershell
$env:ANKI_DB_PATH = 'C:\path\to\collection.anki2'
$env:STATS_DB_PATH = 'typing-practice/data/stats/stats.db'
```

## Docker

标准部署仍使用 `docker-compose.yml`；本地构建使用 `docker-compose.local-build.yml`。应用和页面在同一个 Flask 进程中运行，不需要单独启动前端开发服务器。

