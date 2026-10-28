"""Runtime configuration for the Flask application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

DEFAULT_DECK_NAME = "Word Atlas"
DEFAULT_DECK_ID = 1958430017


@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = 8080


@dataclass
class AnkiConfig:
    db_path: str = ""
    deck_name: str = DEFAULT_DECK_NAME
    deck_id: int = DEFAULT_DECK_ID
    media_dir: str = ""


@dataclass
class PracticeConfig:
    default_limit: int = 20
    max_limit: int = 100


@dataclass
class StatsConfig:
    db_path: str = "data/stats.db"


@dataclass
class Config:
    server: ServerConfig
    anki: AnkiConfig
    practice: PracticeConfig
    stats: StatsConfig
    access_password: str = ""


def discover_anki_db(anki_root: Path) -> str:
    """Find the first Anki profile collection below an Anki data directory."""
    if not anki_root.is_dir():
        return ""
    for profile in sorted(anki_root.iterdir()):
        if not profile.is_dir() or profile.name.startswith("."):
            continue
        if profile.name in {"addons21", "logs"}:
            continue
        collection = profile / "collection.anki2"
        if collection.is_file():
            return str(collection)
    return ""


def default_anki_db_path() -> str:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        root = Path(appdata) / "Anki2"
        user_one = root / "User 1" / "collection.anki2"
        if user_one.is_file():
            return str(user_one)
        found = discover_anki_db(root)
        if found:
            return found
        return str(user_one)

    home = Path.home()
    for root in (
        home / "Library" / "Application Support" / "Anki2",
        home / ".local" / "share" / "Anki2",
    ):
        found = discover_anki_db(root)
        if found:
            return found
    return ""


def _config_path() -> Path | None:
    candidates = (
        Path("config") / "config.yaml",
        Path("typing-practice") / "backend" / "config" / "config.yaml",
        Path(__file__).resolve().parent / "config" / "config.yaml",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_config() -> Config:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    raw: dict = {}
    path = _config_path()
    if path:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}

    server = raw.get("server", {}) or {}
    anki = raw.get("anki", {}) or {}
    practice = raw.get("practice", {}) or {}
    stats = raw.get("stats", {}) or {}

    cfg = Config(
        server=ServerConfig(
            host=str(server.get("host", "localhost")),
            port=_as_int(server.get("port", 8080), 8080),
        ),
        anki=AnkiConfig(
            db_path=str(anki.get("db_path", "") or ""),
            deck_name=str(anki.get("deck_name", DEFAULT_DECK_NAME) or DEFAULT_DECK_NAME),
            deck_id=_as_int(anki.get("deck_id", DEFAULT_DECK_ID), DEFAULT_DECK_ID),
            media_dir=str(anki.get("media_dir", "") or ""),
        ),
        practice=PracticeConfig(
            default_limit=_as_int(practice.get("default_limit", 20), 20),
            max_limit=_as_int(practice.get("max_limit", 100), 100),
        ),
        stats=StatsConfig(db_path=str(stats.get("db_path", "data/stats.db") or "data/stats.db")),
        access_password=os.environ.get("ACCESS_PASSWORD", ""),
    )

    env = os.environ
    if env.get("SERVER_HOST", "").strip():
        cfg.server.host = env["SERVER_HOST"].strip()
    if env.get("SERVER_PORT", "").strip():
        cfg.server.port = _as_int(env["SERVER_PORT"], cfg.server.port)
    if env.get("ANKI_DB_PATH", "").strip():
        cfg.anki.db_path = env["ANKI_DB_PATH"].strip()
    if env.get("ANKI_DECK_NAME", "").strip():
        cfg.anki.deck_name = env["ANKI_DECK_NAME"].strip()
    if env.get("ANKI_DECK_ID", "").strip():
        cfg.anki.deck_id = _as_int(env["ANKI_DECK_ID"], cfg.anki.deck_id)
    if env.get("ANKI_MEDIA_DIR", "").strip():
        cfg.anki.media_dir = env["ANKI_MEDIA_DIR"].strip()
    if env.get("PRACTICE_DEFAULT_LIMIT", "").strip():
        cfg.practice.default_limit = _as_int(env["PRACTICE_DEFAULT_LIMIT"], cfg.practice.default_limit)
    if env.get("PRACTICE_MAX_LIMIT", "").strip():
        cfg.practice.max_limit = _as_int(env["PRACTICE_MAX_LIMIT"], cfg.practice.max_limit)
    if env.get("STATS_DB_PATH", "").strip():
        cfg.stats.db_path = env["STATS_DB_PATH"].strip()

    if not cfg.anki.db_path.strip():
        cfg.anki.db_path = default_anki_db_path()
    if not cfg.server.host.strip():
        cfg.server.host = "localhost"
    if cfg.server.port <= 0:
        cfg.server.port = 8080
    if cfg.practice.default_limit <= 0:
        cfg.practice.default_limit = 20
    if cfg.practice.max_limit <= 0:
        cfg.practice.max_limit = 100
    cfg.practice.default_limit = min(cfg.practice.default_limit, cfg.practice.max_limit)
    if not cfg.stats.db_path.strip():
        cfg.stats.db_path = "data/stats.db"
    return cfg

