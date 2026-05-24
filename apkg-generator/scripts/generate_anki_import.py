from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import tempfile
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

try:
    import eng_to_ipa
except ImportError:
    eng_to_ipa = None


ROOT_DIR = Path(__file__).resolve().parents[1]
VOCABULARY_FILE = ROOT_DIR / "data" / "vocabulary.txt"
AUDIO_ROOT = ROOT_DIR / "data" / "audio"
OUTPUT_DIR = ROOT_DIR / "anki_export"
CACHE_DIR = OUTPUT_DIR / "cache"
OUTPUT_TSV = OUTPUT_DIR / "ielts_vocabulary.tsv"
OUTPUT_APKG = OUTPUT_DIR / "ielts_vocabulary.apkg"
PHONETIC_CACHE = CACHE_DIR / "phonetics.json"
AI_CACHE = CACHE_DIR / "ai_enrichment.json"

DECK_ID = 2055274336
MODEL_ID = 1641870956
DECK_NAME = "IELTS Vocabulary"
MODEL_NAME = "IELTS Vocabulary Enhanced"
FIELD_SEPARATOR = "\x1f"

PHONETIC_WORKERS = int(os.getenv("PHONETIC_WORKERS", "8"))
AI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
AI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY")
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
AI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))
AI_REQUEST_DELAY = float(os.getenv("AI_REQUEST_DELAY", "0.05"))
PROGRESS_EVERY = int(os.getenv("ANKI_PROGRESS_EVERY", "10"))

FIELDS = [
    "Word",
    "Phonetic",
    "PartOfSpeech",
    "ChineseMeaning",
    "ExampleEN",
    "ExampleCN",
    "Audio",
    "Category",
    "Etymology",
    "Notes",
]

SCHEMA = """
CREATE TABLE col (
    id integer primary key,
    crt integer not null,
    mod integer not null,
    scm integer not null,
    ver integer not null,
    dty integer not null,
    usn integer not null,
    ls integer not null,
    conf text not null,
    models text not null,
    decks text not null,
    dconf text not null,
    tags text not null
);
CREATE TABLE notes (
    id integer primary key,
    guid text not null,
    mid integer not null,
    mod integer not null,
    usn integer not null,
    tags text not null,
    flds text not null,
    sfld integer not null,
    csum integer not null,
    flags integer not null,
    data text not null
);
CREATE TABLE cards (
    id integer primary key,
    nid integer not null,
    did integer not null,
    ord integer not null,
    mod integer not null,
    usn integer not null,
    type integer not null,
    queue integer not null,
    due integer not null,
    ivl integer not null,
    factor integer not null,
    reps integer not null,
    lapses integer not null,
    left integer not null,
    odue integer not null,
    odid integer not null,
    flags integer not null,
    data text not null
);
CREATE TABLE revlog (
    id integer primary key,
    cid integer not null,
    usn integer not null,
    ease integer not null,
    ivl integer not null,
    lastIvl integer not null,
    factor integer not null,
    time integer not null,
    type integer not null
);
CREATE TABLE graves (
    usn integer not null,
    oid integer not null,
    type integer not null
);
CREATE INDEX ix_notes_usn ON notes (usn);
CREATE INDEX ix_cards_usn ON cards (usn);
CREATE INDEX ix_revlog_usn ON revlog (usn);
CREATE INDEX ix_cards_nid ON cards (nid);
CREATE INDEX ix_cards_sched ON cards (did, queue, due);
CREATE INDEX ix_revlog_cid ON revlog (cid);
CREATE INDEX ix_notes_csum ON notes (csum);
"""

FRONT_FORWARD = """
<div class="card-front">
  <div class="header-section">
    <div class="category">{{Category}}</div>
    <div class="tags">{{Tags}}</div>
  </div>
  
  <div class="word-container">
    <div class="word">{{Word}}</div>
    <div class="phonetic">{{Phonetic}}</div>
  </div>
  
  {{#Image}}
  <div class="image-container">
    <img src="{{Image}}" alt="{{Word}}" class="word-image">
  </div>
  {{/Image}}
</div>
""".strip()

