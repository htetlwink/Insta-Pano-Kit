"""
InstaPanoramaSplitter — Core Image Processing Engine
===================================================
Production-grade image processing pipeline for splitting wide panoramic photos
into seamless multi-slide Instagram carousels and multi-tile profile grids.

Supports:
- Aspect ratios: Portrait (4:5) [1080x1350], Square (1:1) [1080x1080], Story (9:16) [1080x1920]
- Fit modes:
    * Standard (Fit & Crop)
    * Proportional (Full Width)
    * Blurred Background Fill
    * Solid Gallery Border
- Precise pan offsets (X & Y from -1.0 to +1.0)
- Color space management: sRGB profile conversion via LittleCMS (ImageCms)
- Smart sharpening via UnsharpMask
- Overlays & Indicators:
    * Seam Arrow (continuous badge spanning slide i and i+1 seams)
    * Swipe Badge (modern pill indicator on Slide 1)
    * Dot Indicators (carousel pagination dots)
    * Title text (Slide 1 heading)
    * Watermark text (author credit)
- Instagram Profile Grid Splitter (3x1, 3x2, 3x3) with reverse-upload sequence calculation
- Aesthetic Visual Contact Sheet / Upload Sequence Guide generator
- Robust multi-format disk export with color sanitization and chroma subsampling control
"""

from __future__ import annotations

import io
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageCms, ImageDraw, ImageFilter, ImageFont, ImageOps

# ---------------------------------------------------------------------------
# Constants & Aspect Ratio Presets
# ---------------------------------------------------------------------------

ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "Portrait (4:5)": (1080, 1350),
    "Square (1:1)": (1080, 1080),
    "Story (9:16)": (1080, 1920),
}

# Alias map for user-friendly resolution lookups
_ASPECT_RATIO_ALIASES: Dict[str, Tuple[int, int]] = {
    "portrait (4:5)": (1080, 1350),
    "portrait": (1080, 1350),
    "4:5": (1080, 1350),
    "4/5": (1080, 1350),
    "square (1:1)": (1080, 1080),
    "square": (1080, 1080),
    "1:1": (1080, 1080),
    "story (9:16)": (1080, 1920),
    "story": (1080, 1920),
    "9:16": (1080, 1920),
    "9/16": (1080, 1920),
}


# ---------------------------------------------------------------------------
# Color Parsing Utilities
# ---------------------------------------------------------------------------

def parse_color(color_val: Union[Tuple[int, int, int], str, List[int]]) -> Tuple[int, int, int]:
    """
    Parse various color representations into an (R, G, B) tuple.
    Accepts:
      - Tuple or List: (255, 255, 255)
      - Hex string: "#ffffff" or "#FFF"
      - String tuple: "(255, 255, 255)" or "255, 255, 255"
      - Named colors: "white", "black", "dark", "gray"
    """
    if isinstance(color_val, (tuple, list)):
        if len(color_val) >= 3:
            return (int(color_val[0]), int(color_val[1]), int(color_val[2]))
        return (255, 255, 255)

    if not isinstance(color_val, str):
        return (255, 255, 255)

    s = color_val.strip().lower()

    named_colors = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "dark": (18, 18, 18),
        "gray": (128, 128, 128),
        "light_gray": (240, 240, 240),
    }
    if s in named_colors:
        return named_colors[s]

    if s.startswith("#"):
        hex_str = s.lstrip("#")
        if len(hex_str) == 3:
            hex_str = "".join([c * 2 for c in hex_str])
        if len(hex_str) == 6:
            try:
                return (
                    int(hex_str[0:2], 16),
                    int(hex_str[2:4], 16),
                    int(hex_str[4:6], 16),
                )
            except ValueError:
                return (255, 255, 255)

    # Clean string format "(255, 255, 255)"
    cleaned = s.replace("(", "").replace(")", "").replace("[", "").replace("]", "")
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if len(parts) >= 3:
        try:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return (255, 255, 255)

    return (255, 255, 255)


# ---------------------------------------------------------------------------
# Font Helper
# ---------------------------------------------------------------------------

_FONT_CACHE: Dict[Tuple[int, bool], ImageFont.ImageFont] = {}


def get_pil_font(size: int = 14, bold: bool = False) -> ImageFont.ImageFont:
    """Load a clean TrueType font, falling back gracefully to PIL default font."""
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    font_candidates: List[str] = [
        # Linux / Ubuntu / Debian paths
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        # Windows font names
        "arialbd.ttf" if bold else "arial.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
        # macOS font names
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFProText-Bold.otf" if bold else "/System/Library/Fonts/SFProText-Regular.otf",
        # Generic names
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
        "Arial.ttf",
    ]

    for candidate in font_candidates:
        try:
            font = ImageFont.truetype(candidate, size)
            _FONT_CACHE[key] = font
            return font
        except Exception:
            continue

    # Fallback to default
    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


