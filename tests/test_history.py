import json

from src.history import load_recent_links, load_recent_topic_titles


def test_load_recent_links_uses_json_and_legacy_markdown(tmp_path):
    json_day = tmp_path / "2026-08-23"
    json_day.mkdir()
    (json_day / "digest.json").write_text(
        json.dumps({"picks": [{"link": "https://example.com/a?utm_source=x"}]}),
        encoding="utf-8",
    )
    article_dir = json_day / "article-01"
    article_dir.mkdir()
    (article_dir / "article.json").write_text(
        json.dumps({
            "topic": {
                "working_title": "历史工作标题",
                "evidence": [{"url": "https://example.com/c"}],
            },
            "article": {"selected_title": "历史正式标题"},
        }),
        encoding="utf-8",
    )
    markdown_day = tmp_path / "2026-08-22"
    markdown_day.mkdir()
    (markdown_day / "digest.md").write_text(
        "来源：X · [原文链接](https://example.com/b)",
        encoding="utf-8",
    )
    current_day = tmp_path / "2026-08-24"
    current_day.mkdir()
    (current_day / "digest.json").write_text(
        json.dumps({"picks": [{"link": "https://example.com/current"}]}),
        encoding="utf-8",
    )

    links = load_recent_links(tmp_path, "2026-08-24", history_days=2)
    assert links == {"https://example.com/a", "https://example.com/b", "https://example.com/c"}
    assert load_recent_topic_titles(tmp_path, "2026-08-24", 2) == ["历史工作标题", "历史正式标题"]


def test_load_recent_links_can_be_disabled(tmp_path):
    assert load_recent_links(tmp_path, "2026-08-24", history_days=0) == set()
