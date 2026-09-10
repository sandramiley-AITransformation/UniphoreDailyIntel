#!/usr/bin/env python3
"""Generate a readable Markdown archive of the Daily Intel brief.

Reads index.html (the live edition) and writes a Markdown copy into a
date-ordered location: daily-reports/YYYY/MM/DD/daily-intel-YYYY-MM-DD.md

The edition date is parsed from the masthead ("Edition <strong>Wed, Sep 9
2026</strong>"); if that can't be found it falls back to today's date.

Pure standard library — no third-party dependencies.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "index.html"
REPORTS_DIR = ROOT / "daily-reports"
CANONICAL_DIR = ROOT / "reports"
CANONICAL_FILE = CANONICAL_DIR / "uniphore-daily-intel.html"
# public/ is the ONLY folder published to GitHub Pages (see
# .github/workflows/pages.yml). index.html here is the latest edition.
PUBLIC_DIR = ROOT / "public"
PUBLIC_FILE = PUBLIC_DIR / "index.html"

# Tags we drop entirely, contents and all.
SKIP_TAGS = {"head", "style", "script", "nav", "link", "meta", "title"}

BLOCK_TAGS = {
    "div", "section", "main", "header", "footer", "article",
    "ul", "ol", "li", "p", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
HEADING_LEVEL = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

# Spans/divs whose class should be rendered as a bold inline label.
BOLD_LABEL_CLASSES = {
    "label", "card-meta", "angle-label", "cat-pill", "theme-tag",
}
# ...and as italic.
ITALIC_LABEL_CLASSES = {"kicker", "role", "stance", "cat-count", "sub"}
# ...and dropped entirely (redundant with list numbering, etc.).
DROP_CLASSES = {"move-num", "dot"}


class Node:
    __slots__ = ("tag", "attrs", "children", "text")

    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.children = []
        self.text = None  # set for text nodes (tag is None)

    @property
    def classes(self):
        return set((self.attrs.get("class") or "").split())


class TreeBuilder(HTMLParser):
    """Builds a lightweight DOM tree, skipping SKIP_TAGS subtrees."""

    VOID = {"br", "img", "hr", "meta", "link", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]
        self.skip_depth = 0
        self.skip_tag = None

    def handle_starttag(self, tag, attrs):
        if self.skip_depth:
            if tag == self.skip_tag and tag not in self.VOID:
                self.skip_depth += 1
            return
        if tag in SKIP_TAGS:
            if tag not in self.VOID:
                self.skip_depth = 1
                self.skip_tag = tag
            return
        if tag in self.VOID:
            self.stack[-1].children.append(Node(tag, attrs))
            return
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        if self.skip_depth:
            return
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        if self.skip_depth:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth == 0:
                    self.skip_tag = None
            return
        if tag in self.VOID:
            return
        # Pop to the matching open tag if present.
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.skip_depth:
            return
        if data:
            tn = Node(None)
            tn.text = data
            self.stack[-1].children.append(tn)


def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def render_inline(node: Node) -> str:
    """Render a node's content as inline Markdown (no block breaks)."""
    parts = []
    for child in node.children:
        if child.tag is None:
            parts.append(collapse_ws(child.text))
        elif child.tag == "br":
            parts.append("  \n")
        elif child.tag in ("b", "strong"):
            inner = render_inline(child).strip()
            parts.append(f"**{inner}**" if inner else "")
        elif child.tag in ("i", "em"):
            inner = render_inline(child).strip()
            parts.append(f"*{inner}*" if inner else "")
        elif child.tag == "a":
            inner = render_inline(child).strip()
            href = child.attrs.get("href", "").strip()
            parts.append(f"[{inner}]({href})" if href else inner)
        elif child.tag in ("span", "small"):
            if child.classes & DROP_CLASSES:
                continue
            inner = render_inline(child).strip()
            if not inner:
                continue
            cls = child.classes
            if cls & BOLD_LABEL_CLASSES:
                parts.append(f"**{inner}**")
            elif cls & ITALIC_LABEL_CLASSES:
                parts.append(f"*{inner}*")
            else:
                parts.append(inner)
        elif child.tag == "blockquote":
            parts.append(render_inline(child).strip())
        else:
            parts.append(render_inline(child))
    return "".join(parts)


