"""Render typing-desktop/frontend into typing-desktop/dist.

CDN scripts in the templates are replaced with the pinned copies in
typing-desktop/vendor so the app works offline. Run from the repository root:

    .venv/Scripts/python.exe typing-desktop/scripts/build_frontend.py
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "typing-desktop"
FRONTEND = DESKTOP / "frontend"
DIST = DESKTOP / "dist"
PAGES = {"index.html": "词间 · 练习", "stats.html": "词间 · 统计"}
CDN = re.compile(r"https://cdn\.jsdelivr\.net/npm/[^/\"]+/dist/([^\"]+)")


def render() -> dict[str, str]:
    # Jinja uses [[ ]] so Vue keeps {{ }}.
    env = Environment(loader=FileSystemLoader(FRONTEND / "templates"),
                      variable_start_string="[[", variable_end_string="]]", autoescape=True)
    pages = {}
    for name, title in PAGES.items():
        html = CDN.sub(lambda m: f"/vendor/{m.group(1)}", env.get_template(name).render(page_title=title))
        missing = [path for path in re.findall(r"/vendor/([^\"?]+)", html) if not (DESKTOP / "vendor" / path).is_file()]
        external = re.findall(r"(?:src|href)=\"(https?://[^\"]+)\"", html)
        if missing or external:
            raise SystemExit(f"{name}: missing vendor {missing}, external {external}")
        pages[name] = html
    return pages


def main() -> None:
    pages = render()
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(FRONTEND / "assets", DIST / "assets")
    shutil.copytree(FRONTEND / "src", DIST / "src", ignore=shutil.ignore_patterns("*.test.*"))
    shutil.copytree(DESKTOP / "vendor", DIST / "vendor", ignore=shutil.ignore_patterns("LICENSE-*"))
    for name, html in pages.items():
        (DIST / name).write_text(html, encoding="utf-8")
    print(f"wrote {DIST.relative_to(ROOT)}: {', '.join(PAGES)}")


if __name__ == "__main__":
    main()
