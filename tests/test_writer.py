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
            {"title": "技术进展背后的真正变化", "angle": "信息型", "score": 92},
            {"title": "这项新技术解决了什么问题", "angle": "问题型", "score": 88},
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
        "visual_plan": {
            "cover": {"concept": "展示核心技术与真实应用之间的联系", "alt": "技术与应用场景的封面图"},
            "illustrations": [
                {"after_section": 2, "concept": "解释训练方法的关键关系", "alt": "训练方法的结构关系"},
                {"after_section": 4, "concept": "展示开发者实际使用时的影响", "alt": "开发者使用技术的场景"},
            ],
        },
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
            "headline": 86,
        },
        "issues": [],
        "fact_check": "pass",
    }


def test_article_sanitization_selects_highest_scoring_title():
    raw = valid_article()
    raw["selected_title"] = raw["title_candidates"][1]["title"]
    article = writer._sanitize_article(raw, evidence())
    assert article["selected_title"] == "技术进展背后的真正变化"


def test_article_metrics_enforce_quality_gate():
    article = writer._sanitize_article(valid_article(), evidence())
    review = writer._sanitize_review(passing_review())
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["publishable"] is True
    article["lead"] = "随着人工智能的快速发展，让我们拭目以待。"
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["checks"]["human_style"] is False


def test_article_metrics_require_focused_logical_and_clear_structure():
    article = writer._sanitize_article(valid_article(), evidence())
    review = writer._sanitize_review(passing_review())

    for dimension, check in (
        ("topic_focus", "topic_focus"),
        ("logic", "logical_flow"),
        ("structure", "clear_structure"),
    ):
        failing_review = {**review, "dimensions": {**review["dimensions"], dimension: 84}}
        metrics = writer.article_metrics(article, failing_review, target_chars=2_000)
        assert metrics["checks"][check] is False
        assert metrics["publishable"] is False

    article["sections"][1]["heading"] = article["sections"][0]["heading"]
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["checks"]["clear_structure"] is False


def test_article_metrics_require_an_attractive_but_not_clickbait_headline():
    article = writer._sanitize_article(valid_article(), evidence())
    review = writer._sanitize_review(passing_review())

    article["title_candidates"][0]["score"] = 84
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["checks"]["headline_quality"] is False

    article = writer._sanitize_article(valid_article(), evidence())
    article["selected_title"] = "震惊：技术进展背后的真正变化"
    article["title_candidates"][0]["title"] = article["selected_title"]
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["checks"]["headline_quality"] is False


def test_article_sanitization_keeps_text_when_visual_plan_is_incomplete():
    raw = valid_article()
    raw["visual_plan"]["illustrations"] = raw["visual_plan"]["illustrations"][:1]
    article = writer._sanitize_article(raw, evidence())
    metrics = writer.article_metrics(article, writer._sanitize_review(passing_review()))
    assert len(article["visual_plan"]["illustrations"]) == 1
    assert metrics["publishable"] is True


def test_article_visual_plan_accepts_zero_to_five_body_images():
    raw = valid_article()
    raw["visual_plan"]["illustrations"] = []
    article = writer._sanitize_article(raw, evidence())
    assert article["visual_plan"]["illustrations"] == []

    raw = valid_article()
    raw["visual_plan"]["illustrations"] = [
        {
            "after_section": index,
            "concept": f"解释第{index}个章节的信息关系",
            "alt": f"第{index}个章节插图",
        }
        for index in range(1, 6)
    ]
    article = writer._sanitize_article(raw, evidence())
    assert len(article["visual_plan"]["illustrations"]) == 5


def test_article_metrics_reject_nontechnical_english_glosses():
    article = writer._sanitize_article(valid_article(), evidence())
    article["lead"] += "这是一项重要变化（important change）。"
    review = writer._sanitize_review(passing_review())
    metrics = writer.article_metrics(article, review, target_chars=2_000)
    assert metrics["checks"]["no_unnecessary_english_gloss"] is False


def test_fallback_article_is_never_publishable():
    topic = {"working_title": "待审核话题", "reason": "证据不足", "evidence": evidence()}
    bundle = writer.fallback_article(topic, "simulated failure")
    assert bundle["publishable"] is False
    assert bundle["review"]["fact_check"] == "needs_review"


def test_produce_article_runs_research_write_and_review(monkeypatch):
    topic = {"working_title": "话题", "angle": "角度", "reason": "理由", "evidence": evidence()}
    article = writer._sanitize_article(valid_article(), evidence())
    review = writer._sanitize_review(passing_review())
    monkeypatch.setattr(writer, "build_research_brief", lambda *_args, **_kwargs: {"facts": []})
    monkeypatch.setattr(writer, "write_draft", lambda *_args, **_kwargs: article)
    monkeypatch.setattr(writer, "edit_and_review", lambda *_args, **_kwargs: (article, review))
    bundle = writer.produce_article(topic, target_chars=2_000)
    assert bundle["publishable"] is True
