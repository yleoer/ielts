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

- [APKG 生成器说明](docs/apkg-generator/README.zh-CN.md)
- [APKG 生成器英文说明](docs/apkg-generator/README.md)
- [Anki 卡片模板说明](docs/apkg-generator/anki-card-template.md)

## 打字练习

用于读取本地 Anki `collection.anki2` 中的单词，提供拼写练习和学习统计。

```powershell
cd typing-practice\backend
go run .
```

访问：

```text
http://localhost:8080/
http://localhost:8080/stats.html
```

文档：

- [打字练习规格](docs/typing-practice/SPEC.md)
- [前端说明](docs/typing-practice/FRONTEND.md)
- [Docker 部署说明](docs/typing-practice/DOCKER-DEPLOY.md)
- [统计功能总结](docs/typing-practice/statistics/SUMMARY.md)

## 资源边界

- `apkg-generator/data/`：APKG 生成器使用的源词表和单词音频
- `apkg-generator/anki_export/`：APKG/TSV 输出和可复用缓存
- `typing-practice/backend/data/`：打字练习服务运行时数据
