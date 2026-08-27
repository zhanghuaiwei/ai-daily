from types import SimpleNamespace

import pytest

import src.curator as curator
from src.fetcher import FeedItem

_PROVIDER_ENV_VARS = (
    "LLM_PROVIDER_ORDER",
    "GPT_API_KEY",
    "OPENAI_API_KEY",
    "LLM_API_KEY",
    "DEEPSEEK_API_KEY",
    "WORKBUDDY_API_KEY",
    "TOKENHUB_API_KEY",
    "QWEN_API_KEY",
    "DASHSCOPE_API_KEY",
    "LLM_BASE_URL",
    "GPT_BASE_URL",
    "OPENAI_BASE_URL",
    "DEEPSEEK_BASE_URL",
    "WORKBUDDY_BASE_URL",
    "TOKENHUB_BASE_URL",
    "QWEN_BASE_URL",
    "DASHSCOPE_BASE_URL",
)


@pytest.fixture(autouse=True)
def isolate_provider_state(monkeypatch):
    for name in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    curator._UNAVAILABLE_PROVIDERS.clear()


def make_item(
    title: str,
    source: str,
    published_ts: float,
    priority: int = 1,
    link: str | None = None,
    category: str = "AI",
) -> FeedItem:
    return FeedItem(
        title=title,
        link=link or f"https://example.com/{title}",
        summary=f"summary {title}",
        source=source,
        category=category,
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


class RecordingCompletions(ContentCompletions):
    def __init__(self, content: str):
        super().__init__(content)
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return super().create(**kwargs)


def test_openai_defaults_are_used_when_optional_values_are_empty(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "")
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(curator, "OpenAI", fake_openai)
    assert curator._build_client() is not None
    assert captured["base_url"] == "https://api.openai.com/v1"


def test_request_json_uses_gpt_5_6_structured_output_options(monkeypatch):
    completions = RecordingCompletions('{"result": "ok"}')
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(curator, "_build_client", lambda _provider=None: fake_client(completions))
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "medium")

    assert curator.request_json("system", "user", temperature=0.6) == {"result": "ok"}
    assert completions.kwargs["model"] == "gpt-5.6-terra"
    assert completions.kwargs["reasoning_effort"] == "medium"
    assert completions.kwargs["response_format"] == {"type": "json_object"}
    assert "temperature" not in completions.kwargs


def test_non_gpt_5_6_provider_keeps_temperature(monkeypatch):
    completions = RecordingCompletions('{"result": "ok"}')
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(curator, "_build_client", lambda _provider=None: fake_client(completions))

    curator.request_json("system", "user", model="compatible-model", temperature=0.2)
    assert completions.kwargs["temperature"] == 0.2
    assert "reasoning_effort" not in completions.kwargs


def test_qwen_disables_thinking_and_bounds_output(monkeypatch):
    completions = RecordingCompletions('{"result": "ok"}')
    monkeypatch.setenv("QWEN_API_KEY", "qwen-key")
    monkeypatch.setattr(curator, "_build_client", lambda _provider=None: fake_client(completions))

    curator.request_json("system", "user", max_output_tokens=1_200)
    assert completions.kwargs["extra_body"] == {"enable_thinking": False}
    assert completions.kwargs["max_tokens"] == 1_200
    assert completions.kwargs["response_format"] == {"type": "json_object"}


def test_json_parser_repairs_only_common_trailing_commas():
    assert curator._parse_json_content('{"items": [1, 2,],}') == {"items": [1, 2]}


def test_json_parser_rejects_non_json_prose():
    with pytest.raises(ValueError):
        curator._parse_json_content("this is not json")


def test_transport_error_degrades_to_fallback(monkeypatch):
    items = [make_item("new", "A", 2), make_item("old", "A", 1)]
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        curator,
        "_build_client",
        lambda _provider=None: fake_client(RaisingCompletions()),
    )
    assert [pick["title"] for pick in curator.curate_with_llm(items)] == ["new", "old"]


def test_invalid_response_shape_degrades_to_fallback(monkeypatch):
    items = [make_item("new", "A", 2), make_item("old", "B", 1)]
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        curator,
        "_build_client",
        lambda _provider=None: fake_client(ContentCompletions('{"picks": "not-a-list"}')),
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


def test_topic_validation_rejects_prior_topic_even_with_a_new_link():
    items = [make_item("New agent memory release", "Official", 1)]
    raw = [{
        "working_title": "AI 智能体记忆迎来新变化",
        "angle": "解释更新",
        "reason": "热门",
        "source_links": [items[0].link],
    }]
    with pytest.raises(ValueError, match="往日话题重复"):
        curator._validate_topics(
            raw,
            items,
            maximum=1,
            recent_titles=["AI 智能体记忆迎来新变化！"],
        )


