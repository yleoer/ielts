from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app import create_app
from auth import COOKIE_NAME
from config import load_config
from test_app import make_config


class AccessGateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = replace(make_config(Path(temporary.name)), access_password="测试-password")
        self.app = self.make_app()
        self.client = self.app.test_client()

    def make_app(self, password=None):
        config = self.config if password is None else replace(self.config, access_password=password)
        app = create_app(config)
        app.testing = True
        self.addCleanup(app.extensions["typing_practice_state"].close)
        return app

    def login(self, client=None, target="/"):
        return (client or self.client).post(
            "/login", query_string={"next": target}, data={"password": self.config.access_password},
        )

    def test_pages_and_business_apis_require_authentication(self):
        for path in ("/", "/index.html", "/stats.html", "/unknown-page"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertTrue(response.location.startswith("/login?next="), path)
        for path in ("/api/words", "/api/config", "/api/stats/overview", "/api/sync/status"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401, path)
            self.assertEqual(response.json["code"], "authentication_required")
        for path in ("/api/stats/sessions", "/api/sync/now"):
            self.assertEqual(self.client.post(path, json={}).status_code, 401)
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_login_page_and_wrong_password(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'type="submit"', response.data)
        self.assertIn('进入'.encode(), response.data)
        self.assertNotIn('IELTS'.encode(), response.data)
        self.assertNotIn(b'placeholder=', response.data)
        self.assertNotIn(self.config.access_password.encode(), response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        for password in ("", "incorrect", "错误密码"):
            response = self.client.post("/login", data={"password": password})
            self.assertEqual(response.status_code, 401)
            self.assertIn(b'aria-invalid="true"', response.data)
            self.assertNotIn('密码不正确'.encode(), response.data)
            self.assertIsNone(self.client.get_cookie(COOKIE_NAME))

    def test_success_remembers_browser_and_returns_to_requested_page(self):
        response = self.login(target="/stats.html")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, "/stats.html")
        cookie = response.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Max-Age=315360000", cookie)
        self.assertNotIn(self.config.access_password, cookie)
        for path in ("/", "/stats.html", "/api/config", "/api/stats/overview"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/login").status_code, 302)
        self.assertEqual(self.app.test_client().get("/").status_code, 302)

    def test_secure_cookie_when_served_over_https(self):
        response = self.client.post("/login", data={"password": self.config.access_password}, base_url="https://localhost")
        self.assertIn("Secure;", response.headers["Set-Cookie"])

    def test_credential_survives_restart_but_password_change_invalidates_it(self):
        self.login()
        value = self.client.get_cookie(COOKIE_NAME).value
        restarted = self.make_app().test_client()
        restarted.set_cookie(COOKIE_NAME, value)
        self.assertEqual(restarted.get("/api/config").status_code, 200)
        changed = self.make_app("different-password").test_client()
        changed.set_cookie(COOKIE_NAME, value)
        self.assertEqual(changed.get("/api/config").status_code, 401)

    def test_forged_cookie_and_cleared_browser_require_password(self):
        self.client.set_cookie(COOKIE_NAME, "forged")
        self.assertEqual(self.client.get("/api/config").status_code, 401)
        self.login()
        self.client.delete_cookie(COOKIE_NAME)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_login_cannot_redirect_to_another_site(self):
        for target in ("https://example.com", "//example.com", "/\\example.com", "/login", "//[invalid"):
            client = self.app.test_client()
            response = self.login(client, target)
            self.assertEqual(response.location, "/", target)

    def test_password_can_be_disabled_and_loaded_from_environment(self):
        self.assertEqual(self.make_app("").test_client().get("/").status_code, 200)
        with patch.dict("os.environ", {"ACCESS_PASSWORD": "from-environment"}):
            self.assertEqual(load_config().access_password, "from-environment")


if __name__ == "__main__":
    unittest.main()
