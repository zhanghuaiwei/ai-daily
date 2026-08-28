"""Read all prior Markdown articles to prevent topic and source repetition."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path

from .safety import clean_plain_text, normalize_url_for_dedupe

log = logging.getLogger(__name__)
_MARKDOWN_LINK_RE = re.compile(r"\[原文(?:链接)?\]\((?:<([^>]+)>|([^)]+))\)")
_MARKDOWN_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# 新格式把当日来源链接放在不可见的 HTML 注释里，既保持正文干净又保留全历史去重。
_SOURCE_COMMENT_RE = re.compile(r"<!--\s*ai-daily-sources:(.*?)-->", re.DOTALL)


def _included_day(name: str, current_day: str, history_days: int | None) -> bool:
    try:
        today = dt.date.fromisoformat(current_day)
        edition_day = dt.date.fromisoformat(name)
    except ValueError:
        return False
    age = (today - edition_day).days
    return age > 0 and (history_days is None or age <= history_days)


def _article_markdown_paths(day_dir: Path) -> list[Path]:
    """Return the new single-file artifact plus legacy per-article Markdown files."""
    paths = []
    current = day_dir / "article.md"
    if current.is_file():
        paths.append(current)
    paths.extend(sorted(day_dir.glob("article-*/article.md")))
    return paths


def load_recent_links(
    out_root: str | Path,
    current_day: str,
    history_days: int | None = None,
) -> set[str]:
    """Load links from all prior editions; ``None`` means the complete repository history."""
    if history_days is not None and history_days <= 0:
        return set()
    root = Path(out_root)
    if not root.is_dir():
        return set()

    links: set[str] = set()
    for day_dir in sorted(root.iterdir(), reverse=True):
        if not day_dir.is_dir() or not _included_day(day_dir.name, current_day, history_days):
            continue

        for markdown_path in _article_markdown_paths(day_dir):
            try:
                markdown = markdown_path.read_text(encoding="utf-8")
            except OSError as err:
                log.warning("历史 Markdown 读取失败: %s (%s)", markdown_path, err)
                continue
            for match in _MARKDOWN_LINK_RE.finditer(markdown):
                key = normalize_url_for_dedupe(match.group(1) or match.group(2))
                if key:
                    links.add(key)
            for match in _SOURCE_COMMENT_RE.finditer(markdown):
                for token in match.group(1).split():
                    key = normalize_url_for_dedupe(token)
                    if key:
                        links.add(key)

        # Backward compatibility keeps old JSON editions in the no-repeat history.
        for json_path in (day_dir / "digest.json", *day_dir.glob("article-*/article.json")):
            if not json_path.is_file():
                continue
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                sources = payload.get("picks", []) if json_path.name == "digest.json" else (
                    payload.get("topic", {}).get("evidence", [])
                )
                for source in sources:
                    raw_url = source.get("link") or source.get("url") if isinstance(source, dict) else ""
                    key = normalize_url_for_dedupe(raw_url)
                    if key:
                        links.add(key)
            except (OSError, json.JSONDecodeError, AttributeError) as err:
                log.warning("历史 JSON 读取失败: %s (%s)", json_path, err)
    return links


def load_recent_topic_titles(
    out_root: str | Path,
    current_day: str,
    history_days: int | None = None,
) -> list[str]:
    """Load every prior final title, including legacy JSON artifacts."""
    if history_days is not None and history_days <= 0:
        return []
    root = Path(out_root)
    if not root.is_dir():
        return []

    titles: list[str] = []

    def add(value: object) -> None:
        title = clean_plain_text(value, 120)
        if title and title not in titles:
            titles.append(title)

    for day_dir in sorted(root.iterdir(), reverse=True):
        if not day_dir.is_dir() or not _included_day(day_dir.name, current_day, history_days):
            continue
        for markdown_path in _article_markdown_paths(day_dir):
            try:
                match = _MARKDOWN_TITLE_RE.search(markdown_path.read_text(encoding="utf-8"))
                add(match.group(1) if match else "")
            except OSError as err:
                log.warning("历史标题读取失败: %s (%s)", markdown_path, err)
        for article_path in day_dir.glob("article-*/article.json"):
            try:
                bundle = json.loads(article_path.read_text(encoding="utf-8"))
                add(bundle.get("topic", {}).get("working_title"))
                add(bundle.get("article", {}).get("selected_title"))
            except (OSError, json.JSONDecodeError, AttributeError) as err:
                log.warning("旧版文章标题读取失败: %s (%s)", article_path, err)
    return titles
