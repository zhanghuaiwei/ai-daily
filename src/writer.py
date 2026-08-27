"""Research, write, edit and quality-gate one Chinese public-account article per topic."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping

from .curator import SYSTEM_PROMPT, request_json
from .safety import clean_plain_text

log = logging.getLogger(__name__)
AI_TASTE_PHRASES = (
    "随着人工智能的快速发展",
    "在这个日新月异的时代",
    "值得注意的是",
    "不可否认的是",
    "综上所述",
    "总而言之",
    "无疑将",
    "开启了新的篇章",
    "带来了无限可能",
    "让我们拭目以待",
    "赋能千行百业",
    "颠覆性变革",
    "在当今数字化时代",
    "毋庸置疑",
    "我们可以看到",
    "由此可见",
)
REQUIRED_REVIEW_DIMENSIONS = {
    "timeliness",
    "frontier",
    "accuracy",
    "topic_focus",
    "logic",
    "structure",
    "readability",
    "chinese_style",
    "human_style",
    "headline",
}
CRITICAL_REVIEW_THRESHOLDS = {
    "topic_focus": 85,
    "logic": 85,
    "structure": 85,
    "headline": 85,
}
MIN_REVIEW_TOTAL = 85
MIN_HEADLINE_SCORE = 85
_ATTENTION_TITLE_MARKERS = (
    "？",
    "！",
    "：",
    "为什么",
    "如何",
    "竟然",
    "终于",
    "真相",
    "背后",
    "没想到",
    "正在",
    "首次",
    "关键",
    "危险",
    "机会",
    "改变",
)
_ENGLISH_GLOSS_RE = re.compile(r"[\u4e00-\u9fff]{2,}[（(]([A-Za-z][A-Za-z ._-]{1,50})[)）]")
_ALLOWED_TECH_GLOSSES = {
    "ai",
    "api",
    "llm",
    "mcp",
    "ocr",
    "rag",
    "sdk",
    "transformer",
    "vla",
    "vlm",
}


class ArticleGenerationError(RuntimeError):
    """Raised when no complete daily article can be produced."""

RESEARCH_PROMPT = """请基于下面的选题和证据包，制作写作前的事实调研卡。

要求：
- 只使用证据包中的信息，不得用记忆补造数字、结论、机构表态或时间；
- 区分已证实事实、来源方自述、合理推断和仍不确定的信息；
- 每条事实必须填写支持它的 source_ids；
- 找出泛读者真正会问的问题，以及文章需要解释的技术概念；
- 技术概念优先用中文解释，只保留必要的模型名、论文名、API、代码或行业术语；
- 证据互相冲突或不足时写入 uncertainties，不要替来源下结论。

<topic_and_evidence>
{payload}
</topic_and_evidence>

只输出严格 JSON：
{{"facts":[{{"claim":"事实或带归属的来源方说法","source_ids":[1],"certainty":"confirmed|claimed|inferred"}}],
"uncertainties":["尚不能确认的内容"],"reader_questions":["读者关心的问题"],
"key_terms":[{{"term":"必要技术术语","explanation_cn":"简洁中文解释"}}],
"recommended_structure":["建议章节"]}}"""

WRITE_PROMPT = """请根据调研卡写一篇可供编辑审核的中文公众号文章初稿。

受众与篇幅：
- 面向泛读者，不假设读者有专业背景；目标正文约 {target_chars} 个中文字符；
- 技术准确，但解释到“能理解为什么重要”即可，不写成论文综述或产品软文；
- 中文为主。模型名、论文名、API、代码等技术专名可保留英文，普通概念不要附带英文翻译。

公众号文章标准：
- 一个话题只写一篇，不拼接无关新闻；
- 写作前先用一句话确定全文唯一的中心命题，正文中的每个章节都必须直接服务于这个命题；
- 开头直接从事实、冲突、问题或具体场景切入，不使用宏大时代背景；
- 结构为：切入 → 背景问题 → 核心技术 → 实际影响 → 局限/争议 → 读者建议 → 收束；
- 每一节只承担一个清晰作用，前一节提出的问题要在后文得到解释，事实、分析和结论之间不能跳步；
- 段落和章节之间要有自然过渡，句式长短有变化，避免连续排比、套路小标题和重复总结；
- 不使用“值得注意的是、综上所述、让我们拭目以待、赋能、颠覆性变革”等 AI 腔套话；
- 事实段落填写 source_ids；观点必须明确写成判断或推测；
- 不编造采访、体验、数据或引用原话。

