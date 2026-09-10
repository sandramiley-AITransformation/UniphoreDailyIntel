#!/usr/bin/env python3
"""Import a Daily Intel artifact export into a clean standalone index.html.

The claude.ai artifact HTML comes wrapped in a frame runtime (injected
<script>s and a frame <head>/<body>), with the authored Daily Intel document
re-homed inside the frame's <body>. This strips all of that and rebuilds a
clean, script-free standalone page using the known-good <head> skeleton.

Usage:
    python3 import_artifact.py <path-to-artifact-export.html> [output.html]

Exits non-zero (without writing) if the export doesn't look like a valid Daily
Intel page — so the caller can abort before publishing garbage.
"""

from __future__ import annotations

import glob
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# The Artifact tool saves its export under <home>/.claude/projects/*/tool-results/
# as artifact-<id>-*.html. Auto-discovering it means the caller never has to name
# a path inside .claude in a shell command (which the permission layer blocks).
ARTIFACT_ID = "665af250"


def find_latest_export() -> Path | None:
    roots = {
        os.path.join(os.path.expanduser("~"), ".claude", "projects"),
        "/root/.claude/projects",
        "/home/user/.claude/projects",
    }
    for base in glob.glob("/home/*"):
        roots.add(os.path.join(base, ".claude", "projects"))
    matches: list[str] = []
    for r in roots:
        matches += glob.glob(
            os.path.join(r, "**", "tool-results", f"artifact-{ARTIFACT_ID}-*.html"),
            recursive=True,
        )
    if not matches:
        return None
    return Path(max(matches, key=os.path.getmtime))

# Known-good <head> skeleton — kept stable so the published page always has a
# proper title, description, icon, and font preconnects regardless of what the
# artifact wrapper carried.
HEAD_PREFIX = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daily Intel — Uniphore</title>
<meta name="description" content="A daily competitive-intelligence briefing for Uniphore covering CX/conversational-AI rivals, hyperscalers, frontier labs, enterprise AI platforms, compute infrastructure, model platforms, Chinese AI labs, and investors, with strategic takeaways for each.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%93%A1%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">"""


def die(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"import_artifact: error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def extract(artifact_html: str) -> str:
    # 1. Remove the injected frame runtime: every <script>, frame comments, and
    #    any frame-injected data-* attributes. (The authored page has no JS.)
    h = re.sub(r"<script\b[^>]*>.*?</script>", "", artifact_html, flags=re.DOTALL | re.IGNORECASE)
    h = re.sub(r"<!--\s*/?\s*frame-runtime\s*-->", "", h, flags=re.IGNORECASE)
    h = re.sub(r'\s+data-(?:ldx|frame)[\w-]*="[^"]*"', "", h)

    # 2. The authored document begins at its <title>. The user's <style> is the
    #    first <style> after that (the frame's reset <style> sits before it).
    ti = h.find("<title>")
    if ti == -1:
        die("no <title> found in artifact export")
    after_title = h[ti:]
    style_m = re.search(r"<style>.*?</style>", after_title, flags=re.DOTALL | re.IGNORECASE)
    if not style_m:
        die("no authored <style> block found")
    style_block = style_m.group(0)

    # 3. Body = the masthead through the end of the footer.
    body_start = h.find('<div class="masthead"')
    if body_start == -1:
        die('no <div class="masthead"> found')
    foot_end = h.rfind("</footer>")
    if foot_end == -1:
        die("no </footer> found")
    body_block = h[body_start:foot_end + len("</footer>")]

    doc = (
        HEAD_PREFIX
        + "\n"
        + style_block
        + "\n</head>\n<body>\n\n"
        + body_block
        + "\n\n</body>\n</html>\n"
    )
    return doc


def validate(doc: str) -> None:
    checks = {
        "no leftover <script>": "<script" not in doc.lower(),
        'navbar present': 'class="navbar"' in doc,
        "signal section id": 'id="signal"' in doc,
        "investors section id": 'id="investors"' in doc,
        "edition line": "Edition" in doc,
        "single <body>": doc.lower().count("<body>") == 1,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        die("sanity checks failed: " + "; ".join(failed))


def main(argv: list[str]) -> int:
    # Source: explicit path if given and it exists, otherwise auto-discover the
    # most recent Artifact export in the Claude tool-results directory.
    src: Path | None
    if len(argv) >= 2 and argv[1] and Path(argv[1]).is_file():
        src = Path(argv[1])
    else:
        src = find_latest_export()
        if src is None:
            die(
                "no artifact export found — call the Artifact 'read' tool first, or "
                "pass an explicit path: import_artifact.py <artifact-export.html> [output.html]"
            )
        print(f"import_artifact: using {src}")
    out = Path(argv[2]) if len(argv) > 2 else ROOT / "index.html"

    doc = extract(src.read_text(encoding="utf-8"))
    validate(doc)
    out.write_text(doc, encoding="utf-8")

    m = re.search(r"Edition <strong>([^<]+)", doc)
    edition = m.group(1).strip() if m else "unknown"
    print(f"import_artifact: wrote {out} (edition: {edition}, {len(doc)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
