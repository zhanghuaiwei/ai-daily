import sys

import src.pipeline as pipeline
from src.fetcher import FeedItem


def test_pipeline_writes_one_markdown_and_does_not_gate_delivery(monkeypatch, tmp_path):
    used = FeedItem("Old AI item", "https://example.com/old", "summary", "A", "AI", 1, 1)
    fresh = FeedItem("Fresh AI item", "https://example.com/fresh", "summary", "B", "AI", 1, 2)
    topic = {
        "working_title": "Fresh AI item",
        "angle": "最新变化",
        "reason": "正在受到关注",
        "sources": [fresh.to_dict()],
        "ai_selected": True,
    }
    researched = {
        **topic,
        "evidence": [{
            "id": 1,
            "title": fresh.title,
            "source": fresh.source,
            "url": fresh.link,
            "excerpt": fresh.summary,
        }],
    }
    article_bundle = {
        "topic": researched,
        "article": {
            "selected_title": "Fresh AI item：为什么这次不一样？",
            "abstract": "一个新的 AI 事件正在发生。",
            "lead": "先看事实。",
            "sections": [{
                "heading": "发生了什么",
                "paragraphs": ["完整正文。"],
            }],
            "conclusion": "继续观察。",
        },
        "metrics": {"checks": {"length": False}},
        "delivery_ready": True,
    }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "_today_str", lambda: "2026-08-27")
    monkeypatch.setattr(pipeline, "load_sources", lambda _path: [{"name": "source"}])
    monkeypatch.setattr(pipeline, "fetch_all", lambda *_args, **_kwargs: [used, fresh])
    monkeypatch.setattr(pipeline, "load_recent_links", lambda *_args: {"https://example.com/old"})
    monkeypatch.setattr(pipeline, "load_recent_topic_titles", lambda *_args, **_kwargs: ["Old AI item"])
    monkeypatch.setattr(pipeline, "load_cross_edition_titles", lambda *_args, **_kwargs: [])

    def plan(items, **kwargs):
        assert items == [fresh]
        assert kwargs["target"] == kwargs["maximum"] == 1
        assert kwargs["edition"] == "news"
        return [topic]

    monkeypatch.setattr(pipeline, "plan_topics_with_llm", plan)
    monkeypatch.setattr(pipeline, "research_topic", lambda _topic: researched)
    monkeypatch.setattr(pipeline, "produce_article", lambda *_args, **_kwargs: article_bundle)
    monkeypatch.setattr(sys, "argv", ["src.pipeline"])

    assert pipeline.main() == 0
    files = list((tmp_path / "output" / "2026-08-27").iterdir())
    assert [path.name for path in files] == ["article.md"]


def test_pipeline_application_edition_writes_application_file_and_avoids_same_day_clash(
    monkeypatch, tmp_path
):
    fresh = FeedItem("Fresh agent app", "https://apps.example.com/fresh", "summary", "B", "AI", 1, 2)
    topic = {
        "working_title": "Fresh agent app",
        "angle": "应用角度",
        "reason": "能上手",
        "sources": [fresh.to_dict()],
        "ai_selected": True,
    }
    researched = {
        **topic,
        "evidence": [{
            "id": 1,
            "title": fresh.title,
            "source": fresh.source,
            "url": fresh.link,
            "excerpt": fresh.summary,
        }],
    }
    article_bundle = {
        "topic": researched,
        "article": {
            "selected_title": "这个 Agent 应用能自动干活了",
            "abstract": "一个 AI 应用的上手说明。",
            "lead": "先说怎么用。",
            "sections": [{"heading": "能做什么", "paragraphs": ["完整正文。"]}],
            "conclusion": "值得一试。",
        },
        "metrics": {"checks": {}},
        "delivery_ready": True,
    }

    monkeypatch.chdir(tmp_path)
    day_dir = tmp_path / "output" / "2026-10-28"
    day_dir.mkdir(parents=True)
    # 当天资讯线已写：应用线必须把它的标题并入去重，防止同日撞题。
    (day_dir / "article.md").write_text(
        "# 当天资讯标题\n\n正文\n", encoding="utf-8"
    )
    monkeypatch.setattr(pipeline, "_today_str", lambda: "2026-10-28")
    monkeypatch.setattr(pipeline, "load_sources", lambda _path: [{"name": "source"}])
    monkeypatch.setattr(pipeline, "fetch_all", lambda *_args, **_kwargs: [fresh])
    monkeypatch.setattr(pipeline, "load_recent_links", lambda *_args, **_kwargs: set())
    captured_editions = []

    def fake_recent_titles(*_args, **kwargs):
        captured_editions.append(kwargs.get("edition"))
        return ["旧应用标题"]

    monkeypatch.setattr(pipeline, "load_recent_topic_titles", fake_recent_titles)

    def plan(items, **kwargs):
        assert kwargs["edition"] == "application"
        assert "旧应用标题" in kwargs["recent_titles"]
        assert "当天资讯标题" in kwargs["recent_titles"]
        return [topic]

    monkeypatch.setattr(pipeline, "plan_topics_with_llm", plan)
    monkeypatch.setattr(pipeline, "research_topic", lambda _topic: researched)

    def produce(*_args, **kwargs):
        assert kwargs["edition"] == "application"
        return article_bundle

    monkeypatch.setattr(pipeline, "produce_article", produce)
    monkeypatch.setattr(sys, "argv", ["src.pipeline", "--edition", "application"])

    assert pipeline.main() == 0
    assert captured_editions == ["application"]
    assert (day_dir / "application.md").is_file()
    assert (day_dir / "article.md").read_text(encoding="utf-8").startswith("# 当天资讯标题")
