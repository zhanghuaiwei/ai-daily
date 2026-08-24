"""管道入口：抓取 -> 独立选题 -> 调研写作 -> 配图 -> 质量门禁 -> 产物。

用法：
    python -m src.pipeline                  # 完整流程
    python -m src.pipeline --window-hours 48  # 扩大抓取时间窗（周末信息少时用）
    python -m src.pipeline --dry-run        # 不调 LLM，生成待审核结构预览
"""
import argparse
import logging
import sys

from .curator import plan_topics_fallback, plan_topics_with_llm
from .fetcher import fetch_all, load_sources
from .history import load_recent_links, load_recent_topic_titles
from .illustrator import generate_visuals_for_bundles
from .renderer import _today_str, write_article_outputs, write_outputs
from .researcher import research_topics
from .safety import normalize_url_for_dedupe
from .writer import produce_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 前沿公众号文章生产线")
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--window-hours", type=int, default=36,
                        help="只抓最近 N 小时的条目（默认 36，衔接上一次运行）")
    parser.add_argument("--dry-run", action="store_true",
                        help="跳过 LLM，生成不可投递的文章结构预览")
    parser.add_argument("--history-days", type=int, default=7,
                        help="排除最近 N 天已发布链接（默认 7；0 表示关闭）")
    parser.add_argument("--articles", type=int, default=2,
                        help="正式文章目标数量（默认 2，允许 1-3）")
    parser.add_argument("--target-chars", type=int, default=2000,
                        help="每篇目标中文字符数（默认 2000，允许 1200-3500）")
    args = parser.parse_args()
    if args.window_hours <= 0:
        parser.error("--window-hours 必须大于 0")
    if args.history_days < 0:
        parser.error("--history-days 不能小于 0")
    if not 1 <= args.articles <= 3:
        parser.error("--articles 必须在 1-3 之间")
    if not 1200 <= args.target_chars <= 3500:
        parser.error("--target-chars 必须在 1200-3500 之间")

    edition_date = _today_str()
    try:
        # 1. 抓取
        sources = load_sources(args.sources)
        items = fetch_all(sources, window_hours=args.window_hours)
    except Exception as err:  # noqa: BLE001 - CLI boundary reports a concise failure
        log.exception("抓取阶段失败: %s", err)
        return 1
    if not items:
        log.error("时间窗内没有任何条目，把 --window-hours 调大试试")
        return 1

    # 2. 跨天去重（当天重跑不受影响）
    seen_links = load_recent_links("output", edition_date, args.history_days)
    recent_titles = load_recent_topic_titles("output", edition_date, args.history_days)
    unseen_items = [
        item for item in items
        if normalize_url_for_dedupe(item.link) not in seen_links
    ]
    removed = len(items) - len(unseen_items)
    if removed:
        log.info("跨天去重排除 %d 条（回看 %d 天）", removed, args.history_days)
    if not unseen_items:
        log.warning("候选全部在近期出现过，为保证有产出，本次允许重复")
        unseen_items = items

    # 3. 独立话题规划 + 跨源调研
    topics = (
        plan_topics_fallback(unseen_items, args.articles)
        if args.dry_run
        else plan_topics_with_llm(
            unseen_items,
            target=args.articles,
            maximum=3,
            recent_titles=recent_titles,
        )
    )
    if not topics:
        log.error("没有可写成正式文章的话题")
        return 1
    researched_topics = research_topics(topics)

    # 4. 一话题一文章：调研卡 -> 初稿 -> 扩写润色 -> 终审
    bundles = [
        produce_article(
            topic,
            target_chars=args.target_chars,
            dry_run=args.dry_run,
        )
        for topic in researched_topics
    ]
    # 5. 可选配图：尝试 1 张封面和 0-5 张正文插图，失败仍保留文字成品
    out_root = "output-dryrun" if args.dry_run else "output"
    bundles = generate_visuals_for_bundles(bundles, out_root, edition_date)

    overview_picks = []
    for bundle in bundles:
        topic = bundle["topic"]
        article = bundle["article"]
        primary = topic.get("evidence", [{}])[0] if topic.get("evidence") else {}
        overview_picks.append({
            "title": article["selected_title"],
            "link": primary.get("url", ""),
            "source": primary.get("source", "多源调研"),
            "category": "独立文章",
            "summary": article["abstract"],
            "reason": topic.get("reason", ""),
        })

    # 6. 渲染总览 + 每个话题的独立文章
    try:
        overview_paths = write_outputs(
            overview_picks,
            out_root=out_root,
            date=edition_date,
        )
        article_paths = write_article_outputs(bundles, out_root=out_root, date=edition_date)
    except OSError as err:
        log.exception("写入产物失败: %s", err)
        return 1

    log.info("完成。今日生成 %d 篇独立文章：", len(article_paths))
    for index, item in enumerate(article_paths, 1):
        status = "可发布" if item["publishable"] else "待人工审核"
        log.info("  %d. [%s] %s", index, status, item["title"])
    print(f"\n选题总览:\n  {overview_paths['wechat_html']}")
    for item in article_paths:
        print(f"独立文章:\n  {item['wechat_html']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
