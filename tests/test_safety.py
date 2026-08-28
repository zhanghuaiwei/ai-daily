from src.safety import clean_plain_text, normalize_url_for_dedupe, safe_http_url


def test_clean_plain_text_removes_markup_controls_and_whitespace():
    assert clean_plain_text(" <b>Hello</b>\x00\n world ", 100) == "Hello world"


def test_safe_http_url_allows_only_absolute_http_urls():
    assert safe_http_url("HTTPS://Example.COM:443/a?q=1") == "https://example.com/a?q=1"
    assert safe_http_url("javascript:alert(1)") == ""
    assert safe_http_url("https://user:pass@example.com/") == ""
    assert safe_http_url("https://example.com/a b") == ""


def test_normalize_url_removes_tracking_fragment_and_trailing_slash():
    first = normalize_url_for_dedupe("https://EXAMPLE.com/post/?utm_source=x&id=1#part")
    second = normalize_url_for_dedupe("https://example.com/post?id=1")
    assert first == second
