# IELTS Anki Deck Generator

This module is responsible only for generating the Anki deck package. The
typing practice web app lives in `typing-practice/`.

Commands below are intended to be run from the repository root.

This repository contains the source files and script for generating an Anki
deck package (`.apkg`) from the IELTS vocabulary list and local pronunciation
audio.

## Files

- `docs/apkg-generator/anki-card-template.md` - card design notes and template reference.
- `apkg-generator/scripts/generate_anki_import.py` - generator script for TSV and APKG output.
- `apkg-generator/data/vocabulary.txt` - source vocabulary data from
  [`hefengxian/my-ielts`](https://github.com/hefengxian/my-ielts).
- `apkg-generator/data/audio/` - local word audio files.
- `apkg-generator/anki_export/cache/` - reusable cache for phonetics and AI-generated content.

Generated files are written to:

- `apkg-generator/anki_export/ielts_vocabulary.tsv`
- `apkg-generator/anki_export/ielts_vocabulary.apkg`

## Attribution

The vocabulary source file `apkg-generator/data/vocabulary.txt` comes from the
[`hefengxian/my-ielts`](https://github.com/hefengxian/my-ielts) project.

## Requirements

- Python 3.11+
- Network access for phonetic lookup and AI enrichment
- OpenAI-compatible chat completions endpoint

Python dependencies:

```powershell
pip install requests
```

## Environment Variables

Required for AI translation and etymology generation:

```powershell
$env:OPENAI_API_KEY='your-api-key'
$env:OPENAI_API_BASE='http://localhost:8317/v1'
```

Optional:

```powershell
$env:OPENAI_MODEL='gpt-5.4-mini'
$env:AI_REQUEST_DELAY='0.05'
$env:DICTIONARY_WORKERS='8'
$env:ANKI_PROGRESS_EVERY='10'
```

## Generate A Preview Deck

Use `--limit` to generate a small deck first:

```powershell
python apkg-generator\scripts\generate_anki_import.py --limit 20
```

This creates a 20-word preview package at:

```text
apkg-generator/anki_export/ielts_vocabulary.apkg
```

## Generate The Full Deck

```powershell
python apkg-generator\scripts\generate_anki_import.py
```

The script prints progress for phonetics, AI calls, note building, and media
packaging.

You can also choose which AI fields to generate:

```powershell
python apkg-generator\scripts\generate_anki_import.py --ai-task translations
python apkg-generator\scripts\generate_anki_import.py --ai-task etymologies
python apkg-generator\scripts\generate_anki_import.py --ai-task all
```

`translations` fills example translations first. `etymologies` fills word-root
notes later. `all` is the default.

## Generate From Cached AI Only

If the AI service is unavailable, you can generate a temporary deck containing
only words whose AI example translation is already cached:

```powershell
python apkg-generator\scripts\generate_anki_import.py --cached-ai-only
```

This mode does not make new AI calls. Words without cached AI translations are
skipped, while cached etymology is used when available.

## Resume Behavior

The script is safe to stop and rerun.

- Phonetics are cached in `anki_export/cache/phonetics.json`.
- AI translations and etymologies are cached in
  `anki_export/cache/ai_enrichment.json`.
- Each successful API result is saved immediately.

If the script is interrupted, rerunning it will reuse completed cached work and
continue with missing items. The only likely repeat is the single API request
that was in progress when the process was stopped.

## Anki Study Settings

The generated deck is configured for 10 words per day, with forward and reverse
cards:

- New cards per day: `20`
- Learning steps: `15m 4h 8h`
- Graduating interval: `1d`
- Easy interval: `3d`
- Relearning steps: `15m 4h`
- Review limit per day: `200`

Suggested daily rhythm:

- Morning commute: first pass through 10 new words.
- Lunch: memory pass.
- Evening commute: reinforcement.
- Before sleep: clear due cards and review weak items.

## Import Into Anki

1. Open Anki.
2. Choose `File -> Import`.
3. Select `apkg-generator/anki_export/ielts_vocabulary.apkg`.
4. Import the deck.
5. Check the deck options after import, especially new-card limits and FSRS.

## Useful Commands

Refresh phonetics only:

```powershell
python apkg-generator\scripts\generate_anki_import.py --phonetics-only
```

Generate without AI for missing cached fields:

```powershell
python apkg-generator\scripts\generate_anki_import.py --skip-ai
```

Generate only cached AI-translated words:

```powershell
python apkg-generator\scripts\generate_anki_import.py --cached-ai-only
```

Generate only one AI field type:

```powershell
python apkg-generator\scripts\generate_anki_import.py --ai-task translations
python apkg-generator\scripts\generate_anki_import.py --ai-task etymologies
```

Adjust progress frequency:

```powershell
$env:ANKI_PROGRESS_EVERY='25'
python apkg-generator\scripts\generate_anki_import.py
```