BACK_FORWARD = """
<div class="card-back">
  <!-- 显示正面内容 -->
  <div class="header-section">
    <div class="category">{{Category}}</div>
    <div class="tags">{{Tags}}</div>
  </div>
  
  <div class="word-container">
    <div class="word">{{Word}} <span class="audio-icon">{{Audio}}</span></div>
    <div class="phonetic">{{Phonetic}}</div>
  </div>
  
  <hr class="divider">
  
  <!-- 词性和释义 -->
  <div class="meaning-section">
    <span class="part-of-speech">{{PartOfSpeech}}</span>
    <span class="chinese-meaning">{{ChineseMeaning}}</span>
  </div>
  
  <!-- 词根词缀 -->
  {{#Etymology}}
  <div class="etymology-section">
    <span class="etymology-icon">🌱</span>
    <span class="etymology-content">{{Etymology}}</span>
  </div>
  {{/Etymology}}
  
  <!-- 例句部分 -->
  <div class="example-section">
    <div class="example-label">📖 例句</div>
    <div class="example-en">
      {{ExampleEN}}
    </div>
    <div class="example-cn">
      {{ExampleCN}}
    </div>
  </div>
  
  <!-- 额外注释 -->
  {{#Notes}}
  <div class="notes-section">
    <div class="notes-label">💡 补充说明</div>
    <div class="notes-content">{{Notes}}</div>
  </div>
  {{/Notes}}
</div>
""".strip()

FRONT_REVERSE = """
<div class="card-front reverse">
  <div class="header-section">
    <div class="category">{{Category}}</div>
    <div class="reverse-indicator">🔄 反向卡片</div>
  </div>
  
  <div class="chinese-prompt">
    <div class="prompt-label">请回忆这个单词：</div>
    <div class="chinese-meaning-large">{{ChineseMeaning}}</div>
    <div class="part-of-speech-hint">{{PartOfSpeech}}</div>
  </div>
</div>
""".strip()

BACK_REVERSE = """
<div class="card-back reverse">
  <div class="header-section">
    <div class="category">{{Category}}</div>
    <div class="reverse-indicator">🔄 反向卡片</div>
  </div>
  
  <!-- 答案：单词 -->
  <div class="answer-section">
    <div class="answer-label">答案</div>
    <div class="word-container">
      <div class="word">{{Word}} <span class="audio-icon">{{Audio}}</span></div>
      <div class="phonetic">{{Phonetic}}</div>
    </div>
  </div>
  
  <hr class="divider">
  
  <!-- 释义确认 -->
  <div class="meaning-section">
    <span class="part-of-speech">{{PartOfSpeech}}</span>
    <span class="chinese-meaning">{{ChineseMeaning}}</span>
  </div>
  
  <!-- 词根词缀 -->
  {{#Etymology}}
  <div class="etymology-section">
    <span class="etymology-icon">🌱</span>
    <span class="etymology-content">{{Etymology}}</span>
  </div>
  {{/Etymology}}
  
  <!-- 例句 -->
  <div class="example-section">
    <div class="example-label">📖 例句</div>
    <div class="example-en">{{ExampleEN}}</div>
    <div class="example-cn">{{ExampleCN}}</div>
  </div>
</div>
""".strip()

