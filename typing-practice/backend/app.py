"""Single-process Flask application for IELTS typing practice."""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, current_app, jsonify, render_template, request, send_from_directory

from anki import AnkiReader
from config import Config, load_config
from practice import normalize_word, select_words
from stats import StatsStore


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
        try:
            if config.anki.db_path:
                self.reader = AnkiReader(config.anki.db_path, config.anki.deck_name, config.anki.deck_id)
                LOG.info("Using Anki database: %s (deck=%s, id=%s)", config.anki.db_path, config.anki.deck_name, config.anki.deck_id)
        except Exception as exc:
            LOG.warning("Anki reader disabled: %s", exc)

    def close(self) -> None:
        with self.lock:
            if self.reader:
                self.reader.close()
                self.reader = None
            self.stats.close()

    def get_words(self, limit: int, category: str) -> list[dict[str, Any]]:
        with self.lock:
            if not self.reader:
                raise RuntimeError("Anki database is not available")
            if not self.stats:
                return self.reader.get_learned_words(limit, category)
            pool = self.reader.get_learned_word_pool(category)
            try:
                selection = self.stats.selection_stats()
            except Exception:
                return self.reader.get_learned_words(limit, category)
            return select_words(pool, selection, limit)

    def current_pool(self) -> list[dict[str, Any]]:
        with self.lock:
            return self.reader.get_learned_word_pool("all") if self.reader else []

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
            status["target_path"] = sync_target_path(self)
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
                "target_path": sync_target_path(self),
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
                status["copied_files"] = copy_collection_group(source, status["target_path"])
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


def sync_configured() -> bool:
    return bool(os.environ.get("ANKI_SYNC_SOURCE_DIR", "").strip() and os.environ.get("ANKI_SYNC_TARGET", "").strip())


def sync_target_path(state: AppState) -> str:
    return os.environ.get("ANKI_SYNC_TARGET", "").strip() or state.config.anki.db_path


def latest_collection(source_dir: str) -> str:
    root = Path(source_dir.strip())
    if not source_dir.strip():
        raise ValueError("ANKI_SYNC_SOURCE_DIR is not configured")
    candidates = [path for path in root.rglob("collection.anki2") if path.is_file() and path.stat().st_size > 0]
    if not candidates:
        raise FileNotFoundError(f"no collection.anki2 found under {root}")
    return str(max(candidates, key=lambda path: path.stat().st_mtime))


def _group_stats(source: str) -> list[tuple[str, int, float]]:
    result = []
    for suffix in ("", "-wal", "-shm"):
        path = Path(source + suffix)
        if not path.exists():
            if suffix:
                continue
            raise FileNotFoundError(path)
        stat = path.stat()
        result.append((str(path), stat.st_size, stat.st_mtime_ns))
    return result


