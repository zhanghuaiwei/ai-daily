"""管道入口：抓取 -> LLM 筛选 -> 渲染 Markdown + 公众号 HTML。

用法：
    python -m src.pipeline                  # 完整流程
    python -m src.pipeline --window-hours 48  # 扩大抓取时间窗（周末信息少时用）
    python -m src.pipeline --dry-run        # 不调 LLM，走兜底筛选（本地调试）
"""
import argparse
import logging
import sys

from .curator import curate_fallback, curate_with_llm
from .fetcher import fetch_all, load_sources
from .renderer import write_outputs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 前沿日报流水线")
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--window-hours", type=int, default=36,
                        help="只抓最近 N 小时的条目（默认 36，衔接上一次运行）")
    parser.add_argument("--dry-run", action="store_true",
                        help="跳过 LLM，用兜底排序（本地无 key 调试用）")
    args = parser.parse_args()

    # 1. 抓取
    sources = load_sources(args.sources)
    items = fetch_all(sources, window_hours=args.window_hours)
    if not items:
        log.error("时间窗内没有任何条目，把 --window-hours 调大试试")
        return 1

    # 2. 筛选
    picks = curate_fallback(items) if args.dry_run else curate_with_llm(items)
    if not picks:
        log.error("筛选结果为空")
        return 1

    # 3. 渲染产出（dry-run 写到独立目录，避免覆盖正式产物）
    paths = write_outputs(picks, out_root="output-dryrun" if args.dry_run else "output")
    log.info("完成。今日 %d 条：", len(picks))
    for i, p in enumerate(picks, 1):
        log.info("  %d. [%s] %s", i, p.get("source", "?"), p.get("title", "?"))
    print(f"\n公众号成品（打开后全选复制 -> 粘贴进公众号编辑器）:\n  {paths['wechat_html']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
