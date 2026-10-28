"""Daily pipeline: fetch -> one unique AI topic -> research -> one edition article.

线路（edition）决定信息源、输出文件名和选题/写作角度；其余约束两条线完全一致：
单篇产出、全历史去重（链接池共享）、质量诊断只记录不阻断。
"""

from __future__ import annotations

import argparse
import logging
import sys

from .curator import plan_topics_fallback, plan_topics_with_llm
from .editions import DEFAULT_EDITION, EDITIONS
from .fetcher import fetch_all, load_sources
from .history import (
    load_cross_edition_titles,
    load_recent_links,
    load_recent_topic_titles,
)
from .renderer import _today_str, write_article_output
from .researcher import research_topic
from .safety import normalize_url_for_dedupe
from .writer import ArticleGenerationError, produce_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 每日单篇 Markdown 文章生产线")
    parser.add_argument(
        "--edition",
        choices=sorted(EDITIONS),
        default=DEFAULT_EDITION,
        help="推送线路：news=AI 资讯，application=AI 应用（默认 news）",
    )
    parser.add_argument(
        "--sources",
        default=None,
        help="RSS 源配置路径（不传时按线路取默认：news=config/sources.yaml，"
        "application=config/sources-application.yaml）",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=48,
        help="只抓最近 N 小时的条目（默认 48）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="跳过文字模型，生成不可自动投递的 Markdown 结构预览",
    )
    parser.add_argument(
        "--target-chars",
        type=int,
        default=1_200,
        help="文章目标中文字符数（默认 1200 短平快，允许 1200-3500）",
    )
    args = parser.parse_args()
    if args.window_hours <= 0:
        parser.error("--window-hours 必须大于 0")
    if not 1_200 <= args.target_chars <= 3_500:
        parser.error("--target-chars 必须在 1200-3500 之间")

    spec = EDITIONS[args.edition]
    edition_date = _today_str()
    try:
        sources = load_sources(args.sources or spec["sources"])
        items = fetch_all(sources, window_hours=args.window_hours)
    except Exception as err:  # noqa: BLE001 - CLI boundary reports a concise failure
        log.exception("抓取阶段失败: %s", err)
        return 1
    if not items:
        log.error("时间窗内没有任何条目，把 --window-hours 调大后重试")
        return 1

    # 链接去重池是两条线共享的；标题史按线路分开，另加当日另一条线的标题防同日撞题。
    seen_links = load_recent_links("output", edition_date)
    previous_titles = load_recent_topic_titles("output", edition_date, edition=args.edition)
    previous_titles += load_cross_edition_titles("output", edition_date, args.edition)
    unseen_items = [
        item for item in items if normalize_url_for_dedupe(item.link) not in seen_links
    ]
    removed = len(items) - len(unseen_items)
    if removed:
        log.info("永久历史去重排除 %d 条已使用来源", removed)
    if not unseen_items:
        log.error("候选全部在往日文章中使用过；拒绝重复生成")
        return 1

    topics = (
        plan_topics_fallback(unseen_items, target=1, recent_titles=previous_titles)
        if args.dry_run
        else plan_topics_with_llm(
            unseen_items,
            target=1,
            maximum=1,
            recent_titles=previous_titles,
            edition=args.edition,
        )
    )
    if len(topics) != 1:
        log.error("没有找到不重复的 AI 热门或最新话题")
        return 1

    topic = research_topic(topics[0])
    try:
        bundle = produce_article(
            topic,
            target_chars=args.target_chars,
            dry_run=args.dry_run,
            edition=args.edition,
        )
    except ArticleGenerationError as err:
        log.error("文章生成失败，未产生可推送文件: %s", err)
        return 1

    failed_checks = [
        name for name, passed in bundle.get("metrics", {}).get("checks", {}).items() if not passed
    ]
    if failed_checks and not args.dry_run:
        log.warning("质量诊断未全部通过，但不阻止 Markdown 生成与微信投递: %s", ", ".join(failed_checks))

    out_root = "output-dryrun" if args.dry_run else "output"
    try:
        article_path = write_article_output(
            bundle, out_root=out_root, date=edition_date, filename=spec["filename"]
        )
    except OSError as err:
        log.exception("写入 Markdown 失败: %s", err)
        return 1

    line_label = "应用" if args.edition == "application" else "资讯"
    log.info("完成 1 篇%s文章: %s", line_label, bundle["article"]["selected_title"])
    print(f"\nMarkdown 文章:\n  {article_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