CSS = """
/* ========== 通用样式 ========== */
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  max-width: 600px;
  margin: 0 auto;
  padding: 20px;
  background: #ffffff;
  line-height: 1.6;
}

.card-front, .card-back {
  background: #ffffff;
  padding: 20px;
}

/* ========== 头部区域 ========== */
.header-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e5e7eb;
  flex-wrap: wrap;
  gap: 8px;
}

.category {
  display: inline-block;
  background: #f3f4f6;
  color: #6b7280;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.tags {
  font-size: 11px;
  color: #9ca3af;
  padding: 3px 8px;
  background: #f9fafb;
  border-radius: 3px;
}

.reverse-indicator {
  background: #e5e7eb;
  color: #6b7280;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

/* ========== 单词区域 ========== */
.word-container {
  text-align: left;
  margin: 20px 0;
  padding: 15px 0;
}

.word {
  font-size: 28px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
  letter-spacing: 0.5px;
}

.phonetic {
  font-size: 16px;
  color: #6b7280;
  font-family: "Lucida Sans Unicode", "Arial Unicode MS", sans-serif;
}

/* ========== 音频图标 ========== */
.audio-icon {
  display: inline-block;
  font-size: 14px;
  margin-left: 8px;
  opacity: 0.6;
  vertical-align: middle;
}

/* ========== 音频提示 ========== */
.audio-hint {
  text-align: left;
  color: #9ca3af;
  font-size: 12px;
  margin-top: 15px;
  padding: 8px 10px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 2px solid #d1d5db;
}

/* ========== 分隔线 ========== */
.divider {
  border: none;
  height: 1px;
  background: #e5e7eb;
  margin: 20px 0;
}

/* ========== 释义区域 ========== */
.meaning-section {
  margin: 15px 0;
  padding: 12px 15px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 3px solid #9ca3af;
  line-height: 1.6;
}

.part-of-speech {
  display: inline-block;
  background: #e5e7eb;
  color: #4b5563;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 600;
  margin-right: 10px;
  text-transform: lowercase;
}

.chinese-meaning {
  font-size: 16px;
  font-weight: 500;
  color: #1f2937;
  line-height: 1.6;
}

/* ========== 词根词缀区域 ========== */
.etymology-section {
  margin: 15px 0;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 3px solid #d1d5db;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.etymology-icon {
  font-size: 14px;
  color: #9ca3af;
}

.etymology-content {
  font-size: 14px;
  color: #4b5563;
  line-height: 1.5;
}

/* ========== 例句区域 ========== */
.example-section {
  margin: 15px 0;
  padding: 12px 15px;
  background: #ffffff;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
}

.example-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
}

.example-en {
  font-size: 15px;
  line-height: 1.6;
  color: #1f2937;
  margin-bottom: 8px;
}

.example-cn {
  font-size: 14px;
  line-height: 1.6;
  color: #6b7280;
}

/* 高亮例句中的单词 */
.example-en b, .example-en strong {
  color: #1f2937;
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: #d1d5db;
  text-decoration-thickness: 2px;
  text-underline-offset: 2px;
}

.example-cn b, .example-cn strong {
  color: #4b5563;
  font-weight: 600;
}

/* ========== 注释区域 ========== */
.notes-section {
  margin-top: 15px;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 3px solid #9ca3af;
}

.notes-label {
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.notes-content {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.5;
}

/* ========== 反向卡片特殊样式 ========== */
.card-front.reverse {
  background: #f9fafb;
}

.chinese-prompt {
  text-align: left;
  margin: 30px 0;
}

.prompt-label {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 15px;
}

.chinese-meaning-large {
  font-size: 24px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 12px;
  line-height: 1.4;
}

.part-of-speech-hint {
  font-size: 14px;
  color: #6b7280;
  font-weight: 500;
}

.hint-section {
  text-align: left;
  margin-top: 20px;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 4px;
  border-left: 3px solid #d1d5db;
}

.hint-text {
  font-size: 13px;
  color: #6b7280;
}

.answer-section {
  text-align: left;
  margin: 20px 0;
  padding: 15px;
  background: #f9fafb;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
}

.answer-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ========== 响应式设计 ========== */
@media (max-width: 480px) {
  .word {
    font-size: 24px;
  }
  
  .phonetic {
    font-size: 14px;
  }
  
  .chinese-meaning {
    font-size: 15px;
  }
  
  .chinese-meaning-large {
    font-size: 20px;
  }
  
  .example-en {
    font-size: 14px;
  }
  
  .example-cn {
    font-size: 13px;
  }
  
  .word-image {
    max-height: 150px;
  }
}

/* ========== 夜间模式 ========== */
.night_mode .card {
  background: #1f2937;
}

.night_mode .card-front,
.night_mode .card-back {
  background: #1f2937;
  color: #e5e7eb;
}

.night_mode .header-section {
  border-bottom-color: #374151;
}

.night_mode .category,
.night_mode .reverse-indicator {
  background: #374151;
  color: #9ca3af;
}

.night_mode .tags {
  background: #374151;
  color: #6b7280;
}

.night_mode .word {
  color: #f3f4f6;
}

.night_mode .phonetic {
  color: #9ca3af;
}

.night_mode .meaning-section {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .chinese-meaning {
  color: #e5e7eb;
}

.night_mode .etymology-section {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .etymology-content {
  color: #d1d5db;
}

.night_mode .synonyms,
.night_mode .antonyms {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .relation-label,
.night_mode .relation-words {
  color: #d1d5db;
}

.night_mode .example-section {
  background: #1f2937;
  border-color: #374151;
}

.night_mode .example-en {
  color: #e5e7eb;
}

.night_mode .example-cn {
  color: #9ca3af;
}

.night_mode .example-en b,
.night_mode .example-en strong {
  color: #f3f4f6;
  text-decoration-color: #6b7280;
}

.night_mode .notes-section {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .notes-label {
  color: #9ca3af;
}

.night_mode .notes-content {
  color: #d1d5db;
}

.night_mode .chinese-meaning-large {
  color: #f3f4f6;
}

.night_mode .answer-section {
  background: #374151;
  border-color: #4b5563;
}

.night_mode .hint-section {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .audio-hint {
  background: #374151;
  border-left-color: #6b7280;
}

.night_mode .word-image {
  border-color: #374151;
}
""".strip()

LATEX_PRE = r"""\documentclass[12pt]{article}
\special{papersize=3in,5in}
\usepackage[utf8]{inputenc}
\usepackage{amssymb,amsmath}
\pagestyle{empty}
\setlength{\parindent}{0in}
\begin{document}
"""
LATEX_POST = r"\end{document}"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def progress(label: str, completed: int, total: int, detail: str = "") -> None:
    if total <= 0:
        return
    percent = completed * 100 / total
    suffix = f" - {detail}" if detail else ""
    print(f"  {label} {completed}/{total} ({percent:.1f}%){suffix}", flush=True)


