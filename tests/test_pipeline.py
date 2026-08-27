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
                "paragraphs": [{"text": "完整正文。", "source_ids": [1]}],
            }],
            "conclusion": "继续观察。",
        },
        "metrics": {"checks": {"model_review": False}},
        "delivery_ready": True,
    }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "_today_str", lambda: "2026-08-27")
    monkeypatch.setattr(pipeline, "load_sources", lambda _path: [{"name": "source"}])
    monkeypatch.setattr(pipeline, "fetch_all", lambda *_args, **_kwargs: [used, fresh])
    monkeypatch.setattr(pipeline, "load_recent_links", lambda *_args: {"https://example.com/old"})
    monkeypatch.setattr(pipeline, "load_recent_topic_titles", lambda *_args: ["Old AI item"])

    def plan(items, **kwargs):
        assert items == [fresh]
        assert kwargs["target"] == kwargs["maximum"] == 1
        return [topic]

    monkeypatch.setattr(pipeline, "plan_topics_with_llm", plan)
    monkeypatch.setattr(pipeline, "research_topic", lambda _topic: researched)
    monkeypatch.setattr(pipeline, "produce_article", lambda *_args, **_kwargs: article_bundle)
    monkeypatch.setattr(sys, "argv", ["src.pipeline"])

    assert pipeline.main() == 0
    files = list((tmp_path / "output" / "2026-08-27").iterdir())
    assert [path.name for path in files] == ["article.md"]
