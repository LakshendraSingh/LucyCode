"""
Presentation Generator Service for LucyCode.

Generates modern, professional, 16:9 widescreen PowerPoint presentations (.pptx)
with curated typography, cohesive color palettes, structured card/metric layouts,
and executive-grade aesthetic polish.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import pptx
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt
    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False
    RGBColor = None
    Pt = None
    Inches = None
    MSO_SHAPE = None
    PP_ALIGN = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Theme Definitions & Color Palettes
# ---------------------------------------------------------------------------

@dataclass
class PresentationTheme:
    """Design theme palette and typography settings."""
    name: str
    bg_color: tuple[int, int, int]
    card_bg: tuple[int, int, int]
    card_border: tuple[int, int, int]
    primary_text: tuple[int, int, int]
    secondary_text: tuple[int, int, int]
    accent: tuple[int, int, int]
    accent_secondary: tuple[int, int, int]
    tag_bg: tuple[int, int, int]
    tag_text: tuple[int, int, int]
    font_title: str = "Helvetica Neue"
    font_body: str = "Arial"


THEMES: dict[str, PresentationTheme] = {
    "modern_dark": PresentationTheme(
        name="modern_dark",
        bg_color=(15, 23, 42),          # #0F172A slate-900
        card_bg=(30, 41, 59),           # #1E293B slate-800
        card_border=(51, 65, 85),       # #334155 slate-700
        primary_text=(248, 250, 252),   # #F8FAFC slate-50
        secondary_text=(148, 163, 184), # #94A3B8 slate-400
        accent=(99, 102, 241),          # #6366F1 indigo-500
        accent_secondary=(6, 182, 212), # #06B6D4 cyan-500
        tag_bg=(49, 46, 129),           # #312E81 deep indigo
        tag_text=(199, 210, 254),       # #C7D2FE indigo-200
    ),
    "clean_light": PresentationTheme(
        name="clean_light",
        bg_color=(255, 255, 255),       # #FFFFFF pure white
        card_bg=(248, 250, 252),        # #F8FAFC slate-50
        card_border=(226, 232, 240),    # #E2E8F0 slate-200
        primary_text=(15, 23, 42),      # #0F172A slate-900
        secondary_text=(71, 85, 105),   # #475569 slate-600
        accent=(37, 99, 235),           # #2563EB blue-600
        accent_secondary=(16, 185, 129),# #10B981 emerald-500
        tag_bg=(239, 246, 255),         # #EFF6FF blue-50
        tag_text=(29, 78, 216),         # #1D4ED8 blue-700
    ),
    "executive_navy": PresentationTheme(
        name="executive_navy",
        bg_color=(10, 25, 47),          # #0A192F royal deep navy
        card_bg=(23, 42, 69),           # #172A45 navy card
        card_border=(35, 53, 84),       # #233554 border
        primary_text=(255, 255, 255),   # #FFFFFF pure white
        secondary_text=(136, 146, 176), # #8892B0 slate blue
        accent=(245, 158, 11),          # #F59E0B gold/amber
        accent_secondary=(56, 189, 248),# #38BDF8 sky-400
        tag_bg=(45, 36, 18),            # gold dark tint
        tag_text=(252, 211, 77),        # #FCD34D light amber
    ),
    "warm_editorial": PresentationTheme(
        name="warm_editorial",
        bg_color=(253, 251, 247),       # #FDFBF7 warm alabaster
        card_bg=(245, 245, 240),        # #F5F5F0 warm stone
        card_border=(231, 229, 228),    # #E7E5E4 stone-200
        primary_text=(28, 25, 23),      # #1C1917 warm stone-900
        secondary_text=(87, 83, 78),    # #57534E warm stone-600
        accent=(194, 65, 12),           # #C2410C terracotta
        accent_secondary=(15, 118, 110),# #0F766E deep teal
        tag_bg=(254, 242, 242),         # terracotta tint
        tag_text=(153, 27, 27),         # deep red/terracotta
    ),
    "vibrant_tech": PresentationTheme(
        name="vibrant_tech",
        bg_color=(9, 13, 22),           # #090D16 deep dark
        card_bg=(19, 26, 42),           # #131A2A card dark
        card_border=(38, 48, 77),       # #26304D border
        primary_text=(255, 255, 255),   # #FFFFFF white
        secondary_text=(148, 163, 184), # #94A3B8 slate-400
        accent=(139, 92, 246),          # #8B5CF6 violet
        accent_secondary=(20, 184, 166),# #14B8A6 teal
        tag_bg=(46, 16, 101),           # purple dark tint
        tag_text=(221, 214, 254),       # #DDD6FE light violet
    ),
}


# ---------------------------------------------------------------------------
# Image Resolution & Dynamic Visual Generator
# ---------------------------------------------------------------------------

def _resolve_or_generate_image(
    image_path: str = "",
    image_url: str = "",
    title: str = "",
    tag: str = "",
    theme: PresentationTheme | None = None,
) -> str | None:
    """
    Resolve an image from a local path or remote URL.
    If the image cannot be downloaded or found, dynamically generates a high-quality
    visual graphic asset with PIL matching the presentation theme.
    """
    # 1. Try Remote URL Download
    target_url = (image_url or "").strip()
    if not target_url and image_path and image_path.startswith(("http://", "https://")):
        target_url = image_path.strip()

    if target_url.startswith(("http://", "https://")):
        try:
            cache_dir = Path(tempfile.gettempdir()) / "lucy_images"
            cache_dir.mkdir(parents=True, exist_ok=True)
            url_hash = hashlib.md5(target_url.encode("utf-8")).hexdigest()[:12]
            ext = ".png"
            if ".jpg" in target_url.lower() or ".jpeg" in target_url.lower():
                ext = ".jpg"
            cached_file = cache_dir / f"img_{url_hash}{ext}"
            if cached_file.exists() and cached_file.stat().st_size > 500:
                return str(cached_file)

            req = urllib.request.Request(
                target_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                content = response.read()
                if len(content) > 200:
                    cached_file.write_bytes(content)
                    try:
                        from PIL import Image
                        with Image.open(cached_file) as img:
                            img.verify()
                        return str(cached_file)
                    except Exception:
                        if cached_file.exists():
                            cached_file.unlink(missing_ok=True)
        except Exception as e:
            logger.debug("Failed to download image %s: %s", target_url, e)

    # 2. Try Local File Path
    if image_path and not image_path.startswith(("http://", "https://")):
        try:
            p = Path(image_path).expanduser()
            if not p.is_absolute():
                p = Path.cwd() / p
            if p.exists() and p.is_file():
                return str(p.resolve())
        except Exception as e:
            logger.debug("Local file lookup failed for %s: %s", image_path, e)

    # 3. Dynamic High-Quality Visual Generator via PIL (Theme-matched fallback)
    try:
        from PIL import Image, ImageDraw, ImageFont

        cache_dir = Path(tempfile.gettempdir()) / "lucy_images"
        cache_dir.mkdir(parents=True, exist_ok=True)
        theme_name = theme.name if theme else "default"
        fallback_hash = hashlib.md5(
            f"{title}_{tag}_{theme_name}".encode("utf-8")
        ).hexdigest()[:10]
        generated_path = cache_dir / f"visual_{fallback_hash}.png"
        if generated_path.exists() and generated_path.stat().st_size > 1000:
            return str(generated_path)

        w, h = 1200, 800
        bg_col = theme.card_bg if theme else (30, 41, 59)
        accent_col = theme.accent if theme else (99, 102, 241)
        accent_sec = theme.accent_secondary if theme else (6, 182, 212)
        text_col = theme.primary_text if theme else (248, 250, 252)
        sub_col = theme.secondary_text if theme else (148, 163, 184)
        border_col = theme.card_border if theme else (51, 65, 85)

        img = Image.new("RGB", (w, h), color=bg_col)
        draw = ImageDraw.Draw(img)

        # Sleek outer border with rounded corners
        draw.rounded_rectangle([15, 15, w - 15, h - 15], radius=24, outline=border_col, width=3)

        # Subtle geometric decorative background accents
        draw.arc([w - 320, -100, w + 100, 320], start=0, end=360, fill=border_col, width=2)
        draw.arc([w - 260, -40, w + 40, 260], start=0, end=360, fill=accent_col, width=3)
        draw.line([60, 180, 260, 180], fill=accent_col, width=4)

        # Category tag pill
        display_tag = (tag or "VISUAL FOCUS").upper()
        tag_width = max(len(display_tag) * 16 + 40, 180)
        draw.rounded_rectangle([60, 70, 60 + tag_width, 125], radius=14, fill=accent_col)

        # System fonts lookup
        title_font = None
        body_font = None
        tag_font = None
        for fp in [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
        ]:
            if os.path.exists(fp):
                try:
                    title_font = ImageFont.truetype(fp, 46)
                    body_font = ImageFont.truetype(fp, 26)
                    tag_font = ImageFont.truetype(fp, 20)
                    break
                except Exception:
                    pass
        if not title_font:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
            tag_font = ImageFont.load_default()

        draw.text((80, 86), display_tag, fill=(255, 255, 255), font=tag_font)

        # Main graphic title wrapping
        display_title = title or "Visual Architecture"
        words = display_title.split()
        lines = []
        curr: list[str] = []
        for wd in words:
            curr.append(wd)
            if len(" ".join(curr)) > 26:
                lines.append(" ".join(curr[:-1]))
                curr = [wd]
        if curr:
            lines.append(" ".join(curr))

        y_text = 220
        for line in lines[:3]:
            draw.text((60, y_text), line, fill=text_col, font=title_font)
            y_text += 60

        # Decorative accent KPI cards inside the graphic
        y_cards = max(y_text + 40, 480)
        cw = 320
        ch = 180
        for ci in range(3):
            cx = 60 + ci * (cw + 40)
            if cx + cw < w - 40:
                draw.rounded_rectangle(
                    [cx, y_cards, cx + cw, y_cards + ch],
                    radius=16,
                    fill=border_col,
                    outline=accent_sec,
                    width=2,
                )
                draw.rectangle([cx + 20, y_cards + 25, cx + 60, y_cards + 30], fill=accent_sec)
                draw.text(
                    (cx + 20, y_cards + 45),
                    f"Architecture 0{ci+1}",
                    fill=text_col,
                    font=body_font,
                )
                draw.text(
                    (cx + 20, y_cards + 90),
                    "High-Throughput Node",
                    fill=sub_col,
                    font=tag_font,
                )

        img.save(str(generated_path), format="PNG")
        return str(generated_path)
    except Exception as e:
        logger.warning("Could not generate fallback visual image: %s", e)
        return None


# ---------------------------------------------------------------------------
# SlideDeck Engine
# ---------------------------------------------------------------------------

class SlideDeck:
    """
    Builder for 16:9 widescreen PowerPoint presentations with curated aesthetics.
    """

    def __init__(self, theme: str = "modern_dark"):
        if not HAS_PPTX:
            raise RuntimeError(
                "python-pptx is not installed. Please run: pip install python-pptx"
            )

        self.theme_name = theme if theme in THEMES else "modern_dark"
        self.theme: PresentationTheme = THEMES[self.theme_name]

        self.prs = pptx.Presentation()
        # 16:9 Widescreen dimensions (13.333" x 7.5" = 1280x720 pt)
        self.prs.slide_width = Inches(13.333)
        self.prs.slide_height = Inches(7.5)
        self.blank_layout = self.prs.slide_layouts[6]  # Blank slide

    def _rgb(self, color_tuple: tuple[int, int, int]):
        return RGBColor(*color_tuple)

    def _set_slide_bg(self, slide) -> None:
        """Fill slide background with the theme's background color."""
        bg_shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5)
        )
        bg_shape.fill.solid()
        bg_shape.fill.fore_color.rgb = self._rgb(self.theme.bg_color)
        bg_shape.line.fill.background()

    def _add_header(
        self,
        slide,
        title: str,
        subtitle: str = "",
        tag: str = "",
        top_offset: float = 0.5,
    ) -> float:
        """Add standardized top header with category badge, title, and subtitle."""
        current_top = top_offset

        # 1. Category Tag / Pill Badge
        if tag:
            tag_width = max(len(tag) * 0.11 + 0.5, 1.4)
            tag_box = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(0.8),
                Inches(current_top),
                Inches(tag_width),
                Inches(0.32),
            )
            tag_box.fill.solid()
            tag_box.fill.fore_color.rgb = self._rgb(self.theme.tag_bg)
            tag_box.line.color.rgb = self._rgb(self.theme.accent)
            tag_box.line.width = Pt(1.0)

            tf_tag = tag_box.text_frame
            tf_tag.word_wrap = False
            tf_tag.margin_left = Inches(0.08)
            tf_tag.margin_top = Inches(0.02)
            p_tag = tf_tag.paragraphs[0]
            p_tag.text = tag.upper()
            p_tag.font.name = self.theme.font_title
            p_tag.font.size = Pt(9.5)
            p_tag.font.bold = True
            p_tag.font.color.rgb = self._rgb(self.theme.tag_text)
            p_tag.alignment = PP_ALIGN.CENTER
            current_top += 0.42

        # 2. Main Slide Title
        title_box = slide.shapes.add_textbox(
            Inches(0.8), Inches(current_top), Inches(11.7), Inches(0.65)
        )
        tf_title = title_box.text_frame
        tf_title.word_wrap = True
        tf_title.margin_left = Inches(0)
        tf_title.margin_top = Inches(0)
        p_title = tf_title.paragraphs[0]
        p_title.text = title
        p_title.font.name = self.theme.font_title
        p_title.font.size = Pt(26)
        p_title.font.bold = True
        p_title.font.color.rgb = self._rgb(self.theme.primary_text)
        current_top += 0.65

        # 3. Subtitle / Context description
        if subtitle:
            sub_box = slide.shapes.add_textbox(
                Inches(0.8), Inches(current_top), Inches(11.7), Inches(0.4)
            )
            tf_sub = sub_box.text_frame
            tf_sub.word_wrap = True
            tf_sub.margin_left = Inches(0)
            tf_sub.margin_top = Inches(0)
            p_sub = tf_sub.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.name = self.theme.font_body
            p_sub.font.size = Pt(13)
            p_sub.font.color.rgb = self._rgb(self.theme.secondary_text)
            current_top += 0.5

        return current_top

    # -----------------------------------------------------------------------
    # Slide Builders
    # -----------------------------------------------------------------------

    def add_title_slide(
        self,
        title: str,
        subtitle: str = "",
        presenter: str = "",
        date: str = "",
        tag: str = "PRESENTATION",
        image_path: str = "",
        image_url: str = "",
    ) -> None:
        """Create a high-impact title / cover slide."""
        slide = self.prs.slides.add_slide(self.blank_layout)
        self._set_slide_bg(slide)

        resolved_img = None
        if image_path or image_url:
            resolved_img = _resolve_or_generate_image(
                image_path=image_path,
                image_url=image_url,
                title=title,
                tag=tag,
                theme=self.theme,
            )

        # Decorative left accent stripe
        stripe = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(0.08), Inches(3.6)
        )
        stripe.fill.solid()
        stripe.fill.fore_color.rgb = self._rgb(self.theme.accent)
        stripe.line.fill.background()

        # Tag badge
        if tag:
            tag_width = max(len(tag) * 0.12 + 0.6, 1.6)
            tag_box = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(1.1),
                Inches(1.8),
                Inches(tag_width),
                Inches(0.36),
            )
            tag_box.fill.solid()
            tag_box.fill.fore_color.rgb = self._rgb(self.theme.tag_bg)
            tag_box.line.color.rgb = self._rgb(self.theme.accent)
            tag_box.line.width = Pt(1.0)
            tf_tag = tag_box.text_frame
            tf_tag.word_wrap = False
            p_tag = tf_tag.paragraphs[0]
            p_tag.text = tag.upper()
            p_tag.font.name = self.theme.font_title
            p_tag.font.size = Pt(10)
            p_tag.font.bold = True
            p_tag.font.color.rgb = self._rgb(self.theme.tag_text)
            p_tag.alignment = PP_ALIGN.CENTER

        # Width adjustment if title has right-hand visual/hero image
        text_width = 7.2 if resolved_img else 11.0

        # Title
        title_box = slide.shapes.add_textbox(
            Inches(1.1), Inches(2.35), Inches(text_width), Inches(1.6)
        )
        tf_title = title_box.text_frame
        tf_title.word_wrap = True
        tf_title.margin_left = Inches(0)
        p_title = tf_title.paragraphs[0]
        p_title.text = title
        p_title.font.name = self.theme.font_title
        p_title.font.size = Pt(40)
        p_title.font.bold = True
        p_title.font.color.rgb = self._rgb(self.theme.primary_text)

        # Subtitle
        if subtitle:
            sub_box = slide.shapes.add_textbox(
                Inches(1.1), Inches(4.1), Inches(text_width), Inches(0.8)
            )
            tf_sub = sub_box.text_frame
            tf_sub.word_wrap = True
            tf_sub.margin_left = Inches(0)
            p_sub = tf_sub.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.name = self.theme.font_body
            p_sub.font.size = Pt(17)
            p_sub.font.color.rgb = self._rgb(self.theme.secondary_text)

        # Hero Image on right side if provided
        if resolved_img and Path(resolved_img).exists():
            try:
                slide.shapes.add_picture(
                    resolved_img,
                    Inches(8.5),
                    Inches(1.8),
                    width=Inches(4.0),
                )
            except Exception as e:
                logger.debug("Failed adding picture to title slide: %s", e)

        # Presenter & Date metadata footer
        meta_parts = []
        if presenter:
            meta_parts.append(presenter)
        if date:
            meta_parts.append(date)
        if meta_parts:
            meta_box = slide.shapes.add_textbox(
                Inches(1.1), Inches(5.6), Inches(text_width), Inches(0.4)
            )
            tf_meta = meta_box.text_frame
            p_meta = tf_meta.paragraphs[0]
            p_meta.text = "   •   ".join(meta_parts)
            p_meta.font.name = self.theme.font_body
            p_meta.font.size = Pt(12)
            p_meta.font.color.rgb = self._rgb(self.theme.secondary_text)

    def add_card_slide(
        self,
        title: str,
        subtitle: str = "",
        cards: list[dict[str, Any]] | None = None,
        tag: str = "OVERVIEW",
    ) -> None:
        """
        Add a multi-column card slide (2, 3, or 4 columns).
        Each card in `cards` can contain:
          - 'title': str
          - 'body': str or list[str]
          - 'badge': str (optional category or label)
        """
        cards = cards or []
        slide = self.prs.slides.add_slide(self.blank_layout)
        self._set_slide_bg(slide)

        header_bottom = self._add_header(slide, title, subtitle, tag)
        content_top = max(header_bottom + 0.3, 1.9)
        content_height = 4.8

        num_cards = min(max(len(cards), 1), 4)
        margin_left = 0.8
        margin_right = 0.8
        available_width = 13.333 - margin_left - margin_right
        gap = 0.35
        card_width = (available_width - (gap * (num_cards - 1))) / num_cards

        for i, card_info in enumerate(cards[:4]):
            x_pos = margin_left + i * (card_width + gap)

            # Card Container
            card_shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(x_pos),
                Inches(content_top),
                Inches(card_width),
                Inches(content_height),
            )
            card_shape.fill.solid()
            card_shape.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
            card_shape.line.color.rgb = self._rgb(self.theme.card_border)
            card_shape.line.width = Pt(1.2)

            tf = card_shape.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(0.28)
            tf.margin_right = Inches(0.28)
            tf.margin_top = Inches(0.28)
            tf.margin_bottom = Inches(0.28)

            first_para = True

            # Badge / Category
            badge = card_info.get("badge", "")
            if badge:
                p_badge = tf.paragraphs[0]
                p_badge.text = badge.upper()
                p_badge.font.name = self.theme.font_title
                p_badge.font.size = Pt(10)
                p_badge.font.bold = True
                p_badge.font.color.rgb = self._rgb(self.theme.accent)
                first_para = False

            # Card Title
            c_title = card_info.get("title", "")
            if c_title:
                p_card_title = tf.paragraphs[0] if first_para else tf.add_paragraph()
                p_card_title.text = c_title
                p_card_title.font.name = self.theme.font_title
                p_card_title.font.size = Pt(18)
                p_card_title.font.bold = True
                p_card_title.font.color.rgb = self._rgb(self.theme.primary_text)
                p_card_title.space_after = Pt(12)
                first_para = False

            # Body / Bullets
            body = card_info.get("body", "")
            if isinstance(body, list):
                for item in body:
                    p_bullet = tf.add_paragraph()
                    p_bullet.text = f"•  {item}"
                    p_bullet.font.name = self.theme.font_body
                    p_bullet.font.size = Pt(13)
                    p_bullet.font.color.rgb = self._rgb(self.theme.secondary_text)
                    p_bullet.space_after = Pt(6)
            elif body:
                p_body = tf.add_paragraph() if not first_para else tf.paragraphs[0]
                p_body.text = str(body)
                p_body.font.name = self.theme.font_body
                p_body.font.size = Pt(13)
                p_body.font.color.rgb = self._rgb(self.theme.secondary_text)

    def add_metrics_slide(
        self,
        title: str,
        subtitle: str = "",
        metrics: list[dict[str, str]] | None = None,
        tag: str = "KEY METRICS",
    ) -> None:
        """
        Add a high-impact metrics / KPI slide.
        Each metric in `metrics`:
          - 'value': str (e.g. '99.9%', '10x', '$4.2M')
          - 'label': str (e.g. 'Uptime SLA')
          - 'detail': str (optional context)
        """
        metrics = metrics or []
        slide = self.prs.slides.add_slide(self.blank_layout)
        self._set_slide_bg(slide)

        header_bottom = self._add_header(slide, title, subtitle, tag)
        content_top = max(header_bottom + 0.35, 2.0)
        content_height = 4.6

        num_metrics = min(max(len(metrics), 1), 4)
        margin_left = 0.8
        margin_right = 0.8
        available_width = 13.333 - margin_left - margin_right
        gap = 0.35
        card_width = (available_width - (gap * (num_metrics - 1))) / num_metrics

        for i, m in enumerate(metrics[:4]):
            x_pos = margin_left + i * (card_width + gap)

            card_shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(x_pos),
                Inches(content_top),
                Inches(card_width),
                Inches(content_height),
            )
            card_shape.fill.solid()
            card_shape.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
            card_shape.line.color.rgb = self._rgb(self.theme.card_border)
            card_shape.line.width = Pt(1.2)

            tf = card_shape.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(0.25)
            tf.margin_right = Inches(0.25)
            tf.margin_top = Inches(0.4)

            # Metric Value (Big Number)
            p_val = tf.paragraphs[0]
            p_val.text = m.get("value", "0")
            p_val.font.name = self.theme.font_title
            p_val.font.size = Pt(44)
            p_val.font.bold = True
            p_val.font.color.rgb = self._rgb(self.theme.accent)
            p_val.space_after = Pt(8)

            # Label (Header)
            label = m.get("label", "")
            if label:
                p_lbl = tf.add_paragraph()
                p_lbl.text = label.upper()
                p_lbl.font.name = self.theme.font_title
                p_lbl.font.size = Pt(13)
                p_lbl.font.bold = True
                p_lbl.font.color.rgb = self._rgb(self.theme.primary_text)
                p_lbl.space_after = Pt(8)

            # Detail / Description
            detail = m.get("detail", "")
            if detail:
                p_det = tf.add_paragraph()
                p_det.text = detail
                p_det.font.name = self.theme.font_body
                p_det.font.size = Pt(12)
                p_det.font.color.rgb = self._rgb(self.theme.secondary_text)

    def add_process_slide(
        self,
        title: str,
        subtitle: str = "",
        steps: list[dict[str, str]] | None = None,
        tag: str = "PROCESS",
    ) -> None:
        """
        Add a horizontal process / step timeline slide.
        Each step in `steps`:
          - 'step': str (e.g. '01', 'Phase 1')
          - 'title': str
          - 'description': str
        """
        steps = steps or []
        slide = self.prs.slides.add_slide(self.blank_layout)
        self._set_slide_bg(slide)

        header_bottom = self._add_header(slide, title, subtitle, tag)
        content_top = max(header_bottom + 0.35, 2.0)
        content_height = 4.6

        num_steps = min(max(len(steps), 1), 4)
        margin_left = 0.8
        margin_right = 0.8
        available_width = 13.333 - margin_left - margin_right
        gap = 0.35
        card_width = (available_width - (gap * (num_steps - 1))) / num_steps

        for i, s in enumerate(steps[:4]):
            x_pos = margin_left + i * (card_width + gap)

            # Container Box
            box = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(x_pos),
                Inches(content_top),
                Inches(card_width),
                Inches(content_height),
            )
            box.fill.solid()
            box.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
            box.line.color.rgb = self._rgb(self.theme.card_border)
            box.line.width = Pt(1.2)

            tf = box.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(0.25)
            tf.margin_right = Inches(0.25)
            tf.margin_top = Inches(0.3)

            # Step Number / Badge
            step_num = s.get("step", f"0{i+1}")
            p_step = tf.paragraphs[0]
            p_step.text = step_num
            p_step.font.name = self.theme.font_title
            p_step.font.size = Pt(28)
            p_step.font.bold = True
            p_step.font.color.rgb = self._rgb(self.theme.accent)
            p_step.space_after = Pt(8)

            # Step Title
            s_title = s.get("title", "")
            if s_title:
                p_st = tf.add_paragraph()
                p_st.text = s_title
                p_st.font.name = self.theme.font_title
                p_st.font.size = Pt(16)
                p_st.font.bold = True
                p_st.font.color.rgb = self._rgb(self.theme.primary_text)
                p_st.space_after = Pt(10)

            # Description
            desc = s.get("description", "")
            if desc:
                p_desc = tf.add_paragraph()
                p_desc.text = desc
                p_desc.font.name = self.theme.font_body
                p_desc.font.size = Pt(13)
                p_desc.font.color.rgb = self._rgb(self.theme.secondary_text)

    def add_comparison_slide(
        self,
        title: str,
        subtitle: str = "",
        left_column: dict[str, Any] | None = None,
        right_column: dict[str, Any] | None = None,
        tag: str = "COMPARISON",
    ) -> None:
        """
        Add a 2-column side-by-side comparison slide (e.g. Current vs Future, Problem vs Solution).
        `left_column` and `right_column`:
          - 'title': str
          - 'subtitle': str
          - 'items': list[str]
        """
        left_column = left_column or {}
        right_column = right_column or {}
        slide = self.prs.slides.add_slide(self.blank_layout)
        self._set_slide_bg(slide)

        header_bottom = self._add_header(slide, title, subtitle, tag)
        content_top = max(header_bottom + 0.35, 2.0)
        content_height = 4.6

        margin_left = 0.8
        gap = 0.4
        col_width = (13.333 - 1.6 - gap) / 2

        columns_data = [
            (left_column, margin_left, self.theme.accent_secondary),
            (right_column, margin_left + col_width + gap, self.theme.accent),
        ]

        for col_data, x_pos, accent_col in columns_data:
            box = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(x_pos),
                Inches(content_top),
                Inches(col_width),
                Inches(content_height),
            )
            box.fill.solid()
            box.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
            box.line.color.rgb = self._rgb(accent_col)
            box.line.width = Pt(1.5)

            tf = box.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(0.35)
            tf.margin_right = Inches(0.35)
            tf.margin_top = Inches(0.35)

            c_title = col_data.get("title", "")
            p_head = tf.paragraphs[0]
            p_head.text = c_title
            p_head.font.name = self.theme.font_title
            p_head.font.size = Pt(20)
            p_head.font.bold = True
            p_head.font.color.rgb = self._rgb(accent_col)
            p_head.space_after = Pt(4)

            c_sub = col_data.get("subtitle", "")
            if c_sub:
                p_sub = tf.add_paragraph()
                p_sub.text = c_sub
                p_sub.font.name = self.theme.font_body
                p_sub.font.size = Pt(13)
                p_sub.font.color.rgb = self._rgb(self.theme.secondary_text)
                p_sub.space_after = Pt(14)

            items = col_data.get("items", [])
            for item in items:
                p_item = tf.add_paragraph()
                p_item.text = f"•  {item}"
                p_item.font.name = self.theme.font_body
                p_item.font.size = Pt(13)
                p_item.font.color.rgb = self._rgb(self.theme.primary_text)
                p_item.space_after = Pt(8)

    def add_quote_slide(
        self,
        quote: str,
        author: str = "",
        role: str = "",
        tag: str = "VISION",
    ) -> None:
        """Add a full-slide editorial quote or vision callout."""
        slide = self.prs.slides.add_slide(self.blank_layout)
        self._set_slide_bg(slide)

        header_bottom = self._add_header(slide, "", "", tag)
        content_top = max(header_bottom + 0.5, 2.2)

        # Quotation mark symbol
        quote_mark = slide.shapes.add_textbox(
            Inches(1.5), Inches(content_top - 0.4), Inches(2.0), Inches(1.0)
        )
        tf_qm = quote_mark.text_frame
        p_qm = tf_qm.paragraphs[0]
        p_qm.text = "“"
        p_qm.font.name = "Georgia"
        p_qm.font.size = Pt(72)
        p_qm.font.bold = True
        p_qm.font.color.rgb = self._rgb(self.theme.accent)

        # Quote Text
        box = slide.shapes.add_textbox(
            Inches(1.5), Inches(content_top + 0.6), Inches(10.3), Inches(2.4)
        )
        tf = box.text_frame
        tf.word_wrap = True
        p_q = tf.paragraphs[0]
        p_q.text = quote
        p_q.font.name = self.theme.font_title
        p_q.font.size = Pt(24)
        p_q.font.italic = True
        p_q.font.color.rgb = self._rgb(self.theme.primary_text)

        # Attribution / Author
        if author or role:
            attr_box = slide.shapes.add_textbox(
                Inches(1.5), Inches(content_top + 3.2), Inches(10.3), Inches(0.8)
            )
            tf_attr = attr_box.text_frame
            p_author = tf_attr.paragraphs[0]
            p_author.text = f"—  {author}" if author else ""
            p_author.font.name = self.theme.font_title
            p_author.font.size = Pt(16)
            p_author.font.bold = True
            p_author.font.color.rgb = self._rgb(self.theme.accent)

            if role:
                p_role = tf_attr.add_paragraph()
                p_role.text = role
                p_role.font.name = self.theme.font_body
                p_role.font.size = Pt(12)
                p_role.font.color.rgb = self._rgb(self.theme.secondary_text)

    def add_summary_slide(
        self,
        title: str = "Summary & Next Steps",
        subtitle: str = "",
        takeaways: list[str] | None = None,
        next_steps: list[str] | None = None,
        tag: str = "KEY TAKEAWAYS",
    ) -> None:
        """Add split summary slide with key takeaways and actionable next steps."""
        takeaways = takeaways or []
        next_steps = next_steps or []
        slide = self.prs.slides.add_slide(self.blank_layout)
        self._set_slide_bg(slide)

        header_bottom = self._add_header(slide, title, subtitle, tag)
        content_top = max(header_bottom + 0.35, 2.0)
        content_height = 4.6

        margin_left = 0.8
        gap = 0.4
        col_width = (13.333 - 1.6 - gap) / 2

        # 1. Takeaways (Left Box)
        box_left = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(margin_left),
            Inches(content_top),
            Inches(col_width),
            Inches(content_height),
        )
        box_left.fill.solid()
        box_left.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
        box_left.line.color.rgb = self._rgb(self.theme.card_border)
        box_left.line.width = Pt(1.2)

        tf_l = box_left.text_frame
        tf_l.word_wrap = True
        tf_l.margin_left = Inches(0.35)
        tf_l.margin_right = Inches(0.35)
        tf_l.margin_top = Inches(0.35)

        p_l_head = tf_l.paragraphs[0]
        p_l_head.text = "Key Takeaways"
        p_l_head.font.name = self.theme.font_title
        p_l_head.font.size = Pt(20)
        p_l_head.font.bold = True
        p_l_head.font.color.rgb = self._rgb(self.theme.accent)
        p_l_head.space_after = Pt(14)

        for item in takeaways:
            p = tf_l.add_paragraph()
            p.text = f"✓  {item}"
            p.font.name = self.theme.font_body
            p.font.size = Pt(13)
            p.font.color.rgb = self._rgb(self.theme.primary_text)
            p.space_after = Pt(8)

        # 2. Next Steps (Right Box)
        box_right = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(margin_left + col_width + gap),
            Inches(content_top),
            Inches(col_width),
            Inches(content_height),
        )
        box_right.fill.solid()
        box_right.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
        box_right.line.color.rgb = self._rgb(self.theme.accent_secondary)
        box_right.line.width = Pt(1.2)

        tf_r = box_right.text_frame
        tf_r.word_wrap = True
        tf_r.margin_left = Inches(0.35)
        tf_r.margin_right = Inches(0.35)
        tf_r.margin_top = Inches(0.35)

        p_r_head = tf_r.paragraphs[0]
        p_r_head.text = "Next Steps & Roadmap"
        p_r_head.font.name = self.theme.font_title
        p_r_head.font.size = Pt(20)
        p_r_head.font.bold = True
        p_r_head.font.color.rgb = self._rgb(self.theme.accent_secondary)
        p_r_head.space_after = Pt(14)

        for i, step in enumerate(next_steps):
            p = tf_r.add_paragraph()
            p.text = f"{i+1}.  {step}"
            p.font.name = self.theme.font_body
            p.font.size = Pt(13)
            p.font.color.rgb = self._rgb(self.theme.primary_text)
            p.space_after = Pt(8)

    def add_image_slide(
        self,
        title: str,
        subtitle: str = "",
        image_path: str = "",
        image_url: str = "",
        caption: str = "",
        points: list[str] | None = None,
        tag: str = "VISUAL",
    ) -> None:
        """
        Add a dedicated visual / image slide.
        If `points` are provided, renders a split two-column layout:
          - Left column: The visual image inside a curated card frame with caption
          - Right column: Explanatory highlights, analysis bullets, and insights
        If no `points` are provided, renders a spacious, centered showcase layout.
        """
        points = points or []
        slide = self.prs.slides.add_slide(self.blank_layout)
        self._set_slide_bg(slide)

        header_bottom = self._add_header(slide, title, subtitle, tag)
        content_top = max(header_bottom + 0.25, 1.9)
        content_height = 4.8

        resolved_img = _resolve_or_generate_image(
            image_path=image_path,
            image_url=image_url,
            title=title,
            tag=tag,
            theme=self.theme,
        )

        if points:
            # Two-column layout
            margin_left = 0.8
            img_col_width = 5.8
            gap = 0.4
            text_col_width = 13.333 - margin_left * 2 - img_col_width - gap

            # 1. Left Image Container Card
            img_card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(margin_left),
                Inches(content_top),
                Inches(img_col_width),
                Inches(content_height),
            )
            img_card.fill.solid()
            img_card.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
            img_card.line.color.rgb = self._rgb(self.theme.card_border)
            img_card.line.width = Pt(1.2)

            if resolved_img and Path(resolved_img).exists():
                max_w = 5.2
                max_h = 3.6 if caption else 4.1
                try:
                    from PIL import Image

                    with Image.open(resolved_img) as pil_img:
                        iw, ih = pil_img.size
                    ratio = iw / ih if ih else 1.0
                    if ratio >= (max_w / max_h):
                        render_w = max_w
                        render_h = max_w / ratio
                    else:
                        render_h = max_h
                        render_w = max_h * ratio
                except Exception:
                    render_w = max_w
                    render_h = max_h

                pic_left = margin_left + 0.3 + (max_w - render_w) / 2
                pic_top = content_top + 0.3 + (max_h - render_h) / 2
                try:
                    slide.shapes.add_picture(
                        resolved_img,
                        Inches(pic_left),
                        Inches(pic_top),
                        width=Inches(render_w),
                        height=Inches(render_h),
                    )
                except Exception as e:
                    logger.debug("Failed adding picture to image slide: %s", e)

            # Caption below image if present
            if caption:
                cap_box = slide.shapes.add_textbox(
                    Inches(margin_left + 0.3),
                    Inches(content_top + 4.1),
                    Inches(img_col_width - 0.6),
                    Inches(0.5),
                )
                tf_cap = cap_box.text_frame
                tf_cap.word_wrap = True
                p_cap = tf_cap.paragraphs[0]
                p_cap.text = caption
                p_cap.font.name = self.theme.font_body
                p_cap.font.size = Pt(11)
                p_cap.font.italic = True
                p_cap.font.color.rgb = self._rgb(self.theme.secondary_text)
                p_cap.alignment = PP_ALIGN.CENTER

            # 2. Right Text/Bullets Card
            text_x = margin_left + img_col_width + gap
            text_card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(text_x),
                Inches(content_top),
                Inches(text_col_width),
                Inches(content_height),
            )
            text_card.fill.solid()
            text_card.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
            text_card.line.color.rgb = self._rgb(self.theme.card_border)
            text_card.line.width = Pt(1.2)

            tf_text = text_card.text_frame
            tf_text.word_wrap = True
            tf_text.margin_left = Inches(0.4)
            tf_text.margin_right = Inches(0.4)
            tf_text.margin_top = Inches(0.4)

            p_head = tf_text.paragraphs[0]
            p_head.text = "Key Insights & Architecture"
            p_head.font.name = self.theme.font_title
            p_head.font.size = Pt(20)
            p_head.font.bold = True
            p_head.font.color.rgb = self._rgb(self.theme.accent)
            p_head.space_after = Pt(16)

            for pt in points:
                p_pt = tf_text.add_paragraph()
                p_pt.text = f"•  {pt}"
                p_pt.font.name = self.theme.font_body
                p_pt.font.size = Pt(13)
                p_pt.font.color.rgb = self._rgb(self.theme.primary_text)
                p_pt.space_after = Pt(10)
        else:
            # Showcase Layout (Spacious Centered Frame)
            frame_width = 10.6
            frame_left = (13.333 - frame_width) / 2
            card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(frame_left),
                Inches(content_top),
                Inches(frame_width),
                Inches(content_height),
            )
            card.fill.solid()
            card.fill.fore_color.rgb = self._rgb(self.theme.card_bg)
            card.line.color.rgb = self._rgb(self.theme.card_border)
            card.line.width = Pt(1.2)

            if resolved_img and Path(resolved_img).exists():
                max_w = 9.8
                max_h = 3.8 if caption else 4.2
                try:
                    from PIL import Image

                    with Image.open(resolved_img) as pil_img:
                        iw, ih = pil_img.size
                    ratio = iw / ih if ih else 1.0
                    if ratio >= (max_w / max_h):
                        render_w = max_w
                        render_h = max_w / ratio
                    else:
                        render_h = max_h
                        render_w = max_h * ratio
                except Exception:
                    render_w = max_w
                    render_h = max_h

                pic_left = frame_left + (frame_width - render_w) / 2
                pic_top = content_top + 0.3 + (max_h - render_h) / 2
                try:
                    slide.shapes.add_picture(
                        resolved_img,
                        Inches(pic_left),
                        Inches(pic_top),
                        width=Inches(render_w),
                        height=Inches(render_h),
                    )
                except Exception as e:
                    logger.debug("Failed adding picture to showcase slide: %s", e)

            if caption:
                cap_box = slide.shapes.add_textbox(
                    Inches(frame_left + 0.4),
                    Inches(content_top + 4.2),
                    Inches(frame_width - 0.8),
                    Inches(0.4),
                )
                tf_cap = cap_box.text_frame
                tf_cap.word_wrap = True
                p_cap = tf_cap.paragraphs[0]
                p_cap.text = caption
                p_cap.font.name = self.theme.font_body
                p_cap.font.size = Pt(12)
                p_cap.font.italic = True
                p_cap.font.color.rgb = self._rgb(self.theme.secondary_text)
                p_cap.alignment = PP_ALIGN.CENTER

    # -----------------------------------------------------------------------
    # Output & Persistence
    # -----------------------------------------------------------------------

    def save(self, output_path: str | Path) -> str:
        """Save the PowerPoint file to the requested path."""
        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(str(path))
        logger.info("Saved presentation to %s (%d slides)", path, len(self.prs.slides))
        return str(path)