def clean_text(value: str) -> str:
    value = value.strip()
    if value == "-":
        return ""
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>").replace(FIELD_SEPARATOR, " ")


def parse_vocabulary() -> list[dict[str, Any]]:
    contents = "\n".join(line.strip() for line in VOCABULARY_FILE.read_text(encoding="utf-8").splitlines())
    records: list[dict[str, Any]] = []
    note_id = 0

    for category_index, category in enumerate(contents.split("===\n"), start=1):
        if not category.strip():
            continue
        category_parts = category.split("+++\n", 1)
        if len(category_parts) != 2:
            raise ValueError(f"Malformed category block {category_index}")

        category_name = category_parts[0].strip()
        category_audio_label = f"{category_index:02d}_{category_name}"
        for group_index, word_group in enumerate(category_parts[1].split("---\n"), start=1):
            for line in word_group.strip().splitlines():
                if not line.strip():
                    continue
                parts = [part.strip() for part in line.split("|", 4)]
                while len(parts) < 5:
                    parts.append("")

                note_id += 1
                word_raw, pos, meaning, example, extra = parts
                variants = [item.strip() for item in word_raw.split("/") if item.strip()]
                primary = variants[0] if variants else word_raw
                records.append(
                    {
                        "id": note_id,
                        "group": group_index,
                        "category": category_name,
                        "category_audio_label": category_audio_label,
                        "word_raw": word_raw,
                        "word_variants": variants or [word_raw],
                        "primary_word": primary,
                        "pos": clean_text(pos),
                        "meaning": clean_text(meaning),
                        "example": clean_text(example),
                        "extra": clean_text(extra),
                    }
                )

    return records


def display_word(record: dict[str, Any]) -> str:
    return " / ".join(str(word) for word in record["word_variants"])


def stable_guid(record: dict[str, Any]) -> str:
    base = f"{record['category_audio_label']}::{record['word_raw']}::{record['id']}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]


def checksum(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:8], 16)


def tagify(value: str) -> str:
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"[^\w:.-]+", "_", value, flags=re.UNICODE)
    return value.strip("_") or "unknown"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value[:48] or "word"


def highlight_example(example: str, variants: list[str]) -> str:
    if not example:
        return ""

    escaped = html.escape(example, quote=False)
    words = sorted((html.escape(word, quote=False) for word in variants if word), key=len, reverse=True)
    if not words:
        return escaped

    pattern = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(word) for word in words) + r")(?![A-Za-z])", re.IGNORECASE)
    return pattern.sub(r"<b>\1</b>", escaped)


def normalize_cache_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def normalize_ipa(value: str) -> str:
    value = value.strip().strip("/[]")
    if not value or "*" in value:
        return ""

    # CMU-derived converters can emit multiple primary stress marks for
    # compounds. Keep the first primary stress and demote later ones.
    seen_primary_stress = False
    normalized: list[str] = []
    for char in value:
        if char == "ˈ":
            if seen_primary_stress:
                normalized.append("ˌ")
            else:
                normalized.append(char)
                seen_primary_stress = True
            continue
        normalized.append(char)

    value = "".join(normalized).strip()
    return f"/{value}/" if value else ""


def local_ipa_candidates(word: str) -> list[str]:
    candidates = [word.strip()]
    folded = ascii_fold(word).strip()
    if folded and folded not in candidates:
        candidates.append(folded)
    if "-" in folded:
        candidates.append(folded.replace("-", " "))

    spelling_variants = {
        "despatch": "dispatch",
        "enrol": "enroll",
        "fulfil": "fulfill",
        "instalment": "installment",
        "instil": "instill",
        "maths": "mathematics",
    }
    if folded in spelling_variants:
        candidates.append(spelling_variants[folded])
    if "isation" in folded:
        candidates.append(folded.replace("isation", "ization"))
    if folded.endswith("iser"):
        candidates.append(folded[:-4] + "izer")
    if folded.endswith("ise"):
        candidates.append(folded[:-3] + "ize")
    if folded.endswith("yse"):
        candidates.append(folded[:-3] + "yze")
    if "our" in folded:
        candidates.append(folded.replace("our", "or"))

    compound_variants = {
        "biorhythm": "bio rhythm",
        "brickwork": "brick work",
        "hydrosphere": "hydro sphere",
        "interbreed": "inter breed",
        "preposition": "pre position",
        "slothful": "sloth full",
        "takeaway": "take away",
        "thermodynamic": "thermo dynamic",
    }
    if folded in compound_variants:
        candidates.append(compound_variants[folded])

    unique_candidates: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates


def generate_local_phonetic(word: str) -> str:
    for candidate in local_ipa_candidates(word):
        phonetic = normalize_ipa(eng_to_ipa.convert(candidate))
        if phonetic:
            return phonetic
    return ""


