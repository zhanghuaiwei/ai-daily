"""Deliver the daily Markdown articles to WeChat through ServerChan Turbo."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .editions import EDITIONS, edition_title_prefix
from .fetcher import SSL_CONTEXT
from .safety import clean_plain_text

log = logging.getLogger(__name__)
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


def load_daily_markdowns(day_dir: Path, only: list[str] | None = None) -> list[tuple[Path, str]]:
    """Load every edition article present in the day directory (news + application).

    ``only`` 把推送范围限制在指定文件名（如重跑某条线路时只推新生成的那篇）；
    点名文件全部缺失时直接报错，避免把“没生成出来”误当成“无事可推”。
    """
    day_root = day_dir.resolve()
    loaded: list[tuple[Path, str]] = []
    for spec in EDITIONS.values():
        article_path = (day_dir / spec["filename"]).resolve()
        if article_path.parent != day_root or not article_path.is_file():
            continue
        try:
            markdown = article_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise DeliveryError(f"无法读取当日 Markdown 文章: {spec['filename']}") from err
        if not markdown.strip():
            raise DeliveryError(f"当日 Markdown 文章为空: {spec['filename']}")
        loaded.append((article_path, markdown))
    if only is not None:
        wanted = {name.strip() for name in only if name.strip()}
        loaded = [entry for entry in loaded if entry[0].name in wanted]
        if not loaded:
            raise DeliveryError("请求推送的文章不存在: " + "、".join(sorted(wanted)))
    if not loaded:
        raise DeliveryError("找不到当日 Markdown 文章")
    return loaded


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


def deliver_daily_markdown(
    day_dir: Path, sendkey: str | None = None, only: list[str] | None = None
) -> dict:
    """Send every requested edition article present; no quality score can block delivery.

    每篇独立尝试、互不拖垮：部分成功时返回成功映射并记录失败日志，
    全部失败才抛出 DeliveryError，交由调用方以失败退出码处理。
    """
    delivered: dict[str, dict] = {}
    failures: list[str] = []
    for path, markdown in load_daily_markdowns(day_dir, only=only):
        title = f"{edition_title_prefix(path.name)}{article_title(markdown)}"
        try:
            delivered[path.name] = send_to_wechat(
                title, strip_internal_comments(markdown), sendkey=sendkey
            )
        except DeliveryError as err:
            failures.append(f"{path.name}: {err}")
            log.warning("微信投递失败 %s", failures[-1])
    if failures and not delivered:
        raise DeliveryError("；".join(failures))
    return delivered


def main() -> int:
    parser = argparse.ArgumentParser(description="把当日 Markdown 文章推送到个人微信")
    parser.add_argument("--day-dir", type=Path, required=True)
    parser.add_argument(
        "--only",
        default=None,
        help="只推送指定文件名（逗号分隔，如 application.md）；不传则推送目录下全部线路文章",
    )
    args = parser.parse_args()
    only = [name for name in args.only.split(",")] if args.only else None
    try:
        delivered = deliver_daily_markdown(args.day_dir, only=only)
        print(f"已推送 {len(delivered)} 篇 Markdown 文章到个人微信")
        return 0
    except DeliveryError as err:
        print(f"微信投递失败：{err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
