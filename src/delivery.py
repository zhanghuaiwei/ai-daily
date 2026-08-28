"""Deliver the daily Markdown article to WeChat through ServerChan Turbo."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .fetcher import SSL_CONTEXT
from .safety import clean_plain_text

SERVERCHAN_ENDPOINT = "https://sctapi.ftqq.com/{sendkey}.send"
_SENDKEY_RE = re.compile(r"^[A-Za-z0-9._-]{12,200}$")
_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_internal_comments(markdown: str) -> str:
    """Remove hidden source metadata before the article leaves this repository."""
    return _HTML_COMMENT_RE.sub("", markdown).strip()


class DeliveryError(RuntimeError):
    """A redacted delivery failure safe to print in CI logs."""


def article_title(markdown: str) -> str:
    match = _TITLE_RE.search(markdown)
    return clean_plain_text(match.group(1) if match else "", 80) or "AI 每日热门话题"


def load_daily_markdown(day_dir: Path) -> tuple[Path, str]:
    day_root = day_dir.resolve()
    article_path = (day_dir / "article.md").resolve()
    if article_path.parent != day_root or not article_path.is_file():
        raise DeliveryError("找不到当日 Markdown 文章")
    try:
        markdown = article_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise DeliveryError("无法读取当日 Markdown 文章") from err
    if not markdown.strip():
        raise DeliveryError("当日 Markdown 文章为空")
    return article_path, markdown


def send_to_wechat(
    title: str,
    markdown: str,
    sendkey: str | None = None,
    timeout: int = 20,
) -> dict:
    key = (sendkey or os.environ.get("WECHAT_SENDKEY", "")).strip()
    if not _SENDKEY_RE.fullmatch(key):
        raise DeliveryError("WECHAT_SENDKEY 未配置或格式无效")
    payload = urlencode({
        "title": clean_plain_text(title, 80),
        "desp": markdown,
        "short": clean_plain_text(markdown, 120),
    }).encode()
    request = Request(
        SERVERCHAN_ENDPOINT.format(sendkey=key),
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as err:
        raise DeliveryError(f"微信推送返回 HTTP {err.code}") from None
    except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as err:
        raise DeliveryError(f"微信推送网络或响应异常: {type(err).__name__}") from None
    if not isinstance(result, dict) or result.get("code") != 0:
        message = clean_plain_text(result.get("message") if isinstance(result, dict) else "", 120)
        raise DeliveryError(f"微信推送失败: {message or '未知服务错误'}")
    return result


def deliver_daily_markdown(day_dir: Path, sendkey: str | None = None) -> dict:
    """Send the article whenever it exists; no quality score can block delivery."""
    _path, markdown = load_daily_markdown(day_dir)
    return send_to_wechat(
        article_title(markdown), strip_internal_comments(markdown), sendkey=sendkey
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="把当日 Markdown 文章推送到个人微信")
    parser.add_argument("--day-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        deliver_daily_markdown(args.day_dir)
        print("已推送 1 篇 Markdown 文章到个人微信")
        return 0
    except DeliveryError as err:
        print(f"微信投递失败：{err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
