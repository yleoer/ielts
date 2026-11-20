"""Run the desktop smoke flows against the real Tauri window on a virtual display (Linux only).

    python3 desktop/e2e/run.py

Builds the pages and the debug app, then starts, all disposable and isolated from real data:
Xvfb, a private D-Bus session (keeps the test tray icon off the desktop panel), a mock sync
server and tauri-driver. Needs `xvfb`, `webkitgtk-webdriver`, `dbus` and
`cargo install tauri-driver --locked`; only the Python standard library is used.
Screenshots go to desktop/target/e2e/.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flows  # noqa: E402


def word(index: int, text: str, senses: list[tuple[str, str]], cefr: str = 'A2', category: str = '生活') -> dict:
    """One learned Word Atlas entry in the server snapshot format."""
    return {'id': 1000 + index, 'source_id': text, 'word': text, 'chinese_meaning': senses[0][1],
            'chinese_senses': [{'part_of_speech': pos, 'chinese_meaning': meaning} for pos, meaning in senses],
            'part_of_speech': senses[0][0], 'category': category, 'cefr': cefr, 'learned': True, 'illustration_file': ''}


SMOKE_WORDS = [word(i, text, senses) for i, (text, senses) in enumerate([
    ('apple', [('n.', '苹果')]), ('bridge', [('n.', '桥'), ('v.', '弥合')]),
    ('garden', [('n.', '花园'), ('v.', '从事园艺')]), ('river', [('n.', '河流'), ('n.', '大量涌流')]),
    ('window', [('n.', '窗户'), ('n.', '（计算机）窗口')]),
])]


class MockServer:
    """The two calls of the sync server (`server/`): the vocabulary snapshot and the answer log."""

    def __init__(self, words: list[dict], log: list[dict] | None = None):
        self.words = list(words)
        self.log = list(log or [])
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def reply(self, data, status=200):
                body = json.dumps({'success': status == 200, 'data': data}, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path != '/api/vocab':
                    return self.reply({}, 404)
                self.reply({'format': 1, 'words': mock.words, 'sync_history': [],
                            'last_anki_sync_at': '2026-01-01T00:00:00.000000Z'})

            def do_POST(self):
                if self.path != '/api/sync':
                    return self.reply({}, 404)
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                known = {row['attempt_id'] for row in mock.log}
                fresh = [item for item in request['attempts'] if item['attempt_id'] not in known]
                mock.log.extend(fresh)
                cursor = request['cursor']
                page = mock.log[cursor:cursor + 500]
                self.reply({'accepted': len(fresh), 'attempts': page, 'next_cursor': cursor + len(page),
                            'more': cursor + len(page) < len(mock.log)})

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def add_word(self, text, senses):
        """Simulates a word learned in Anki; the app picks it up on its next background sync."""
        self.words.append(word(len(self.words), text, senses))

    def answer_elsewhere(self, text):
        """Simulates another computer answering `text` correctly (Good) just now."""
        entry = next(item for item in self.words if item['word'] == text)
        self.log.append({'attempt_id': f'other-device-{text}', 'word_key': f'word-atlas:{text}', 'word': text,
                         'chinese_meaning': entry['chinese_meaning'], 'category': entry['category'], 'user_input': text,
                         'is_correct': True, 'rating': 3, 'reviewed_at': datetime.now(timezone.utc).isoformat(),
                         'duration_ms': 8000, 'first_input_ms': 1000})


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def start(command, **kwargs) -> subprocess.Popen:
    # A new session per process so cleanup also reaches tauri-driver's WebKitWebDriver and the app.
    return subprocess.Popen(command, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)


def stop(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass


@contextlib.contextmanager
def environment(mock: MockServer):
    """Builds the app and yields (tauri-driver URL, app path) on a virtual display; cleans up afterwards."""
    driver = shutil.which('tauri-driver') or str(Path.home() / '.cargo/bin/tauri-driver')
    missing = [name for name, path in (('Xvfb', shutil.which('Xvfb')), ('WebKitWebDriver', shutil.which('WebKitWebDriver')),
               ('dbus-run-session', shutil.which('dbus-run-session')), ('tauri-driver', Path(driver).exists() and driver)) if not path]
    if missing:
        print('missing: ' + ', '.join(missing))
        print('install: sudo apt install xvfb webkitgtk-webdriver dbus && cargo install tauri-driver --locked')
        sys.exit(2)
    subprocess.run([sys.executable, str(DESKTOP / 'scripts/build_frontend.py')], check=True)
    subprocess.run(['cargo', 'build', '-p', 'cijian'], cwd=DESKTOP, check=True)

    processes = []
    with tempfile.TemporaryDirectory(prefix='cijian-e2e-') as data:
        try:
            read, write = os.pipe()
            processes.append(start(['Xvfb', '-displayfd', str(write), '-screen', '0', '1280x900x24', '-nolisten', 'tcp'],
                                   pass_fds=(write,)))
            os.close(write)
            with os.fdopen(read) as pipe:
                display = ':' + pipe.readline().strip()
            port = free_port()
            # WebKit keeps localStorage and its cache under the XDG directories, not CIJIAN_DATA_DIR;
            # point them at the temporary directory so runs start clean and never touch the real app.
            env = {**os.environ, 'DISPLAY': display, 'CIJIAN_DATA_DIR': data, 'CIJIAN_SERVER_URL': mock.url,
                   'CIJIAN_SERVER_TOKEN': 'e2e', 'CIJIAN_SYNC_MINUTES': '1', 'CIJIAN_OPTIMIZATION': '0',
                   **{name: f'{data}/{name.lower()}' for name in ('XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME')}}
            processes.append(start(['dbus-run-session', '--', driver, '--port', str(port), '--native-port', str(free_port())], env=env))
            base = f'http://127.0.0.1:{port}'
            for _ in range(50):
                try:
                    with urllib.request.urlopen(base + '/status', timeout=2) as response:
                        if json.load(response)['value']['ready']:
                            break
                except OSError:
                    time.sleep(0.2)
            yield base, str(DESKTOP / 'target/debug/cijian')
        finally:
            for process in reversed(processes):
                stop(process)
            mock.server.shutdown()


def main() -> int:
    shots = DESKTOP / 'target/e2e'
    shots.mkdir(parents=True, exist_ok=True)
    for old in shots.glob('*.png'):
        old.unlink()
    mock = MockServer(SMOKE_WORDS)
    with environment(mock) as (base, app):
        return flows.run(base, app, mock, shots)


if __name__ == '__main__':
    sys.exit(main())
