"""RSS 抓取器：读取 sources.yaml，抓取全部信息源，产出统一格式的候选条目。

设计要点：
- 单个源失败只打警告、不中断（有些 RSS 源就是偶尔抽风）
- 每条带 priority / category / 时间戳，供 LLM 筛选和兜底排序使用
"""
import calendar
import concurrent.futures
import logging
import ssl
import time
from dataclasses import asdict, dataclass
from urllib.request import Request, urlopen

import certifi
import feedparser
import yaml

from .safety import clean_plain_text, normalize_url_for_dedupe, safe_http_url

log = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 20
FETCH_RETRIES = 2
MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_FETCH_WORKERS = 6
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


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
    with open(path, encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError(f"信息源配置格式错误: {path} 缺少 sources 列表")

    sources, names, urls = [], set(), set()
    for index, raw in enumerate(payload["sources"], 1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 个信息源必须是对象")
        name = clean_plain_text(raw.get("name"), 100)
        url = safe_http_url(raw.get("url"))
        if not name or not url:
            raise ValueError(f"第 {index} 个信息源缺少合法 name/url")
        try:
            priority = int(raw.get("priority", 3))
        except (TypeError, ValueError) as err:
            raise ValueError(f"信息源 {name} 的 priority 必须是整数") from err
        if not 1 <= priority <= 5:
            raise ValueError(f"信息源 {name} 的 priority 必须在 1-5 之间")
        if name in names or url in urls:
            raise ValueError(f"信息源重复: {name} / {url}")
        names.add(name)
        urls.add(url)
        sources.append({
            "name": name,
            "url": url,
            "category": clean_plain_text(raw.get("category"), 100),
            "priority": priority,
        })
    return sources


def _clean_summary(raw: str, limit: int = 500) -> str:
    """RSS 摘要里经常混着 HTML 标签和空白，清洗成纯文本。"""
    return clean_plain_text(raw, limit)


def _entry_ts(entry, now: float) -> float:
    # feedparser 的 *_parsed 是 UTC struct_time，必须用 timegm 而不是 mktime
    # （mktime 会按本地时区换算，在 UTC+8 环境下所有条目会"凭空变旧" 8 小时）
    for attr in ("published_parsed", "updated_parsed"):
        st = getattr(entry, attr, None)
        if st:
            return calendar.timegm(st)
    return now


def _download_feed(
    url: str,
    timeout: int = FETCH_TIMEOUT_SECONDS,
    retries: int = FETCH_RETRIES,
) -> bytes:
    """Download one bounded-size feed with timeout and short exponential retries."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0 (ai-daily-pipeline)"})
            with urlopen(  # noqa: S310 - URLs are validated config
                request,
                timeout=timeout,
                context=SSL_CONTEXT,
            ) as response:
                data = response.read(MAX_FEED_BYTES + 1)
            if len(data) > MAX_FEED_BYTES:
                raise ValueError(f"Feed 超过 {MAX_FEED_BYTES // 1024 // 1024} MiB 上限")
            return data
        except Exception as err:  # noqa: BLE001 - network boundary is retried then isolated per source
            last_error = err
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"下载失败（重试 {retries} 次）: {last_error}") from last_error


def download_url(url: str) -> bytes:
    """Download a validated public article/feed URL using the shared network policy."""
    safe_url = safe_http_url(url)
    if not safe_url:
        raise ValueError("URL 不是合法的 HTTP(S) 地址")
    return _download_feed(safe_url)


def fetch_one(source: dict, window_hours: int) -> list[FeedItem]:
    if window_hours <= 0:
        raise ValueError("window_hours 必须大于 0")
    now = time.time()
    parsed = feedparser.parse(_download_feed(source["url"]))

    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"解析失败: {parsed.bozo_exception}")

    items = []
    for entry in parsed.entries:
        ts = min(_entry_ts(entry, now), now)
        # 只保留时间窗口内的条目；没有时间信息的条目也保留（宁多勿漏）
        if now - ts > window_hours * 3600:
            continue
        title = clean_plain_text(entry.get("title"), 300) or "(无标题)"
        link = safe_http_url(entry.get("link"))
        if not link:
            log.warning("[%s] 跳过无合法链接条目: %s", source["name"], title)
            continue
        items.append(FeedItem(
            title=title,
            link=link,
            summary=_clean_summary(entry.get("summary", "")),
            source=source["name"],
            category=source.get("category", ""),
            priority=int(source.get("priority", 3)),
            published_ts=ts,
        ))
    return items


def fetch_all(
    sources: list[dict],
    window_hours: int = 36,
    max_workers: int = MAX_FETCH_WORKERS,
) -> list[FeedItem]:
    """并发抓取全部源；单个源失败只警告，最终顺序仍按配置保持稳定。"""
    if window_hours <= 0:
        raise ValueError("window_hours 必须大于 0")
    if not sources:
        return []

    results: list[list[FeedItem]] = [[] for _ in sources]
    worker_count = max(1, min(max_workers, len(sources)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(fetch_one, source, window_hours): (index, source)
            for index, source in enumerate(sources)
        }
        for future in concurrent.futures.as_completed(future_map):
            index, source = future_map[future]
            try:
                results[index] = future.result()
                log.info("[OK] %-28s %3d 条", source["name"], len(results[index]))
            except Exception as err:  # noqa: BLE001 - 单源失败不应中断整体
                log.warning("[FAIL] %-28s %s", source["name"], err)

    all_items = [item for source_items in results for item in source_items]
    # 去重：不同源经常转发同一条
    seen, deduped = set(), []
    for it in all_items:
        key = normalize_url_for_dedupe(it.link) or it.title.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(it)
    log.info("合计 %d 条（去重后）", len(deduped))
    return deduped
