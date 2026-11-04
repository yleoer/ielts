"""Runtime configuration for the sync server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    anki: AnkiConfig = field(default_factory=AnkiConfig)
    # Answer log; kept at the old stats path so the web history is imported in place.
    db_path: str = "data/stats.db"
    # Desktop clients send `Authorization: Bearer <token>`; empty disables the check.
    access_token: str = ""


CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.yaml"


def default_anki_db_path() -> str:
    """The first profile collection in the local Anki data directory, or ""."""
    appdata = os.environ.get("APPDATA", "")
    home = Path.home()
    roots = ([Path(appdata) / "Anki2"] if appdata else
             [home / "Library" / "Application Support" / "Anki2", home / ".local" / "share" / "Anki2"])
    for root in roots:
        for collection in sorted(root.glob("*/collection.anki2")):
            if collection.is_file():
                return str(collection)
    return ""


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def load_config() -> Config:
    """YAML defaults, overridden by `typing-practice/.env` and process environment variables."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {} if CONFIG_PATH.is_file() else {}
    server, anki, stats = (raw.get(name) or {} for name in ("server", "anki", "stats"))
    return Config(
        server=ServerConfig(host=_env("SERVER_HOST") or server.get("host") or "localhost",
                            port=int(_env("SERVER_PORT") or server.get("port") or 8080)),
        anki=AnkiConfig(
            db_path=_env("ANKI_DB_PATH") or anki.get("db_path") or default_anki_db_path(),
            deck_name=_env("ANKI_DECK_NAME") or anki.get("deck_name") or DEFAULT_DECK_NAME,
            deck_id=int(_env("ANKI_DECK_ID") or anki.get("deck_id") or DEFAULT_DECK_ID),
        ),
        db_path=_env("STATS_DB_PATH") or stats.get("db_path") or "data/stats.db",
        # ACCESS_PASSWORD is the old web login; honour it so an upgrade never opens the server.
        access_token=_env("ACCESS_TOKEN") or _env("ACCESS_PASSWORD"),
    )
