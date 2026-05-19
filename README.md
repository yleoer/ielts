# IELTS Anki Deck Generator

This repository contains the source files and script for generating an Anki
deck package (`.apkg`) from the IELTS vocabulary list and local pronunciation
audio.

## Files

- `anki-card-template.md` - card design notes and template reference.
- `scripts/generate_anki_import.py` - generator script for TSV and APKG output.
- `data/vocabulary.txt` - source vocabulary data from
  [`hefengxian/my-ielts`](https://github.com/hefengxian/my-ielts).
- `data/audio/` - local word audio files.
- `anki_export/cache/` - reusable cache for phonetics and AI-generated content.

Generated files are written to:

- `anki_export/ielts_vocabulary.tsv`
- `anki_export/ielts_vocabulary.apkg`

## Attribution

The vocabulary source file `data/vocabulary.txt` comes from the
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
python scripts\generate_anki_import.py --limit 20
```

This creates a 20-word preview package at:

```text
anki_export/ielts_vocabulary.apkg
```

## Generate The Full Deck

```powershell
python scripts\generate_anki_import.py
```

The script prints progress for phonetics, AI calls, note building, and media
packaging.

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
3. Select `anki_export/ielts_vocabulary.apkg`.
4. Import the deck.
5. Check the deck options after import, especially new-card limits and FSRS.

## Useful Commands

Refresh phonetics only:

```powershell
python scripts\generate_anki_import.py --phonetics-only
```

Generate without AI for missing cached fields:

```powershell
python scripts\generate_anki_import.py --skip-ai
```

Adjust progress frequency:

```powershell
$env:ANKI_PROGRESS_EVERY='25'
python scripts\generate_anki_import.py
```