def test_fallback_topic_count_never_exceeds_target():
    items = [make_item(f"item-{index}", f"S{index}", index) for index in range(1, 5)]
    topics = curator.plan_topics_fallback(items, target=2)
    assert len(topics) == 2
    assert all(topic["ai_selected"] is False for topic in topics)


def test_topic_fallback_uses_latest_unique_ai_item():
    items = [
        make_item("Old AI model", "A", 1),
        make_item("Newest AI agent", "B", 3),
        make_item("Football transfer", "C", 4, category="General"),
    ]
    topics = curator.plan_topics_fallback(
        items,
        target=1,
        recent_titles=["Old AI model"],
    )
    assert [topic["working_title"] for topic in topics] == ["Newest AI agent"]


def test_fallback_prioritizes_ai_relevance_before_source_priority():
    items = [
        make_item("Traffic camera policy", "News", 3, priority=1, category="General"),
        make_item("New reasoning model for agents", "Research", 2, priority=3),
    ]
    picks = curator.curate_fallback(items, k=1)
    assert picks[0]["title"] == "New reasoning model for agents"


def test_qwen_is_always_the_last_configured_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_ORDER", "qwen,deepseek,gpt,workbuddy")
    monkeypatch.setenv("LLM_API_KEY", "gpt-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("WORKBUDDY_API_KEY", "workbuddy-key")
    monkeypatch.setenv("QWEN_API_KEY", "qwen-key")

    assert [provider.name for provider in curator._configured_providers()] == [
        "deepseek",
        "gpt",
        "workbuddy",
        "qwen",
    ]


def test_ollama_and_local_model_endpoint_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    assert curator._provider_config("gpt") is None


def test_topic_planner_accepts_up_to_configured_maximum(monkeypatch):
    items = [
        make_item(
            f"AI item {index}",
            f"S{index}",
            index,
            link=f"https://example.com/ai-item-{index}",
        )
        for index in range(1, 4)
    ]
    raw_topics = [
        {
            "working_title": f"AI 热门话题 {index}",
            "angle": "技术变化",
            "reason": "多个来源正在关注",
            "source_links": [items[index - 1].link],
        }
        for index in range(1, 4)
    ]
    monkeypatch.setattr(curator, "_configured_providers", lambda: [object()])
    monkeypatch.setattr(curator, "request_json", lambda *_args, **_kwargs: {"topics": raw_topics})
    topics = curator.plan_topics_with_llm(items, target=2, maximum=3)
    assert len(topics) == 3
    assert all(topic["ai_selected"] for topic in topics)


class FakeQuotaError(Exception):
    status_code = 429


class FakePaymentRequiredError(Exception):
    status_code = 402


def test_payment_required_opens_provider_circuit():
    assert curator._provider_is_unavailable(FakePaymentRequiredError("Insufficient Balance"))


class CountingCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.content = content
        self.error = error
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_quota_failure_switches_provider_and_opens_circuit(monkeypatch):
    providers = [
        curator.LLMProvider("gpt", "gpt-key", "https://gpt.example/v1", "gpt-5.6-terra"),
        curator.LLMProvider("qwen", "qwen-key", "https://qwen.example/v1", "qwen-model"),
    ]
    gpt = CountingCompletions(error=FakeQuotaError("insufficient_quota"))
    qwen = CountingCompletions(content='{"result": "千问兜底成功"}')
    clients = {"gpt": fake_client(gpt), "qwen": fake_client(qwen)}
    monkeypatch.setattr(curator, "_configured_providers", lambda: providers)
    monkeypatch.setattr(curator, "_build_client", lambda provider=None: clients[provider.name])

    assert curator.request_json("system", "user") == {"result": "千问兜底成功"}
    assert curator.request_json("system", "user") == {"result": "千问兜底成功"}
    assert gpt.calls == 1
    assert qwen.calls == 2
    assert "gpt" in curator._UNAVAILABLE_PROVIDERS


def test_invalid_json_tries_the_next_provider_without_opening_circuit(monkeypatch):
    providers = [
        curator.LLMProvider("deepseek", "ds-key", "https://ds.example", "deepseek-model"),
        curator.LLMProvider("qwen", "qwen-key", "https://qwen.example", "qwen-model"),
    ]
    deepseek = CountingCompletions(content="not-json")
    qwen = CountingCompletions(content='{"result": "ok"}')
    clients = {"deepseek": fake_client(deepseek), "qwen": fake_client(qwen)}
    monkeypatch.setattr(curator, "_configured_providers", lambda: providers)
    monkeypatch.setattr(curator, "_build_client", lambda provider=None: clients[provider.name])

    assert curator.request_json("system", "user") == {"result": "ok"}
    assert "deepseek" not in curator._UNAVAILABLE_PROVIDERS


def test_provider_error_summary_redacts_api_key():
    provider = curator.LLMProvider("qwen", "secret-key", "https://qwen.example", "qwen")
    summary = curator._safe_error_summary(RuntimeError("bad secret-key request"), provider)
    assert "secret-key" not in summary
    assert "***" in summary