def copy_collection_group(source: str, target: str) -> list[str]:
    if not target.strip():
        raise ValueError("ANKI_SYNC_TARGET is not configured")
    first = _group_stats(source)
    stable_seconds = _env_seconds("ANKI_SYNC_STABLE_SECONDS", 2, 0)
    if stable_seconds:
        time.sleep(stable_seconds)
    if first != _group_stats(source):
        raise RuntimeError("Anki collection files are changing; try again later")
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for suffix in ("", "-wal", "-shm"):
        src = Path(source + suffix)
        dst = Path(str(target_path) + suffix)
        if not src.exists():
            if suffix:
                dst.unlink(missing_ok=True)
                continue
            raise FileNotFoundError(src)
        tmp = Path(str(dst) + ".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
        copied.append(dst.name)
    return copied


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


def _unpracticed_details(words: list[dict[str, Any]], selection: dict[str, dict[str, Any]], limit: int = 0) -> list[dict[str, Any]]:
    practiced = {normalize_word(key) for key in selection}
    result = []
    seen: set[str] = set()
    for word in words:
        key = normalize_word(word.get("word", ""))
        if not key or key in seen or key in practiced:
            continue
        seen.add(key)
        result.append({"word": word["word"], "chinese_meaning": word.get("chinese_meaning", ""), "total_attempts": 0, "correct_attempts": 0, "incorrect_attempts": 0, "accuracy": 0, "average_time": 0})
        if limit and len(result) >= limit:
            break
    return result


def create_app(config: Config | None = None) -> Flask:
    cfg = config or load_config()
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(root / "frontend" / "templates"), static_folder=None)
    # Vue uses {{ }} bindings. Jinja still renders the pages, but uses a
    # separate delimiter so those client-side bindings remain untouched.
    app.jinja_env.variable_start_string = "[["
    app.jinja_env.variable_end_string = "]]"
    state = AppState(cfg)
    app.extensions["typing_practice_state"] = state

    @app.teardown_appcontext
    def _close_on_shutdown(_exc):
        # Flask invokes teardown for every request; the shared state must stay
        # alive, so resources are closed only by the process shutdown path.
        return None

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
        return render_template("index.html", page_title="IELTS 打字练习")

    @app.route("/stats.html")
    def stats_page():
        return render_template("stats.html", page_title="学习统计 - IELTS 打字练习")

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

    @app.route("/api/sync/status")
    def sync_status_endpoint():
        return jsonify(success=True, data=state.sync_status())

    @app.route("/api/sync/now", methods=["POST"])
    def sync_now_endpoint():
        status, error = state.sync_now()
        status["history"] = state.stats.list_sync_history(50)
        return (jsonify(success=False, error=error, data=status), 400) if error else jsonify(success=True, data=status)

    @app.route("/api/stats/sessions", methods=["POST"])
    def save_session():
        payload = request.get_json(silent=True) or {}
        try:
            state.stats.save_session(payload)
            return jsonify(success=True, message="Session saved successfully", session_id=payload.get("session_id"))
        except (TypeError, ValueError, KeyError) as exc:
            return jsonify(success=False, error=str(exc)), 400

    @app.route("/api/stats/heatmap")
    def heatmap():
        return _stats_response(lambda: state.stats.heatmap(request.args.get("start_date", ""), request.args.get("end_date", "")))

    @app.route("/api/stats/accuracy-trend")
    def accuracy_trend():
        return _stats_response(lambda: state.stats.accuracy_trend(_int_query("days", 30)))

    @app.route("/api/stats/mastery-distribution")
    def mastery_distribution():
        def fetch():
            data = state.stats.mastery_distribution()
            data["new"] = len(_unpracticed_details(state.current_pool(), state.stats.selection_stats()))
            return data
        return _stats_response(fetch)

    @app.route("/api/stats/mastery-words")
    def mastery_words():
        level = request.args.get("level", "")
        if level != "new":
            return _stats_response(lambda: state.stats.mastery_words(level, _int_query("limit", 200)))
        return _stats_response(lambda: _unpracticed_details(state.current_pool(), state.stats.selection_stats(), min(_int_query("limit", 200), 1000)))

    @app.route("/api/stats/speed-trend")
    def speed_trend():
        return _stats_response(lambda: state.stats.speed_trend(_int_query("days", 30)))

    @app.route("/api/stats/daily-duration")
    def daily_duration():
        return _stats_response(lambda: state.stats.daily_duration(_int_query("days", 30)))

    @app.route("/api/stats/streak")
    def streak():
        return _stats_response(state.stats.streak)

    @app.route("/api/stats/error-types")
    def error_types():
        return _stats_response(state.stats.error_types)

    @app.route("/api/stats/error-type-words")
    def error_type_words():
        return _stats_response(lambda: state.stats.error_type_words(request.args.get("type", "spelling"), _int_query("limit", 200)))

    @app.route("/api/stats/milestones")
    def milestones():
        return _stats_response(state.stats.milestones)

    @app.route("/api/stats/overview")
    def overview():
        return _stats_response(state.stats.overview)

    @app.errorhandler(404)
    def not_found(_error):
        if request.method == "GET" and not request.path.startswith("/api/"):
            return render_template("index.html", page_title="IELTS 打字练习")
        return jsonify(success=False, error="not found"), 404

    if sync_configured() and not app.testing:
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
    application.run(host=cfg.server.host, port=cfg.server.port)

