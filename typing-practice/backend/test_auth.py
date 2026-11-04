from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from config import load_config
from test_app import make_config


class TokenTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config = make_config(Path(temporary.name))
        config.access_token = "测试-token"
        self.app = create_app(config, start_background_tasks=False)
        self.addCleanup(self.app.extensions["cijian_state"].close)
        self.client = self.app.test_client()

    def test_health_is_open_but_vocabulary_and_sync_need_the_token(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "测试-token"}):
            for method, path in (("get", "/api/vocab"), ("post", "/api/sync")):
                response = getattr(self.client, method)(path, headers=headers, json={"device_id": "d"})
                self.assertEqual(response.status_code, 401, (path, headers))
                self.assertEqual(response.json["code"], "authentication_required")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        ok = self.client.post("/api/sync", headers={"Authorization": "Bearer 测试-token"}, json={"device_id": "d"})
        self.assertEqual(ok.status_code, 200)

    def test_token_comes_from_environment_and_old_password_still_protects(self):
        with patch("config.load_dotenv"), patch("config.default_anki_db_path", return_value=""):
            for env, expected in (({}, ""), ({"ACCESS_PASSWORD": "old"}, "old"),
                                  ({"ACCESS_TOKEN": " new ", "ACCESS_PASSWORD": "old"}, "new")):
                with self.subTest(env=env), patch.dict("os.environ", env, clear=True):
                    self.assertEqual(load_config().access_token, expected)


if __name__ == "__main__":
    unittest.main()
