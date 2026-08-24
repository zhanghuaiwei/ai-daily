"""Deliver publishable articles to a personal WeChat account through ServerChan Turbo."""

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
from .safety import clean_plain_text, safe_http_url

SERVERCHAN_ENDPOINT = "https://sctapi.ftqq.com/{sendkey}.send"
_SENDKEY_RE = re.compile(r"^[A-Za-z0-9._-]{12,200}$")
_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[([^\]\n]*)\]\((?:<)?images/([A-Za-z0-9._-]+\.(?:jpg|jpeg|png|webp))(?:>)?\)",
    re.IGNORECASE,
)


class DeliveryError(RuntimeError):
    """A redacted delivery failure safe to print in CI logs."""


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


def _with_public_images(markdown: str, article_base_url: str) -> str:
    base_url = safe_http_url(article_base_url.rstrip("/"))
    if not base_url or not base_url.startswith("https://"):
        raise DeliveryError("配图公网地址必须是有效的 HTTPS URL")

    def replace(match: re.Match) -> str:
        alt, filename = match.groups()
        return f"![{alt}](<{base_url}/images/{filename}>)"

    return _MARKDOWN_IMAGE_RE.sub(replace, markdown)


def deliver_article_paths(
    paths: list[dict[str, object]],
    asset_base_url: str | None = None,
) -> list[dict]:
    delivered = []
    day_asset_base = (asset_base_url or os.environ.get("ASSET_BASE_URL", "")).strip()
    for item in paths:
        if not item.get("publishable"):
            continue
        markdown_path = item.get("markdown")
        if not isinstance(markdown_path, Path):
            raise DeliveryError("文章 Markdown 路径无效")
        try:
            markdown = markdown_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise DeliveryError("无法读取待投递文章") from err
        if item.get("has_visuals"):
            relative_dir = clean_plain_text(item.get("relative_dir"), 40)
            if not relative_dir or not day_asset_base:
                raise DeliveryError("文章含配图，但 ASSET_BASE_URL 未配置，已阻止残缺推送")
            markdown = _with_public_images(
                markdown,
                f"{day_asset_base.rstrip('/')}/{relative_dir}",
            )
        result = send_to_wechat(
            str(item.get("title", "AI 前沿文章")),
            markdown,
        )
        delivered.append({"title": item.get("title"), "result": result})
    return delivered


def load_day_article_paths(day_dir: Path) -> list[dict[str, object]]:
    index_path = day_dir / "articles.json"
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as err:
        raise DeliveryError("无法读取当日文章索引") from err
    if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
        raise DeliveryError("当日文章索引格式无效")

    day_root = day_dir.resolve()
    paths = []
    for item in payload["articles"]:
        if not isinstance(item, dict):
            continue
        raw_paths = item.get("paths", {})
        if not isinstance(raw_paths, dict):
            continue
        resolved_paths = {}
        for key in ("markdown", "wechat_html"):
            relative_path = raw_paths.get(key)
            if not isinstance(relative_path, str):
                raise DeliveryError("文章索引缺少投递文件路径")
            resolved_path = (day_dir / relative_path).resolve()
            if day_root not in resolved_path.parents or not resolved_path.is_file():
                raise DeliveryError("文章索引包含无效投递文件路径")
            resolved_paths[key] = resolved_path
        markdown_path = resolved_paths["markdown"]
        relative_dir = markdown_path.parent.name
        paths.append({
            "markdown": markdown_path,
            "wechat_html": resolved_paths["wechat_html"],
            "publishable": bool(item.get("publishable")),
            "title": clean_plain_text(item.get("title"), 80),
            "relative_dir": relative_dir,
            "has_visuals": bool(item.get("has_visuals")),
        })
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="推送已提交的当日公众号文章到个人微信")
    parser.add_argument("--day-dir", type=Path, required=True)
    parser.add_argument("--asset-base-url", required=True)
    args = parser.parse_args()
    try:
        paths = load_day_article_paths(args.day_dir)
        delivered = deliver_article_paths(paths, asset_base_url=args.asset_base_url)
        if delivered:
            print(f"已推送 {len(delivered)} 篇图文文章到个人微信")
            return 0
        send_to_wechat(
            "AI 文章生成需要人工检查",
            "今天没有文章通过文字质量门禁，请查看仓库中的当日产物。",
        )
        print("没有成品文章，已发送人工检查提醒")
        return 0
    except DeliveryError as err:
        print(f"微信投递失败：{err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
