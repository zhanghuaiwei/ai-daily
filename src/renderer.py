"""渲染器：把筛选结果渲染成三份产物。

1. digest.md           —— Markdown 存档（人读 / 二次编辑 / 长期沉淀）
2. digest_wechat.html  —— 公众号专用 HTML（全部内联 CSS）
3. digest.json         —— 机器可读存档（跨天去重 / 二次开发）

公众号编辑器的关键限制：不认识 <style> 标签和 class，只认每个标签上的
内联 style。所以模板里所有样式都写在 style="" 里，复制粘贴后格式
原样保留——这也是 mdnice / Doocs MD 的原理。
"""
import datetime as dt
import html
import json
import logging
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

from .safety import sanitize_pick

log = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
_MARKDOWN_ESCAPE_RE = re.compile(r"([\\`*_[\]{}()#+.!|>\-])")
_ARTICLE_IMAGE_RE = re.compile(
    r"^images/[A-Za-z0-9._-]+\.(?:jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)


def _today_str(now: dt.datetime | None = None) -> str:
    if now is None:
        now = dt.datetime.now(BEIJING_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING_TZ)
    else:
        now = now.astimezone(BEIJING_TZ)
    return now.strftime("%Y-%m-%d")


def _markdown_text(value: str) -> str:
    escaped_html = html.escape(value, quote=False)
    return _MARKDOWN_ESCAPE_RE.sub(r"\\\1", escaped_html)


def _prepared_visuals(bundle: dict) -> dict:
    raw = bundle.get("visuals", {})
    empty = {"status": "unavailable", "cover": None, "illustrations": []}
    if not isinstance(raw, dict) or raw.get("status") != "ready":
        return empty

    def prepare(item: object) -> dict | None:
        if not isinstance(item, dict):
            return None
        path = str(item.get("path", ""))
        alt = str(item.get("alt", ""))[:120].strip()
        if not _ARTICLE_IMAGE_RE.fullmatch(path) or not alt:
            return None
        return {**item, "path": path, "alt": alt}

    cover = prepare(raw.get("cover"))
    illustrations = []
    used_sections: set[int] = set()
    section_count = len(bundle.get("article", {}).get("sections", []))
    raw_illustrations = raw.get("illustrations", [])
    if not isinstance(raw_illustrations, list):
        return empty
    for item in raw_illustrations:
        prepared = prepare(item)
        if not prepared:
            continue
        try:
            prepared["after_section"] = int(prepared.get("after_section", 0))
        except (TypeError, ValueError):
            continue
        if (
            not 1 <= prepared["after_section"] <= section_count
            or prepared["after_section"] in used_sections
        ):
            continue
        used_sections.add(prepared["after_section"])
        illustrations.append(prepared)
        if len(illustrations) == 5:
            break
    if not cover and not illustrations:
        return empty
    return {"status": "ready", "cover": cover, "illustrations": illustrations}


def render_markdown(picks: list[dict], date: str | None = None) -> str:
    prepared = [sanitize_pick(pick) for pick in picks]
    edition_date = date or _today_str()
    lines = [
        f"# AI 前沿日报 · {edition_date}",
        "",
        f"今日精选 {len(prepared)} 条 | 由 AI 流水线自动筛选生成",
        "",
        "---",
        "",
    ]
    for i, p in enumerate(prepared, 1):
        source = _markdown_text(p["source"])
        link = p["link"]
        source_line = f"来源：{source}"
        if link:
            source_line += f" · [原文链接](<{link}>)"
        lines += [
            f"## {i}\\. {_markdown_text(p['title'])}",
            "",
            f"> {_markdown_text(p['summary'])}",
            "",
            f"**为什么值得关注：** {_markdown_text(p['reason'])}",
            "",
            source_line,
            "",
            "---",
            "",
        ]
    lines += ["<sub>本文由 AI 流水线自动生成，人工审核后发布</sub>"]
    return "\n".join(lines)


def render_wechat_html(
    picks: list[dict],
    template_dir: str = "templates",
    date: str | None = None,
) -> str:
    prepared = [sanitize_pick(pick) for pick in picks]
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,          # 用户内容一律转义，防止意外 HTML
        trim_blocks=True,
    )
    tpl = env.get_template("wechat.html")
    return tpl.render(date=date or _today_str(), picks=prepared, count=len(prepared))


def write_outputs(
    picks: list[dict],
    out_root: str = "output",
    date: str | None = None,
) -> dict[str, Path]:
    edition_date = date or _today_str()
    prepared = [sanitize_pick(pick) for pick in picks]
    day_dir = Path(out_root) / edition_date
    day_dir.mkdir(parents=True, exist_ok=True)

    md_path = day_dir / "digest.md"
    html_path = day_dir / "digest_wechat.html"
    json_path = day_dir / "digest.json"
    md_path.write_text(render_markdown(prepared, date=edition_date), encoding="utf-8")
    html_path.write_text(render_wechat_html(prepared, date=edition_date), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"date": edition_date, "count": len(prepared), "picks": prepared},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    log.info("产物已写入: %s / %s / %s", md_path, html_path, json_path)
    return {"markdown": md_path, "wechat_html": html_path, "json": json_path}


