import datetime as dt

import pytest

import src.cleanup as cleanup


class FakeIMAP:
    instances = []

    def __init__(self, host, port, ssl_context, timeout):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.timeout = timeout
        self.login_args = None
        self.selected = []
        self.uid_calls = []
        self.expunge_calls = 0
        self.instances.append(self)

    def login(self, user, secret):
        self.login_args = (user, secret)
        return "OK", []

    def list(self):
        return "OK", [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Sent) "/" "Sent Messages"',
        ]

    def select(self, mailbox, readonly=False):
        self.selected.append((mailbox, readonly))
        return "OK", [b"2"]

    def uid(self, command, *args):
        self.uid_calls.append((command, args))
        if command == "search":
            return "OK", [b"101 102"]
        return "OK", []

    def expunge(self):
        self.expunge_calls += 1
        return "OK", []

    def logout(self):
        return "BYE", []


def test_output_cleanup_removes_only_expired_date_directories(tmp_path):
    output = tmp_path / "output"
    for name in ("2026-08-10", "2026-08-11", "2026-08-24", "notes"):
        directory = output / name
        directory.mkdir(parents=True)
        (directory / "keep.txt").write_text(name, encoding="utf-8")

    removed = cleanup.cleanup_output_directories(
        output,
        dt.date(2026, 8, 24),
        retention_days=14,
    )

    assert removed == ["2026-08-10"]
    assert not (output / "2026-08-10").exists()
    assert (output / "2026-08-11").is_dir()
    assert (output / "notes").is_dir()


def test_output_cleanup_dry_run_does_not_delete(tmp_path):
    old = tmp_path / "output" / "2026-01-01"
    old.mkdir(parents=True)
    removed = cleanup.cleanup_output_directories(
        tmp_path / "output",
        dt.date(2026, 8, 24),
        dry_run=True,
    )
    assert removed == ["2026-01-01"]
    assert old.is_dir()


def test_output_cleanup_refuses_expired_symlink(tmp_path):
    output = tmp_path / "output"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (output / "2026-01-01").symlink_to(outside, target_is_directory=True)
    with pytest.raises(cleanup.CleanupError, match="拒绝清理异常输出目录"):
        cleanup.cleanup_output_directories(output, dt.date(2026, 8, 24))
    assert outside.is_dir()


def test_qq_cleanup_targets_only_tagged_old_messages(monkeypatch):
    FakeIMAP.instances.clear()
    monkeypatch.setattr(cleanup.imaplib, "IMAP4_SSL", FakeIMAP)

    result = cleanup.cleanup_qq_articles(
        dt.date(2026, 8, 24),
        retention_days=14,
        sender="123456789@qq.com",
        auth_code="abcdefghijklmnop",
    )

    assert result == {"status": "completed", "deleted": 4, "folders": 2}
    client = FakeIMAP.instances[0]
    assert client.login_args == ("123456789@qq.com", "abcdefghijklmnop")
    assert client.selected == [("INBOX", False), (b'"Sent Messages"', False)]
    searches = [args[1] for command, args in client.uid_calls if command == "search"]
    assert all('HEADER X-AI-Daily "article"' in criteria for criteria in searches)
    assert all("BEFORE 11-Aug-2026" in criteria for criteria in searches)
    assert client.expunge_calls == 2


def test_cleanup_interval_and_state(monkeypatch, tmp_path):
    state = tmp_path / ".maintenance" / "cleanup-state.json"
    output = tmp_path / "output"
    old = output / "2026-01-01"
    old.mkdir(parents=True)
    monkeypatch.setattr(
        cleanup,
        "cleanup_qq_articles",
        lambda *_args, **_kwargs: {"status": "skipped_not_configured", "deleted": 0, "folders": 0},
    )

    report = cleanup.run_cleanup(output, state, dt.date(2026, 8, 24))
    assert report["output_removed"] == ["2026-01-01"]
    assert state.is_file()

    skipped = cleanup.run_cleanup(output, state, dt.date(2026, 8, 31))
    assert skipped["status"] == "skipped_not_due"
    assert cleanup.cleanup_is_due(state, dt.date(2026, 9, 7)) is True
