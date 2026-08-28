"""Render one daily WeChat-ready Markdown article."""

from __future__ import annotations

import datetime as dt
import html
import logging
import re
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
_MARKDOWN_ESCAPE_RE = re.compile(r"([\\`*_[\]{}()#+.!|>\-])")
_LEGACY_ARTICLE_DIR_RE = re.compile(r"^article-\d{2}$")
_LEGACY_FILES = ("digest.md", "digest_wechat.html", "digest.json", "articles.json")


def _today_str(now: dt.datetime | None = None) -> str:
    if now is None:
        now = dt.datetime.now(BEIJING_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING_TZ)
    else:
        now = now.astimezone(BEIJING_TZ)
    return now.strftime("%Y-%m-%d")


def _markdown_text(value: object) -> str:
    text = value if isinstance(value, str) else ""
    escaped_html = html.escape(text, quote=False)
    return _MARKDOWN_ESCAPE_RE.sub(r"\\\1", escaped_html)


def render_article_markdown(bundle: dict) -> str:
    """Create one clean WeChat-ready Markdown article without template scaffolding."""
    article = bundle["article"]
    evidence = bundle["topic"].get("evidence", [])
    lines = [
        f"# {_markdown_text(article['selected_title'])}",
        "",
        f"> **导读**｜{_markdown_text(article['abstract'])}",
        "",
        "---",
        "",
        _markdown_text(article["lead"]),
        "",
    ]
    for section in article["sections"]:
        lines += [f"## {_markdown_text(section['heading'])}", ""]
        for paragraph in section["paragraphs"]:
            lines += [_markdown_text(paragraph), ""]

    lines += [
        "---",
        "",
        _markdown_text(article["conclusion"]),
        "",
    ]
    # Hidden source list keeps repository-wide link dedupe working without visible references.
    links = [source.get("url", "") for source in evidence if source.get("url")]
    if links:
        lines.append("<!-- ai-daily-sources:")
        lines.extend(f"  {link}" for link in links)
        lines.append("-->")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_article_output(
    bundle: dict,
    out_root: str | Path = "output",
    date: str | None = None,
) -> Path:
    """Atomically write the day's only artifact: ``article.md``."""
    edition_date = date or _today_str()
    day_dir = Path(out_root) / edition_date
    day_dir.mkdir(parents=True, exist_ok=True)
    destination = day_dir / "article.md"
    temporary = day_dir / ".article.md.tmp"
    temporary.write_text(render_article_markdown(bundle), encoding="utf-8")
    temporary.replace(destination)
    # A same-day migration/rerun must leave one Markdown artifact, never the old multi-file set.
    for filename in _LEGACY_FILES:
        (day_dir / filename).unlink(missing_ok=True)
    for child in day_dir.iterdir():
        if not _LEGACY_ARTICLE_DIR_RE.fullmatch(child.name):
            continue
        if child.is_symlink():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
    log.info("Markdown 文章已写入: %s", destination)
    return destination
