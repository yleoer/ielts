"""Check a built image with its default command in a disposable Docker container.

Only the Python standard library and a working Docker CLI are needed on the host.
This script also works over SSH: python3 - IMAGE --pull < check_image.py.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from uuid import uuid4


# Run inside the container so neither a published port nor external networking
# is needed. The application must start through the image's own CMD/ENTRYPOINT.
PROBE = r"""
import json
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

base = "http://127.0.0.1:8080"
deadline = time.monotonic() + float(sys.argv[1])
while True:
    try:
        with urlopen(base + "/api/health", timeout=2) as response:
            health = json.load(response)
        assert health.get("success") is True and health.get("status") == "ok", health
        assert response.headers.get("Server") == "waitress", response.headers.get("Server")
        break
    except (URLError, TimeoutError):
        if time.monotonic() >= deadline:
            raise
        time.sleep(1)
print("PASS Waitress /api/health", flush=True)

from urllib.error import HTTPError
from urllib.request import Request

# Without an Anki database the vocabulary is unavailable, but the log works.
try:
    urlopen(base + "/api/vocab", timeout=5)
    raise AssertionError("/api/vocab should be unavailable without Anki")
except HTTPError as error:
    assert error.code == 503, error.code
print("PASS /api/vocab 503 without Anki", flush=True)

# Verify the packaged reader against an isolated modern Anki schema.
import sqlite3
from pathlib import Path
from anki import AnkiReader, WORD_ATLAS_FIELDS
collection = Path("/tmp/image-check/variants.anki2")
with sqlite3.connect(collection) as db:
    db.executescript("CREATE TABLE decks(id INTEGER PRIMARY KEY,name TEXT);"
                     "CREATE TABLE notes(id INTEGER PRIMARY KEY,flds TEXT,tags TEXT);"
                     "CREATE TABLE cards(id INTEGER PRIMARY KEY,nid INTEGER,did INTEGER,type INTEGER,queue INTEGER);"
                     "INSERT INTO decks VALUES(1,'Word Atlas');"
                     "INSERT INTO cards VALUES(1,101,1,2,-1),(2,102,1,0,0);")
    for note_id, word, tags in ((101, "aeroplane", " word_atlas::excluded word_atlas::canonical::airplane "),
                                (102, "airplane", "")):
        fields = {"Word": word, "SourceId": word, "MeaningZH": "飞机"}
        db.execute("INSERT INTO notes VALUES(?,?,?)", (note_id, "\x1f".join(fields.get(k, "") for k in WORD_ATLAS_FIELDS), tags))
reader = AnkiReader(str(collection), "Word Atlas", 1)
try:
    assert [(w["source_id"], w["learned"]) for w in reader.snapshot()] == [("airplane", True)]
finally:
    reader.close()
print("PASS excluded Anki variants and canonical learned state", flush=True)

attempt = {"attempt_id": "image-check", "word_key": "word-atlas:check", "word": "check", "chinese_meaning": "检查",
           "category": "", "user_input": "check", "is_correct": True, "rating": 3,
           "reviewed_at": "2026-01-01T00:00:00Z", "duration_ms": 7000, "first_input_ms": None}
for expected in (1, 0):
    body = json.dumps({"device_id": "image-check", "cursor": 0, "attempts": [attempt]}).encode()
    request = Request(base + "/api/sync", data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        data = json.load(response)["data"]
    assert data["accepted"] == expected and [row["attempt_id"] for row in data["attempts"]] == ["image-check"], data
print("PASS /api/sync", flush=True)

for path in ("/", "/stats.html", "/api/stats/overview"):
    try:
        urlopen(base + path, timeout=5)
        raise AssertionError(path + " should be removed")
    except HTTPError as error:
        assert error.code == 404, (path, error.code)
print("PASS retired pages and APIs return 404", flush=True)

import importlib.util
for module in ("fsrs", "torch"):
    assert importlib.util.find_spec(module) is None, module + " should not be installed"
print("PASS no fsrs / torch in the image", flush=True)
"""


def docker(*arguments: str, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *arguments], check=True, timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="Image tag or immutable repository@sha256:digest")
    parser.add_argument("--platform", choices=("linux/amd64", "linux/arm64"))
    parser.add_argument("--pull", action="store_true", help="Pull the image before checking")
    parser.add_argument("--timeout", type=int, default=60, help="Startup timeout in seconds")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if not shutil.which("docker"):
        parser.exit(1, "Docker CLI is missing. Run this check on a Docker host or via SSH.\n")

    platform = ["--platform", args.platform] if args.platform else []
    name = "typing-practice-check-" + uuid4().hex[:12]
    created = False
    result = 0
    try:
        if args.pull:
            docker("pull", *platform, args.image, timeout=600)
        # Mark ownership before run: a failed start may still leave a container.
        created = True
        docker(
            "run", "--detach", "--name", name, "--network", "none",
            "--pull", "never", *platform,
            "--env", "SERVER_HOST=127.0.0.1", "--env", "SERVER_PORT=8080",
            "--env", "ACCESS_TOKEN=", "--env", "ACCESS_PASSWORD=",
            "--env", "ANKI_DB_PATH=/tmp/image-check/missing.anki2",
            "--env", "STATS_DB_PATH=/tmp/image-check/stats.db",
            "--env", "ANKI_SYNC_SOURCE_DIR=", "--env", "ANKI_SYNC_TARGET=",
            args.image,
        )
        docker("exec", name, "python", "-c", PROBE, str(args.timeout), timeout=args.timeout + 60)
        print("Image check passed: " + args.image, flush=True)
    except (OSError, subprocess.SubprocessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            detail = "docker " + exc.cmd[1] + " exited with status " + str(exc.returncode)
        elif isinstance(exc, subprocess.TimeoutExpired):
            detail = "docker " + exc.cmd[1] + " timed out"
        else:
            detail = str(exc)
        print("Image check failed: " + detail, file=sys.stderr)
        if created:
            try:
                docker("logs", "--tail", "100", name, timeout=15)
            except (OSError, subprocess.SubprocessError) as log_error:
                print("Could not read container logs: " + str(log_error), file=sys.stderr)
        result = 1
    finally:
        if created:
            try:
                docker("rm", "--force", name, timeout=30)
            except (OSError, subprocess.SubprocessError) as cleanup_error:
                print("Could not remove " + name + ": " + str(cleanup_error), file=sys.stderr)
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
