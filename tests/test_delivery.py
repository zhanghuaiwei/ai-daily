import json
from urllib.error import HTTPError

import pytest

import src.delivery as delivery


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_send_to_wechat_posts_markdown_without_logging_key(monkeypatch):
    captured = {}

    def fake_urlopen(request, **_kwargs):
        captured["url"] = request.full_url
        captured["data"] = request.data
        return Response({"code": 0, "data": {"pushid": "1"}})

    monkeypatch.setattr(delivery, "urlopen", fake_urlopen)
    result = delivery.send_to_wechat("标题", "# 正文", sendkey="SCT1234567890")
    assert result["code"] == 0
    assert "SCT1234567890" in captured["url"]
    assert b"desp=%23+%E6%AD%A3%E6%96%87" in captured["data"]


def test_delivery_error_redacts_sendkey(monkeypatch):
    secret = "SCT1234567890"

    def fail(request, **_kwargs):
        raise HTTPError(request.full_url, 500, "bad", {}, None)

    monkeypatch.setattr(delivery, "urlopen", fail)
    with pytest.raises(delivery.DeliveryError) as caught:
        delivery.send_to_wechat("标题", "正文", sendkey=secret)
    assert secret not in str(caught.value)


def test_load_daily_markdowns_reads_edition_files(tmp_path):
    day_dir = tmp_path / "2026-08-27"
    day_dir.mkdir()
    (day_dir / "article.md").write_text("# 一个吸引人的标题？\n\n正文\n", encoding="utf-8")
    loaded = delivery.load_daily_markdowns(day_dir)
    assert [path.name for path, _markdown in loaded] == ["article.md"]
    assert delivery.article_title(loaded[0][1]) == "一个吸引人的标题？"


def test_load_daily_markdowns_requires_at_least_one_article(tmp_path):
    day_dir = tmp_path / "2026-08-27"
    day_dir.mkdir()
    with pytest.raises(delivery.DeliveryError, match="找不到当日"):
        delivery.load_daily_markdowns(day_dir)


def test_delivery_never_checks_quality_gate(monkeypatch, tmp_path):
    day_dir = tmp_path / "2026-08-27"
    day_dir.mkdir()
    (day_dir / "article.md").write_text("# 标题：发生了什么？\n\n正文\n", encoding="utf-8")
    sent = []
    monkeypatch.setattr(
        delivery,
        "send_to_wechat",
        lambda title, markdown, sendkey=None: sent.append((title, markdown, sendkey)) or {"code": 0},
    )
    assert delivery.deliver_daily_markdown(day_dir, sendkey="test-key") == {
        "article.md": {"code": 0}
    }
    assert sent[0][0] == "标题：发生了什么？"


def test_delivery_strips_hidden_source_comments(monkeypatch, tmp_path):
    day_dir = tmp_path / "2026-08-27"
    day_dir.mkdir()
    (day_dir / "article.md").write_text(
        "# 标题：发生了什么？\n\n正文\n\n<!-- ai-daily-sources:\n  https://example.com/source\n-->\n",
        encoding="utf-8",
    )
    sent = []
    monkeypatch.setattr(
        delivery,
        "send_to_wechat",
        lambda title, markdown, sendkey=None: sent.append((title, markdown)) or {"code": 0},
    )
    assert delivery.deliver_daily_markdown(day_dir, sendkey="test-key") == {
        "article.md": {"code": 0}
    }
    assert "ai-daily-sources" not in sent[0][1]
    assert "https://example.com/source" not in sent[0][1]
    assert sent[0][1].endswith("正文")


def test_delivery_prefixes_application_title_only(monkeypatch, tmp_path):
    day_dir = tmp_path / "2026-08-27"
    day_dir.mkdir()
    (day_dir / "article.md").write_text("# 资讯标题\n\n正文\n", encoding="utf-8")
    (day_dir / "application.md").write_text("# 应用标题\n\n正文\n", encoding="utf-8")
    sent = []
    monkeypatch.setattr(
        delivery,
        "send_to_wechat",
        lambda title, markdown, sendkey=None: sent.append(title) or {"code": 0},
    )
    delivered = delivery.deliver_daily_markdown(day_dir, sendkey="test-key")
    assert sorted(delivered) == ["application.md", "article.md"]
    assert sent == ["资讯标题", "AI应用|应用标题"]


def test_delivery_partial_failure_still_returns_successes(monkeypatch, tmp_path):
    day_dir = tmp_path / "2026-08-27"
    day_dir.mkdir()
    (day_dir / "article.md").write_text("# 资讯标题\n\n正文\n", encoding="utf-8")
    (day_dir / "application.md").write_text("# 应用标题\n\n正文\n", encoding="utf-8")

    def fake_send(title, _markdown, sendkey=None):
        if title.startswith("AI应用|"):
            raise delivery.DeliveryError("微信推送返回 HTTP 500")
        return {"code": 0}

    monkeypatch.setattr(delivery, "send_to_wechat", fake_send)
    delivered = delivery.deliver_daily_markdown(day_dir, sendkey="test-key")
    assert list(delivered) == ["article.md"]


def test_delivery_all_failures_raise(monkeypatch, tmp_path):
    day_dir = tmp_path / "2026-08-27"
    day_dir.mkdir()
    (day_dir / "article.md").write_text("# 资讯标题\n\n正文\n", encoding="utf-8")
    (day_dir / "application.md").write_text("# 应用标题\n\n正文\n", encoding="utf-8")

    def fail(_title, _markdown, sendkey=None):
        raise delivery.DeliveryError("微信推送返回 HTTP 500")

    monkeypatch.setattr(delivery, "send_to_wechat", fail)
    with pytest.raises(delivery.DeliveryError, match="article.md"):
        delivery.deliver_daily_markdown(day_dir, sendkey="test-key")
