import src.researcher as researcher


def test_extract_page_text_ignores_scripts_and_navigation():
    html = b"""
    <html><body><nav>This navigation text should never be included.</nav>
    <article><h1>Technical headline long enough</h1>
    <p>This is the useful article paragraph with concrete evidence.</p></article>
    <script>malicious instructions should be ignored</script></body></html>
    """
    text = researcher.extract_page_text(html)
    assert "useful article paragraph" in text
    assert "navigation" not in text
    assert "malicious" not in text


def test_research_topic_assigns_source_ids_and_falls_back_to_summary(monkeypatch):
    calls = []

    def fake_download(url):
        calls.append(url)
        if url.endswith("broken"):
            raise TimeoutError
        return b"<article><p>A sufficiently long retrieved article paragraph.</p></article>"

    monkeypatch.setattr(researcher, "download_url", fake_download)
    topic = {
        "working_title": "话题",
        "sources": [
            {
                "title": "A",
                "link": "https://example.com/good",
                "summary": "摘要 A",
                "source": "Source A",
                "category": "技术",
                "published_ts": 1,
            },
            {
                "title": "B",
                "link": "https://example.com/broken",
                "summary": "这是回退使用的 RSS 摘要内容",
                "source": "Source B",
                "category": "技术",
                "published_ts": 2,
            },
        ],
    }
    result = researcher.research_topic(topic)
    assert [item["id"] for item in result["evidence"]] == [1, 2]
    assert result["evidence"][0]["retrieved"] is True
    assert result["evidence"][1]["excerpt"] == "这是回退使用的 RSS 摘要内容"
    assert len(calls) == 2
