# My IELTS Tools

Personal IELTS vocabulary tooling built around Anki.

This repository contains two small, independent projects:

- `apkg-generator`: builds an IELTS vocabulary Anki package from local word data, audio, and optional AI-enriched fields.
- `typing-practice`: runs a web typing-practice app backed by an Anki `collection.anki2` file and a local statistics database.

中文说明: [README.zh-CN.md](README.zh-CN.md)

## Why This Exists

I use Anki as the source of truth for IELTS vocabulary. This repo keeps the surrounding workflow in one place: generate a deck, sync it to a server, practice spelling in the browser, and review learning statistics.

The code is intentionally self-hostable and low ceremony. The typing app can run locally during development, while the server deployment uses Docker Compose and a prebuilt Docker image.

## Projects

### APKG Generator

Creates an Anki deck package from the vocabulary assets under `apkg-generator/`.

Use it when the source vocabulary or card content changes and a new importable deck is needed.

Key paths:

- `apkg-generator/scripts/generate_anki_import.py`
- `apkg-generator/data/`
- `apkg-generator/anki_export/`

Docs:

- [APKG generator notes](docs/apkg-generator/README.md)
- [Anki card design notes](docs/apkg-generator/anki-card-template.md)

### Typing Practice

Runs the web app for spelling practice and learning statistics.

The app reads learned words from Anki, selects practice words with a weighted strategy, checks spelling in the browser, and stores normal practice sessions in SQLite.

Highlights:

- Chinese meaning prompt with English spelling input.
- Local answer checking during practice, without per-word backend requests.
- Fast correct-answer animation before moving to the next word.
- Draft session restore after refresh or reopening the page.
- Same-session mistake review that does not affect historical statistics.
- Clear empty state when no practice words are available.

Key paths:

- `typing-practice/backend/`
- `typing-practice/frontend/`
- `typing-practice/docker-compose.yml`
- `typing-practice/data/`

Docs:

- [Typing practice overview](docs/typing-practice/SPEC.md)
- [Frontend notes](docs/typing-practice/FRONTEND.md)
- [Word selection](docs/typing-practice/WORD-SELECTION.md)
- [Docker deployment](docs/typing-practice/DOCKER-DEPLOY.md)
- [Statistics summary](docs/typing-practice/statistics/SUMMARY.md)

## Documentation

The docs are written as a project knowledge base rather than full tutorials. Start from:

- [Documentation index](docs/README.md)
- [Chinese documentation index](docs/README.zh-CN.md)

## Repository Boundaries

- Generated Anki exports stay under `apkg-generator/anki_export/`.
- Runtime typing-practice data stays under `typing-practice/data/`.
- Deployment configuration lives in `typing-practice/`.
- Long-term design notes live under `docs/`.