def fetch_one_phonetic(word: str) -> tuple[str, str]:
    return word, generate_local_phonetic(word)


def refresh_phonetics(records: list[dict[str, Any]], force: bool = False) -> dict[str, str]:
    cache: dict[str, str] = read_json(PHONETIC_CACHE, {})
    words = sorted({normalize_cache_key(str(record["primary_word"])) for record in records})
    pending = words if force else [word for word in words if not cache.get(word)]
    if not pending:
        return cache

    if eng_to_ipa is None:
        raise RuntimeError("Missing phonetic dependency. Install it with: pip install eng-to-ipa")

    action = "Refreshing" if force else "Fetching"
    print(f"{action} phonetics from eng-to-ipa: {len(pending)} words", flush=True)
    completed = 0
    with ThreadPoolExecutor(max_workers=PHONETIC_WORKERS) as pool:
        futures = {pool.submit(fetch_one_phonetic, word): word for word in pending}
        for future in as_completed(futures):
            word, phonetic = future.result()
            cache[word] = phonetic
            completed += 1
            write_json(PHONETIC_CACHE, cache)
            if completed == 1 or completed % max(PROGRESS_EVERY, 1) == 0 or completed == len(pending):
                progress("phonetics", completed, len(pending), word)

    write_json(PHONETIC_CACHE, cache)
    missing = [word for word in words if not cache.get(word)]
    if missing:
        print(
            f"  eng-to-ipa did not return phonetics for {len(missing)} words: {', '.join(missing[:20])}",
            flush=True,
        )
    return cache


def translation_prompt(word: str, text: str) -> str:
    return f"""请将以下英文句子翻译成中文，并在翻译中用<b></b>标签标注出与英文单词"{word}"对应的中文词汇。

英文句子：{text}
目标单词：{word}

要求：
1. 翻译要准确、自然
2. 用<b></b>标签包裹对应的中文词汇
3. 只返回翻译结果，不要其他说明

翻译："""


def etymology_prompt(word: str) -> str:
    return f"""请分析英文单词"{word}"的词根词缀构成。

要求：
1. 如果有明确的词根词缀，按格式返回：词根1(含义) + 词根2(含义)
2. 如果没有明显的词根词缀结构，返回空字符串
3. 只返回分析结果，不要其他说明
4. 示例格式：atmo-(蒸汽) + sphere(球)

单词：{word}
词根词缀："""


def ai_cache_key(prefix: str, *parts: str) -> str:
    raw = "\x1f".join([prefix, *parts])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def sanitize_ai_result(value: Any) -> str:
    if value is None:
        return ""
    value = str(value)
    value = value.strip()
    if value in {'""', "''", "空字符串", "无", "没有", "N/A", "n/a", "None", "none"}:
        return ""
    return value.strip('"').strip("'").strip()


def call_openai_chat(prompt: str) -> str:
    if not AI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for AI translation and etymology generation.")

    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": AI_TEMPERATURE,
    }
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{AI_BASE_URL}/chat/completions"

    for attempt in range(5):
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code in {429, 500, 502, 503, 504} and attempt < 4:
            time.sleep(2 * (attempt + 1))
            continue
        response.raise_for_status()
        data = response.json()
        return sanitize_ai_result(data["choices"][0]["message"]["content"])

    return ""


