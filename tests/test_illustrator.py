import base64
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

import src.illustrator as illustrator


def jpeg_payload() -> str:
    buffer = BytesIO()
    Image.new("RGB", (1280, 800), (25, 90, 150)).save(buffer, "JPEG", quality=90)
    return base64.b64encode(buffer.getvalue()).decode()


def article_bundle() -> dict:
    return {
        "publishable": True,
        "metrics": {"checks": {"text_quality": True}, "publishable": True},
        "article": {
            "selected_title": "一项技术如何走向真实应用",
            "abstract": "文章解释一项新技术的工作方法、现实价值和仍需观察的边界。",
            "visual_plan": {
                "cover": {"concept": "实验原型与真实应用场景形成连接", "alt": "技术走向实际应用"},
                "illustrations": [
                    {"after_section": 2, "concept": "三个处理步骤之间的关系", "alt": "技术处理步骤"},
                    {"after_section": 4, "concept": "开发者在真实任务中使用工具", "alt": "真实任务中的使用场景"},
                ],
            },
        },
    }


class FakeImages:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=jpeg_payload())])


def settings() -> illustrator.ImageSettings:
    return illustrator.ImageSettings(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-image-2",
        quality="medium",
        timeout=60,
        max_retries=0,
    )


def test_generates_cover_and_two_body_images(monkeypatch, tmp_path):
    fake = SimpleNamespace(images=FakeImages())
    monkeypatch.setattr(illustrator, "_client", lambda _settings: fake)
    bundle = article_bundle()

    illustrator.generate_article_visuals(bundle, tmp_path / "article-01", settings())

    assert bundle["publishable"] is True
    assert bundle["visuals"]["status"] == "ready"
    assert bundle["metrics"]["visual_assets_ready"] is True
    assert len(fake.images.calls) == 3
    assert fake.images.calls[0]["size"] == "1280x544"
    assert "不得出现任何文字" in fake.images.calls[0]["prompt"]
    cover = tmp_path / "article-01" / "images" / "cover.jpg"
    body = tmp_path / "article-01" / "images" / "illustration-01.jpg"
    assert Image.open(cover).size == (900, 383)
    assert Image.open(body).size == (1200, 800)


def test_missing_key_keeps_publishable_text_without_calling_api(monkeypatch, tmp_path):
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)
    bundle = article_bundle()
    illustrator.generate_article_visuals(bundle, tmp_path / "article-01")
    assert bundle["publishable"] is True
    assert bundle["metrics"]["visual_assets_ready"] is False
    assert bundle["visuals"]["status"] == "failed"


def test_zero_planned_images_needs_no_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)
    bundle = article_bundle()
    bundle["article"]["visual_plan"] = {"cover": {}, "illustrations": []}
    article_dir = tmp_path / "article-01"
    image_dir = article_dir / "images"
    image_dir.mkdir(parents=True)
    stale_image = image_dir / "illustration-05.jpg"
    stale_image.write_bytes(b"stale")
    illustrator.generate_article_visuals(bundle, article_dir)
    assert bundle["publishable"] is True
    assert bundle["visuals"]["status"] == "not_planned"
    assert bundle["metrics"]["visual_assets_ready"] is False
    assert not stale_image.exists()


def test_generates_up_to_five_body_images(monkeypatch, tmp_path):
    fake = SimpleNamespace(images=FakeImages())
    monkeypatch.setattr(illustrator, "_client", lambda _settings: fake)
    bundle = article_bundle()
    bundle["article"]["visual_plan"]["illustrations"] = [
        {
            "after_section": index,
            "concept": f"解释第{index}个章节",
            "alt": f"第{index}张正文插图",
        }
        for index in range(1, 6)
    ]
    illustrator.generate_article_visuals(bundle, tmp_path / "article-01", settings())
    assert len(bundle["visuals"]["illustrations"]) == 5
    assert len(fake.images.calls) == 6
    assert (tmp_path / "article-01" / "images" / "illustration-05.jpg").is_file()