标题 A/B 测试：给出 5 个有点击冲动的自然中文标题，覆盖悬念型、冲突型、问题型和影响型。
允许适度“标题党”，可以使用问句、反差、强冲突和意外结果吸引注意，但标题中的主体、变化和结论必须能被
证据支持，不得虚构事实或承诺正文没有的内容。避免“一个重大变化”“你需要知道”等空泛表达。
score 按准确性、具体性、读者收益和传播力综合评分，selected_title 选择最吸引人且事实准确的一项。

<material>
{payload}
</material>

只输出严格 JSON：
{{"title_candidates":[{{"title":"标题","angle":"测试角度","score":88}}],
"abstract":"80-120字摘要","lead":"开头段",
"sections":[{{"heading":"中文小标题","paragraphs":[{{"text":"段落","source_ids":[1]}}]}}],
"conclusion":"自然收束，不喊口号"}}"""

EDIT_PROMPT = """你是公众号终审编辑。请对文章进行扩写、润色和结构修订，并完成质量自检。

编辑目标：
1. 删除 AI 味：空洞判断、机械排比、重复总结、模板化过渡、夸张宣传和假装亲历；
2. 补齐必要背景与章节过渡，让泛读者读得懂，但不要把普通词汇翻译成英文；
3. 技术名词、模型名、论文名、API 和代码可保留英文，其余尽量使用自然中文；
4. 所有具体事实和数字必须能追溯到 source_ids；证据不足就降低语气或删除；
5. 用一句话概括全文中心命题；删掉偏离命题的材料，确保读者读完能清楚复述文章究竟在讲什么；
6. 检查论证链：问题、证据、解释、影响、局限和结论必须前后衔接，不能把相关性写成因果关系；
7. 文章长度接近 {target_chars} 个中文字符，保留 4-8 个职责明确、标题不重复的小节；
8. 重做标题评分，selected_title 必须是候选中最吸引人且与正文一致的标题；允许问句、悬念、反差和
   适度“标题党”，但标题中的事实、主体和结论不得夸大或虚构；
9. 逐项检查实时性、前沿性、事实可靠性、主题聚焦、逻辑、结构、可读性、中文表达、AI 味和标题质量。
   topic_focus、logic、structure、headline 任一项低于 85 分，都必须在 issues 中说明，不得虚报分数；
10. 输出只服务于 Markdown 公众号文章，段落短而有节奏，小标题清楚，重点信息前置。

<draft_and_material>
{payload}
</draft_and_material>

