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

# 轻量 .env 加载：key 持久化到项目根目录 .env，避免每次手动 export。
# TODO(学习者): 想深入可换 python-dotenv，但这里几行就够用，不引额外依赖。
def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


PROMPT = """你是一名「AI 前沿日报」的资深编辑，读者是中文开发者。

从下面的候选新闻中筛选出 3-5 条**最有价值**的，规则：
1. 价值排序：突破性模型/论文发布 > 重大开源项目 > 影响开发者工作流的产品更新 > 行业动态
2. 偏好主题：AI Coding（编程智能体、代码模型、开发者工具）、具身智能（机器人、世界模型、VLA）
3. 排除：纯融资八卦、炒作稿、重复事件
4. 同一事件只保留一条（选信息量最大的来源）
5. **多样性硬约束：论文类最多 2 条**，其余从产品发布/开源项目/社区热点中选，避免日报被单一类型或单一来源刷屏
6. summary 用中文重写，50 字以内，程序员能秒懂；reason 说明"为什么值得关注"，1-2 句

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
        base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    )


def _sample_items(items: list[FeedItem], limit: int = 80) -> list[dict]:
    """按源轮询采样：保证每个源都有代表进入 payload。

    背景：直接 items[:80] 会被条数最多的源（如 arXiv 一次 290 条）占满，
    LLM 根本看不到其他源的内容，导致日报单一化。
    """
    by_source: dict[str, list[FeedItem]] = {}
    for it in items:
        by_source.setdefault(it.source, []).append(it)
    sampled: list[FeedItem] = []
    i = 0
    while len(sampled) < limit:
        added = False
        for queue in by_source.values():
            if i < len(queue):
                sampled.append(queue[i])
                added = True
                if len(sampled) >= limit:
                    break
        if not added:  # 所有源都取完了
            break
        i += 1
    return [
        {k: it.to_dict()[k] for k in ("title", "link", "source", "category", "summary")}
        for it in sampled
    ]


def curate_with_llm(items: list[FeedItem], model: str | None = None) -> list[dict]:
    client = _build_client()
    if client is None:
        log.warning("未配置 LLM_API_KEY，走兜底筛选（priority + 新鲜度）")
        return curate_fallback(items)

    model = model or os.environ.get("LLM_MODEL", "deepseek-v4-pro")
    payload = _sample_items(items)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROMPT.format(items=json.dumps(payload, ensure_ascii=False))}],
        temperature=0.3,
        timeout=300,  # 推理模型（v4-pro 类）思考可能要 1-2 分钟
    )
    content = resp.choices[0].message.content.strip()
    # 容错清洗：推理模型可能带 <think> 块或 ```json 包裹
    if "</think>" in content:
        content = content.split("</think>", 1)[1].strip()
    content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    s, e = content.find("{"), content.rfind("}")
    if s != -1 and e > s:
        content = content[s:e + 1]
    try:
        picks = json.loads(content)["picks"]
    except (json.JSONDecodeError, KeyError) as err:
        # LLM 输出不规范不应该毁掉整天的日报，降级兜底并保留现场便于排查
        log.error("LLM 输出解析失败(%s)，降级兜底。原始输出前 300 字: %.300s", err, content)
        return curate_fallback(items)
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
