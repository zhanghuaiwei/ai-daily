from types import SimpleNamespace

import pytest

import src.curator as curator
from src.fetcher import FeedItem


def make_item(
    title: str,
    source: str,
    published_ts: float,
    priority: int = 1,
    link: str | None = None,
) -> FeedItem:
    return FeedItem(
        title=title,
        link=link or f"https://example.com/{title}",
        summary=f"summary {title}",
        source=source,
        category="category",
        priority=priority,
        published_ts=published_ts,
    )


def test_fallback_prefers_newer_items_and_caps_each_source():
    items = [
        make_item("new", "A", 300),
        make_item("old", "A", 100),
        make_item("middle", "A", 200),
        make_item("b", "B", 50, priority=2),
    ]
    picks = curator.curate_fallback(items, k=4, per_source=2)
    assert [pick["title"] for pick in picks] == ["new", "middle", "b"]


def test_round_robin_sampling_represents_each_source():
    items = [
        make_item("a1", "A", 3),
        make_item("a2", "A", 2),
        make_item("b1", "B", 1),
    ]
    assert [item["source"] for item in curator._sample_items(items)] == ["A", "B", "A"]


class RaisingCompletions:
    def create(self, **_kwargs):
        raise TimeoutError("simulated timeout")


class ContentCompletions:
    def __init__(self, content: str):
        self.content = content

    def create(self, **_kwargs):
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_transport_error_degrades_to_fallback(monkeypatch):
    items = [make_item("new", "A", 2), make_item("old", "A", 1)]
    monkeypatch.setattr(curator, "_build_client", lambda: fake_client(RaisingCompletions()))
    assert [pick["title"] for pick in curator.curate_with_llm(items)] == ["new", "old"]


def test_invalid_response_shape_degrades_to_fallback(monkeypatch):
    items = [make_item("new", "A", 2), make_item("old", "B", 1)]
    monkeypatch.setattr(
        curator,
        "_build_client",
        lambda: fake_client(ContentCompletions('{"picks": "not-a-list"}')),
    )
    assert [pick["title"] for pick in curator.curate_with_llm(items)] == ["new", "old"]


def test_validate_picks_restores_authoritative_candidate_fields():
    items = [make_item(f"item-{index}", f"S{index}", index) for index in range(1, 4)]
    raw = [
        {
            "title": "invented",
            "link": item.link,
            "source": "invented",
            "category": "invented",
            "summary": "<b>中文摘要</b>",
            "reason": "推荐理由",
        }
        for item in items
    ]
    picks = curator._validate_picks(raw, items)
    assert [pick["title"] for pick in picks] == [item.title for item in items]
    assert picks[0]["source"] == items[0].source
    assert picks[0]["summary"] == "中文摘要"


def test_validate_picks_rejects_invented_link():
    items = [make_item(f"item-{index}", f"S{index}", index) for index in range(1, 4)]
    raw = [
        {
            "title": "x",
            "link": "https://attacker.example/item",
            "source": "x",
            "category": "x",
            "summary": "摘要",
            "reason": "理由",
        }
        for _ in range(3)
    ]
    with pytest.raises(ValueError, match="不属于候选列表"):
        curator._validate_picks(raw, items)


def test_topic_validation_clusters_real_candidate_sources():
    items = [make_item(f"item-{index}", f"S{index}", index) for index in range(1, 4)]
    raw = [{
        "working_title": "一个中文选题",
        "angle": "解释技术原理与实际影响",
        "reason": "有两个来源可以交叉验证",
        "source_links": [items[0].link, items[1].link],
    }]
    topics = curator._validate_topics(raw, items, maximum=3)
    assert topics[0]["ai_selected"] is True
    assert [source["link"] for source in topics[0]["sources"]] == [items[0].link, items[1].link]


def test_topic_validation_rejects_source_reused_across_topics():
    items = [make_item(f"item-{index}", f"S{index}", index) for index in range(1, 4)]
    raw = [
        {"working_title": "话题一", "angle": "角度", "reason": "理由", "source_links": [items[0].link]},
        {"working_title": "话题二", "angle": "角度", "reason": "理由", "source_links": [items[0].link]},
    ]
    with pytest.raises(ValueError, match="重复使用"):
        curator._validate_topics(raw, items, maximum=3)


def test_fallback_topic_count_never_exceeds_target():
    items = [make_item(f"item-{index}", f"S{index}", index) for index in range(1, 5)]
    topics = curator.plan_topics_fallback(items, target=2)
    assert len(topics) == 2
    assert all(topic["ai_selected"] is False for topic in topics)


def test_fallback_prioritizes_ai_relevance_before_source_priority():
    items = [
        make_item("Traffic camera policy", "News", 3, priority=1),
        make_item("New reasoning model for agents", "Research", 2, priority=3),
    ]
    picks = curator.curate_fallback(items, k=1)
    assert picks[0]["title"] == "New reasoning model for agents"