def render_block_listsafe(node: Node) -> list[str]:
    """Render a container's children for use inside a list item, demoting any
    headings to bold text so they don't break the list."""
    out: list[str] = []
    for child in node.children:
        if child.tag in HEADING_LEVEL:
            htext = render_inline(child).strip()
            if htext:
                out.append(f"**{htext}**")
        elif child.tag in ("div", "section"):
            out.extend(render_block_listsafe(child))
        elif child.tag is None:
            if child.text and child.text.strip():
                out.append(collapse_ws(child.text).strip())
        elif child.tag in ("span", "b", "strong", "i", "em", "a", "small"):
            wrapper = Node("p")
            wrapper.children = [child]
            t = render_inline(wrapper).strip()
            if t:
                out.append(t)
        else:
            out.extend(render_block(child))
    return out


def render_block(node: Node, ordered_index=None) -> list[str]:
    """Render a node to a list of Markdown block strings."""
    blocks: list[str] = []

    # Leaf-ish blocks that should be rendered as a single inline unit.
    if node.tag in HEADING_LEVEL:
        level = HEADING_LEVEL[node.tag]
        text = render_inline(node).strip()
        if text:
            blocks.append("#" * level + " " + text)
        return blocks

    if node.tag == "p":
        text = render_inline(node).strip()
        if text:
            blocks.append(text)
        return blocks

    if node.tag == "blockquote":
        text = render_inline(node).strip()
        if text:
            quoted = "\n".join("> " + ln for ln in text.split("\n"))
            blocks.append(quoted)
        return blocks

    if node.tag == "li":
        # A li may mix inline content and nested blocks. Render inline lead
        # text plus any nested block children.
        inline_parts = []
        child_blocks = []
        for child in node.children:
            if child.tag is None or child.tag in (
                "span", "b", "strong", "i", "em", "a", "br", "small",
            ):
                inline_parts.append(child)
            elif child.tag in HEADING_LEVEL:
                # Demote headings nested in a list item to bold text so they
                # don't break the surrounding list.
                htext = render_inline(child).strip()
                if htext:
                    child_blocks.append(f"**{htext}**")
            elif child.tag in ("div", "section"):
                # Unwrap containers so their headings are demoted too.
                for blk in render_block_listsafe(child):
                    child_blocks.append(blk)
            else:
                child_blocks.extend(render_block(child))
        wrapper = Node("p")
        wrapper.children = inline_parts
        lead = render_inline(wrapper).strip()
        body_parts = [p for p in [lead] + child_blocks if p]
        joined = "\n\n".join(body_parts)
        marker = f"{ordered_index}. " if ordered_index else "- "
        indent = " " * len(marker)
        lines = joined.split("\n")
        if lines:
            out = marker + lines[0]
            for ln in lines[1:]:
                out += "\n" + (indent + ln if ln else "")
            blocks.append(out)
        return blocks

    if node.tag in ("ul", "ol"):
        items = [c for c in node.children if c.tag == "li"]
        rendered = []
        for i, li in enumerate(items, start=1):
            idx = i if node.tag == "ol" else None
            rendered.extend(render_block(li, ordered_index=idx))
        if rendered:
            blocks.append("\n".join(rendered))
        return blocks

    # Label containers (e.g. <div class="card-meta">) with only inline content:
    # render as a single emphasized line.
    cls = node.classes
    has_block_child = any(
        c.tag in BLOCK_TAGS for c in node.children if c.tag is not None
    )
    if not has_block_child and (cls & BOLD_LABEL_CLASSES or cls & ITALIC_LABEL_CLASSES):
        text = render_inline(node).strip()
        if text:
            mark = "**" if cls & BOLD_LABEL_CLASSES else "*"
            blocks.append(f"{mark}{text}{mark}")
        return blocks

    # Generic container (div, section, main, etc.): recurse, but first emit any
    # inline lead content (e.g. a cat-head with pill + h2 + count).
    inline_buffer = []

    def flush_inline():
        if inline_buffer:
            wrapper = Node("p")
            wrapper.children = list(inline_buffer)
            text = render_inline(wrapper).strip()
            if text:
                blocks.append(text)
            inline_buffer.clear()

    for child in node.children:
        if child.tag is None:
            if child.text and child.text.strip():
                inline_buffer.append(child)
        elif child.tag in ("span", "b", "strong", "i", "em", "a", "small", "br"):
            inline_buffer.append(child)
        else:
            flush_inline()
            blocks.extend(render_block(child))
    flush_inline()
    return blocks


