import smtplib

import pytest

import src.email_delivery as email_delivery


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout, context):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.login_args = None
        self.sent = []
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def login(self, user, secret):
        self.login_args = (user, secret)

    def send_message(self, message, from_addr, to_addrs):
        self.sent.append((message, from_addr, to_addrs))


def article_paths(tmp_path, publishable=True, with_image=True):
    article_dir = tmp_path / "article-01"
    image_dir = article_dir / "images"
    image_dir.mkdir(parents=True)
    markdown = "# 测试文章\n\n正文"
    html = "<html><body><h1>测试文章</h1><p>正文</p>"
    if with_image:
        (image_dir / "cover.jpg").write_bytes(b"jpeg-payload")
        markdown += "\n\n![封面](<images/cover.jpg>)"
        html += '<img src="images/cover.jpg" alt="封面">'
    html += "</body></html>"
    markdown_path = article_dir / "article.md"
    html_path = article_dir / "article_wechat.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return [{
        "markdown": markdown_path,
        "wechat_html": html_path,
        "publishable": publishable,
        "title": "测试文章",
        "relative_dir": "article-01",
        "has_visuals": with_image,
    }]


def test_qq_email_embeds_article_html_and_images(monkeypatch, tmp_path):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", FakeSMTP)
    delivered = email_delivery.deliver_article_emails(
        article_paths(tmp_path),
        sender="123456789@qq.com",
        auth_code="abcdefghijklmnop",
    )

    assert delivered == ["测试文章"]
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.qq.com", 465)
    assert smtp.login_args == ("123456789@qq.com", "abcdefghijklmnop")
    message, from_addr, to_addrs = smtp.sent[0]
    assert from_addr == "123456789@qq.com"
    assert to_addrs == ["123456789@qq.com"]
    assert message["Subject"] == "AI 前沿文章｜测试文章"
    assert "cid:ai-daily-1-cover.jpg" in message.get_body(preferencelist=("html",)).get_content()
    assert any(part.get_filename() == "cover.jpg" for part in message.walk())


def test_qq_email_sends_text_version_without_images(monkeypatch, tmp_path):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", FakeSMTP)
    delivered = email_delivery.deliver_article_emails(
        article_paths(tmp_path, with_image=False),
        sender="123456789@qq.com",
        auth_code="abcdefghijklmnop",
    )
    assert delivered == ["测试文章"]
    assert not any(part.get_content_maintype() == "image" for part in FakeSMTP.instances[0].sent[0][0].walk())


def test_qq_email_error_never_exposes_authorization_code(monkeypatch, tmp_path):
    secret = "abcdefghijklmnop"

    class FailingSMTP(FakeSMTP):
        def login(self, user, auth_code):
            raise smtplib.SMTPAuthenticationError(535, b"authentication failed")

    monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", FailingSMTP)
    with pytest.raises(email_delivery.EmailDeliveryError) as caught:
        email_delivery.deliver_article_emails(
            article_paths(tmp_path),
            sender="123456789@qq.com",
            auth_code=secret,
        )
    assert secret not in str(caught.value)


def test_qq_email_rejects_header_injection():
    with pytest.raises(email_delivery.EmailDeliveryError):
        email_delivery._email_config(
            sender="123456789@qq.com\nBcc: attacker@example.com",
            auth_code="abcdefghijklmnop",
        )
