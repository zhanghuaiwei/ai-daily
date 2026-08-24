"""Read prior digest outputs to avoid repeating links across adjacent editions."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path

from .safety import normalize_url_for_dedupe

log = logging.getLogger(__name__)
_MARKDOWN_LINK_RE = re.compile(r"\[原文链接\]\((?:<([^>]+)>|([^)]+))\)")


def load_recent_links(
    out_root: str | Path,
    current_day: str,
    history_days: int = 7,
) -> set[str]:
    """Load normalized links from prior digest.json files (Markdown as legacy fallback)."""
    if history_days <= 0:
        return set()
    root = Path(out_root)
    if not root.exists():
        return set()

    today = dt.date.fromisoformat(current_day)
    links: set[str] = set()
    for day_dir in root.iterdir():
        if not day_dir.is_dir():
            continue
        try:
            edition_day = dt.date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        age = (today - edition_day).days
        if age <= 0 or age > history_days:
            continue

        json_path = day_dir / "digest.json"
        loaded_digest_json = False
        if json_path.exists():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                for pick in payload.get("picks", []):
                    key = normalize_url_for_dedupe(pick.get("link") if isinstance(pick, dict) else "")
                    if key:
                        links.add(key)
                loaded_digest_json = True
            except (OSError, json.JSONDecodeError, AttributeError) as err:
                log.warning("历史文件读取失败，尝试 Markdown: %s (%s)", json_path, err)

        markdown_path = day_dir / "digest.md"
        if not loaded_digest_json and markdown_path.exists():
            try:
                for match in _MARKDOWN_LINK_RE.finditer(markdown_path.read_text(encoding="utf-8")):
                    key = normalize_url_for_dedupe(match.group(1) or match.group(2))
                    if key:
                        links.add(key)
            except OSError as err:
                log.warning("历史文件读取失败: %s (%s)", markdown_path, err)

        for article_path in day_dir.glob("article-*/article.json"):
            try:
                bundle = json.loads(article_path.read_text(encoding="utf-8"))
                for source in bundle.get("topic", {}).get("evidence", []):
                    key = normalize_url_for_dedupe(source.get("url") if isinstance(source, dict) else "")
                    if key:
                        links.add(key)
            except (OSError, json.JSONDecodeError, AttributeError) as err:
                log.warning("文章历史读取失败: %s (%s)", article_path, err)
    return links


def load_recent_topic_titles(
    out_root: str | Path,
    current_day: str,
    history_days: int = 7,
) -> list[str]:
    """Load prior working/final titles so the topic model can avoid semantic repeats."""
    if history_days <= 0:
        return []
    root = Path(out_root)
    if not root.exists():
        return []
    today = dt.date.fromisoformat(current_day)
    titles: list[str] = []
    for article_path in root.glob("*/article-*/article.json"):
        try:
            edition_day = dt.date.fromisoformat(article_path.parents[1].name)
        except ValueError:
            continue
        age = (today - edition_day).days
        if age <= 0 or age > history_days:
            continue
        try:
            bundle = json.loads(article_path.read_text(encoding="utf-8"))
            for value in (
                bundle.get("topic", {}).get("working_title"),
                bundle.get("article", {}).get("selected_title"),
            ):
                if isinstance(value, str) and value.strip() and value.strip() not in titles:
                    titles.append(value.strip())
        except (OSError, json.JSONDecodeError, AttributeError) as err:
            log.warning("文章标题历史读取失败: %s (%s)", article_path, err)
    return titles
