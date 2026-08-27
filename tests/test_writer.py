import pytest

import src.writer as writer


def evidence():
    return [{
        "id": 1,
        "title": "来源标题",
        "source": "官方来源",
        "url": "https://example.com/source",
        "published_at": "2026-08-24T00:00:00+00:00",
        "excerpt": "来源正文",
        "retrieved": True,
    }]


def valid_article():
    paragraph = "这项技术通过新的训练方法降低了部署成本，同时保留了可验证的性能边界。" * 8
    return {
        "title_candidates": [
            {"title": "技术进展背后的真正变化", "angle": "悬念型", "score": 92},
            {"title": "这项新技术解决了什么问题？", "angle": "问题型", "score": 88},
            {"title": "开发者为什么需要关注这次更新", "angle": "影响型", "score": 86},
        ],
        "selected_title": "技术进展背后的真正变化",
        "abstract": "这是一段面向泛读者的文章摘要，说明事件、技术价值与仍需观察的局限，也解释它可能如何影响开发者和普通用户，并区分已经确认的事实与仍待验证的说法。",
        "lead": "一个具体问题正在推动这项技术从研究原型走向真实场景。",
        "sections": [
            {"heading": f"第{index}个问题", "paragraphs": [{"text": paragraph, "source_ids": [1]}]}
            for index in range(1, 6)
        ],
        "conclusion": "真正需要观察的不是宣传口号，而是它能否在更多真实任务中保持稳定。",
    }


def passing_review():
    return {
        "total": 90,
        "dimensions": {
            "timeliness": 90,
            "frontier": 88,
            "accuracy": 92,
            "topic_focus": 90,
            "logic": 88,
            "structure": 88,
            "readability": 90,
            "chinese_style": 90,
            "human_style": 88,
            "headline": 90,
        },
        "issues": [],
        "fact_check": "pass",
    }


def test_article_sanitization_selects_highest_scoring_hook_title():
    raw = valid_article()
    raw["selected_title"] = raw["title_candidates"][1]["title"]
    article = writer._sanitize_article(raw, evidence())
    assert article["selected_title"] == "技术进展背后的真正变化"


def test_article_sanitization_adds_hook_when_best_title_has_none():
    raw = valid_article()
    raw["title_candidates"][0]["title"] = "技术进展带来新变化"
    raw["selected_title"] = raw["title_candidates"][0]["title"]
    article = writer._sanitize_article(raw, evidence())
    assert article["selected_title"].endswith("：为什么这次不一样？")


def test_sanitization_removes_known_ai_taste_phrases():
    raw = valid_article()
    raw["lead"] = "随着人工智能的快速发展，这项技术进入真实场景。"
    raw["sections"][0]["paragraphs"][0]["text"] += "综上所述，让我们拭目以待。"
    article = writer._sanitize_article(raw, evidence())
    body = str(article)
    assert all(phrase not in body for phrase in writer.AI_TASTE_PHRASES)


def test_metrics_are_diagnostic_and_allow_attention_headline():
    article = writer._sanitize_article(valid_article(), evidence())
    review = writer._sanitize_review(passing_review())
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["quality_passed"] is True
    article["selected_title"] = "震惊：技术进展背后的真正变化"
    article["title_candidates"][0]["title"] = article["selected_title"]
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["checks"]["headline_quality"] is True


def test_metrics_still_report_quality_failures():
    article = writer._sanitize_article(valid_article(), evidence())
    review = writer._sanitize_review(passing_review())
    review["dimensions"]["logic"] = 10
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["checks"]["logical_flow"] is False
    assert metrics["quality_passed"] is False


def test_fallback_article_is_not_delivery_ready():
    topic = {"working_title": "待审核话题", "reason": "证据不足", "evidence": evidence()}
    bundle = writer.fallback_article(topic, "simulated failure")
    assert bundle["delivery_ready"] is False
    assert bundle["review"]["fact_check"] == "needs_review"


def test_produce_article_is_delivery_ready_even_when_diagnostic_fails(monkeypatch):
    topic = {"working_title": "话题", "angle": "角度", "reason": "理由", "evidence": evidence()}
    article = writer._sanitize_article(valid_article(), evidence())
    failing_review = writer._sanitize_review({"issues": ["需要人工留意"]})
    monkeypatch.setattr(writer, "build_research_brief", lambda *_args, **_kwargs: {"facts": []})
    monkeypatch.setattr(writer, "write_draft", lambda *_args, **_kwargs: article)
    monkeypatch.setattr(writer, "edit_and_review", lambda *_args, **_kwargs: (article, failing_review))
    bundle = writer.produce_article(topic, target_chars=2_000)
    assert bundle["delivery_ready"] is True
    assert bundle["metrics"]["quality_passed"] is False


def test_produce_article_raises_when_no_complete_draft_exists(monkeypatch):
    topic = {"working_title": "话题", "angle": "角度", "reason": "理由", "evidence": evidence()}
    monkeypatch.setattr(
        writer,
        "build_research_brief",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider down")),
    )
    with pytest.raises(writer.ArticleGenerationError, match="provider down"):
        writer.produce_article(topic)
