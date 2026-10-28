"""每日线路注册表：资讯线与应用线共用全部约束，只差来源、产物名和推送标题前缀。

新增线路时在这里登记一条即可，pipeline / renderer / delivery / history 都按这里
的配置取默认值；两条线的已用链接去重池是共享的（见 history.load_recent_links）。
"""

from __future__ import annotations

EDITIONS: dict[str, dict[str, str]] = {
    "news": {
        "sources": "config/sources.yaml",
        "filename": "article.md",
        "title_prefix": "",
    },
    "application": {
        "sources": "config/sources-application.yaml",
        "filename": "application.md",
        "title_prefix": "AI应用|",
    },
}
DEFAULT_EDITION = "news"


def edition_filename(edition: str) -> str:
    return EDITIONS[edition]["filename"]


def edition_title_prefix(filename: str) -> str:
    """WeChat push title prefix for a Markdown artifact name; unknown files get none."""
    for spec in EDITIONS.values():
        if spec["filename"] == filename:
            return spec["title_prefix"]
    return ""
