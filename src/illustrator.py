"""Generate an optional cover plus zero to five editorial illustrations per article."""

from __future__ import annotations

import base64
import binascii
import logging
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from openai import OpenAI
from PIL import Image, ImageOps, UnidentifiedImageError

from .safety import clean_plain_text

log = logging.getLogger(__name__)
_MAX_IMAGE_BYTES = 25 * 1024 * 1024
_OUTPUT_FILES = ("cover.jpg",) + tuple(
    f"illustration-{index:02d}.jpg" for index in range(1, 6)
)
_STYLE = (
    "高质量中文科技媒体编辑插画，克制、现代、清晰，半扁平与轻微三维质感结合；"
    "主体具体，层次明确，深蓝、青色和少量暖橙作为统一色系，光线自然，细节可信。"
)
_SAFETY = (
    "这是解释性概念插画，不得伪装成新闻现场照片，不得虚构人物、机构背书、数据图表或产品界面。"
    "画面中不得出现任何文字、字母、数字、标题、标签、品牌标志、水印、二维码和边框。"
    "避免俗套的发光大脑、握手机器人、密集电路线和纯装饰性抽象背景。"
)


class IllustrationError(RuntimeError):
    """A concise image-generation failure safe to persist in article metadata."""


@dataclass(frozen=True)
class ImageSettings:
    api_key: str
    base_url: str
    model: str
    quality: str
    timeout: float
    max_retries: int

    @classmethod
    def from_env(cls) -> ImageSettings:
        api_key = os.environ.get("IMAGE_API_KEY", "").strip()
        if not api_key:
            raise IllustrationError("IMAGE_API_KEY 未配置，不能生成成品配图")
        try:
            timeout = max(10.0, min(float(os.environ.get("IMAGE_TIMEOUT_SECONDS", "240")), 600.0))
            max_retries = max(0, min(int(os.environ.get("IMAGE_MAX_RETRIES", "1")), 3))
        except ValueError as err:
            raise IllustrationError("图像超时或重试配置无效") from err
        quality = os.environ.get("IMAGE_QUALITY", "medium").strip().lower()
        if quality not in {"low", "medium", "high"}:
            raise IllustrationError("IMAGE_QUALITY 只能是 low、medium 或 high")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("IMAGE_BASE_URL", "").strip() or "https://api.openai.com/v1",
            model=os.environ.get("IMAGE_MODEL", "").strip() or "gpt-image-2",
            quality=quality,
            timeout=timeout,
            max_retries=max_retries,
        )


def _client(settings: ImageSettings) -> OpenAI:
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
    )


def _build_prompt(article: dict, plan: dict, kind: str) -> str:
    title = clean_plain_text(article.get("selected_title"), 80)
    abstract = clean_plain_text(article.get("abstract"), 220)
    concept = clean_plain_text(plan.get("concept"), 500)
    if kind == "cover":
        composition = (
            "用途：公众号文章封面。2.35:1 超宽横向构图，核心主体居中或略偏左，"
            "在小尺寸缩略图中仍能一眼看清主题；不预留文字，也不要做成海报。"
        )
    else:
        composition = (
            "用途：公众号正文插图。3:2 横向构图，用一个具体场景、结构关系或工作机制帮助泛读者理解；"
            "不要重复封面构图，不要只画氛围背景。"
        )
    return "\n".join((
        _STYLE,
        composition,
        f"文章主题：{title}",
        f"文章摘要：{abstract}",
        f"本图必须表达：{concept}",
        _SAFETY,
    ))


def _request_image(client: OpenAI, settings: ImageSettings, prompt: str, size: str) -> bytes:
    try:
        result = client.images.generate(
            model=settings.model,
            prompt=prompt,
            n=1,
            size=size,
            quality=settings.quality,
            output_format="jpeg",
            output_compression=92,
        )
        encoded = result.data[0].b64_json if result.data else None
        if not encoded or len(encoded) > _MAX_IMAGE_BYTES * 2:
            raise IllustrationError("图像接口未返回有效图像数据")
        data = base64.b64decode(encoded, validate=True)
    except IllustrationError:
        raise
    except (binascii.Error, IndexError, TypeError, ValueError) as err:
        raise IllustrationError("图像接口响应无法解析") from err
    except Exception as err:  # noqa: BLE001 - external SDK errors must not leak credentials
        raise IllustrationError(f"图像生成失败：{type(err).__name__}") from None
    if not data or len(data) > _MAX_IMAGE_BYTES:
        raise IllustrationError("图像文件为空或超过大小限制")
    return data


