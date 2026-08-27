"""Untrusted-content normalization shared by fetching, curation and rendering."""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_RE = re.compile(r"<[^>]*>")
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def clean_plain_text(value: object, limit: int) -> str:
    """Return single-line plain text with HTML and control characters removed."""
    if not isinstance(value, str) or limit <= 0:
        return ""
    # NFC keeps Chinese full-width punctuation, which reads better in public-account articles.
    text = unicodedata.normalize("NFC", html.unescape(value))
    text = _CONTROL_RE.sub("", text)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def safe_http_url(value: object) -> str:
    """Allow only absolute HTTP(S) URLs suitable for HTML/Markdown links."""
    if not isinstance(value, str):
        return ""
    url = value.strip()
    if not url or any(ch.isspace() or ch in "\\<>\"'" for ch in url):
        return ""
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return ""
        if parts.username or parts.password:
            return ""
        hostname = parts.hostname.encode("idna").decode("ascii").lower()
        port = parts.port
    except (UnicodeError, ValueError):
        return ""

    host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = (parts.scheme.lower() == "http" and port == 80) or (
        parts.scheme.lower() == "https" and port == 443
    )
    netloc = host if port is None or default_port else f"{host}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, parts.fragment))


def normalize_url_for_dedupe(value: object) -> str:
    """Normalize a safe URL and remove common tracking parameters."""
    url = safe_http_url(value)
    if not url:
        return ""
    parts = urlsplit(url)
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query, doseq=True), ""))


def sanitize_pick(value: object) -> dict[str, str]:
    """Normalize one curated item so renderers never receive raw model/feed data."""
    pick: Mapping = value if isinstance(value, Mapping) else {}
    return {
        "title": clean_plain_text(pick.get("title"), 300) or "(无标题)",
        "link": safe_http_url(pick.get("link")),
        "source": clean_plain_text(pick.get("source"), 100),
        "category": clean_plain_text(pick.get("category"), 100),
        "summary": clean_plain_text(pick.get("summary"), 300),
        "reason": clean_plain_text(pick.get("reason"), 500),
    }
