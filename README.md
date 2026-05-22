# My IELTS Tools

中文文档：[README.zh-CN.md](README.zh-CN.md)

This repository has two independent modules:

```text
my-ielts/
├── apkg-generator/      # Generate Anki .apkg packages
├── typing-practice/     # Typing practice web app
├── docs/                # Project documentation
├── README.md
└── README.zh-CN.md
```

## APKG Generator

Generate an Anki deck package from the IELTS vocabulary list, local word audio,
and optional AI enrichment.

```powershell
python apkg-generator\scripts\generate_anki_import.py --limit 20
python apkg-generator\scripts\generate_anki_import.py
```

Docs:

- [APKG generator guide](docs/apkg-generator/README.md)
- [APKG generator guide in Chinese](docs/apkg-generator/README.zh-CN.md)
- [Anki card template notes](docs/apkg-generator/anki-card-template.md)
- [Chinese documentation index](docs/README.zh-CN.md)

## Typing Practice

Run a web app that reads words from Anki `collection.anki2`, provides typing
practice, and records learning statistics. The recommended server deployment
uses Docker Compose with an Anki sync server and the prebuilt Docker Hub image.

```bash
cd typing-practice
cp .env.example .env
docker compose pull
docker compose up -d
```

Then open:

```text
http://localhost:8080/
http://localhost:8080/stats.html
```

Docs:

- [中文文档](README.zh-CN.md)
- [Chinese documentation index](docs/README.zh-CN.md)
- [Typing practice spec](docs/typing-practice/SPEC.md)
- [Frontend guide](docs/typing-practice/FRONTEND.md)
- [Word selection algorithm](docs/typing-practice/WORD-SELECTION.md)
- [Docker deploy guide](docs/typing-practice/DOCKER-DEPLOY.md)
- [Local server build testing](docs/typing-practice/LOCAL-BUILD.md)
- [Statistics summary](docs/typing-practice/statistics/SUMMARY.md)

## Resource Boundaries

- `apkg-generator/data/`: source vocabulary and word audio for APKG generation
- `apkg-generator/anki_export/`: generated APKG/TSV files and reusable caches
- `typing-practice/.env.example`: Docker Compose environment variable example
- `typing-practice/data/anki-sync/`: Anki sync server data
- `typing-practice/data/anki-cache/`: cached `collection.anki2` used by the app
- `typing-practice/data/stats/`: learning statistics SQLite data