只输出严格 JSON，article 的结构必须与初稿相同，并额外给出 selected_title：
{{"article":{{"title_candidates":[{{"title":"标题","angle":"角度","score":90}}],
"selected_title":"最终标题","abstract":"摘要","lead":"开头",
"sections":[{{"heading":"小标题","paragraphs":[{{"text":"段落","source_ids":[1]}}]}}],
"conclusion":"结尾"}},
"review":{{"total":88,"dimensions":{{"timeliness":90,"frontier":88,"accuracy":90,
"topic_focus":90,"logic":88,"structure":86,"readability":90,"chinese_style":90,
"human_style":86,"headline":88}},
"issues":["仍需人工关注的问题"],"fact_check":"pass|needs_review"}}}}"""


def _source_ids(evidence: list[dict]) -> set[int]:
    return {item["id"] for item in evidence if isinstance(item.get("id"), int)}


def _sanitize_ids(value: object, valid_ids: set[int]) -> list[int]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, int) and item in valid_ids})


def _sanitize_research_brief(raw: object, evidence: list[dict]) -> dict:
    if not isinstance(raw, Mapping):
        raise ValueError("调研卡不是对象")
    valid_ids = _source_ids(evidence)
    facts = []
    for item in raw.get("facts", []):
        if not isinstance(item, Mapping):
            continue
        claim = clean_plain_text(item.get("claim"), 500)
        ids = _sanitize_ids(item.get("source_ids"), valid_ids)
        certainty = item.get("certainty")
        if claim and ids and certainty in {"confirmed", "claimed", "inferred"}:
            facts.append({"claim": claim, "source_ids": ids, "certainty": certainty})
    if not facts:
        raise ValueError("调研卡没有可追溯事实")

    terms = []
    for item in raw.get("key_terms", []):
        if isinstance(item, Mapping):
            term = clean_plain_text(item.get("term"), 100)
            explanation = clean_plain_text(item.get("explanation_cn"), 300)
            if term and explanation:
                terms.append({"term": term, "explanation_cn": explanation})
    return {
        "facts": facts[:15],
        "uncertainties": [
            clean_plain_text(item, 400)
            for item in raw.get("uncertainties", [])[:10]
            if clean_plain_text(item, 400)
        ],
        "reader_questions": [
            clean_plain_text(item, 300)
            for item in raw.get("reader_questions", [])[:10]
            if clean_plain_text(item, 300)
        ],
        "key_terms": terms[:10],
        "recommended_structure": [
            clean_plain_text(item, 100)
            for item in raw.get("recommended_structure", [])[:8]
            if clean_plain_text(item, 100)
        ],
    }


def _sanitize_title_candidates(raw: object, strict: bool = True) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("title_candidates 必须是列表")
    candidates, seen = [], set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        title = clean_plain_text(item.get("title"), 64)
        angle = clean_plain_text(item.get("angle"), 120)
        try:
            score = max(0, min(int(item.get("score", 0)), 100))
        except (TypeError, ValueError):
            score = 0
        if title and title not in seen:
            candidates.append({"title": title, "angle": angle, "score": score})
            seen.add(title)
    minimum = 3 if strict else 1
    if not minimum <= len(candidates) <= 5:
        raise ValueError(f"标题候选必须是 {minimum}-5 个")
    best = max(candidates, key=lambda item: item["score"])
    if strict and not _has_attention_hook(best["title"]):
        best["title"] = clean_plain_text(f"{best['title']}：为什么这次不一样？", 64)
    return candidates


def _has_attention_hook(title: str) -> bool:
    return any(marker in title for marker in _ATTENTION_TITLE_MARKERS)


def _remove_ai_taste(value: object, limit: int) -> str:
    """Deterministically remove known model-like filler after normal sanitization."""
    text = clean_plain_text(value, limit)
    for phrase in AI_TASTE_PHRASES:
        text = text.replace(phrase, "")
    text = re.sub(r"^[，,。；;：:\s]+|[，,；;：:]\s*[。！？!?]", "", text).strip()
    return text[:limit]


def _sanitize_article(raw: object, evidence: list[dict], strict: bool = True) -> dict:
    if not isinstance(raw, Mapping):
        raise ValueError("文章不是对象")
    valid_ids = _source_ids(evidence)
    candidates = _sanitize_title_candidates(raw.get("title_candidates"), strict=strict)
    selected = clean_plain_text(raw.get("selected_title"), 64)
    best_title = max(candidates, key=lambda item: item["score"])["title"]
    if selected not in {item["title"] for item in candidates} or selected != best_title:
        selected = best_title

    sections = []
    raw_sections = raw.get("sections")
    if not isinstance(raw_sections, list):
        raise ValueError("sections 必须是列表")
    for section in raw_sections:
        if not isinstance(section, Mapping):
            continue
        heading = _remove_ai_taste(section.get("heading"), 80)
        paragraphs = []
        for paragraph in section.get("paragraphs", []):
            if isinstance(paragraph, str):
                text, ids = _remove_ai_taste(paragraph, 1_000), []
            elif isinstance(paragraph, Mapping):
                text = _remove_ai_taste(paragraph.get("text"), 1_000)
                ids = _sanitize_ids(paragraph.get("source_ids"), valid_ids)
            else:
                continue
            if text:
                paragraphs.append({"text": text, "source_ids": ids})
        if heading and paragraphs:
            sections.append({"heading": heading, "paragraphs": paragraphs})
    minimum_sections = 4 if strict else 1
    if not minimum_sections <= len(sections) <= 8:
        raise ValueError(f"有效章节必须是 {minimum_sections}-8 个")
    abstract = _remove_ai_taste(raw.get("abstract"), 220)
    lead = _remove_ai_taste(raw.get("lead"), 600)
    conclusion = _remove_ai_taste(raw.get("conclusion"), 600)
    if not abstract or not lead or not conclusion:
        raise ValueError("摘要、开头或结尾为空")
    return {
        "title_candidates": candidates,
        "selected_title": selected,
        "abstract": abstract,
        "lead": lead,
        "sections": sections,
        "conclusion": conclusion,
    }


def _sanitize_review(raw: object) -> dict:
    if not isinstance(raw, Mapping):
        return {"total": 0, "dimensions": {}, "issues": ["未完成模型终审"], "fact_check": "needs_review"}
    try:
        total = max(0, min(int(raw.get("total", 0)), 100))
    except (TypeError, ValueError):
        total = 0
    dimensions = {}
    if isinstance(raw.get("dimensions"), Mapping):
        for key, value in raw["dimensions"].items():
            try:
                dimensions[clean_plain_text(str(key), 40)] = max(0, min(int(value), 100))
            except (TypeError, ValueError):
                continue
    fact_check = raw.get("fact_check")
    if fact_check not in {"pass", "needs_review"}:
        fact_check = "needs_review"
    return {
        "total": total,
        "dimensions": dimensions,
        "issues": [
            clean_plain_text(item, 300)
            for item in raw.get("issues", [])[:10]
            if clean_plain_text(item, 300)
        ],
        "fact_check": fact_check,
    }


def build_research_brief(topic: dict, model: str | None = None) -> dict:
    payload = {
        "working_title": topic.get("working_title"),
        "angle": topic.get("angle"),
        "evidence": topic.get("evidence", []),
    }
    raw = request_json(
        SYSTEM_PROMPT,
        RESEARCH_PROMPT.format(payload=json.dumps(payload, ensure_ascii=False)),
        model=model,
        temperature=0.1,
    )
    return _sanitize_research_brief(raw, topic.get("evidence", []))


def write_draft(
    topic: dict,
    brief: dict,
    target_chars: int = 2_000,
    model: str | None = None,
) -> dict:
    payload = {
        "topic": {key: topic.get(key) for key in ("working_title", "angle", "reason")},
        "research_brief": brief,
        "sources": [
            {key: source.get(key) for key in ("id", "title", "source", "url", "published_at")}
            for source in topic.get("evidence", [])
        ],
    }
    raw = request_json(
        SYSTEM_PROMPT,
        WRITE_PROMPT.format(target_chars=target_chars, payload=json.dumps(payload, ensure_ascii=False)),
        model=model,
        temperature=0.6,
    )
    return _sanitize_article(raw, topic.get("evidence", []))


def edit_and_review(
    topic: dict,
    brief: dict,
    draft: dict,
    target_chars: int = 2_000,
    model: str | None = None,
) -> tuple[dict, dict]:
    payload = {
        "topic": {key: topic.get(key) for key in ("working_title", "angle", "reason")},
        "research_brief": brief,
        "sources": [
            {key: source.get(key) for key in ("id", "title", "source", "url", "published_at")}
            for source in topic.get("evidence", [])
        ],
        "draft": draft,
    }
    raw = request_json(
        SYSTEM_PROMPT,
        EDIT_PROMPT.format(target_chars=target_chars, payload=json.dumps(payload, ensure_ascii=False)),
        model=model,
        temperature=0.35,
    )
    article = _sanitize_article(raw.get("article"), topic.get("evidence", []))
    review = _sanitize_review(raw.get("review"))
    return article, review


def article_metrics(article: dict, review: dict, target_chars: int = 2_000) -> dict:
    paragraphs = [
        paragraph
        for section in article.get("sections", [])
        for paragraph in section.get("paragraphs", [])
    ]
    body_parts = [article.get("lead", "")]
    body_parts += [paragraph.get("text", "") for paragraph in paragraphs]
    body_parts.append(article.get("conclusion", ""))
    body = "".join(body_parts)
    chinese = len(re.findall(r"[\u4e00-\u9fff]", body))
    latin = len(re.findall(r"[A-Za-z]", body))
    chinese_ratio = chinese / max(chinese + latin, 1)
    title = article.get("selected_title", "")
    title_length = len(re.sub(r"\s+", "", title))
    title_chinese = len(re.findall(r"[\u4e00-\u9fff]", title))
    title_latin = len(re.findall(r"[A-Za-z]", title))
    title_chinese_ratio = title_chinese / max(title_chinese + title_latin, 1)
    ai_phrases = [phrase for phrase in AI_TASTE_PHRASES if phrase in body]
    english_glosses = [
        match.group(0)
        for match in _ENGLISH_GLOSS_RE.finditer(body)
        if match.group(1).strip().casefold() not in _ALLOWED_TECH_GLOSSES
    ]
    cited = sum(bool(paragraph.get("source_ids")) for paragraph in paragraphs)
    citation_ratio = cited / max(len(paragraphs), 1)
    char_count = len(re.sub(r"\s+", "", body))
    dimensions = review.get("dimensions", {})
    dimension_gate = REQUIRED_REVIEW_DIMENSIONS <= set(dimensions) and all(
        dimensions[name] >= 75 for name in REQUIRED_REVIEW_DIMENSIONS
    )
    headings = [section.get("heading", "").strip() for section in article.get("sections", [])]
    unique_headings = len(headings) == len(set(headings))
    title_scores = [
        item.get("score", 0)
        for item in article.get("title_candidates", [])
        if isinstance(item.get("score"), int)
    ]
    best_title_score = max(title_scores, default=0)
    selected_title_score = next(
        (
            item.get("score", 0)
            for item in article.get("title_candidates", [])
            if item.get("title") == title and isinstance(item.get("score"), int)
        ),
        0,
    )
    critical_dimensions = {
        name: dimensions.get(name, 0) >= minimum
        for name, minimum in CRITICAL_REVIEW_THRESHOLDS.items()
    }
    abstract_count = len(re.sub(r"\s+", "", article.get("abstract", "")))
    checks = {
        "length": int(target_chars * 0.65) <= char_count <= int(target_chars * 1.6),
        "chinese_first": chinese_ratio >= 0.72,
        "chinese_headline": title_chinese_ratio >= 0.55,
        "abstract": 60 <= abstract_count <= 180,
        "human_style": not ai_phrases,
        "no_unnecessary_english_gloss": not english_glosses,
        "citations": citation_ratio >= 0.25,
        "structure": 4 <= len(article.get("sections", [])) <= 8,
        "topic_focus": critical_dimensions["topic_focus"],
        "logical_flow": critical_dimensions["logic"],
        "clear_structure": critical_dimensions["structure"] and unique_headings,
        "headline_ab": len(article.get("title_candidates", [])) >= 3,
        "headline_quality": (
            critical_dimensions["headline"]
            and selected_title_score == best_title_score >= MIN_HEADLINE_SCORE
            and 8 <= title_length <= 40
            and _has_attention_hook(title)
        ),
        "model_review": (
            review.get("total", 0) >= MIN_REVIEW_TOTAL
            and review.get("fact_check") == "pass"
            and dimension_gate
        ),
    }
    return {
        "char_count": char_count,
        "chinese_ratio": round(chinese_ratio, 3),
        "title_chinese_ratio": round(title_chinese_ratio, 3),
        "headline_score": selected_title_score,
        "citation_ratio": round(citation_ratio, 3),
        "ai_phrases": ai_phrases,
        "unnecessary_english_glosses": english_glosses,
        "checks": checks,
        "quality_passed": all(checks.values()),
    }


def fallback_article(topic: dict, error: str = "") -> dict:
    evidence = topic.get("evidence", [])
    paragraphs = []
    for source in evidence:
        summary = clean_plain_text(source.get("excerpt"), 500)
        if summary:
            paragraphs.append({"text": summary, "source_ids": [source["id"]]})
    if not paragraphs:
        paragraphs = [{"text": "当前证据不足，等待人工补充调研后再发布。", "source_ids": []}]
    title = clean_plain_text(topic.get("working_title"), 64) or "待审核选题"
    article = _sanitize_article(
        {
            "title_candidates": [{"title": title, "angle": "兜底标题", "score": 0}],
            "selected_title": title,
            "abstract": "自动写作未完成，以下内容仅作为选题和资料预览，不应直接发布。",
            "lead": clean_plain_text(topic.get("reason"), 500) or "这是一个待进一步调研的话题。",
            "sections": [{"heading": "现有资料", "paragraphs": paragraphs}],
            "conclusion": "请补充事实核验、结构编辑和人工审核后再发布。",
        },
        evidence,
        strict=False,
    )
    review = {
        "total": 0,
        "dimensions": {},
        "issues": [clean_plain_text(error, 300) or "未完成大模型调研与终审"],
        "fact_check": "needs_review",
    }
    return {
        "topic": topic,
        "research_brief": {},
        "article": article,
        "review": review,
        "metrics": article_metrics(article, review),
        "delivery_ready": False,
    }


def produce_article(
    topic: dict,
    target_chars: int = 2_000,
    model: str | None = None,
    dry_run: bool = False,
) -> dict:
    if dry_run:
        return fallback_article(topic, "dry-run 不调用大模型")
    try:
        brief = build_research_brief(topic, model=model)
        draft = write_draft(topic, brief, target_chars=target_chars, model=model)
        try:
            article, review = edit_and_review(
                topic,
                brief,
                draft,
                target_chars=target_chars,
                model=model,
            )
        except Exception as err:  # noqa: BLE001 - preserve a valid draft for manual editing
            log.error("文章终审失败，保留完整初稿并继续生成 Markdown: %s", err)
            article = draft
            review = _sanitize_review({"issues": [f"终审失败: {err}"]})
        metrics = article_metrics(article, review, target_chars=target_chars)
        return {
            "topic": topic,
            "research_brief": brief,
            "article": article,
            "review": review,
            "metrics": metrics,
            "delivery_ready": True,
        }
    except Exception as err:  # noqa: BLE001 - model boundary is converted to a concise pipeline failure
        raise ArticleGenerationError(clean_plain_text(str(err), 300) or type(err).__name__) from None
