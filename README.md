# My IELTS Tools

Personal IELTS vocabulary tooling built around Anki.

This repository contains three related projects:

- `apkg-generator`: builds an IELTS vocabulary Anki package from local word data, audio, and optional AI-enriched fields.
- `typing-desktop`: the 词间 desktop app (Tauri + Rust) for spelling practice, FSRS scheduling and learning statistics.
- `typing-practice`: a minimal sync server that serves the Anki vocabulary snapshot and the shared answer log for the desktop app.

中文说明: [README.zh-CN.md](README.zh-CN.md)

## Why This Exists

I use Anki as the source of truth for IELTS vocabulary. This repo keeps the surrounding workflow in one place: generate a deck, sync it to a server, practice spelling in the desktop app, and review learning statistics.

The code is intentionally self-hostable and low ceremony. The desktop app works offline; the sync server is deployed with Docker Compose and a prebuilt Docker image.

## Projects

### APKG Generator

Creates an Anki deck package from the vocabulary assets under `apkg-generator/`.

The [Word Atlas deck](docs/apkg-generator/word-atlas.md) exports all 7,298 words as 7,298 English-to-Chinese cards with illustrations and offline audio, using the local `genanki` source. Both generators create one English-to-Chinese card per word.

Use it when the source vocabulary or card content changes and a new importable deck is needed.

Key paths:

- `apkg-generator/scripts/generate_anki_import.py`
- `apkg-generator/data/`
- `apkg-generator/anki_export/`

Docs:

- [APKG generator notes](docs/apkg-generator/README.md)
- [Anki card design notes](docs/apkg-generator/anki-card-template.md)

### Typing Desktop (词间)

Runs spelling practice and learning statistics on the desktop. Scheduling (a Rust port of py-fsrs 6.3.2), statistics, parameter optimization, pages and illustrations all run locally on SQLite; answers sync through the server and every device replays the merged log.

Highlights:

- Chinese meaning prompt with English spelling input.
- Automatic Again/Hard/Good/Easy grades from correctness and 6/20-second thresholds.
- Draft and pending-answer recovery, with idempotent submissions across retries.
- Same-session mistake review that does not affect historical statistics.
- Next-review time and optional free practice when nothing is due.
- Automatic background parameter optimization after 1,000 effective reviews, followed by monthly evaluations.
- Offline practice; syncs at startup, every 10 minutes and on demand.

Key paths:

- `typing-desktop/core/`
- `typing-desktop/app/`
- `typing-desktop/frontend/`

Docs:

- [Desktop README](typing-desktop/README.md)
- [Desktop design](docs/typing-desktop/DESIGN.md)
- [Frontend notes](docs/typing-desktop/FRONTEND.md)
- [Word selection](docs/typing-desktop/WORD-SELECTION.md)
- [FSRS and optimization](docs/typing-desktop/SRS-PLAN.md)
- [Statistics summary](docs/typing-desktop/statistics/SUMMARY.md)

### Typing Practice Sync Server

A small Flask service: `GET /api/vocab` returns the Word Atlas snapshot read from Anki, `POST /api/sync` stores and pages the append-only answer log, and a background job copies `collection.anki2` from anki-sync-server. Access uses a bearer token. It no longer serves pages, media, FSRS or statistics.

Key paths:

- `typing-practice/backend/`
- `typing-practice/docker-compose.yml`
- `typing-practice/data/`

Docs:

- [Sync server overview](docs/typing-practice/SPEC.md)
- [Docker deployment](docs/typing-practice/DOCKER-DEPLOY.md)

## Documentation

The docs are written as a project knowledge base rather than full tutorials. Start from:

- [Documentation index](docs/README.md)
- [Chinese documentation index](docs/README.zh-CN.md)

## Repository Boundaries

- Generated Anki exports stay under `apkg-generator/anki_export/`.
- Runtime sync-server data stays under `typing-practice/data/`.
- Server deployment configuration lives in `typing-practice/`.
- Long-term design notes live under `docs/`.