# ---------------------------------------------------------------------------
# Declarative Specification Parser
# ---------------------------------------------------------------------------

def generate_presentation_from_spec(spec: dict[str, Any]) -> str:
    """
    Build a complete presentation from a structured dictionary.

    Schema:
    {
      "theme": "modern_dark" | "clean_light" | "executive_navy" | "warm_editorial" | "vibrant_tech",
      "output_path": "presentation.pptx",
      "slides": [
        {
          "type": "title",
          "title": "...",
          "subtitle": "...",
          "presenter": "...",
          "date": "...",
          "tag": "..."
        },
        {
          "type": "cards",
          "title": "...",
          "subtitle": "...",
          "cards": [{"title": "...", "body": "...", "badge": "..."}]
        },
        {
          "type": "metrics",
          "title": "...",
          "metrics": [{"value": "...", "label": "...", "detail": "..."}]
        },
        {
          "type": "process",
          "title": "...",
          "steps": [{"step": "01", "title": "...", "description": "..."}]
        },
        {
          "type": "comparison",
          "title": "...",
          "left": {"title": "...", "items": [...]},
          "right": {"title": "...", "items": [...]}
        },
        {
          "type": "quote",
          "quote": "...",
          "author": "...",
          "role": "..."
        },
        {
          "type": "summary",
          "title": "...",
          "takeaways": [...],
          "next_steps": [...]
        }
      ]
    }
    """
    theme = spec.get("theme", "modern_dark")
    output_path = spec.get("output_path", "presentation.pptx")
    deck = SlideDeck(theme=theme)

    slides = spec.get("slides", [])
    for slide_data in slides:
        stype = slide_data.get("type", "cards").lower()
        title = slide_data.get("title", "")
        subtitle = slide_data.get("subtitle", "")
        tag = slide_data.get("tag", "")

        if stype == "title":
            deck.add_title_slide(
                title=title,
                subtitle=subtitle,
                presenter=slide_data.get("presenter", ""),
                date=slide_data.get("date", ""),
                tag=tag or "PRESENTATION",
                image_path=slide_data.get("image_path", ""),
                image_url=slide_data.get("image_url", ""),
            )
        elif stype in ("image", "visual", "graphic"):
            deck.add_image_slide(
                title=title,
                subtitle=subtitle,
                image_path=slide_data.get("image_path", ""),
                image_url=slide_data.get("image_url", ""),
                caption=slide_data.get("caption", ""),
                points=slide_data.get("points") or slide_data.get("bullets", []),
                tag=tag or "VISUAL",
            )
        elif stype == "cards":
            deck.add_card_slide(
                title=title,
                subtitle=subtitle,
                cards=slide_data.get("cards", []),
                tag=tag or "OVERVIEW",
            )
        elif stype == "metrics":
            deck.add_metrics_slide(
                title=title,
                subtitle=subtitle,
                metrics=slide_data.get("metrics", []),
                tag=tag or "KEY METRICS",
            )
        elif stype == "process":
            deck.add_process_slide(
                title=title,
                subtitle=subtitle,
                steps=slide_data.get("steps", []),
                tag=tag or "PROCESS",
            )
        elif stype == "comparison":
            deck.add_comparison_slide(
                title=title,
                subtitle=subtitle,
                left_column=slide_data.get("left", {}),
                right_column=slide_data.get("right", {}),
                tag=tag or "COMPARISON",
            )
        elif stype == "quote":
            deck.add_quote_slide(
                quote=slide_data.get("quote", title),
                author=slide_data.get("author", ""),
                role=slide_data.get("role", ""),
                tag=tag or "VISION",
            )
        elif stype == "summary":
            deck.add_summary_slide(
                title=title or "Summary & Next Steps",
                subtitle=subtitle,
                takeaways=slide_data.get("takeaways", []),
                next_steps=slide_data.get("next_steps", []),
                tag=tag or "KEY TAKEAWAYS",
            )
        else:
            # Fallback to cards
            deck.add_card_slide(
                title=title,
                subtitle=subtitle,
                cards=slide_data.get("cards", []),
                tag=tag or "OVERVIEW",
            )

    return deck.save(output_path)

