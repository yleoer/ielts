"""Single-process Flask application for Word Atlas typing practice."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, abort, current_app, jsonify, render_template, request, send_from_directory

from anki import AnkiReader
from auth import install_access_gate
from config import Config, load_config
from memory import FREE_PRACTICE_LIMIT, MemoryStore, PracticeConflict
from optimizer_service import OptimizationService
from stats import StatsStore
from sync import copy_collection_group, latest_collection, sync_configured, sync_target_path


LOG = logging.getLogger(__name__)


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        self.sync: dict[str, Any] = {}
        self.stats = StatsStore(config.stats.db_path)
        self.memory = MemoryStore(self.stats, config.memory)
        self.optimizer = OptimizationService(self.stats, self.memory, config.optimization)
        self.closed = False
        try:
            if config.anki.db_path:
                self.reader = AnkiReader(config.anki.db_path, config.anki.deck_name, config.anki.deck_id)
                LOG.info("Using Anki database: %s (deck=%s, id=%s)", config.anki.db_path, config.anki.deck_name, config.anki.deck_id)
        except Exception as exc:
            LOG.warning("Anki reader disabled: %s", exc)

    def close(self) -> None:
        if self.closed:
            return
        self.optimizer.stop()
        with self.lock:
            if self.reader:
                self.reader.close()
                self.reader = None
            self.stats.close()
            self.closed = True

    def get_words(self, limit: int, category: str) -> list[dict[str, Any]]:
        # Read-only vocabulary endpoint for integrations.
        return [word for word in self.current_pool() if category == "all" or word["category"] == category][:limit]

    def current_pool(self) -> list[dict[str, Any]]:
        with self.lock:
            if not self.reader:
                raise RuntimeError("Anki database is not available")
            return self.reader.get_learned_word_pool("all")

    def config_payload(self) -> dict[str, Any]:
        with self.lock:
            total = 0
            deck_id = self.config.anki.deck_id
            available = self.reader is not None
            if self.reader:
                deck_id = self.reader.deck_id
                try:
                    total = self.reader.count_learned()
                except Exception:
                    pass
            return {
                "success": True,
                "anki_available": available,
                "anki_path": self.config.anki.db_path,
                "deck_name": self.config.anki.deck_name,
                "deck_id": deck_id,
                "total_learned": total,
                "default_limit": self.config.practice.default_limit,
                "max_limit": self.config.practice.max_limit,
                "easy_seconds": self.config.memory.easy_seconds,
                "hard_seconds": self.config.memory.hard_seconds,
            }

    def sync_status(self) -> dict[str, Any]:
        with self.lock:
            status = dict(self.sync)
            status.setdefault("before_words", 0)
            status.setdefault("after_words", 0)
            status.setdefault("added_words", 0)
            status.setdefault("added_word_list", [])
            status.setdefault("success", False)
            status["sync_configured"] = sync_configured()
            status["target_path"] = sync_target_path(self.config.anki.db_path)
            if self.reader and not status["after_words"]:
                try:
                    status["after_words"] = self.reader.count_learned()
                except Exception:
                    pass
        status["history"] = self.stats.list_sync_history(50)
        return status

    def sync_now(self) -> tuple[dict[str, Any], str | None]:
        with self.lock:
            status: dict[str, Any] = {
                "last_sync_at": _now_text(),
                "target_path": sync_target_path(self.config.anki.db_path),
                "sync_configured": sync_configured(),
                "before_words": 0,
                "after_words": 0,
                "added_words": 0,
                "added_word_list": [],
                "success": False,
                "history": [],
            }
            if not status["sync_configured"]:
                status["message"] = "Anki sync source is not configured"
                self.sync = status
                return status, status["message"]
            try:
                source = latest_collection(os.environ.get("ANKI_SYNC_SOURCE_DIR", ""))
                status["source_path"] = source
                before = self.reader.get_learned_word_pool("all") if self.reader else []
                status["before_words"] = len(before)
                if self.reader:
                    self.reader.close()
                    self.reader = None
                status["copied_files"] = copy_collection_group(
                    source,
                    status["target_path"],
                    _env_seconds("ANKI_SYNC_STABLE_SECONDS", 2, 0),
                )
                self.reader = AnkiReader(self.config.anki.db_path, self.config.anki.deck_name, self.config.anki.deck_id)
                after = self.reader.get_learned_word_pool("all")
                status["after_words"] = len(after)
                known = {word["id"] for word in before}
                status["added_word_list"] = [word for word in after if word["id"] not in known]
                status["added_words"] = len(status["added_word_list"])
                status["success"] = True
                status["message"] = "Anki collection synced"
                self.stats.save_sync_history(status)
                self.sync = status
                LOG.info("Anki sync completed: added_words=%s source=%s", status["added_words"], source)
                status["history"] = self.stats.list_sync_history(50)
                return status, None
            except Exception as exc:
                status["message"] = str(exc)
                self.sync = status
                return status, str(exc)


def _int_query(name: str, default: int) -> int:
    try:
        value = int(request.args.get(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _state() -> AppState:
    return current_app.extensions["typing_practice_state"]


def _stats_response(callback):
    try:
        return jsonify(success=True, data=callback())
    except Exception as exc:
        LOG.exception("stats query failed")
        return jsonify(success=False, error=str(exc)), 500


def create_app(config: Config | None = None, *, start_background_tasks: bool = True) -> Flask:
    cfg = config or load_config()
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(root / "frontend" / "templates"), static_folder=None)
    # Vue uses {{ }} bindings. Jinja still renders the pages, but uses a
    # separate delimiter so those client-side bindings remain untouched.
    app.jinja_env.variable_start_string = "[["
    app.jinja_env.variable_end_string = "]]"
    state = AppState(cfg)
    app.extensions["typing_practice_state"] = state
    install_access_gate(app, cfg.access_password, cfg.stats.db_path)

    @app.after_request
    def _cors(response):
        origin = request.headers.get("Origin", "")
        if origin in {"", "null", "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8080", "http://127.0.0.1:8080"}:
            response.headers["Access-Control-Allow-Origin"] = origin or "null"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Origin, Content-Type, Accept"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.route("/")
    @app.route("/index.html")
    def index():
        return render_template("index.html", page_title="词间 · 练习")

    @app.route("/stats.html")
    def stats_page():
        return render_template("stats.html", page_title="词间 · 统计")

    @app.route("/assets/<path:filename>")
    def assets(filename: str):
        return send_from_directory(root / "frontend" / "assets", filename)

    @app.route("/src/<path:filename>")
    def source_files(filename: str):
        return send_from_directory(root / "frontend" / "src", filename)

    @app.route("/api/health")
    def health():
        return jsonify(success=True, status="ok")

    @app.route("/api/words")
    def words():
        limit = _int_query("limit", cfg.practice.default_limit)
        limit = min(limit, cfg.practice.max_limit)
        try:
            data = state.get_words(limit, request.args.get("category", "all"))
            return jsonify(success=True, data=data, total=len(data))
        except RuntimeError as exc:
            return jsonify(success=False, error=str(exc)), 503
        except Exception as exc:
            return jsonify(success=False, error=str(exc)), 500

    @app.route("/api/config")
    def config_endpoint():
        return jsonify(state.config_payload())

    @app.route("/api/media/<int:note_id>/<kind>")
    def word_media(note_id: int, kind: str):
        if kind != "illustration":
            abort(404)
        with state.lock:
            filename = state.reader.get_media_filename(note_id, kind) if state.reader else ""
        if not filename:
            abort(404)
        media_dir = Path(cfg.anki.media_dir or Path(cfg.anki.db_path).parent / "collection.media").expanduser().resolve()
        media_path = (media_dir / filename).resolve()
        if media_path.parent != media_dir or not media_path.is_file():
            abort(404)
        return send_from_directory(media_dir, filename, conditional=True)

    @app.route("/api/sync/status")
    def sync_status_endpoint():
        return jsonify(success=True, data=state.sync_status())

    @app.route("/api/sync/now", methods=["POST"])
    def sync_now_endpoint():
        status, error = state.sync_now()
        status["history"] = state.stats.list_sync_history(50)
        return (jsonify(success=False, error=error, data=status), 400) if error else jsonify(success=True, data=status)

    @app.route("/api/practice/queue")
    def practice_queue():
        mode = request.args.get("mode", "scheduled")
        limit = min(_int_query("limit", FREE_PRACTICE_LIMIT if mode == "free" else 1), cfg.practice.max_limit)
        data = state.memory.queue(
            state.current_pool(), request.args.get("session_id", ""),
            limit, mode,
        )
        return jsonify(success=True, data=data)

    @app.route("/api/practice/attempts", methods=["POST"])
    def practice_attempt():
        payload = request.get_json(silent=True)
        # A committed retry can be acknowledged even if Anki is temporarily unavailable.
        try:
            pool = state.current_pool()
        except RuntimeError:
            pool = None
        return jsonify(success=True, data=state.memory.submit(payload, pool))

    @app.route("/api/memory/summary")
    def memory_summary():
        return jsonify(success=True, data=state.memory.summary(state.current_pool()))

    @app.route("/api/memory/forecast-words")
    def forecast_words():
        return jsonify(success=True, data=state.memory.forecast_words(state.current_pool(), request.args.get("date", "")))

    @app.route("/api/memory/optimization")
    def optimization_status():
        return jsonify(success=True, data=state.optimizer.status())

    @app.route("/api/memory/optimization/runs")
    def optimization_history():
        try:
            before_id = int(request.args.get("before_id", "0"))
        except ValueError as exc:
            raise ValueError("无效的记录游标") from exc
        if before_id < 0:
            raise ValueError("无效的记录游标")
        return jsonify(success=True, data=state.optimizer.history(before_id, _int_query("limit", 20)))

    @app.route("/api/memory/optimization/runs/<int:run_id>")
    def optimization_record(run_id):
        record = state.optimizer.run_record(run_id)
        if record is None:
            abort(404)
        return jsonify(success=True, data=record)

    @app.route("/api/stats/sessions", methods=["POST"])
    def legacy_sessions():
        return jsonify(success=False, error="练习已升级，请刷新页面后使用逐题保存", code="client_upgrade_required"), 410

    @app.route("/api/stats/heatmap")
    def heatmap():
        return _stats_response(lambda: state.stats.heatmap(request.args.get("start_date", ""), request.args.get("end_date", "")))

    @app.route("/api/stats/accuracy-trend")
    def accuracy_trend():
        return _stats_response(lambda: state.stats.accuracy_trend(_int_query("days", 30)))

    @app.route("/api/stats/mastery-distribution")
    def mastery_distribution():
        summary = state.memory.summary(state.current_pool())
        return jsonify(success=True, data={key: summary[key] for key in ("new", "learning", "mastered")})

    @app.route("/api/stats/mastery-words")
    def mastery_words():
        return jsonify(success=True, data=state.memory.mastery_words(state.current_pool(), request.args.get("level", ""), _int_query("limit", 200)))

    @app.route("/api/stats/error-types")
    def error_types():
        return _stats_response(state.stats.error_types)

    @app.route("/api/stats/error-type-words")
    def error_type_words():
        return _stats_response(lambda: state.stats.error_type_words(request.args.get("type", "spelling"), _int_query("limit", 200)))

    @app.route("/api/stats/overview")
    def overview():
        return _stats_response(state.stats.overview)

    @app.errorhandler(PracticeConflict)
    def practice_conflict(error):
        return jsonify(success=False, error=str(error), code="practice_conflict"), 409

    @app.errorhandler(ValueError)
    def invalid_request(error):
        return jsonify(success=False, error=str(error)), 400

    @app.errorhandler(sqlite3.Error)
    @app.errorhandler(OSError)
    def storage_unavailable(error):
        LOG.exception("Practice storage unavailable")
        return jsonify(success=False, error="练习数据暂不可用，请稍后重试"), 503

    @app.errorhandler(RuntimeError)
    def unavailable(error):
        return jsonify(success=False, error=str(error)), 503

    @app.errorhandler(404)
    def not_found(_error):
        if request.method == "GET" and not request.path.startswith("/api/"):
            return render_template("index.html", page_title="打字练习")
        return jsonify(success=False, error="not found"), 404

    if start_background_tasks and not app.testing:
        state.optimizer.start()
        if sync_configured():
            start_sync_scheduler(app)
    return app


def start_sync_scheduler(app: Flask) -> None:
    def run() -> None:
        initial_wait = _env_seconds("ANKI_SYNC_INITIAL_WAIT_SECONDS", 60, 0)
        if initial_wait:
            time.sleep(initial_wait)
        state = app.extensions["typing_practice_state"]
        while True:
            with app.app_context():
                status, error = state.sync_now()
                if error:
                    LOG.warning("Scheduled Anki sync skipped: %s", error)
                elif status.get("added_words", 0) == 0:
                    LOG.info("Scheduled Anki sync completed with no new words")
            time.sleep(_env_seconds("ANKI_SYNC_INTERVAL_SECONDS", 300, 1))

    threading.Thread(target=run, name="anki-sync", daemon=True).start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    application = create_app()
    cfg = application.extensions["typing_practice_state"].config
    try:
        application.run(host=cfg.server.host, port=cfg.server.port)
    finally:
        application.extensions["typing_practice_state"].close()

