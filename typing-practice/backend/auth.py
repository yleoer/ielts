"""Shared-password access with a persistent browser credential."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, redirect, render_template, request, url_for


COOKIE_NAME = "typing_practice_access"
COOKIE_MAX_AGE = 10 * 365 * 24 * 60 * 60


def install_access_gate(app: Flask, password: str, stats_path: str) -> None:
    if not password:
        return

    # Keep credentials valid across process/container restarts. The stats
    # directory is already persistent in both local and Docker deployments.
    key_path = Path(stats_path).parent / ".access-secret"
    try:
        with key_path.open("xb") as handle:
            handle.write(secrets.token_bytes(32))
        key_path.chmod(0o600)
    except FileExistsError:
        pass
    secret = key_path.read_bytes()
    if len(secret) != 32:
        raise ValueError("Invalid access secret file")
    credential = hmac.new(secret, password.encode("utf-8"), hashlib.sha256).hexdigest()

    def authenticated() -> bool:
        supplied = request.cookies.get(COOKIE_NAME, "")
        return hmac.compare_digest(supplied.encode("utf-8"), credential.encode("ascii"))

    def destination() -> str:
        target = request.args.get("next", "/")
        try:
            parsed = urlsplit(target)
        except ValueError:
            return "/"
        if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//") or "\\" in target:
            return "/"
        if parsed.path == "/login":
            return "/"
        return target

    @app.before_request
    def require_access():
        if request.path == "/api/health" or request.endpoint == "login":
            return None
        if request.path.startswith(("/assets/", "/src/")):
            return None
        if authenticated():
            return None
        if request.path.startswith("/api/"):
            return jsonify(success=False, error="请先输入访问密码", code="authentication_required"), 401
        target = request.full_path.rstrip("?")
        return redirect(url_for("login", next=target))

    @app.after_request
    def prevent_private_caching(response):
        if (request.endpoint == "word_media" and response.status_code in {200, 304}
                and response.cache_control.private and response.cache_control.max_age):
            return response
        if not request.path.startswith(("/assets/", "/src/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if authenticated():
            return redirect(destination())
        error = ""
        if request.method == "POST":
            supplied = request.form.get("password", "")
            if hmac.compare_digest(supplied.encode("utf-8"), password.encode("utf-8")):
                response = redirect(destination(), code=303)
                response.set_cookie(
                    COOKIE_NAME, credential, max_age=COOKIE_MAX_AGE,
                    httponly=True, secure=request.is_secure, samesite="Strict", path="/",
                )
                return response
            error = "密码不正确，请重试"
        return render_template("login.html", error=error), 401 if error else 200