# ---------------------------------------------------------------------------
# Configuration Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SlicingConfig:
    """Configuration options for panorama carousel slicing."""
    num_slices: int = 3
    aspect_ratio: str = "Portrait (4:5)"
    fit_mode: str = "Standard (Fit & Crop)"
    border_color: Union[Tuple[int, int, int], str] = (255, 255, 255)
    border_padding: int = 0
    pan_offset_x: float = 0.0  # -1.0 (left) to +1.0 (right), 0.0 = center
    pan_offset_y: float = 0.0  # -1.0 (top) to +1.0 (bottom), 0.0 = center
    apply_srgb: bool = True
    smart_sharpen: bool = False
    smart_sharpen_radius: float = 1.2
    smart_sharpen_percent: int = 60
    smart_sharpen_threshold: int = 2
    swipe_indicator: str = "None"  # "None", "Seam Arrow", "Swipe Badge (Slide 1)", "Dot Indicators"
    title_text: Optional[str] = None
    watermark_text: Optional[str] = None
    watermark_all_slides: bool = False
    format: str = "JPEG"  # "JPEG" or "PNG"
    jpeg_quality: int = 95
    prefix: str = "panorama_slice"

    def __post_init__(self) -> None:
        """Validate and clamp configuration parameters."""
        self.num_slices = max(2, min(10, int(self.num_slices)))
        self.pan_offset_x = max(-1.0, min(1.0, float(self.pan_offset_x)))
        self.pan_offset_y = max(-1.0, min(1.0, float(self.pan_offset_y)))
        self.jpeg_quality = max(1, min(100, int(self.jpeg_quality)))
        self.format = "PNG" if self.format.upper() == "PNG" else "JPEG"

    def get_target_dimensions(self) -> Tuple[int, int]:
        """Resolve aspect ratio into (width, height) per slice."""
        key = self.aspect_ratio.strip().lower()
        if key in _ASPECT_RATIO_ALIASES:
            return _ASPECT_RATIO_ALIASES[key]
        for name, dims in ASPECT_RATIOS.items():
            if name.lower() == key:
                return dims
        return (1080, 1350)  # Default Portrait (4:5)


@dataclass
class GridConfig:
    """Configuration options for Instagram Profile Grid splitting (3x1, 3x2, 3x3)."""
    rows: int = 3
    cols: int = 3
    tile_size: int = 1080
    pan_offset_x: float = 0.0
    pan_offset_y: float = 0.0
    apply_srgb: bool = True
    smart_sharpen: bool = False
    smart_sharpen_radius: float = 1.2
    smart_sharpen_percent: int = 60
    smart_sharpen_threshold: int = 2
    format: str = "JPEG"
    jpeg_quality: int = 95
    prefix: str = "grid"

    def __post_init__(self) -> None:
        self.rows = max(1, min(3, int(self.rows)))
        self.cols = max(1, min(6, int(self.cols)))
        self.tile_size = max(100, int(self.tile_size))
        self.pan_offset_x = max(-1.0, min(1.0, float(self.pan_offset_x)))
        self.pan_offset_y = max(-1.0, min(1.0, float(self.pan_offset_y)))
        self.jpeg_quality = max(1, min(100, int(self.jpeg_quality)))
        self.format = "PNG" if self.format.upper() == "PNG" else "JPEG"


@dataclass
class GridTile:
    """Metadata and image payload for an individual tile in a profile grid."""
    image: Image.Image
    row: int          # 0-indexed from top
    col: int          # 0-indexed from left
    tile_number: int  # 1-based reading order (row-major: top-left = 1)
    upload_order: int # 1-based Instagram upload sequence (bottom-right = 1)
    filename: str     # Formatted filename for export


# ---------------------------------------------------------------------------
# Core Image Engine
# ---------------------------------------------------------------------------

