import calendar
import email.utils
import socket
from types import SimpleNamespace

import pytest

import src.fetcher as fetcher
from src.fetcher import FeedItem


def test_load_sources_validates_and_normalizes(tmp_path):
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - name: Example\n"
        "    url: HTTPS://Example.COM/feed\n"
        "    category: Test\n"
        "    priority: 2\n",
        encoding="utf-8",
    )
    assert fetcher.load_sources(str(config)) == [{
        "name": "Example",
        "url": "https://example.com/feed",
        "category": "Test",
        "priority": 2,
    }]


def test_load_sources_rejects_unsafe_url(tmp_path):
    config = tmp_path / "sources.yaml"
    config.write_text("sources:\n  - name: Bad\n    url: file:///etc/passwd\n", encoding="utf-8")
    with pytest.raises(ValueError, match="合法 name/url"):
        fetcher.load_sources(str(config))


def test_entry_timestamp_is_interpreted_as_utc():
    parsed = (2026, 8, 24, 1, 2, 3, 0, 0, 0)
    entry = SimpleNamespace(published_parsed=parsed, updated_parsed=None)
    assert fetcher._entry_ts(entry, 0) == calendar.timegm(parsed)


def test_download_feed_retries_then_succeeds(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b"feed"

    def fake_urlopen(_request, timeout, context):
        calls.append(timeout)
        assert context is fetcher.SSL_CONTEXT
        if len(calls) == 1:
            raise TimeoutError("first attempt")
        return Response()

    monkeypatch.setattr(fetcher, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetcher.time, "sleep", lambda _seconds: None)
    assert fetcher._download_feed("https://example.com/feed", timeout=3, retries=1) == b"feed"
    assert calls == [3, 3]


def test_fetch_one_cleans_content_and_rejects_unsafe_entry_link(monkeypatch):
    now = 1_700_000_000
    published = email.utils.formatdate(now - 60, usegmt=True)
    body = f"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>T</title>
      <item><title><![CDATA[<b>Good</b>]]></title><link>https://example.com/good</link>
        <description><![CDATA[<p>Hello</p> world]]></description><pubDate>{published}</pubDate></item>
      <item><title>Bad</title><link>javascript:alert(1)</link><pubDate>{published}</pubDate></item>
    </channel></rss>""".encode()
    monkeypatch.setattr(fetcher, "_download_feed", lambda _url: body)
    monkeypatch.setattr(fetcher.time, "time", lambda: now)
    source = {"name": "Source", "url": "https://example.com/feed", "category": "C", "priority": 1}
    items = fetcher.fetch_one(source, 1)
    assert [(item.title, item.summary, item.link) for item in items] == [
        ("Good", "Hello world", "https://example.com/good")
    ]


def test_fetch_all_isolates_failures_and_keeps_config_order(monkeypatch):
    sources = [
        {"name": "A", "url": "https://a.example/feed"},
        {"name": "Broken", "url": "https://broken.example/feed"},
        {"name": "B", "url": "https://b.example/feed"},
    ]

    def fake_fetch(source, _window):
        if source["name"] == "Broken":
            raise RuntimeError("boom")
        link = "https://example.com/post?utm_source=a" if source["name"] == "A" else "https://example.com/post"
        return [FeedItem(source["name"], link, "s", source["name"], "c", 1, 1)]

    monkeypatch.setattr(fetcher, "fetch_one", fake_fetch)
    items = fetcher.fetch_all(sources, max_workers=3)
    assert [item.source for item in items] == ["A"]


def test_download_url_rejects_private_and_local_targets():
    for url in (
        "http://localhost:1200/feed",
        "http://127.0.0.1/x",
        "http://192.168.1.1/feed",
        "http://10.0.0.5/article",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/feed",
    ):
        with pytest.raises(ValueError):
            fetcher.download_url(url)


def test_download_url_rejects_public_name_resolving_to_private_ip(monkeypatch):
    def fake_getaddrinfo(_host, _port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(fetcher.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="内网"):
        fetcher.download_url("https://attacker.example/article")


def test_redirect_handler_rejects_private_redirect_target():
    handler = fetcher._PublicOnlyRedirectHandler()
    with pytest.raises(ValueError):
        handler.redirect_request(None, None, 302, "Found", {}, "http://10.0.0.9/secret")
