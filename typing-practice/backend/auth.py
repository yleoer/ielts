"""Bearer-token access for desktop clients."""

from __future__ import annotations

import hmac

from flask import Flask, jsonify, request


def install_token_gate(app: Flask, token: str) -> None:
    if not token:
        return
    expected = f"Bearer {token}".encode("utf-8")

    @app.before_request
    def require_token():
        if request.path == "/api/health":
            return None
        supplied = request.headers.get("Authorization", "").encode("utf-8")
        if hmac.compare_digest(supplied, expected):
            return None
        return jsonify(success=False, error="访问令牌无效", code="authentication_required"), 401

    @app.after_request
    def prevent_caching(response):
        response.headers["Cache-Control"] = "no-store"
        return response