class ImageEngine:
    """Production-grade image processing engine for Instagram panoramas and grids."""

    @staticmethod
    def load_image(source: Union[str, Path, Image.Image]) -> Image.Image:
        """
        Load an image from file path or PIL Image object.
        Applies EXIF orientation normalization (ImageOps.exif_transpose).
        """
        if isinstance(source, (str, Path)):
            img = Image.open(str(source))
        elif isinstance(source, Image.Image):
            img = source.copy()
        else:
            raise TypeError(f"Expected file path or PIL Image, got {type(source).__name__}")

        # Correct smartphone rotation metadata
        try:
            transposed = ImageOps.exif_transpose(img)
            if transposed is not None:
                img = transposed
        except Exception:
            pass

        # Memory safety guard for cloud containers (Render 512MB RAM ceiling):
        # Extremely huge smartphone/drone panoramas (30-100 Megapixels) consume hundreds of MBs
        # of raw uncompressed bitmap RAM. Capping at 25 Megapixels preserves 100% of the detail
        # needed for 1080px Instagram carousels while keeping peak memory under 80MB.
        max_pixels = 25_000_000
        if img.width * img.height > max_pixels:
            scale = (max_pixels / (img.width * img.height)) ** 0.5
            new_w = max(1, int(round(img.width * scale)))
            new_h = max(1, int(round(img.height * scale)))
            img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        return img

    @staticmethod
    def apply_color_profile(img: Image.Image, to_srgb: bool = True) -> Image.Image:
        """
        Convert image color space to standard sRGB using LittleCMS (ImageCms).
        This eliminates washed-out, desaturated colors when uploaded to Instagram
        from wide-gamut devices (iPhone Display P3, Adobe RGB).
        """
        if not to_srgb:
            return img

        icc_data = img.info.get("icc_profile")
        if not icc_data:
            # Already assumed standard sRGB or untagged
            return img

        try:
            in_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_data))
            srgb_profile = ImageCms.createProfile("sRGB")

            # ImageCms requires consistent color modes
            working_img = img if img.mode == "RGB" else img.convert("RGB")
            transformed = ImageCms.profileToProfile(
                working_img,
                in_profile,
                srgb_profile,
                outputMode="RGB",
            )
            return transformed
        except Exception:
            # Fallback gracefully if profile is malformed
            return img

    @staticmethod
    def apply_sharpen(
        img: Image.Image,
        radius: float = 1.2,
        percent: int = 60,
        threshold: int = 2,
    ) -> Image.Image:
        """Apply subtle, smart unsharp masking to enhance crispness post-downsampling."""
        return img.filter(
            ImageFilter.UnsharpMask(
                radius=radius,
                percent=percent,
                threshold=threshold,
            )
        )

    # -----------------------------------------------------------------------
    # Panorama Carousel Slicing
    # -----------------------------------------------------------------------

    @classmethod
    def slice_panorama(
        cls,
        image: Union[str, Path, Image.Image],
        config: Optional[SlicingConfig] = None,
        **kwargs: Any,
    ) -> List[Image.Image]:
        """
        Split a panoramic image into an exact list of carousel slide PIL Images.
        """
        if config is None:
            config = SlicingConfig(**kwargs)

        img = cls.load_image(image)
        orig_w, orig_h = img.size

        target_w, target_h = config.get_target_dimensions()
        n_slices = config.num_slices
        total_target_w = target_w * n_slices
        fit_mode = config.fit_mode.strip()

        # Build carousel canvas according to the requested fit mode
        if "proportional" in fit_mode.lower():
            # Strategy: Proportional Full Width (No Crop)
            scale = target_h / orig_h
            new_w = max(n_slices, int(round(orig_w * scale)))
            new_h = target_h

            carousel_canvas = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            slice_boundaries = [
                (
                    int(round(i * new_w / n_slices)),
                    int(round((i + 1) * new_w / n_slices)),
                )
                for i in range(n_slices)
            ]

            # Draw Seam Arrow across slide boundaries if requested
            if config.swipe_indicator == "Seam Arrow":
                carousel_canvas = cls._draw_seam_arrows_proportional(
                    carousel_canvas, slice_boundaries, target_h
                )

            # Extract individual slices
            slices: List[Image.Image] = []
            for i, (x0, x1) in enumerate(slice_boundaries):
                slice_img = carousel_canvas.crop((x0, 0, x1, new_h))
                slice_img = cls._apply_slide_overlays(slice_img, i, n_slices, config)
                slices.append(slice_img)

            return slices

        elif "blurred" in fit_mode.lower():
            # Strategy: Blurred Background Fill
            carousel_canvas = cls._build_blurred_fill_canvas(
                img, total_target_w, target_h, config.pan_offset_x, config.pan_offset_y
            )

        elif "gallery" in fit_mode.lower() or "solid" in fit_mode.lower() or "border" in fit_mode.lower():
            # Strategy: Solid Gallery Border
            carousel_canvas = cls._build_gallery_border_canvas(
                img,
                total_target_w,
                target_h,
                config.border_color,
                config.border_padding,
                config.pan_offset_x,
                config.pan_offset_y,
            )

        else:
            # Strategy: Standard (Fit & Crop)
            carousel_canvas = cls._build_standard_fit_canvas(
                img, total_target_w, target_h, config.pan_offset_x, config.pan_offset_y
            )

        # Draw Seam Arrows on unified canvas before slicing to guarantee exact seam alignment
        if config.swipe_indicator == "Seam Arrow":
            carousel_canvas = cls._draw_seam_arrows_standard(
                carousel_canvas, n_slices, target_w, target_h
            )

        # Slice into n_slices slides of size (target_w, target_h)
        slices = []
        for i in range(n_slices):
            x0 = i * target_w
            x1 = (i + 1) * target_w
            slice_img = carousel_canvas.crop((x0, 0, x1, target_h))
            slice_img = cls._apply_slide_overlays(slice_img, i, n_slices, config)
            slices.append(slice_img)

        return slices

    # -----------------------------------------------------------------------
    # Canvas Construction Strategies
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_standard_fit_canvas(
        img: Image.Image,
        total_w: int,
        target_h: int,
        pan_x: float,
        pan_y: float,
    ) -> Image.Image:
        """Scale and crop image to fill exact carousel dimensions with pan offsets."""
        orig_w, orig_h = img.size
        scale = max(total_w / orig_w, target_h / orig_h)
        scaled_w = int(round(orig_w * scale))
        scaled_h = int(round(orig_h * scale))

        resized = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        excess_x = max(0, scaled_w - total_w)
        excess_y = max(0, scaled_h - target_h)

        crop_x = int(round(excess_x * (pan_x + 1.0) / 2.0))
        crop_y = int(round(excess_y * (pan_y + 1.0) / 2.0))
        crop_x = max(0, min(crop_x, excess_x))
        crop_y = max(0, min(crop_y, excess_y))

        cropped = resized.crop((crop_x, crop_y, crop_x + total_w, crop_y + target_h))
        if cropped.mode in ("RGBA", "LA") or (cropped.mode == "P" and "transparency" in cropped.info):
            bg = Image.new("RGBA", cropped.size, (255, 255, 255, 255))
            return Image.alpha_composite(bg, cropped.convert("RGBA")).convert("RGB")
        return cropped

    @staticmethod
    def _build_blurred_fill_canvas(
        img: Image.Image,
        total_w: int,
        target_h: int,
        pan_x: float,
        pan_y: float,
    ) -> Image.Image:
        """
        Fit panorama completely without cropping and place over a heavily blurred,
        color-matched background of itself.
        """
        orig_w, orig_h = img.size

        # 1. Scale background to cover entire canvas
        # Memory-optimized ambient blur: compute blur on proxy resolution to avoid allocating
        # massive buffers during Gaussian blur on multi-megapixel canvases.
        proxy_w = 640
        proxy_h = max(1, int(round(640 * target_h / total_w)))
        bg_proxy = img.resize((proxy_w, proxy_h), Image.Resampling.BILINEAR)
        bg_blurred_proxy = bg_proxy.filter(ImageFilter.GaussianBlur(radius=14))
        bg_blurred = bg_blurred_proxy.resize((total_w, target_h), Image.Resampling.BILINEAR)

        # Subtle dark veil (18% black overlay) to give crisp contrast to foreground
        veil = Image.new("RGBA", bg_blurred.size, (0, 0, 0, 45))
        bg_composite = Image.alpha_composite(bg_blurred.convert("RGBA"), veil).convert("RGB")

        # 2. Scale foreground image to fit inside canvas without any clipping
        fg_scale = min(total_w / orig_w, target_h / orig_h)
        fg_w = max(1, int(round(orig_w * fg_scale)))
        fg_h = max(1, int(round(orig_h * fg_scale)))
        fg_resized = img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

        excess_x = total_w - fg_w
        excess_y = target_h - fg_h
        pos_x = int(round(excess_x * (pan_x + 1.0) / 2.0))
        pos_y = int(round(excess_y * (pan_y + 1.0) / 2.0))

        if fg_resized.mode in ("RGBA", "LA") or (fg_resized.mode == "P" and "transparency" in fg_resized.info):
            bg_composite.paste(fg_resized, (pos_x, pos_y), mask=fg_resized.split()[-1])
        else:
            bg_composite.paste(fg_resized, (pos_x, pos_y))

        return bg_composite

    @staticmethod
    def _build_gallery_border_canvas(
        img: Image.Image,
        total_w: int,
        target_h: int,
        border_color: Union[Tuple[int, int, int], str],
        border_padding: int,
        pan_x: float,
        pan_y: float,
    ) -> Image.Image:
        """Place the fitted panorama on a clean minimalist solid color canvas."""
        orig_w, orig_h = img.size
        color_rgb = parse_color(border_color)

        canvas = Image.new("RGB", (total_w, target_h), color_rgb)

        avail_w = max(10, total_w - 2 * border_padding)
        avail_h = max(10, target_h - 2 * border_padding)

        fit_scale = min(avail_w / orig_w, avail_h / orig_h)
        fit_w = max(1, int(round(orig_w * fit_scale)))
        fit_h = max(1, int(round(orig_h * fit_scale)))
        fg = img.resize((fit_w, fit_h), Image.Resampling.LANCZOS)

        excess_x = avail_w - fit_w
        excess_y = avail_h - fit_h
        pos_x = border_padding + int(round(excess_x * (pan_x + 1.0) / 2.0))
        pos_y = border_padding + int(round(excess_y * (pan_y + 1.0) / 2.0))

        if fg.mode in ("RGBA", "LA"):
            canvas.paste(fg, (pos_x, pos_y), mask=fg.split()[-1])
        else:
            canvas.paste(fg, (pos_x, pos_y))

        return canvas

    # -----------------------------------------------------------------------
    # Overlays: Seam Indicators, Badges, Watermarks & Typography
    # -----------------------------------------------------------------------

    @staticmethod
    def _draw_seam_arrows_standard(
        canvas: Image.Image,
        num_slices: int,
        target_w: int,
        target_h: int,
    ) -> Image.Image:
        """
        Draw a stylish seam indicator across the junction of slide i and slide i+1.
        Centered at x = (i + 1) * target_w, half is placed on slide i, half on slide i+1.
        """
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        cy = int(target_h * 0.5)  # Vertically centered on the seam
        radius = 42

        for i in range(1, num_slices):
            cx = i * target_w

            # Dark translucent circular glass pill badge
            draw.ellipse(
                [(cx - radius, cy - radius), (cx + radius, cy - radius + 2 * radius)],
                fill=(18, 18, 24, 185),
                outline=(255, 255, 255, 220),
                width=2,
            )

            # Elegant chevron / arrow pointing right
            arrow_w = 18
            arrow_h = 14
            # Arrow stem
            draw.line(
                [(cx - arrow_w, cy), (cx + arrow_w, cy)],
                fill=(255, 255, 255, 245),
                width=4,
            )
            # Arrowhead
            draw.line(
                [(cx + arrow_w, cy), (cx + arrow_w - arrow_h, cy - arrow_h)],
                fill=(255, 255, 255, 245),
                width=4,
            )
            draw.line(
                [(cx + arrow_w, cy), (cx + arrow_w - arrow_h, cy + arrow_h)],
                fill=(255, 255, 255, 245),
                width=4,
            )

        canvas_rgba = canvas.convert("RGBA")
        result = Image.alpha_composite(canvas_rgba, overlay)
        return result.convert("RGB")

    @staticmethod
    def _draw_seam_arrows_proportional(
        canvas: Image.Image,
        boundaries: List[Tuple[int, int]],
        target_h: int,
    ) -> Image.Image:
        """Draw seam arrows at arbitrary proportional boundaries."""
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        cy = int(target_h * 0.5)
        radius = 42

        for i in range(len(boundaries) - 1):
            cx = boundaries[i][1]
            draw.ellipse(
                [(cx - radius, cy - radius), (cx + radius, cy + radius)],
                fill=(18, 18, 24, 185),
                outline=(255, 255, 255, 220),
                width=2,
            )
            arrow_w = 18
            arrow_h = 14
            draw.line(
                [(cx - arrow_w, cy), (cx + arrow_w, cy)],
                fill=(255, 255, 255, 245),
                width=4,
            )
            draw.line(
                [(cx + arrow_w, cy), (cx + arrow_w - arrow_h, cy - arrow_h)],
                fill=(255, 255, 255, 245),
                width=4,
            )
            draw.line(
                [(cx + arrow_w, cy), (cx + arrow_w - arrow_h, cy + arrow_h)],
                fill=(255, 255, 255, 245),
                width=4,
            )

        canvas_rgba = canvas.convert("RGBA")
        result = Image.alpha_composite(canvas_rgba, overlay)
        return result.convert("RGB")

    @classmethod
    def _apply_slide_overlays(
        cls,
        slide_img: Image.Image,
        slide_index: int,
        total_slices: int,
        config: SlicingConfig,
    ) -> Image.Image:
        """Apply slide-specific badges, dot indicators, text, color correction, and sharpening."""
        sw, sh = slide_img.size
        overlay = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 1. Swipe Badge (Slide 1 only)
        if slide_index == 0 and config.swipe_indicator == "Swipe Badge (Slide 1)":
            cls._draw_swipe_badge(draw, sw, sh)

        # 2. Dot Indicators (all slides)
        if config.swipe_indicator == "Dot Indicators":
            cls._draw_dot_indicators(draw, sw, sh, slide_index, total_slices)

        # 3. Title Text (Slide 1 only)
        if slide_index == 0 and config.title_text:
            cls._draw_title_text(draw, sw, sh, config.title_text)

        # 4. Watermark Text (Slide 1 or all slides)
        if config.watermark_text and (config.watermark_all_slides or slide_index == 0):
            cls._draw_watermark(draw, sw, sh, config.watermark_text)

        # Ensure clean white background if slide has alpha/transparency
        if slide_img.mode in ("RGBA", "LA") or (slide_img.mode == "P" and "transparency" in slide_img.info):
            base_bg = Image.new("RGBA", (sw, sh), (255, 255, 255, 255))
            slide_rgba = Image.alpha_composite(base_bg, slide_img.convert("RGBA"))
        else:
            slide_rgba = slide_img.convert("RGBA")

        # Composite overlay
        composited = Image.alpha_composite(slide_rgba, overlay).convert("RGB")

        # Color Space Conversion (sRGB)
        if config.apply_srgb:
            composited = cls.apply_color_profile(composited, to_srgb=True)

        # Smart Sharpen
        if config.smart_sharpen:
            composited = cls.apply_sharpen(
                composited,
                radius=config.smart_sharpen_radius,
                percent=config.smart_sharpen_percent,
                threshold=config.smart_sharpen_threshold,
            )

        return composited

    @staticmethod
    def _draw_swipe_badge(draw: ImageDraw.ImageDraw, sw: int, sh: int) -> None:
        """Render a modern pill-shaped 'SWIPE ➔' badge in the lower right of Slide 1."""
        font = get_pil_font(size=26, bold=True)
        text = "SWIPE ➔"

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x = 24
        pad_y = 14
        badge_w = text_w + pad_x * 2
        badge_h = text_h + pad_y * 2

        margin_right = 45
        margin_bottom = 60

        bx0 = sw - margin_right - badge_w
        by0 = sh - margin_bottom - badge_h
        bx1 = bx0 + badge_w
        by1 = by0 + badge_h

        # Rounded pill badge background
        draw.rounded_rectangle(
            [(bx0, by0), (bx1, by1)],
            radius=badge_h // 2,
            fill=(15, 15, 20, 195),
            outline=(255, 255, 255, 160),
            width=2,
        )

        # Text inside badge
        draw.text(
            (bx0 + pad_x, by0 + pad_y - 2),
            text,
            fill=(255, 255, 255, 245),
            font=font,
        )

    @staticmethod
    def _draw_dot_indicators(
        draw: ImageDraw.ImageDraw,
        sw: int,
        sh: int,
        active_index: int,
        total_slices: int,
    ) -> None:
        """Render pagination dots at the bottom of the slide."""
        dot_spacing = 22
        active_r = 6
        inactive_r = 4
        pill_pad_x = 18
        pill_pad_y = 10

        dots_total_w = (total_slices - 1) * dot_spacing
        pill_w = dots_total_w + pill_pad_x * 2
        pill_h = active_r * 2 + pill_pad_y * 2

        cx = sw // 2
        cy = sh - 45

        # Background translucent pill
        draw.rounded_rectangle(
            [
                (cx - pill_w // 2, cy - pill_h // 2),
                (cx + pill_w // 2, cy + pill_h // 2),
            ],
            radius=pill_h // 2,
            fill=(0, 0, 0, 140),
            outline=(255, 255, 255, 80),
            width=1,
        )

        start_x = cx - dots_total_w // 2
        for j in range(total_slices):
            dot_x = start_x + j * dot_spacing
            if j == active_index:
                draw.ellipse(
                    [(dot_x - active_r, cy - active_r), (dot_x + active_r, cy + active_r)],
                    fill=(255, 255, 255, 255),
                )
            else:
                draw.ellipse(
                    [(dot_x - inactive_r, cy - inactive_r), (dot_x + inactive_r, cy + inactive_r)],
                    fill=(255, 255, 255, 110),
                )

    @staticmethod
    def _draw_title_text(draw: ImageDraw.ImageDraw, sw: int, sh: int, title: str) -> None:
        """Draw an elegant typography title on Slide 1."""
        font = get_pil_font(size=44, bold=True)
        margin_left = 60
        margin_top = 70

        bbox = draw.textbbox((margin_left, margin_top), title, font=font)
        pad = 16

        # Backing pill for contrast
        draw.rounded_rectangle(
            [(bbox[0] - pad, bbox[1] - pad), (bbox[2] + pad, bbox[3] + pad)],
            radius=12,
            fill=(0, 0, 0, 150),
            outline=(255, 255, 255, 60),
            width=1,
        )

        # Drop shadow & title
        draw.text((margin_left + 2, margin_top + 2), title, fill=(0, 0, 0, 180), font=font)
        draw.text((margin_left, margin_top), title, fill=(255, 255, 255, 250), font=font)

    @staticmethod
    def _draw_watermark(draw: ImageDraw.ImageDraw, sw: int, sh: int, text: str) -> None:
        """Draw subtle author watermark in bottom right."""
        font = get_pil_font(size=22, bold=False)
        margin_x = 40
        margin_y = 35

        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        x = sw - margin_x - tw
        y = sh - margin_y - th

        draw.text((x + 1, y + 1), text, fill=(0, 0, 0, 140), font=font)
        draw.text((x, y), text, fill=(255, 255, 255, 190), font=font)

    # -----------------------------------------------------------------------
    # Instagram Profile Grid Splitter (3x1, 3x2, 3x3)
    # -----------------------------------------------------------------------

    @classmethod
    def slice_grid(
        cls,
        image: Union[str, Path, Image.Image],
        rows: int = 3,
        cols: int = 3,
        prefix: str = "grid",
        config: Optional[GridConfig] = None,
        **kwargs: Any,
    ) -> List[GridTile]:
        """
        Split an image into an Instagram profile grid (e.g. 3x3 giant grid, 3x1 banner).
        Each tile is exactly 1080x1080 px.
        Returns GridTile instances with Instagram reverse-upload numbering.

        Instagram profile feed ordering explanation:
        Instagram places the newest upload at the top-left (Row 0, Col 0).
        Thus, to assemble correctly on a profile:
          - Bottom-right tile (Row rows-1, Col cols-1) MUST be uploaded 1st.
          - Top-left tile (Row 0, Col 0) MUST be uploaded last (order rows*cols).
        """
        if config is None:
            config = GridConfig(rows=rows, cols=cols, prefix=prefix, **kwargs)
        else:
            config.rows = rows
            config.cols = cols
            config.prefix = prefix

        img = cls.load_image(image)
        orig_w, orig_h = img.size

        tile_size = config.tile_size
        total_w = config.cols * tile_size
        total_h = config.rows * tile_size

        # Fit & Crop to cover the grid canvas
        scale = max(total_w / orig_w, total_h / orig_h)
        scaled_w = int(round(orig_w * scale))
        scaled_h = int(round(orig_h * scale))

        resized = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        excess_x = max(0, scaled_w - total_w)
        excess_y = max(0, scaled_h - total_h)

        crop_x = int(round(excess_x * (config.pan_offset_x + 1.0) / 2.0))
        crop_y = int(round(excess_y * (config.pan_offset_y + 1.0) / 2.0))
        crop_x = max(0, min(crop_x, excess_x))
        crop_y = max(0, min(crop_y, excess_y))

        grid_canvas = resized.crop((crop_x, crop_y, crop_x + total_w, crop_y + total_h))

        ext = "png" if config.format.upper() == "PNG" else "jpg"
        tiles: List[GridTile] = []

        for r in range(config.rows):
            for c in range(config.cols):
                x0 = c * tile_size
                y0 = r * tile_size
                tile_img = grid_canvas.crop((x0, y0, x0 + tile_size, y0 + tile_size))

                # Color & sharpen processing
                if config.apply_srgb:
                    tile_img = cls.apply_color_profile(tile_img, to_srgb=True)
                if config.smart_sharpen:
                    tile_img = cls.apply_sharpen(
                        tile_img,
                        radius=config.smart_sharpen_radius,
                        percent=config.smart_sharpen_percent,
                        threshold=config.smart_sharpen_threshold,
                    )

                # Reading order: 1 = top-left (r=0, c=0), 2 = top-middle, etc.
                tile_number = r * config.cols + c + 1

                # Instagram Reverse Upload Order:
                # Row from bottom: (rows - 1 - r)
                # Col from right: (cols - 1 - c)
                row_from_bottom = config.rows - 1 - r
                col_from_right = config.cols - 1 - c
                upload_order = row_from_bottom * config.cols + col_from_right + 1

                filename = f"{config.prefix}_upload_{upload_order:02d}_tile_{tile_number:02d}.{ext}"

                tiles.append(
                    GridTile(
                        image=tile_img,
                        row=r,
                        col=c,
                        tile_number=tile_number,
                        upload_order=upload_order,
                        filename=filename,
                    )
                )

        return tiles

    # -----------------------------------------------------------------------
    # Visual Contact Sheet / Upload Guide Generator
    # -----------------------------------------------------------------------

    @classmethod
    def generate_upload_guide(
        cls,
        slices: Union[List[Image.Image], List[GridTile]],
        output_path: Optional[str] = None,
        title: str = "Instagram Upload Sequence Guide",
    ) -> Image.Image:
        """
        Generate an aesthetic visual contact sheet showing slide sequence,
        upload arrows [1] ➔ [2] ➔ [3], and posting tips.
        Supports both carousel slices and profile grid tiles.
        """
        if not slices:
            raise ValueError("slices list cannot be empty")

        # Detect whether input is GridTile list or Carousel Image list
        if isinstance(slices[0], GridTile):
            guide_img = cls._generate_grid_upload_guide(slices, title)  # type: ignore
        else:
            guide_img = cls._generate_carousel_upload_guide(slices, title)  # type: ignore

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            guide_img.save(output_path, quality=95, optimize=True)

        return guide_img

    @staticmethod
    def _generate_carousel_upload_guide(
        slices: List[Image.Image],
        title: str,
    ) -> Image.Image:
        """Generate aesthetic contact sheet for multi-slide carousel."""
        n_slices = len(slices)

        # Contact Sheet Dimensions
        guide_w = max(1600, n_slices * 280 + 120)
        guide_h = 1000

        guide = Image.new("RGB", (guide_w, guide_h), (18, 18, 22))
        draw = ImageDraw.Draw(guide)

        # Header Section
        font_title = get_pil_font(size=36, bold=True)
        font_sub = get_pil_font(size=18, bold=False)
        font_badge = get_pil_font(size=16, bold=True)
        font_tip_title = get_pil_font(size=20, bold=True)
        font_tips = get_pil_font(size=15, bold=False)

        draw.text((60, 45), title, fill=(255, 255, 255), font=font_title)
        draw.text(
            (60, 95),
            f"Multi-Slide Seamless Carousel ({n_slices} Slides) • Post in Numerical Order 1 ➔ {n_slices}",
            fill=(156, 163, 175),
            font=font_sub,
        )

        # Slide Thumbnails Row
        margin_x = 60
        margin_top = 160
        spacing = 28
        total_avail_w = guide_w - 2 * margin_x - (n_slices - 1) * spacing
        thumb_w = max(120, total_avail_w // n_slices)

        # Calculate thumb height matching slide aspect ratio
        first_w, first_h = slices[0].size
        thumb_h = int(round(thumb_w * (first_h / first_w)))
        max_thumb_h = 420
        if thumb_h > max_thumb_h:
            thumb_h = max_thumb_h
            thumb_w = int(round(thumb_h * (first_w / first_h)))
            # Recenter thumbnails row
            margin_x = (guide_w - (n_slices * thumb_w + (n_slices - 1) * spacing)) // 2

        for i, s_img in enumerate(slices):
            tx = margin_x + i * (thumb_w + spacing)
            ty = margin_top

            thumb = s_img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            guide.paste(thumb, (tx, ty))

            # Border around thumbnail
            draw.rectangle(
                [(tx, ty), (tx + thumb_w - 1, ty + thumb_h - 1)],
                outline=(59, 130, 246) if i == 0 else (75, 85, 99),
                width=2,
            )

            # Slide Number Badge above thumbnail
            badge_text = f"Slide {i + 1}"
            sub_text = "Upload 1st" if i == 0 else f"Step {i + 1}"

            bx = tx + thumb_w // 2
            draw.text((bx, ty - 32), badge_text, fill=(255, 255, 255), font=font_badge, anchor="mm")
            draw.text((bx, ty - 14), sub_text, fill=(147, 197, 253), font=font_tips, anchor="mm")

            # Upload sequence arrow between slides
            if i < n_slices - 1:
                arrow_cx = tx + thumb_w + spacing // 2
                arrow_cy = ty + thumb_h // 2
                draw.text((arrow_cx, arrow_cy), "➔", fill=(96, 165, 250), font=font_title, anchor="mm")

        # Pro Tips Card at the Bottom
        card_y = margin_top + thumb_h + 55
        card_h = guide_h - card_y - 40
        draw.rounded_rectangle(
            [(60, card_y), (guide_w - 60, card_y + card_h)],
            radius=12,
            fill=(28, 28, 35),
            outline=(60, 60, 75),
            width=1,
        )

        draw.text((90, card_y + 20), "💡 Instagram Upload Tips for Perfect Panoramas", fill=(96, 165, 250), font=font_tip_title)

        tips = [
            "1. In the Instagram App: Tap '+' then tap the multi-select (layered squares) icon.",
            f"2. Selection Sequence: Tap Slide 1 first, then Slide 2, then Slide 3 up to Slide {n_slices} in numerical order.",
            f"3. Framing: Tap the '< >' crop button in the bottom-left to set full {first_w}x{first_h} framing without auto-crop.",
            "4. Filters: Do not apply filters or vignettes in Instagram, preserving seamless color continuity across slides.",
        ]
        line_y = card_y + 55
        for tip in tips:
            draw.text((90, line_y), tip, fill=(209, 213, 219), font=font_tips)
            line_y += 26

        return guide

    @staticmethod
    def _generate_grid_upload_guide(
        tiles: List[GridTile],
        title: str,
    ) -> Image.Image:
        """Generate visual contact sheet for Instagram Profile Grids with reverse-upload guide."""
        rows = max(t.row for t in tiles) + 1
        cols = max(t.col for t in tiles) + 1
        total_tiles = len(tiles)

        guide_w = 1400
        guide_h = 1100

        guide = Image.new("RGB", (guide_w, guide_h), (18, 18, 22))
        draw = ImageDraw.Draw(guide)

        font_title = get_pil_font(size=36, bold=True)
        font_sub = get_pil_font(size=18, bold=False)
        font_badge = get_pil_font(size=18, bold=True)
        font_tip_title = get_pil_font(size=20, bold=True)
        font_tips = get_pil_font(size=15, bold=False)

        draw.text((60, 45), title, fill=(255, 255, 255), font=font_title)
        draw.text(
            (60, 95),
            f"Instagram Profile Grid ({cols}×{rows}) • Post in REVERSE Order: Upload #1 (Bottom Right) ➔ Upload #{total_tiles} (Top Left)",
            fill=(156, 163, 175),
            font=font_sub,
        )

        # Draw Grid Matrix Layout
        grid_start_x = 60
        grid_start_y = 150
        tile_preview_size = 180
        gap = 12

        for t in tiles:
            tx = grid_start_x + t.col * (tile_preview_size + gap)
            ty = grid_start_y + t.row * (tile_preview_size + gap)

            thumb = t.image.resize((tile_preview_size, tile_preview_size), Image.Resampling.LANCZOS)
            guide.paste(thumb, (tx, ty))

            # Border
            draw.rectangle(
                [(tx, ty), (tx + tile_preview_size - 1, ty + tile_preview_size - 1)],
                outline=(244, 63, 94) if t.upload_order == 1 else (59, 130, 246),
                width=2,
            )

            # Prominent Upload Sequence Overlay Badge
            badge_text = f"Post #{t.upload_order}"
            badge_sub = f"Tile {t.tile_number}"

            bx = tx + tile_preview_size // 2
            by = ty + tile_preview_size // 2

            # Badge pill
            draw.rounded_rectangle(
                [(bx - 60, by - 24), (bx + 60, by + 24)],
                radius=10,
                fill=(15, 15, 20, 215),
                outline=(255, 255, 255, 180),
                width=1,
            )
            draw.text((bx, by - 8), badge_text, fill=(255, 255, 255), font=font_badge, anchor="mm")
            draw.text((bx, by + 12), badge_sub, fill=(147, 197, 253), font=font_tips, anchor="mm")

        # Side Information Card
        card_x = grid_start_x + cols * (tile_preview_size + gap) + 40
        card_w = guide_w - card_x - 60
        card_y = grid_start_y
        card_h = rows * (tile_preview_size + gap)

        draw.rounded_rectangle(
            [(card_x, card_y), (card_x + card_w, card_y + card_h)],
            radius=12,
            fill=(28, 28, 35),
            outline=(60, 60, 75),
            width=1,
        )

        draw.text((card_x + 30, card_y + 25), "⚠️ Crucial: Why Reverse Order?", fill=(244, 63, 94), font=font_tip_title)

        tips = [
            "Instagram displays posts from newest (top-left) to oldest (bottom-right).",
            "",
            "To make your giant profile grid display properly:",
            "1. Upload Post #1 first (it will be pushed to the bottom-right).",
            f"2. Continue posting in order: Post #2, #3... up to Post #{total_tiles}.",
            f"3. Upload Post #{total_tiles} last (it will stay at the top-left).",
            "",
            "When viewers visit your Instagram profile page, all tiles will",
            "seamlessly fit together to form one giant panoramic image!",
        ]
        line_y = card_y + 65
        for tip in tips:
            draw.text((card_x + 30, line_y), tip, fill=(209, 213, 219), font=font_tips)
            line_y += 24

        return guide

    # -----------------------------------------------------------------------
    # File Export & Saving Helper
    # -----------------------------------------------------------------------

    @staticmethod
    def save_slices(
        slices: Union[List[Image.Image], List[GridTile]],
        export_dir: str,
        prefix: str = "panorama_slice",
        ext: str = "jpg",
        jpeg_quality: int = 95,
        optimize: bool = True,
    ) -> List[str]:
        """
        Save carousel slices or grid tiles to disk.
        Sanitizes RGBA transparency to clean RGB with white background for JPEGs.
        Embeds sRGB ICC profile for color consistency on Instagram mobile.
        Returns a list of saved file paths.
        """
        os.makedirs(export_dir, exist_ok=True)
        saved_paths: List[str] = []
        ext_clean = ext.lower().replace(".", "")
        is_jpeg = ext_clean in ("jpg", "jpeg")

        # Standard sRGB ICC profile to embed in JPEGs
        srgb_bytes: Optional[bytes] = None
        if is_jpeg:
            try:
                srgb_prof = ImageCms.createProfile("sRGB")
                srgb_bytes = ImageCms.ImageCmsProfile(srgb_prof).tobytes()
            except Exception:
                srgb_bytes = None

        for idx, item in enumerate(slices):
            if isinstance(item, GridTile):
                img = item.image
                filename = item.filename
            else:
                img = item
                filename = f"{prefix}_{idx + 1}.{ext_clean}"

            filepath = os.path.join(export_dir, filename)

            # Sanitize color mode for JPEG
            if is_jpeg:
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    # Paste onto pure white background
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    alpha_mask = img.convert("RGBA").split()[-1]
                    bg.paste(img.convert("RGBA"), mask=alpha_mask)
                    out_img = bg
                elif img.mode != "RGB":
                    out_img = img.convert("RGB")
                else:
                    out_img = img

                save_kwargs: Dict[str, Any] = {
                    "format": "JPEG",
                    "quality": jpeg_quality,
                    "optimize": optimize,
                    "subsampling": 0,  # 4:4:4 chroma subsampling for sharpest photo edges
                }
                if srgb_bytes:
                    save_kwargs["icc_profile"] = srgb_bytes

                out_img.save(filepath, **save_kwargs)
            else:
                # PNG export
                img.save(filepath, format="PNG", optimize=optimize)

            saved_paths.append(filepath)

        return saved_paths


# ---------------------------------------------------------------------------
# Module-Level Convenience Functions
# ---------------------------------------------------------------------------

def slice_panorama(
    image: Union[str, Path, Image.Image],
    config: Optional[SlicingConfig] = None,
    **kwargs: Any,
) -> List[Image.Image]:
    """Convenience functional wrapper for ImageEngine.slice_panorama."""
    return ImageEngine.slice_panorama(image, config, **kwargs)


def slice_grid(
    image: Union[str, Path, Image.Image],
    rows: int = 3,
    cols: int = 3,
    prefix: str = "grid",
    config: Optional[GridConfig] = None,
    **kwargs: Any,
) -> List[GridTile]:
    """Convenience functional wrapper for ImageEngine.slice_grid."""
    return ImageEngine.slice_grid(image, rows=rows, cols=cols, prefix=prefix, config=config, **kwargs)


def generate_upload_guide(
    slices: Union[List[Image.Image], List[GridTile]],
    output_path: Optional[str] = None,
    title: str = "Instagram Upload Sequence Guide",
) -> Image.Image:
    """Convenience functional wrapper for ImageEngine.generate_upload_guide."""
    return ImageEngine.generate_upload_guide(slices, output_path=output_path, title=title)


def save_slices(
    slices: Union[List[Image.Image], List[GridTile]],
    export_dir: str,
    prefix: str = "panorama_slice",
    ext: str = "jpg",
    jpeg_quality: int = 95,
    optimize: bool = True,
) -> List[str]:
    """Convenience functional wrapper for ImageEngine.save_slices."""
    return ImageEngine.save_slices(
        slices=slices,
        export_dir=export_dir,
        prefix=prefix,
        ext=ext,
        jpeg_quality=jpeg_quality,
        optimize=optimize,
    )
