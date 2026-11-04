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
from sync import copy_collection_group, latest_collection

LOG = logging.getLogger(__name__)
VOCABULARY_FORMAT = 1


def _env_seconds(name: str, default: float) -> float:
    return float(os.environ.get(name, "").strip() or default)


class AppState:
    def __init__(self, config: Config):
        self.config = config
        self.lock = threading.RLock()
        self.reader: AnkiReader | None = None
        self.ledger = Ledger(config.db_path)
        self.open_reader()

    def open_reader(self) -> None:
        """Opens the configured collection; when it is missing or unreadable `/api/vocab` returns 503."""
        if not self.config.anki.db_path:
            return
        try:
            self.reader = AnkiReader(self.config.anki.db_path, self.config.anki.deck_name, self.config.anki.deck_id)
            LOG.info("Using Anki database: %s (deck=%s)", self.config.anki.db_path, self.config.anki.deck_name)
        except (OSError, sqlite3.Error) as exc:
            LOG.warning("Anki reader disabled: %s", exc)

    def close(self) -> None:
        with self.lock:
            if self.reader:
                self.reader.close()
                self.reader = None
            self.ledger.close()

    def vocabulary(self) -> dict[str, Any]:
        with self.lock:
            if not self.reader:
                raise RuntimeError("Anki 数据库不可用")
            words = self.reader.snapshot()
        return {"format": VOCABULARY_FORMAT, "generated_at": time_text(datetime.now(timezone.utc)),
                "deck_name": self.config.anki.deck_name, "words": words}

    def refresh_collection(self, source_dir: str, target: str) -> int:
        """Copies the newest collection from anki-sync-server and reopens the reader."""
        source = latest_collection(source_dir)
        with self.lock:
            if self.reader:
                self.reader.close()
                self.reader = None
            try:
                copy_collection_group(source, target, _env_seconds("ANKI_SYNC_STABLE_SECONDS", 2))
            finally:
                self.open_reader()
            if not self.reader:
                raise RuntimeError("复制后的 Anki 数据库无法读取")
            return sum(word["learned"] for word in self.reader.snapshot())


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

    source_dir = os.environ.get("ANKI_SYNC_SOURCE_DIR", "").strip()
    target = os.environ.get("ANKI_SYNC_TARGET", "").strip()
    if start_background_tasks and source_dir and target:
        start_collection_refresh(state, source_dir, target)
    return app


def start_collection_refresh(state: AppState, source_dir: str, target: str) -> None:
    initial_wait = _env_seconds("ANKI_SYNC_INITIAL_WAIT_SECONDS", 60)
    interval = _env_seconds("ANKI_SYNC_INTERVAL_SECONDS", 300)

    def run() -> None:
        time.sleep(initial_wait)
        while True:
            try:
                LOG.info("Anki collection refreshed: %s learned words", state.refresh_collection(source_dir, target))
            except Exception as exc:  # keep the schedule alive; the next copy usually succeeds
                LOG.warning("Scheduled Anki refresh skipped: %s", exc)
            time.sleep(interval)

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
