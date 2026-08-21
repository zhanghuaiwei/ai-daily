"""RSS 抓取器：读取 sources.yaml，抓取全部信息源，产出统一格式的候选条目。

设计要点：
- 单个源失败只打警告、不中断（有些 RSS 源就是偶尔抽风）
- 每条带 priority / category / 时间戳，供 LLM 筛选和兜底排序使用
"""
import calendar
import logging
import re
import time
from dataclasses import dataclass, asdict

import feedparser
import yaml

log = logging.getLogger(__name__)

# 抓不到时间的条目按"最新"处理，宁多勿漏
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str      # 纯文本摘要，超长截断
    source: str       # 来源名，如 "TLDR AI"
    category: str     # 如 "英文聚合/AI Coding"
    priority: int     # 越小越重要
    published_ts: float

    def to_dict(self) -> dict:
        return asdict(self)


def load_sources(path: str = "config/sources.yaml") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def _clean_summary(raw: str, limit: int = 500) -> str:
    """RSS 摘要里经常混着 HTML 标签和空白，清洗成纯文本。"""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _entry_ts(entry, now: float) -> float:
    # feedparser 的 *_parsed 是 UTC struct_time，必须用 timegm 而不是 mktime
    # （mktime 会按本地时区换算，在 UTC+8 环境下所有条目会"凭空变旧" 8 小时）
    for attr in ("published_parsed", "updated_parsed"):
        st = getattr(entry, attr, None)
        if st:
            return calendar.timegm(st)
    return now


def fetch_one(source: dict, window_hours: int) -> list[FeedItem]:
    now = time.time()
    parsed = feedparser.parse(source["url"], request_headers={
        "User-Agent": "Mozilla/5.0 (ai-daily-pipeline)"
    })

    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"解析失败: {parsed.bozo_exception}")

    items = []
    for entry in parsed.entries:
        ts = _entry_ts(entry, now)
        # 只保留时间窗口内的条目；没有时间信息的条目也保留（宁多勿漏）
        if now - ts > window_hours * 3600:
            continue
        items.append(FeedItem(
            title=entry.get("title", "(无标题)").strip(),
            link=entry.get("link", ""),
            summary=_clean_summary(entry.get("summary", "")),
            source=source["name"],
            category=source.get("category", ""),
            priority=int(source.get("priority", 3)),
            published_ts=ts,
        ))
    return items


def fetch_all(sources: list[dict], window_hours: int = 36) -> list[FeedItem]:
    """抓取全部源。单个源失败只警告。"""
    all_items: list[FeedItem] = []
    for source in sources:
        try:
            items = fetch_one(source, window_hours)
            log.info("[OK] %-28s %3d 条", source["name"], len(items))
            all_items.extend(items)
        except Exception as e:  # noqa: BLE001 - 单源失败不应中断整体
            log.warning("[FAIL] %-28s %s", source["name"], e)
    # 去重：不同源经常转发同一条
    seen, deduped = set(), []
    for it in all_items:
        key = it.link.rstrip("/") or it.title
        if key not in seen:
            seen.add(key)
            deduped.append(it)
    log.info("合计 %d 条（去重后）", len(deduped))
    return deduped
