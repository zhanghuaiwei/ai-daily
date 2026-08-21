"""渲染器：把筛选结果渲染成两份产物。

1. digest.md           —— Markdown 存档（人读 / 二次编辑 / 长期沉淀）
2. digest_wechat.html  —— 公众号专用 HTML（全部内联 CSS）

公众号编辑器的关键限制：不认识 <style> 标签和 class，只认每个标签上的
内联 style。所以模板里所有样式都写在 style="" 里，复制粘贴后格式
原样保留——这也是 mdnice / Doocs MD 的原理。
"""
import datetime as dt
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

log = logging.getLogger(__name__)


def _today_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def render_markdown(picks: list[dict]) -> str:
    lines = [
        f"# AI 前沿日报 · {_today_str()}",
        "",
        f"今日精选 {len(picks)} 条 | 由 AI 流水线自动筛选生成",
        "",
        "---",
        "",
    ]
    for i, p in enumerate(picks, 1):
        lines += [
            f"## {i}. {p['title']}",
            "",
            f"> {p.get('summary', '')}",
            "",
            f"**为什么值得关注：** {p.get('reason', '')}",
            "",
            f"来源：{p.get('source', '')} · [原文链接]({p.get('link', '')})",
            "",
            "---",
            "",
        ]
    lines += ["<sub>本文由 AI 流水线自动生成，人工审核后发布</sub>"]
    return "\n".join(lines)


def render_wechat_html(picks: list[dict], template_dir: str = "templates") -> str:
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,          # 用户内容一律转义，防止意外 HTML
        trim_blocks=True,
    )
    tpl = env.get_template("wechat.html")
    return tpl.render(date=_today_str(), picks=picks, count=len(picks))


def write_outputs(picks: list[dict], out_root: str = "output") -> dict[str, Path]:
    day_dir = Path(out_root) / _today_str()
    day_dir.mkdir(parents=True, exist_ok=True)

    md_path = day_dir / "digest.md"
    html_path = day_dir / "digest_wechat.html"
    md_path.write_text(render_markdown(picks), encoding="utf-8")
    html_path.write_text(render_wechat_html(picks), encoding="utf-8")

    log.info("产物已写入: %s / %s", md_path, html_path)
    return {"markdown": md_path, "wechat_html": html_path}