def _fit_jpeg(data: bytes, destination: Path, size: tuple[int, int]) -> dict:
    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            if source.width < 640 or source.height < 360 or source.width * source.height > 12_000_000:
                raise IllustrationError("图像尺寸不符合发布要求")
            rendered = ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS)
            rendered.save(destination, format="JPEG", quality=90, optimize=True, progressive=True)
    except IllustrationError:
        raise
    except (OSError, UnidentifiedImageError) as err:
        raise IllustrationError("生成结果不是可用图像") from err
    return {"width": size[0], "height": size[1]}


def _record_visual_status(bundle: dict, ready: bool) -> None:
    metrics = bundle.setdefault("metrics", {})
    metrics["visual_assets_ready"] = ready


def generate_article_visuals(
    bundle: dict,
    article_dir: Path,
    settings: ImageSettings | None = None,
) -> dict:
    """Generate all required images atomically and attach relative asset metadata."""
    if not bundle.get("publishable"):
        bundle["visuals"] = {"status": "skipped", "error": "文章文字质量门禁未通过"}
        _record_visual_status(bundle, False)
        return bundle

    try:
        article = bundle["article"]
        plan = article["visual_plan"]
        cover_plan = plan.get("cover") if isinstance(plan.get("cover"), dict) else None
        raw_illustrations = plan.get("illustrations", [])
        illustrations = raw_illustrations[:5] if isinstance(raw_illustrations, list) else []
        image_dir = article_dir / "images"
        if image_dir.is_dir():
            for filename in _OUTPUT_FILES:
                (image_dir / filename).unlink(missing_ok=True)
        if not cover_plan and not illustrations:
            bundle["visuals"] = {"status": "not_planned", "cover": None, "illustrations": []}
            _record_visual_status(bundle, False)
            return bundle

        resolved = settings or ImageSettings.from_env()
        client = _client(resolved)

        image_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=".generating-", dir=image_dir) as temporary:
            temporary_dir = Path(temporary)
            generated_filenames = []
            rendered_cover = None
            if cover_plan:
                cover_path = temporary_dir / _OUTPUT_FILES[0]
                cover_meta = _fit_jpeg(
                    _request_image(
                        client,
                        resolved,
                        _build_prompt(article, cover_plan, "cover"),
                        "1280x544",
                    ),
                    cover_path,
                    (900, 383),
                )
                generated_filenames.append(cover_path.name)
                rendered_cover = {
                    "path": f"images/{cover_path.name}",
                    "alt": cover_plan["alt"],
                    **cover_meta,
                }
            rendered_illustrations = []
            for index, item in enumerate(illustrations, 1):
                path = temporary_dir / _OUTPUT_FILES[index]
                dimensions = _fit_jpeg(
                    _request_image(client, resolved, _build_prompt(article, item, "body"), "1536x1024"),
                    path,
                    (1200, 800),
                )
                rendered_illustrations.append({
                    "path": f"images/{path.name}",
                    "alt": item["alt"],
                    "after_section": item["after_section"],
                    **dimensions,
                })
                generated_filenames.append(path.name)
            for filename in generated_filenames:
                (temporary_dir / filename).replace(image_dir / filename)

        bundle["visuals"] = {
            "status": "ready",
            "model": resolved.model,
            "quality": resolved.quality,
            "cover": rendered_cover,
            "illustrations": rendered_illustrations,
        }
        _record_visual_status(bundle, True)
    except (IllustrationError, OSError) as err:
        message = str(err) if isinstance(err, IllustrationError) else "图像文件写入失败"
        log.warning("文章配图失败，将继续发布文字版：%s", message)
        bundle["visuals"] = {"status": "failed", "error": clean_plain_text(message, 240)}
        _record_visual_status(bundle, False)
    return bundle


def generate_visuals_for_bundles(
    bundles: list[dict],
    out_root: str,
    date: str,
    settings: ImageSettings | None = None,
) -> list[dict]:
    day_dir = Path(out_root) / date
    for index, bundle in enumerate(bundles, 1):
        generate_article_visuals(bundle, day_dir / f"article-{index:02d}", settings=settings)
    return bundles
