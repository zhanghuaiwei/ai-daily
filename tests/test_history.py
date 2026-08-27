import json

from src.history import load_recent_links, load_recent_topic_titles


def test_history_reads_all_markdown_editions_and_legacy_json(tmp_path):
    new_day = tmp_path / "2026-01-01"
    new_day.mkdir()
    (new_day / "article.md").write_text(
        "# 往日 AI 热门话题\n\n1. [原文](<https://example.com/new?utm_source=x>)\n",
        encoding="utf-8",
    )

    legacy_day = tmp_path / "2025-01-01" / "article-01"
    legacy_day.mkdir(parents=True)
    (legacy_day / "article.json").write_text(
        json.dumps({
            "topic": {
                "working_title": "旧版工作标题",
                "evidence": [{"url": "https://example.com/legacy"}],
            },
            "article": {"selected_title": "旧版最终标题"},
        }),
        encoding="utf-8",
    )

    links = load_recent_links(tmp_path, "2026-08-27")
    titles = load_recent_topic_titles(tmp_path, "2026-08-27")
    assert links == {"https://example.com/new", "https://example.com/legacy"}
    assert titles == ["往日 AI 热门话题", "旧版工作标题", "旧版最终标题"]


def test_history_excludes_current_day_and_can_limit_window(tmp_path):
    for day in ("2026-08-01", "2026-08-26", "2026-08-27"):
        day_dir = tmp_path / day
        day_dir.mkdir()
        (day_dir / "article.md").write_text(
            f"# {day}\n\n[原文](<https://example.com/{day}>)\n",
            encoding="utf-8",
        )
    assert load_recent_topic_titles(tmp_path, "2026-08-27", history_days=2) == ["2026-08-26"]
    assert load_recent_links(tmp_path, "2026-08-27", history_days=0) == set()