def parse_edition_date(raw_html: str) -> dt.date:
    m = re.search(r"Edition\s*<strong>([^<]+)</strong>", raw_html)
    if m:
        raw = html.unescape(m.group(1)).strip()
        # e.g. "Wed, Sep 9 2026"
        cleaned = re.sub(r"^[A-Za-z]+,\s*", "", raw)  # drop weekday
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                return dt.datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
    return dt.date.today()


def main() -> int:
    if not SOURCE.exists():
        print(f"error: {SOURCE} not found", file=sys.stderr)
        return 1

    raw = SOURCE.read_text(encoding="utf-8")
    edition = parse_edition_date(raw)

    builder = TreeBuilder()
    builder.feed(raw)

    # Render from <body>, falling back to the whole tree.
    body = None
    stack = [builder.root]
    while stack:
        n = stack.pop()
        if n.tag == "body":
            body = n
            break
        stack.extend(c for c in n.children if c.tag is not None)
    target = body or builder.root

    blocks = render_block(target)
    # Tidy: drop empty blocks and collapse runs of blank lines.
    body_md = "\n\n".join(b for b in blocks if b.strip())
    body_md = re.sub(r"\n{3,}", "\n\n", body_md).strip()

    iso = edition.isoformat()
    front_matter = (
        f"> Archived from the live Daily Intel edition on "
        f"{edition.strftime('%A, %B %-d, %Y')}.\n"
        f"> Source: index.html · generated by generate_report.py\n"
    )
    doc = f"{front_matter}\n{body_md}\n"

    out_dir = REPORTS_DIR / f"{edition.year:04d}" / f"{edition.month:02d}" / f"{edition.day:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_file = out_dir / f"daily-intel-{iso}.md"
    md_file.write_text(doc, encoding="utf-8")

    # ---- HTML edition ----
    # We publish the hero page (index.html) VERBATIM so the styled masthead,
    # sticky nav (native #anchor links, no JS), category pills, cards, and
    # "Uniphore angle" boxes are reproduced exactly. The only change is to
    # stamp the edition date into <title> so tabs/bookmarks are distinct.
    human_edition = edition.strftime("%A, %B %-d, %Y")
    page = re.sub(
        r"<title>.*?</title>",
        f"<title>Daily Intel — Uniphore · {human_edition}</title>",
        raw,
        count=1,
        flags=re.DOTALL,
    )

    html_file = out_dir / f"daily-intel-{iso}.html"
    html_file.write_text(page, encoding="utf-8")

    # ---- Canonical permalink: always the latest edition (in-repo, private) ----
    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
    CANONICAL_FILE.write_text(page, encoding="utf-8")

    # ---- Public copy: the only file published to GitHub Pages ----
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_FILE.write_text(page, encoding="utf-8")

    for p in (md_file, html_file, CANONICAL_FILE, PUBLIC_FILE):
        print(str(p.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
