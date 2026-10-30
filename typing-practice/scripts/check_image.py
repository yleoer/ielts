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
        break
    except (URLError, TimeoutError):
        if time.monotonic() >= deadline:
            raise
        time.sleep(1)
print("PASS /api/health", flush=True)

for path, content_type in (
    ("/", "text/html"),
    ("/stats.html", "text/html"),
    ("/assets/style.css", "text/css"),
    ("/src/app.js", "javascript"),
    ("/src/stats.js", "javascript"),
):
    with urlopen(base + path, timeout=5) as response:
        assert response.status == 200, (path, response.status)
        assert content_type in response.headers.get("Content-Type", ""), path
        assert response.read(), path
    print("PASS " + path, flush=True)

for path in (
    "/api/config",
    "/api/stats/overview",
    "/api/stats/monthly-activity",
    "/api/memory/optimization",
):
    with urlopen(base + path, timeout=5) as response:
        payload = json.load(response)
    assert payload.get("success") is True, (path, payload)
    if path == "/api/config":
        assert payload.get("anki_available") is False, payload
    print("PASS " + path, flush=True)
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
            "--env", "ACCESS_PASSWORD=",
            "--env", "ANKI_DB_PATH=/tmp/image-check/missing.anki2",
            "--env", "STATS_DB_PATH=/tmp/image-check/stats.db",
            "--env", "ANKI_SYNC_SOURCE_DIR=", "--env", "ANKI_SYNC_TARGET=",
            "--env", "FSRS_AUTO_OPTIMIZE=false", "--env", "FSRS_PARAMETERS_PATH=",
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