def refresh_ai(
    records: list[dict[str, Any]],
    skip_ai: bool = False,
    ai_tasks: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    if ai_tasks is None:
        ai_tasks = {"translations", "etymologies"}

    cache = read_json(AI_CACHE, {"translations": {}, "etymologies": {}})
    cache.setdefault("translations", {})
    cache.setdefault("etymologies", {})

    translation_jobs: list[tuple[str, dict[str, Any]]] = []
    etymology_jobs: list[tuple[str, dict[str, Any]]] = []

    for record in records:
        word = str(record["primary_word"])
        example = str(record["example"])
        if "translations" in ai_tasks and example:
            key = ai_cache_key("translation-v1", word, example)
            if key not in cache["translations"]:
                translation_jobs.append((key, record))

        if "etymologies" in ai_tasks:
            etymology_key = ai_cache_key("etymology-v1", word)
            if etymology_key not in cache["etymologies"]:
                etymology_jobs.append((etymology_key, record))

    if skip_ai:
        for key, _ in translation_jobs:
            cache["translations"][key] = ""
        for key, _ in etymology_jobs:
            cache["etymologies"][key] = ""
        write_json(AI_CACHE, cache)
        return cache

    if (translation_jobs or etymology_jobs) and not AI_API_KEY:
        raise RuntimeError(
            "Missing OPENAI_API_KEY. "
            f"Need {len(translation_jobs)} sentence translations and {len(etymology_jobs)} etymology analyses. "
            "Set OPENAI_API_KEY, optionally OPENAI_MODEL/OPENAI_BASE_URL, then rerun this script."
        )

    total = len(translation_jobs) + len(etymology_jobs)
    if total:
        print(
            f"Calling AI model {AI_MODEL}: {len(translation_jobs)} translations, "
            f"{len(etymology_jobs)} etymologies",
            flush=True,
        )

    completed = 0
    for key, record in translation_jobs:
        word = str(record["primary_word"])
        example = str(record["example"])
        cache["translations"][key] = call_openai_chat(translation_prompt(word, example))
        completed += 1
        write_json(AI_CACHE, cache)
        if completed == 1 or completed % max(PROGRESS_EVERY, 1) == 0 or completed == total:
            progress("AI translations", completed, total, word)
        time.sleep(AI_REQUEST_DELAY)

    for key, record in etymology_jobs:
        word = str(record["primary_word"])
        cache["etymologies"][key] = call_openai_chat(etymology_prompt(word))
        completed += 1
        write_json(AI_CACHE, cache)
        if completed == 1 or completed % max(PROGRESS_EVERY, 1) == 0 or completed == total:
            progress("AI etymologies", completed, total, word)
        time.sleep(AI_REQUEST_DELAY)

    write_json(AI_CACHE, cache)
    return cache


def translation_for(record: dict[str, Any], cache: dict[str, dict[str, str]]) -> str:
    example = str(record["example"])
    if not example:
        return ""
    key = ai_cache_key("translation-v1", str(record["primary_word"]), example)
    return cache["translations"].get(key, "")


def etymology_for(record: dict[str, Any], cache: dict[str, dict[str, str]]) -> str:
    key = ai_cache_key("etymology-v1", str(record["primary_word"]))
    return cache["etymologies"].get(key, "")


def has_cached_translation(record: dict[str, Any], cache: dict[str, dict[str, str]]) -> bool:
    example = str(record["example"])
    if not example:
        return False
    key = ai_cache_key("translation-v1", str(record["primary_word"]), example)
    return key in cache.get("translations", {})


def find_audio(record: dict[str, Any]) -> Path | None:
    category_dir = AUDIO_ROOT / str(record["category_audio_label"])
    for variant in record["word_variants"]:
        candidate = category_dir / f"{variant}.mp3"
        if candidate.exists():
            return candidate
    return None


def build_notes(record: dict[str, Any]) -> str:
    notes: list[str] = []
    extra = str(record["extra"])
    if extra:
        notes.append(extra)
    if len(record["word_variants"]) > 1:
        notes.append("拼写/词形变体：" + " / ".join(str(word) for word in record["word_variants"]))
    return "<br>".join(html.escape(note, quote=False) for note in notes if note)


def build_note(
    record: dict[str, Any],
    media_name: str | None,
    phonetics: dict[str, str],
    ai_cache: dict[str, dict[str, str]],
) -> dict[str, Any]:
    variants = [str(word) for word in record["word_variants"]]
    display = display_word(record)
    category = str(record["category"])
    pos = str(record["pos"])
    tags = [
        "IELTS",
        f"category::{tagify(category)}",
        f"pos::{tagify(pos.replace('.', ''))}",
    ]
    audio = f"[sound:{media_name}]" if media_name else ""
    example_en = highlight_example(str(record["example"]), variants)
    phonetic = phonetics.get(normalize_cache_key(str(record["primary_word"])), "")

    fields = {
        "Word": html.escape(display, quote=False),
        "Phonetic": html.escape(phonetic, quote=False),
        "PartOfSpeech": html.escape(pos, quote=False),
        "ChineseMeaning": html.escape(str(record["meaning"]), quote=False),
        "ExampleEN": example_en,
        "ExampleCN": translation_for(record, ai_cache),
        "Audio": audio,
        "Category": html.escape(category, quote=False),
        "Etymology": html.escape(etymology_for(record, ai_cache), quote=False),
        "Notes": build_notes(record),
    }
    return {
        "guid": stable_guid(record),
        "sort_field": display,
        "fields": fields,
        "tags": tags,
        "media_name": media_name,
    }


def model_json(mod_time: int) -> dict[str, Any]:
    field_defs = [
        {
            "name": name,
            "ord": index,
            "sticky": False,
            "rtl": False,
            "font": "Arial",
            "size": 20,
        }
        for index, name in enumerate(FIELDS)
    ]
    templates = [
        {
            "name": "Forward",
            "ord": 0,
            "qfmt": FRONT_FORWARD,
            "afmt": BACK_FORWARD,
            "bqfmt": "",
            "bafmt": "",
            "did": None,
        },
        {
            "name": "Reverse",
            "ord": 1,
            "qfmt": FRONT_REVERSE,
            "afmt": BACK_REVERSE,
            "bqfmt": "",
            "bafmt": "",
            "did": None,
        },
    ]
    return {
        "id": MODEL_ID,
        "name": MODEL_NAME,
        "type": 0,
        "mod": mod_time,
        "usn": -1,
        "sortf": 0,
        "did": DECK_ID,
        "tmpls": templates,
        "flds": field_defs,
        "css": CSS,
        "latexPre": LATEX_PRE,
        "latexPost": LATEX_POST,
        "req": [[0, "any", [0]], [1, "any", [3]]],
    }


def deck_json(mod_time: int) -> dict[str, Any]:
    return {
        "id": DECK_ID,
        "mod": mod_time,
        "name": DECK_NAME,
        "usn": -1,
        "lrnToday": [0, 0],
        "revToday": [0, 0],
        "newToday": [0, 0],
        "timeToday": [0, 0],
        "collapsed": False,
        "browserCollapsed": False,
        "dyn": 0,
        "conf": 1,
        "extendNew": 0,
        "extendRev": 0,
        "desc": "IELTS vocabulary deck generated from data/vocabulary.txt.",
    }


def deck_config_json() -> dict[str, Any]:
    return {
        "1": {
            "id": 1,
            "mod": 0,
            "name": "Default",
            "usn": 0,
            "maxTaken": 60,
            "autoplay": True,
            "timer": 0,
            "replayq": True,
            "new": {
                "delays": [15, 240, 480],
                "ints": [1, 3, 7],
                "initialFactor": 2500,
                "separate": True,
                "order": 1,
                "perDay": 20,
                "bury": False,
            },
            "rev": {
                "perDay": 200,
                "ease4": 1.3,
                "fuzz": 0.05,
                "minSpace": 1,
                "ivlFct": 1,
                "maxIvl": 36500,
                "bury": False,
            },
            "lapse": {
                "delays": [15, 240],
                "mult": 0,
                "minInt": 1,
                "leechFails": 8,
                "leechAction": 0,
            },
            "dyn": False,
        }
    }


def collection_config(note_count: int) -> dict[str, Any]:
    return {
        "nextPos": note_count + 1,
        "estTimes": True,
        "activeDecks": [DECK_ID],
        "sortType": "noteFld",
        "timeLim": 0,
        "sortBackwards": False,
        "addToCur": True,
        "curDeck": DECK_ID,
        "curModel": MODEL_ID,
        "newBury": True,
        "newSpread": 0,
        "dueCounts": True,
        "collapseTime": 1200,
    }


def write_collection(db_path: Path, notes: list[dict[str, Any]]) -> None:
    now_sec = int(time.time())
    now_ms = int(time.time() * 1000)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO col VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                now_sec,
                now_sec,
                now_ms,
                11,
                0,
                0,
                0,
                json.dumps(collection_config(len(notes)), ensure_ascii=False),
                json.dumps({str(MODEL_ID): model_json(now_sec)}, ensure_ascii=False),
                json.dumps({str(DECK_ID): deck_json(now_sec)}, ensure_ascii=False),
                json.dumps(deck_config_json(), ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
            ),
        )

        next_id = now_ms
        note_rows = []
        card_rows = []
        for due, note in enumerate(notes, start=1):
            note_id = next_id
            next_id += 1
            field_values = [str(note["fields"][field]) for field in FIELDS]
            flds = FIELD_SEPARATOR.join(field_values)
            tags = " " + " ".join(note["tags"]) + " "
            sfld = str(note["sort_field"])
            note_rows.append(
                (
                    note_id,
                    note["guid"],
                    MODEL_ID,
                    now_sec,
                    -1,
                    tags,
                    flds,
                    sfld,
                    checksum(sfld),
                    0,
                    "",
                )
            )
            for ord_value in (0, 1):
                card_id = next_id
                next_id += 1
                card_rows.append(
                    (
                        card_id,
                        note_id,
                        DECK_ID,
                        ord_value,
                        now_sec,
                        -1,
                        0,
                        0,
                        due,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        "",
                    )
                )

        conn.executemany("INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", note_rows)
        conn.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", card_rows)
        conn.commit()
    finally:
        conn.close()


