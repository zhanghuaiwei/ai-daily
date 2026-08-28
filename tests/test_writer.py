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
            {"heading": f"第{index}个问题", "paragraphs": [paragraph]}
            for index in range(1, 6)
        ],
        "conclusion": "真正需要观察的不是宣传口号，而是它能否在更多真实任务中保持稳定。",
    }


def hook_suffix_of(title: str) -> str:
    return next(
        suffix for suffix in writer._ATTENTION_HOOK_SUFFIXES if title.endswith(suffix)
    )


def test_article_sanitization_selects_highest_scoring_hook_title():
    raw = valid_article()
    raw["selected_title"] = raw["title_candidates"][1]["title"]
    article = writer._sanitize_article(raw)
    assert article["selected_title"] == "技术进展背后的真正变化"


def test_article_sanitization_adds_hook_from_varied_suffix_pool():
    raw = valid_article()
    raw["title_candidates"][0]["title"] = "技术进展带来新变化"
    raw["selected_title"] = raw["title_candidates"][0]["title"]
    article = writer._sanitize_article(raw)
    assert article["selected_title"].startswith("技术进展带来新变化")
    assert article["selected_title"].endswith(hook_suffix_of(article["selected_title"]))


def test_hook_suffix_varies_across_different_titles():
    suffixes = set()
    for index in range(12):
        raw = valid_article()
        raw["title_candidates"][0]["title"] = f"某项技术进展迎来新阶段{index}"
        raw["selected_title"] = raw["title_candidates"][0]["title"]
        article = writer._sanitize_article(raw)
        suffixes.add(hook_suffix_of(article["selected_title"]))
    assert len(suffixes) >= 2


def test_sanitization_removes_known_ai_taste_phrases():
    raw = valid_article()
    raw["lead"] = "随着人工智能的快速发展，这项技术进入真实场景。"
    raw["sections"][0]["paragraphs"][0] += "综上所述，让我们拭目以待。"
    article = writer._sanitize_article(raw)
    body = str(article)
    assert all(phrase not in body for phrase in writer.AI_TASTE_PHRASES)


def test_sanitization_accepts_object_paragraphs_from_model():
    raw = valid_article()
    raw["sections"][0]["paragraphs"] = [{"text": "模型仍可能返回对象形态的段落。", "source_ids": [9]}]
    article = writer._sanitize_article(raw)
    assert article["sections"][0]["paragraphs"] == ["模型仍可能返回对象形态的段落。"]


def test_metrics_are_diagnostic_and_allow_attention_headline():
    article = writer._sanitize_article(valid_article())
    metrics = writer.article_metrics(article, target_chars=2_000)
    assert metrics["quality_passed"] is True
    article["selected_title"] = "震惊：技术进展背后的真正变化"
    article["title_candidates"][0]["title"] = article["selected_title"]
    metrics = writer.article_metrics(article, target_chars=2_000)
    assert metrics["checks"]["headline_quality"] is True


def test_metrics_still_report_quality_failures():
    article = writer._sanitize_article(valid_article())
    article["abstract"] = "过短的摘要"
    metrics = writer.article_metrics(article, target_chars=2_000)
    assert metrics["checks"]["abstract"] is False
    assert metrics["quality_passed"] is False


def test_fallback_article_is_not_delivery_ready():
    topic = {"working_title": "待审核话题", "reason": "证据不足", "evidence": evidence()}
    bundle = writer.fallback_article(topic, "simulated failure")
    assert bundle["delivery_ready"] is False
    assert bundle["generation_error"] == "simulated failure"


def test_write_article_uses_source_excerpt_in_one_bounded_request(monkeypatch):
    topic = {"working_title": "话题", "angle": "角度", "reason": "理由", "evidence": evidence()}
    topic["evidence"][0]["excerpt"] = "只能依据的来源正文"
    captured = {}

    def fake_request(_system, prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return valid_article()

    monkeypatch.setattr(writer, "request_json", fake_request)
    article = writer.write_article(topic, target_chars=2_000)
    assert article["selected_title"]
    assert "只能依据的来源正文" in captured["prompt"]
    assert captured["max_output_tokens"] == 6_000
    assert "source_ids" not in captured["prompt"]


def test_produce_article_is_delivery_ready_even_when_diagnostic_fails(monkeypatch):
    topic = {"working_title": "话题", "angle": "角度", "reason": "理由", "evidence": evidence()}
    article = writer._sanitize_article(valid_article())
    article["abstract"] = "过短的摘要"
    monkeypatch.setattr(writer, "write_article", lambda *_args, **_kwargs: article)
    bundle = writer.produce_article(topic, target_chars=2_000)
    assert bundle["delivery_ready"] is True
    assert bundle["metrics"]["quality_passed"] is False
    assert "review" not in bundle


def test_produce_article_raises_when_no_complete_draft_exists(monkeypatch):
    topic = {"working_title": "话题", "angle": "角度", "reason": "理由", "evidence": evidence()}
    monkeypatch.setattr(
        writer,
        "write_article",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider down")),
    )
    with pytest.raises(writer.ArticleGenerationError, match="provider down"):
        writer.produce_article(topic)
