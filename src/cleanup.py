"""Biweekly retention cleanup for generated outputs and tagged QQ Mail articles."""

from __future__ import annotations

import argparse
import datetime as dt
import imaplib
import json
import os
import re
import shutil
import ssl
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import certifi

from .email_delivery import EmailDeliveryError, _email_config

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
QQ_IMAP_HOST = "imap.qq.com"
QQ_IMAP_PORT = 993
_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LIST_MAILBOX_RE = re.compile(rb"(?:^| )(?P<mailbox>\"(?:[^\"\\]|\\.)*\"|[^ ]+)$")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class CleanupError(RuntimeError):
    """A retention failure safe to print without exposing account credentials."""


def _cutoff(today: dt.date, retention_days: int) -> dt.date:
    if not 1 <= retention_days <= 3_650:
        raise CleanupError("retention_days 必须在 1-3650 之间")
    return today - dt.timedelta(days=retention_days - 1)


def cleanup_output_directories(
    output_root: Path,
    today: dt.date,
    retention_days: int = 14,
    dry_run: bool = False,
) -> list[str]:
    """Delete only YYYY-MM-DD directories older than the retention window."""
    cutoff = _cutoff(today, retention_days)
    if not output_root.exists():
        return []
    if not output_root.is_dir() or output_root.is_symlink():
        raise CleanupError("output_root 不是安全的普通目录")

    root = output_root.resolve()
    removed = []
    for child in sorted(output_root.iterdir()):
        if not _DATE_DIR_RE.fullmatch(child.name):
            continue
        try:
            edition_date = dt.date.fromisoformat(child.name)
        except ValueError:
            continue
        if edition_date >= cutoff:
            continue
        resolved = child.resolve()
        if child.is_symlink() or not child.is_dir() or resolved.parent != root:
            raise CleanupError(f"拒绝清理异常输出目录：{child.name}")
        removed.append(child.name)
        if not dry_run:
            shutil.rmtree(resolved)
    return removed


def _imap_date(value: dt.date) -> str:
    return f"{value.day:02d}-{_MONTHS[value.month - 1]}-{value.year:04d}"


def _sent_mailboxes(client: imaplib.IMAP4_SSL) -> list[bytes]:
    try:
        status, rows = client.list()
    except imaplib.IMAP4.error:
        return []
    if status != "OK" or not rows:
        return []
    mailboxes = []
    for row in rows:
        if not isinstance(row, bytes) or b"\\Sent" not in row:
            continue
        match = _LIST_MAILBOX_RE.search(row)
        if match:
            mailboxes.append(match.group("mailbox"))
    return mailboxes


def _cleanup_mailbox(
    client: imaplib.IMAP4_SSL,
    mailbox: str | bytes,
    cutoff: dt.date,
    dry_run: bool,
) -> int:
    status, _ = client.select(mailbox, readonly=dry_run)
    if status != "OK":
        return 0
    criteria = f'(HEADER X-AI-Daily "article" BEFORE {_imap_date(cutoff)})'
    status, data = client.uid("search", None, criteria)
    if status != "OK" or not data or not data[0]:
        return 0
    uids = data[0].split()
    if dry_run:
        return len(uids)
    uid_set = b",".join(uids)
    status, _ = client.uid("store", uid_set, "+FLAGS.SILENT", r"(\Deleted)")
    if status != "OK":
        raise CleanupError("QQ 邮箱标记删除失败")
    status, _ = client.expunge()
    if status != "OK":
        raise CleanupError("QQ 邮箱永久清理失败")
    return len(uids)


def cleanup_qq_articles(
    today: dt.date,
    retention_days: int = 14,
    dry_run: bool = False,
    sender: str | None = None,
    auth_code: str | None = None,
) -> dict:
    """Delete only tagged AI Daily messages from Inbox and the IMAP Sent folder."""
    configured_user = sender or os.environ.get("QQ_EMAIL_USER", "")
    configured_secret = auth_code or os.environ.get("QQ_EMAIL_AUTH_CODE", "")
    if not configured_user or not configured_secret:
        return {"status": "skipped_not_configured", "deleted": 0, "folders": 0}
    try:
        user, secret, _ = _email_config(configured_user, configured_secret, configured_user)
    except EmailDeliveryError as err:
        return {"status": "failed", "deleted": 0, "folders": 0, "error": str(err)}

    context = ssl.create_default_context(cafile=certifi.where())
    client = None
    try:
        client = imaplib.IMAP4_SSL(
            QQ_IMAP_HOST,
            QQ_IMAP_PORT,
            ssl_context=context,
            timeout=30,
        )
        client.login(user, secret)
        mailboxes: list[str | bytes] = ["INBOX", *_sent_mailboxes(client)]
        unique_mailboxes = list(dict.fromkeys(mailboxes))
        cutoff = _cutoff(today, retention_days)
        deleted = sum(
            _cleanup_mailbox(client, mailbox, cutoff, dry_run)
            for mailbox in unique_mailboxes
        )
        return {
            "status": "dry_run" if dry_run else "completed",
            "deleted": deleted,
            "folders": len(unique_mailboxes),
        }
    except (CleanupError, OSError, TimeoutError, ssl.SSLError, imaplib.IMAP4.error) as err:
        error = str(err) if isinstance(err, CleanupError) else type(err).__name__
        return {"status": "failed", "deleted": 0, "folders": 0, "error": error}
    finally:
        if client is not None:
            try:
                client.logout()
            except (OSError, imaplib.IMAP4.error):
                pass


def _last_run_date(state_file: Path) -> dt.date | None:
    if not state_file.is_file():
        return None
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        return dt.date.fromisoformat(payload["last_run_date"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def cleanup_is_due(
    state_file: Path,
    today: dt.date,
    minimum_interval_days: int = 14,
    force: bool = False,
) -> bool:
    if force:
        return True
    if minimum_interval_days < 1:
        raise CleanupError("minimum_interval_days 必须大于 0")
    last_run = _last_run_date(state_file)
    return last_run is None or (today - last_run).days >= minimum_interval_days


def run_cleanup(
    output_root: Path,
    state_file: Path,
    today: dt.date,
    retention_days: int = 14,
    minimum_interval_days: int = 14,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    if not cleanup_is_due(state_file, today, minimum_interval_days, force):
        return {"status": "skipped_not_due", "last_run_date": str(_last_run_date(state_file))}

    removed = cleanup_output_directories(output_root, today, retention_days, dry_run)
    email_result = cleanup_qq_articles(today, retention_days, dry_run)
    report = {
        "status": "dry_run" if dry_run else "completed",
        "last_run_date": today.isoformat(),
        "retention_days": retention_days,
        "output_removed": removed,
        "qq_email": email_result,
        "wechat": {
            "status": "provider_auto_expiry",
            "detail": "Server酱正文会在 1-3 天后自动过期；微信客户端消息不支持远程删除",
        },
    }
    if not dry_run:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="清理超过保留期的输出和项目 QQ 邮件")
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(".maintenance/cleanup-state.json"),
    )
    parser.add_argument("--retention-days", type=int, default=14)
    parser.add_argument("--minimum-interval-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    today = dt.datetime.now(BEIJING_TZ).date()
    try:
        report = run_cleanup(
            args.output_root,
            args.state_file,
            today,
            args.retention_days,
            args.minimum_interval_days,
            args.dry_run,
            args.force,
        )
    except CleanupError as err:
        print(f"清理失败：{err}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
