import datetime as dt
import json

from src.renderer import (
    _today_str,
    render_markdown,
    render_wechat_html,
    write_article_outputs,
    write_outputs,
)


def hostile_pick(link="javascript:alert(1)"):
    return {
        "title": "<script>alert(1)</script> [title]",
        "link": link,
        "source": "<b>source</b>",
        "category": "category",
        "summary": "<img src=x onerror=alert(1)> summary",
        "reason": "<svg onload=alert(1)> reason",
    }


def test_today_uses_beijing_timezone_across_utc_date_boundary():
    utc = dt.datetime(2026, 8, 24, 23, 30, tzinfo=dt.UTC)
    assert _today_str(utc) == "2026-08-25"


def test_html_escapes_text_and_drops_unsafe_url():
    output = render_wechat_html([hostile_pick()], date="2026-08-24")
    assert "<script>" not in output
    assert "javascript:" not in output
    assert "alert(1) [title]" in output


def test_markdown_escapes_untrusted_markup_and_drops_unsafe_url():
    output = render_markdown([hostile_pick()], date="2026-08-24")
    assert "<script>" not in output
    assert "javascript:" not in output
    assert "\\[title\\]" in output


def test_write_outputs_creates_three_consistent_artifacts(tmp_path):
    paths = write_outputs(
        [hostile_pick("https://example.com/post?a=1&b=2")],
        out_root=str(tmp_path),
        date="2026-08-24",
    )
    assert set(paths) == {"markdown", "wechat_html", "json"}
    assert all(path.exists() for path in paths.values())
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["date"] == "2026-08-24"
    assert payload["count"] == 1
    assert payload["picks"][0]["link"] == "https://example.com/post?a=1&b=2"
    assert "href=\"https://example.com/post?a=1&amp;b=2\"" in paths["wechat_html"].read_text(encoding="utf-8")


def test_write_article_outputs_keeps_one_topic_per_directory(tmp_path):
    bundle = {
        "topic": {
            "working_title": "话题",
            "evidence": [{
                "id": 1,
                "title": "来源",
                "source": "官方",
                "url": "https://example.com/source",
                "excerpt": "不应写入长期归档的来源正文",
            }],
        },
        "research_brief": {},
        "article": {
            "selected_title": "一篇独立文章",
            "title_candidates": [{"title": "一篇独立文章", "angle": "信息型", "score": 90}],
            "abstract": "摘要",
            "lead": "开头",
            "sections": [
                {
                    "heading": "核心变化",
                    "paragraphs": [{"text": "正文内容", "source_ids": [1]}],
                },
                {
                    "heading": "实际影响",
                    "paragraphs": [{"text": "影响内容", "source_ids": [1]}],
                },
            ],
            "conclusion": "结尾",
        },
        "review": {"total": 0},
        "metrics": {"checks": {}},
        "publishable": False,
        "visuals": {
            "status": "ready",
            "cover": {"path": "images/cover.jpg", "alt": "封面", "width": 900, "height": 383},
            "illustrations": [
                {"path": "images/illustration-01.jpg", "alt": "插图一", "after_section": 1, "width": 1200, "height": 800},
                {"path": "images/illustration-02.jpg", "alt": "插图二", "after_section": 2, "width": 1200, "height": 800},
            ],
        },
    }
    paths = write_article_outputs([bundle], str(tmp_path), "2026-08-24")
    assert paths[0]["markdown"].parent.name == "article-01"
    assert paths[0]["wechat_html"].exists()
    markdown = paths[0]["markdown"].read_text(encoding="utf-8")
    assert "images/cover.jpg" in markdown
    assert markdown.count("images/illustration-") == 2
    html = paths[0]["wechat_html"].read_text(encoding="utf-8")
    assert "<img src=\"images/cover.jpg\"" in html
    assert (tmp_path / "2026-08-24" / "articles.json").exists()
    archived = json.loads(paths[0]["json"].read_text(encoding="utf-8"))
    assert "excerpt" not in archived["topic"]["evidence"][0]
