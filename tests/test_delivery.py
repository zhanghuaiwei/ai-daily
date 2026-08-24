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
    requests = []

    def fake_urlopen(request, timeout, context):
        requests.append((request, timeout, context))
        return Response({"code": 0, "message": "SUCCESS"})

    monkeypatch.setattr(delivery, "urlopen", fake_urlopen)
    result = delivery.send_to_wechat("标题", "# 正文", sendkey="SCT1234567890")
    assert result["code"] == 0
    assert requests[0][0].method == "POST"
    assert b"desp=%23+%E6%AD%A3%E6%96%87" in requests[0][0].data


def test_delivery_error_redacts_sendkey(monkeypatch):
    key = "SCT1234567890"

    def fake_urlopen(request, timeout, context):
        raise HTTPError(request.full_url, 403, "denied", {}, None)

    monkeypatch.setattr(delivery, "urlopen", fake_urlopen)
    with pytest.raises(delivery.DeliveryError) as caught:
        delivery.send_to_wechat("标题", "正文", sendkey=key)
    assert key not in str(caught.value)


def test_delivery_rewrites_local_images_to_public_urls(monkeypatch, tmp_path):
    article_dir = tmp_path / "article-01"
    article_dir.mkdir()
    markdown_path = article_dir / "article.md"
    markdown_path.write_text(
        "# 标题\n\n![封面](<images/cover.jpg>)\n\n![正文](<images/illustration-01.jpg>)",
        encoding="utf-8",
    )
    sent = []
    monkeypatch.setattr(
        delivery,
        "send_to_wechat",
        lambda title, markdown: sent.append((title, markdown)) or {"code": 0},
    )
    result = delivery.deliver_article_paths(
        [{
            "markdown": markdown_path,
            "title": "标题",
            "publishable": True,
            "has_visuals": True,
            "relative_dir": "article-01",
        }],
        asset_base_url="https://example.com/output/2026-08-24",
    )
    assert len(result) == 1
    assert "https://example.com/output/2026-08-24/article-01/images/cover.jpg" in sent[0][1]
    assert "(<images/" not in sent[0][1]


def test_delivery_blocks_illustrated_article_without_public_base(tmp_path):
    article_dir = tmp_path / "article-01"
    article_dir.mkdir()
    markdown_path = article_dir / "article.md"
    markdown_path.write_text("![封面](<images/cover.jpg>)", encoding="utf-8")
    with pytest.raises(delivery.DeliveryError, match="ASSET_BASE_URL"):
        delivery.deliver_article_paths([{
            "markdown": markdown_path,
            "title": "标题",
            "publishable": True,
            "has_visuals": True,
            "relative_dir": "article-01",
        }])


def test_delivery_sends_text_version_when_visuals_are_unavailable(monkeypatch, tmp_path):
    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("# 可发布文字文章\n\n正文", encoding="utf-8")
    sent = []
    monkeypatch.setattr(
        delivery,
        "send_to_wechat",
        lambda title, markdown: sent.append((title, markdown)) or {"code": 0},
    )
    result = delivery.deliver_article_paths([{
        "markdown": markdown_path,
        "title": "可发布文字文章",
        "publishable": True,
        "has_visuals": False,
        "relative_dir": "article-01",
    }])
    assert len(result) == 1
    assert sent == [("可发布文字文章", "# 可发布文字文章\n\n正文")]
