"""Deliver publishable articles through QQ Mail SMTP with inline article images."""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path

import certifi

from .delivery import load_day_article_paths
from .safety import clean_plain_text

QQ_SMTP_HOST = "smtp.qq.com"
QQ_SMTP_PORT = 465
QQ_SMTP_STARTTLS_PORT = 587
_IMAGE_SRC_RE = re.compile(
    r"(?P<prefix>\bsrc\s*=\s*)(?P<quote>['\"])images/"
    r"(?P<filename>[A-Za-z0-9._-]+\.(?:jpg|jpeg|png|webp))(?P=quote)",
    re.IGNORECASE,
)
_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[([^\]\n]*)\]\((?:<)?images/[A-Za-z0-9._-]+\.(?:jpg|jpeg|png|webp)(?:>)?\)",
    re.IGNORECASE,
)


class EmailDeliveryError(RuntimeError):
    """A redacted QQ SMTP failure safe to print in CI logs."""


def _valid_email(value: object) -> str:
    if not isinstance(value, str):
        return ""
    address = value.strip()
    _, parsed = parseaddr(address)
    if (
        parsed != address
        or len(address) > 254
        or address.count("@") != 1
        or any(char.isspace() or char in "\r\n" for char in address)
    ):
        return ""
    local, domain = address.rsplit("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        return ""
    return address


def _email_config(
    sender: str | None = None,
    auth_code: str | None = None,
    recipient: str | None = None,
) -> tuple[str, str, str]:
    user = _valid_email(sender or os.environ.get("QQ_EMAIL_USER", ""))
    target = _valid_email(recipient or os.environ.get("EMAIL_TO", "") or user)
    secret = (auth_code or os.environ.get("QQ_EMAIL_AUTH_CODE", "")).strip()
    if not user:
        raise EmailDeliveryError("QQ_EMAIL_USER 未配置或邮箱格式无效")
    if not target:
        raise EmailDeliveryError("EMAIL_TO 未配置或邮箱格式无效")
    if not 8 <= len(secret) <= 128 or any(char.isspace() for char in secret):
        raise EmailDeliveryError("QQ_EMAIL_AUTH_CODE 未配置或格式无效")
    return user, secret, target


def _prepare_html_images(html: str, article_dir: Path) -> tuple[str, list[tuple[Path, str]]]:
    related: list[tuple[Path, str]] = []
    seen: dict[str, str] = {}

    def replace(match: re.Match) -> str:
        filename = match.group("filename")
        path = article_dir / "images" / filename
        if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            return match.group(0)
        cid = seen.get(filename)
        if not cid:
            cid = f"ai-daily-{len(seen) + 1}-{filename}"
            seen[filename] = cid
            related.append((path, cid))
        return f"{match.group('prefix')}{match.group('quote')}cid:{cid}{match.group('quote')}"

    return _IMAGE_SRC_RE.sub(replace, html), related


def build_article_email(
    title: str,
    markdown: str,
    html: str,
    article_dir: Path,
    sender: str,
    recipient: str,
) -> EmailMessage:
    safe_title = clean_plain_text(title, 80) or "AI 前沿文章"
    html_with_cids, related = _prepare_html_images(html, article_dir)
    plain_text = _MARKDOWN_IMAGE_RE.sub(lambda match: f"[配图：{match.group(1)}]", markdown)

    message = EmailMessage()
    message["Subject"] = f"AI 前沿文章｜{safe_title}"
    message["From"] = sender
    message["To"] = recipient
    # 清理器只匹配这个专用头，绝不按模糊主题删除用户的其他邮件。
    message["X-AI-Daily"] = "article"
    message.set_content(plain_text)
    message.add_alternative(html_with_cids, subtype="html")
    html_part = message.get_payload()[-1]
    for path, cid in related:
        mime_type, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (mime_type or "image/jpeg").split("/", 1)
        try:
            data = path.read_bytes()
        except OSError:
            continue
        html_part.add_related(
            data,
            maintype=maintype,
            subtype=subtype,
            cid=f"<{cid}>",
            filename=path.name,
            disposition="inline",
        )
    return message


def send_qq_email(
    message: EmailMessage,
    sender: str | None = None,
    auth_code: str | None = None,
    recipient: str | None = None,
    timeout: int = 30,
) -> None:
    user, secret, target = _email_config(sender, auth_code, recipient)
    if message.get("From") != user or message.get("To") != target:
        raise EmailDeliveryError("邮件发件人或收件人与 SMTP 配置不一致")
    context = ssl.create_default_context(cafile=certifi.where())

    def send_with_ssl() -> tuple[str, Exception | None]:
        stage = "连接"
        try:
            with smtplib.SMTP_SSL(
                QQ_SMTP_HOST,
                QQ_SMTP_PORT,
                timeout=timeout,
                context=context,
            ) as smtp:
                stage = "认证"
                smtp.login(user, secret)
                stage = "发送"
                smtp.send_message(message, from_addr=user, to_addrs=[target])
        except (OSError, smtplib.SMTPException, TimeoutError) as err:
            return stage, err
        return stage, None

    def send_with_starttls() -> tuple[str, Exception | None]:
        stage = "连接"
        try:
            with smtplib.SMTP(
                QQ_SMTP_HOST,
                QQ_SMTP_STARTTLS_PORT,
                timeout=timeout,
            ) as smtp:
                smtp.ehlo()
                stage = "加密"
                smtp.starttls(context=context)
                smtp.ehlo()
                stage = "认证"
                smtp.login(user, secret)
                stage = "发送"
                smtp.send_message(message, from_addr=user, to_addrs=[target])
        except (OSError, smtplib.SMTPException, TimeoutError) as err:
            return stage, err
        return stage, None

    ssl_stage, ssl_error = send_with_ssl()
    if ssl_error is None:
        return
    if isinstance(ssl_error, smtplib.SMTPAuthenticationError):
        raise EmailDeliveryError("SMTP 认证失败，请检查 QQ 邮箱账号、服务开关和授权码") from None
    # 发送阶段的断连可能发生在服务器已收件之后，不能自动重发，以免产生重复邮件。
    if ssl_stage == "发送":
        raise EmailDeliveryError(
            f"SMTP 465/SSL 在发送阶段失败：{type(ssl_error).__name__}"
        ) from None

    tls_stage, tls_error = send_with_starttls()
    if tls_error is None:
        return
    if isinstance(tls_error, smtplib.SMTPAuthenticationError):
        raise EmailDeliveryError("SMTP 认证失败，请检查 QQ 邮箱账号、服务开关和授权码") from None
    raise EmailDeliveryError(
        "SMTP 两种加密连接均失败："
        f"465/SSL {ssl_stage}阶段 {type(ssl_error).__name__}；"
        f"587/STARTTLS {tls_stage}阶段 {type(tls_error).__name__}"
    ) from None


def deliver_article_emails(
    paths: list[dict[str, object]],
    sender: str | None = None,
    auth_code: str | None = None,
    recipient: str | None = None,
) -> list[str]:
    user, secret, target = _email_config(sender, auth_code, recipient)
    delivered = []
    for item in paths:
        if not item.get("publishable"):
            continue
        markdown_path = item.get("markdown")
        html_path = item.get("wechat_html")
        if not isinstance(markdown_path, Path) or not isinstance(html_path, Path):
            raise EmailDeliveryError("文章邮件路径无效")
        try:
            markdown = markdown_path.read_text(encoding="utf-8")
            html = html_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise EmailDeliveryError("无法读取待投递文章") from err
        title = clean_plain_text(item.get("title"), 80) or "AI 前沿文章"
        message = build_article_email(
            title,
            markdown,
            html,
            markdown_path.parent,
            user,
            target,
        )
        send_qq_email(message, user, secret, target)
        delivered.append(title)
    return delivered


def main() -> int:
    parser = argparse.ArgumentParser(description="通过 QQ 邮箱推送已生成的公众号文章")
    parser.add_argument("--day-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        paths = load_day_article_paths(args.day_dir)
        delivered = deliver_article_emails(paths)
        if delivered:
            print(f"已通过 QQ 邮箱推送 {len(delivered)} 篇文章")
        else:
            print("没有文章通过文字质量门禁，跳过邮件推送")
        return 0
    except EmailDeliveryError as err:
        print(f"QQ 邮箱投递失败：{err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
