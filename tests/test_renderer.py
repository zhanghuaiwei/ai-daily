import datetime as dt

from src.renderer import _today_str, render_article_markdown, write_article_output


def bundle():
    return {
        "topic": {
            "evidence": [{
                "id": 1,
                "title": "来源标题",
                "source": "官方来源",
                "url": "https://example.com/source",
            }],
        },
        "article": {
            "selected_title": "AI 新变化：为什么这次不一样？",
            "abstract": "一段清楚说明事件与影响的导读。",
            "lead": "这件事从一个具体变化开始。",
            "sections": [
                {
                    "heading": "发生了什么",
                    "paragraphs": [{"text": "正文事实。", "source_ids": [1]}],
                },
            ],
            "conclusion": "最后留下一个仍需观察的问题。",
        },
    }


def test_today_uses_beijing_timezone_across_utc_date_boundary():
    now = dt.datetime(2026, 8, 23, 16, 30, tzinfo=dt.UTC)
    assert _today_str(now) == "2026-08-24"


def test_markdown_has_wechat_layout_and_escapes_untrusted_markup():
    value = bundle()
    value["article"]["sections"][0]["paragraphs"][0]["text"] = "<script>x</script> **事实**"
    markdown = render_article_markdown(value, "2026-08-27")
    assert markdown.startswith("# AI 新变化：为什么这次不一样？")
    assert "> **导读**｜" in markdown
    assert "## 写在最后" in markdown
    assert "## 参考资料" in markdown
    assert "【1】" in markdown
    assert "&lt;script&gt;x&lt;/script&gt;" in markdown
    assert "\\*\\*事实\\*\\*" in markdown


def test_write_output_creates_only_one_markdown_file(tmp_path):
    legacy_day = tmp_path / "2026-08-27"
    legacy_article = legacy_day / "article-01"
    legacy_article.mkdir(parents=True)
    (legacy_day / "articles.json").write_text("{}", encoding="utf-8")
    (legacy_day / "digest.md").write_text("old", encoding="utf-8")
    (legacy_article / "article.md").write_text("old", encoding="utf-8")
    path = write_article_output(bundle(), out_root=tmp_path, date="2026-08-27")
    assert path == tmp_path / "2026-08-27" / "article.md"
    assert sorted(item.name for item in path.parent.iterdir()) == ["article.md"]
