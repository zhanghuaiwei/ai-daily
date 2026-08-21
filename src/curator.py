"""LLM 筛选器：从几十条候选里挑出 3-5 条高价值内容 + 价值理由。

接口兼容任意 OpenAI 风格的服务（OpenAI / DeepSeek / Kimi / 通义 / GLM ...），
通过环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 控制。

没配 API key 时自动走兜底逻辑（priority + 新鲜度排序取前 5），
保证管道永远能产出东西——先跑通，再调优。
"""
import json
import logging
import os
import time

from openai import OpenAI

from .fetcher import FeedItem

log = logging.getLogger(__name__)

PROMPT = """你是一名「AI 前沿日报」的资深编辑，读者是中文开发者。

从下面的候选新闻中筛选出 3-5 条**最有价值**的，规则：
1. 价值排序：突破性模型/论文发布 > 重大开源项目 > 影响开发者工作流的产品更新 > 行业动态
2. 偏好主题：AI Coding（编程智能体、代码模型、开发者工具）、具身智能（机器人、世界模型、VLA）
3. 排除：纯融资八卦、炒作稿、重复事件
4. 同一事件只保留一条（选信息量最大的来源）
5. summary 用中文重写，50 字以内，程序员能秒懂；reason 说明"为什么值得关注"，1-2 句

候选列表（JSON）：
{items}

只输出严格 JSON，不要任何多余文字，格式：
{{"picks": [{{"title": "...", "link": "...", "source": "...", "category": "...", "summary": "...", "reason": "..."}}]}}"""


def _build_client() -> OpenAI | None:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
    )


def curate_with_llm(items: list[FeedItem], model: str | None = None) -> list[dict]:
    client = _build_client()
    if client is None:
        log.warning("未配置 LLM_API_KEY，走兜底筛选（priority + 新鲜度）")
        return curate_fallback(items)

    model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
    payload = [
        {k: it.to_dict()[k] for k in ("title", "link", "source", "category", "summary")}
        for it in items[:80]  # 控制上下文长度，80 条足够
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROMPT.format(items=json.dumps(payload, ensure_ascii=False))}],
        temperature=0.3,
        timeout=120,
    )
    content = resp.choices[0].message.content.strip()
    # 容错：模型偶尔会包一层 ```json ... ```
    content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    picks = json.loads(content)["picks"]
    log.info("LLM 筛选出 %d 条", len(picks))
    return picks


def curate_fallback(items: list[FeedItem], k: int = 5, per_source: int = 2) -> list[dict]:
    """无 LLM 时的兜底：来源优先级 + 新鲜度排序，且限制单源条数保证多样性。"""
    now = time.time()
    ranked = sorted(items, key=lambda x: (x.priority, -(now - x.published_ts)))
    picked, source_count = [], {}
    for it in ranked:
        if len(picked) >= k:
            break
        if source_count.get(it.source, 0) >= per_source:
            continue
        source_count[it.source] = source_count.get(it.source, 0) + 1
        picked.append({
            "title": it.title,
            "link": it.link,
            "source": it.source,
            "category": it.category,
            "summary": it.summary[:120],
            "reason": "（兜底模式：按来源优先级选出，配置 LLM_API_KEY 后由 AI 撰写推荐理由）",
        })
    return picked
