# My IELTS Tools

这个仓库现在拆成两个独立模块：

```text
my-ielts/
├── apkg-generator/      # 生成 Anki .apkg 牌组
├── typing-practice/     # 打字练习 Web 应用
├── docs/                # 项目文档
├── README.md
└── README.zh-CN.md
```

## APKG 生成器

用于从 IELTS 词表、本地单词音频和可选 AI 补充内容生成 Anki 牌组包。

```powershell
python apkg-generator\scripts\generate_anki_import.py --limit 20
python apkg-generator\scripts\generate_anki_import.py
```

文档：

- [项目文档索引](docs/README.zh-CN.md)
- [APKG 生成器说明](docs/apkg-generator/README.zh-CN.md)
- [APKG 生成器英文说明](docs/apkg-generator/README.md)
- [Anki 卡片模板说明](docs/apkg-generator/anki-card-template.md)

## 打字练习

用于读取 Anki `collection.anki2` 中的单词，提供拼写练习和学习统计。服务器部署推荐使用 Docker Compose：`anki-sync` 接收 Anki 客户端同步数据，`typing-practice` 从 Docker Hub 拉取预构建镜像并定时复制同步数据。

```bash
cd typing-practice
cp .env.example .env
docker compose pull
docker compose up -d
```

访问：

```text
http://localhost:8080/
http://localhost:8080/stats.html
```

文档：

- [项目文档索引](docs/README.zh-CN.md)
- [打字练习规格](docs/typing-practice/SPEC.md)
- [前端说明](docs/typing-practice/FRONTEND.md)
- [选词算法说明](docs/typing-practice/WORD-SELECTION.md)
- [Docker 部署说明](docs/typing-practice/DOCKER-DEPLOY.md)
- [自动部署和回滚](docs/typing-practice/AUTO-DEPLOY.md)
- [本地服务器构建测试](docs/typing-practice/LOCAL-BUILD.md)
- [统计功能总结](docs/typing-practice/statistics/SUMMARY.md)

## 资源边界

- `apkg-generator/data/`：APKG 生成器使用的源词表和单词音频
- `apkg-generator/anki_export/`：APKG/TSV 输出和可复用缓存
- `typing-practice/.env.example`：Docker Compose 环境变量示例
- `typing-practice/data/anki-sync/`：Anki 同步服务器数据
- `typing-practice/data/anki-cache/`：练习服务使用的 `collection.anki2` 缓存
- `typing-practice/data/stats/`：学习统计 SQLite 数据
