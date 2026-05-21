# My IELTS Tools

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

## Typing Practice

Run a local web app that reads words from Anki `collection.anki2`, provides
typing practice, and records learning statistics.

```powershell
cd typing-practice\backend
go run .
```

Then open:

```text
http://localhost:8080/
http://localhost:8080/stats.html
```

Docs:

- [Typing practice spec](docs/typing-practice/SPEC.md)
- [Frontend guide](docs/typing-practice/FRONTEND.md)
- [Docker deploy guide](docs/typing-practice/DOCKER-DEPLOY.md)
- [Statistics summary](docs/typing-practice/statistics/SUMMARY.md)

## Resource Boundaries

- `apkg-generator/data/`: source vocabulary and word audio for APKG generation
- `apkg-generator/anki_export/`: generated APKG/TSV files and reusable caches
- `typing-practice/backend/data/`: runtime data for the typing practice server
