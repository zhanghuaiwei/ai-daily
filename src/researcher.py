"""Build a bounded, source-linked evidence pack for every selected article topic."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
import re
from html.parser import HTMLParser

from .fetcher import download_url
from .safety import clean_plain_text, safe_http_url

log = logging.getLogger(__name__)
MAX_SOURCE_TEXT_CHARS = 6_000
MAX_RESEARCH_WORKERS = 4


class _ReadableTextParser(HTMLParser):
    ignored_tags = {"script", "style", "noscript", "svg", "nav", "footer", "form"}
    block_tags = {"article", "div", "h1", "h2", "h3", "h4", "li", "main", "p", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        if tag in self.ignored_tags:
            self._ignored_depth += 1
        elif tag in self.block_tags and not self._ignored_depth:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag in self.block_tags and not self._ignored_depth:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._chunks.append(data)

    def text(self) -> str:
        lines, seen = [], set()
        for raw in "".join(self._chunks).splitlines():
            line = clean_plain_text(raw, 1_000)
            if len(line) < 12 or line in seen:
                continue
            lines.append(line)
            seen.add(line)
        return "\n".join(lines)[:MAX_SOURCE_TEXT_CHARS]


def _decode_page(data: bytes) -> str:
    head = data[:4_096].decode("ascii", errors="ignore")
    match = re.search(r"charset=[\"']?([\w-]+)", head, flags=re.IGNORECASE)
    encodings = [match.group(1)] if match else []
    encodings += ["utf-8", "gb18030"]
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="ignore")


def extract_page_text(data: bytes) -> str:
    parser = _ReadableTextParser()
    parser.feed(_decode_page(data))
    return parser.text()


def _research_source(source: dict) -> dict:
    url = safe_http_url(source.get("link"))
    excerpt = ""
    retrieved = False
    if url:
        try:
            excerpt = extract_page_text(download_url(url))
            retrieved = bool(excerpt)
        except Exception as err:  # noqa: BLE001 - one article page must not kill the topic
            log.warning("正文抓取失败，使用 RSS 摘要: %s (%s)", source.get("source", "?"), err)
    if not excerpt:
        excerpt = clean_plain_text(source.get("summary"), MAX_SOURCE_TEXT_CHARS)
    published_ts = source.get("published_ts")
    published_at = ""
    if isinstance(published_ts, (int, float)):
        published_at = dt.datetime.fromtimestamp(published_ts, dt.UTC).isoformat()
    return {
        "title": clean_plain_text(source.get("title"), 300),
        "source": clean_plain_text(source.get("source"), 100),
        "category": clean_plain_text(source.get("category"), 100),
        "url": url,
        "published_at": published_at,
        "excerpt": excerpt,
        "retrieved": retrieved,
    }


def research_topic(topic: dict, max_sources: int = 4) -> dict:
    sources = topic.get("sources", [])[:max_sources]
    if not sources:
        return {**topic, "evidence": []}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(MAX_RESEARCH_WORKERS, len(sources))
    ) as executor:
        evidence = list(executor.map(_research_source, sources))
    for index, source in enumerate(evidence, 1):
        source["id"] = index
    return {**topic, "evidence": evidence}


def research_topics(topics: list[dict]) -> list[dict]:
    return [research_topic(topic) for topic in topics]
