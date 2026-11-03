"""Minimal sync server for the 词间 desktop app.

Only three jobs remain on the server:
- read the Anki collection and serve the vocabulary snapshot (`GET /api/vocab`);
- keep the append-only answer log that clients merge (`POST /api/sync`);
- copy the collection from anki-sync-server on a schedule.
Scheduling, statistics, pages and media all live in the desktop client.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request
from waitress import serve

from anki import AnkiReader
from auth import install_token_gate
from config import Config, load_config
from ledger import Ledger, time_text
from sync import copy_collection_group, latest_collection, sync_configured, sync_target_path

LOG = logging.getLogger(__name__)
VOCABULARY_FORMAT = 1


def _env_seconds(name: str, default: float, minimum: float = 0) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
        return value if value >= minimum else default
    except ValueError:
        return default


class AppState:
    def __init__(self, config: Config):
        self.config = config
        self.lock = threading.RLock()
        self.reader: AnkiReader | None = None
        self.ledger = Ledger(config.db_path)
        self.closed = False
        self.open_reader()

    def open_reader(self) -> None:
        try:
            if self.config.anki.db_path:
                self.reader = AnkiReader(self.config.anki.db_path, self.config.anki.deck_name, self.config.anki.deck_id)
                LOG.info("Using Anki database: %s (deck=%s)", self.config.anki.db_path, self.config.anki.deck_name)
        except Exception as exc:
            self.reader = None
            LOG.warning("Anki reader disabled: %s", exc)

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            if self.reader:
                self.reader.close()
                self.reader = None
            self.ledger.close()
            self.closed = True

    def vocabulary(self) -> dict[str, Any]:
        with self.lock:
            if not self.reader:
                raise RuntimeError("Anki 数据库不可用")
            words = self.reader.snapshot()
        return {"format": VOCABULARY_FORMAT, "generated_at": time_text(datetime.now(timezone.utc)),
                "deck_name": self.config.anki.deck_name, "words": words}

    def refresh_collection(self) -> int:
        """Copies the newest collection from anki-sync-server and reopens the reader."""
        source = latest_collection(os.environ.get("ANKI_SYNC_SOURCE_DIR", ""))
        with self.lock:
            if self.reader:
                self.reader.close()
                self.reader = None
            try:
                copy_collection_group(source, sync_target_path(self.config.anki.db_path),
                                      _env_seconds("ANKI_SYNC_STABLE_SECONDS", 2, 0))
            finally:
                self.open_reader()
            if not self.reader:
                raise RuntimeError("复制后的 Anki 数据库无法读取")
            return self.reader.count_learned()


def create_app(config: Config | None = None, *, start_background_tasks: bool = True) -> Flask:
    cfg = config or load_config()
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    state = AppState(cfg)
    app.extensions["cijian_state"] = state
    install_token_gate(app, cfg.access_token)

    @app.route("/api/health")
    def health():
        return jsonify(success=True, status="ok")

    @app.route("/api/vocab")
    def vocabulary():
        return jsonify(success=True, data=state.vocabulary())

    @app.route("/api/sync", methods=["POST"])
    def sync():
        return jsonify(success=True, data=state.ledger.sync(request.get_json(silent=True)))

    @app.errorhandler(ValueError)
    def invalid_request(error):
        return jsonify(success=False, error=str(error)), 400

    @app.errorhandler(sqlite3.Error)
    @app.errorhandler(OSError)
    def storage_unavailable(error):
        LOG.exception("Storage unavailable")
        return jsonify(success=False, error="同步数据暂不可用，请稍后重试"), 503

    @app.errorhandler(RuntimeError)
    def unavailable(error):
        return jsonify(success=False, error=str(error)), 503

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(success=False, error="not found"), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify(success=False, error="method not allowed"), 405

    if start_background_tasks and not app.testing and sync_configured():
        start_collection_refresh(state)
    return app


def start_collection_refresh(state: AppState) -> None:
    def run() -> None:
        time.sleep(_env_seconds("ANKI_SYNC_INITIAL_WAIT_SECONDS", 60, 0))
        while True:
            try:
                LOG.info("Anki collection refreshed: %s learned words", state.refresh_collection())
            except Exception as exc:
                LOG.warning("Scheduled Anki refresh skipped: %s", exc)
            time.sleep(_env_seconds("ANKI_SYNC_INTERVAL_SECONDS", 300, 1))

    threading.Thread(target=run, name="anki-refresh", daemon=True).start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    application = create_app()
    state = application.extensions["cijian_state"]
    if not state.config.access_token:
        LOG.warning("ACCESS_TOKEN is empty: the sync API accepts any request")
    try:
        serve(application, host=state.config.server.host, port=state.config.server.port)
    finally:
        state.close()