def write_tsv(notes: list[dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing TSV: {OUTPUT_TSV}", flush=True)
    with OUTPUT_TSV.open("w", encoding="utf-8", newline="") as file:
        file.write("#separator:Tab\n")
        file.write("#html:true\n")
        file.write("#deck:IELTS Vocabulary\n")
        file.write("#notetype:IELTS Vocabulary Enhanced\n")
        file.write("#tags:IELTS\n")
        file.write("#guid column:1\n")
        file.write("#columns:Guid\t" + "\t".join(FIELDS) + "\n")
        writer = csv.writer(file, dialect="excel-tab", lineterminator="\n")
        for note in notes:
            row = [note["guid"]] + [note["fields"][field] for field in FIELDS]
            writer.writerow(row)


def write_apkg(notes: list[dict[str, Any]], media_sources: list[tuple[Path, str]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing APKG: {OUTPUT_APKG}", flush=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "collection.anki2"
        print("  creating collection.anki2", flush=True)
        write_collection(db_path, notes)

        media_map = {str(index): name for index, (_, name) in enumerate(media_sources)}
        with OUTPUT_APKG.open("wb") as raw_file:
            with zipfile.ZipFile(raw_file, "w", allowZip64=True) as package:
                package.write(db_path, "collection.anki2", compress_type=zipfile.ZIP_DEFLATED)
                package.writestr("media", json.dumps(media_map, ensure_ascii=False), compress_type=zipfile.ZIP_DEFLATED)
                for index, (source_path, _) in enumerate(media_sources):
                    package.write(source_path, str(index), compress_type=zipfile.ZIP_STORED)
                    completed = index + 1
                    if completed == 1 or completed % max(PROGRESS_EVERY, 1) == 0 or completed == len(media_sources):
                        progress("media", completed, len(media_sources), source_path.name)


def build_export(
    skip_ai: bool = False,
    phonetics_only: bool = False,
    refresh_all_phonetics: bool = False,
    limit: int | None = None,
    cached_ai_only: bool = False,
    ai_tasks: set[str] | None = None,
) -> dict[str, int]:
    records = parse_vocabulary()
    if limit is not None:
        records = records[:limit]
    print(f"Parsed vocabulary records: {len(records)}", flush=True)

    ai_cache = read_json(AI_CACHE, {"translations": {}, "etymologies": {}})
    ai_cache.setdefault("translations", {})
    ai_cache.setdefault("etymologies", {})

    if cached_ai_only:
        original_count = len(records)
        records = [record for record in records if has_cached_translation(record, ai_cache)]
        print(
            f"Using cached AI translations only: {len(records)}/{original_count} records ready",
            flush=True,
        )
        if not records:
            raise RuntimeError("No records have cached AI translations yet.")

    phonetics = refresh_phonetics(records, force=refresh_all_phonetics)
    if phonetics_only:
        return {"notes": len(records), "cards": 0, "media": 0, "missing_audio": 0}

    if not cached_ai_only:
        ai_cache = refresh_ai(records, skip_ai=skip_ai, ai_tasks=ai_tasks)
    notes: list[dict[str, Any]] = []
    media_sources: list[tuple[Path, str]] = []
    missing_audio = 0

    print("Building notes and media list", flush=True)
    for index, record in enumerate(records, start=1):
        audio_path = find_audio(record)
        media_name = None
        if audio_path:
            media_name = f"ielts_vocab_{int(record['id']):04d}_{slugify(str(record['primary_word']))}.mp3"
            media_sources.append((audio_path, media_name))
        else:
            missing_audio += 1
        notes.append(build_note(record, media_name, phonetics, ai_cache))
        if index == 1 or index % max(PROGRESS_EVERY, 1) == 0 or index == len(records):
            progress("notes", index, len(records), str(record["primary_word"]))

    write_tsv(notes)
    write_apkg(notes, media_sources)

    return {
        "notes": len(notes),
        "cards": len(notes) * 2,
        "media": len(media_sources),
        "missing_audio": missing_audio,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ai", action="store_true", help="Build with blank AI fields for missing cache entries.")
    parser.add_argument("--phonetics-only", action="store_true", help="Only refresh phonetic cache.")
    parser.add_argument("--refresh-phonetics", action="store_true", help="Regenerate all cached phonetics instead of only missing ones.")
    parser.add_argument("--limit", type=int, help="Only export the first N vocabulary records.")
    parser.add_argument(
        "--ai-task",
        choices=["all", "translations", "etymologies"],
        default="all",
        help="Choose which missing AI fields to generate.",
    )
    parser.add_argument(
        "--cached-ai-only",
        action="store_true",
        help="Export only records with cached AI translations, without making new AI calls.",
    )
    args = parser.parse_args()
    ai_tasks = (
        {"translations", "etymologies"}
        if args.ai_task == "all"
        else {args.ai_task}
    )

    summary = build_export(
        skip_ai=args.skip_ai,
        phonetics_only=args.phonetics_only,
        refresh_all_phonetics=args.refresh_phonetics,
        limit=args.limit,
        cached_ai_only=args.cached_ai_only,
        ai_tasks=ai_tasks,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.phonetics_only:
        print(str(OUTPUT_TSV))
        print(str(OUTPUT_APKG))


if __name__ == "__main__":
    main()