def render_article_markdown(bundle: dict, date: str) -> str:
    article = bundle["article"]
    evidence = bundle["topic"].get("evidence", [])
    visuals = _prepared_visuals(bundle)
    lines = [
        f"# {_markdown_text(article['selected_title'])}",
        "",
        f"> {_markdown_text(article['abstract'])}",
        "",
    ]
    if visuals["cover"]:
        lines += [
            f"![{_markdown_text(visuals['cover']['alt'])}](<{visuals['cover']['path']}>)",
            "",
        ]
    lines += [_markdown_text(article["lead"]), ""]
    illustrations = {
        item["after_section"]: item for item in visuals["illustrations"]
    }
    for section_index, section in enumerate(article["sections"], 1):
        lines += [f"## {_markdown_text(section['heading'])}", ""]
        for paragraph in section["paragraphs"]:
            citations = "".join(f"【{source_id}】" for source_id in paragraph["source_ids"])
            lines += [f"{_markdown_text(paragraph['text'])}{citations}", ""]
        illustration = illustrations.get(section_index)
        if illustration:
            lines += [
                f"![{_markdown_text(illustration['alt'])}](<{illustration['path']}>)",
                "",
            ]
    lines += ["## 写在最后", "", _markdown_text(article["conclusion"]), "", "## 参考资料", ""]
    for source in evidence:
        url = source.get("url", "")
        source_text = _markdown_text(source.get("source", ""))
        title = _markdown_text(source.get("title", ""))
        if url:
            lines.append(f"{source['id']}\\. {source_text}：[原文](<{url}>) · {title}")
        else:
            lines.append(f"{source['id']}\\. {source_text} · {title}")
    lines += ["", f"<sub>资料整理日期：{date}。发布前请进行人工事实核验。</sub>"]
    return "\n".join(lines)


def render_article_html(
    bundle: dict,
    date: str,
    template_dir: str = "templates",
) -> str:
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,
        trim_blocks=True,
    )
    template = env.get_template("article.html")
    visuals = _prepared_visuals(bundle)
    return template.render(
        date=date,
        article=bundle["article"],
        evidence=bundle["topic"].get("evidence", []),
        cover=visuals["cover"],
        illustrations_by_section={
            item["after_section"]: item for item in visuals["illustrations"]
        },
    )


def write_article_outputs(
    bundles: list[dict],
    out_root: str = "output",
    date: str | None = None,
) -> list[dict[str, object]]:
    edition_date = date or _today_str()
    day_dir = Path(out_root) / edition_date
    day_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    index_items = []
    for index, bundle in enumerate(bundles, 1):
        article_dir = day_dir / f"article-{index:02d}"
        article_dir.mkdir(parents=True, exist_ok=True)
        md_path = article_dir / "article.md"
        html_path = article_dir / "article_wechat.html"
        json_path = article_dir / "article.json"
        md_path.write_text(render_article_markdown(bundle, edition_date), encoding="utf-8")
        html_path.write_text(render_article_html(bundle, edition_date), encoding="utf-8")
        archived_topic = {
            **bundle["topic"],
            "evidence": [
                {key: value for key, value in source.items() if key != "excerpt"}
                for source in bundle["topic"].get("evidence", [])
            ],
        }
        archived_bundle = {**bundle, "topic": archived_topic}
        json_path.write_text(
            json.dumps(archived_bundle, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        path_item: dict[str, object] = {
            "markdown": md_path,
            "wechat_html": html_path,
            "json": json_path,
            "publishable": bundle["publishable"],
            "title": bundle["article"]["selected_title"],
            "relative_dir": article_dir.name,
            "has_visuals": bundle.get("visuals", {}).get("status") == "ready",
        }
        paths.append(path_item)
        index_items.append({
            "index": index,
            "title": bundle["article"]["selected_title"],
            "abstract": bundle["article"]["abstract"],
            "publishable": bundle["publishable"],
            "has_visuals": bundle.get("visuals", {}).get("status") == "ready",
            "metrics": bundle["metrics"],
            "title_candidates": bundle["article"]["title_candidates"],
            "paths": {
                "markdown": str(md_path.relative_to(day_dir)),
                "wechat_html": str(html_path.relative_to(day_dir)),
                "json": str(json_path.relative_to(day_dir)),
            },
        })
    (day_dir / "articles.json").write_text(
        json.dumps(
            {"date": edition_date, "count": len(index_items), "articles": index_items},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    log.info("独立文章产物已写入: %s（%d 篇）", day_dir, len(paths))
    return paths
