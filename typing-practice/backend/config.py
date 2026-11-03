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
    stats = raw.get("stats", {}) or {}
    env = os.environ
    cfg = Config(
        server=ServerConfig(host=str(server.get("host", "localhost")), port=_as_int(server.get("port", 8080), 8080)),
        anki=AnkiConfig(
            db_path=str(anki.get("db_path", "") or ""),
            deck_name=str(anki.get("deck_name", DEFAULT_DECK_NAME) or DEFAULT_DECK_NAME),
            deck_id=_as_int(anki.get("deck_id", DEFAULT_DECK_ID), DEFAULT_DECK_ID),
        ),
        db_path=str(stats.get("db_path", "") or "data/stats.db"),
        # ACCESS_PASSWORD is the old web login; honour it so an upgrade never opens the server.
        access_token=(env.get("ACCESS_TOKEN", "").strip() or env.get("ACCESS_PASSWORD", "").strip()),
    )
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
    if env.get("STATS_DB_PATH", "").strip():
        cfg.db_path = env["STATS_DB_PATH"].strip()
    if not cfg.anki.db_path.strip():
        cfg.anki.db_path = default_anki_db_path()
    if not cfg.server.host.strip():
        cfg.server.host = "localhost"
    if cfg.server.port <= 0:
        cfg.server.port = 8080
    return cfg
