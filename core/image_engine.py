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
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import ExifTags, Image, ImageChops, ImageCms, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

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
    color_filter: str = "None"
    include_camera_card: bool = False
    split_headline: Optional[str] = None
    story_mode: bool = False
    slice_weights: Optional[List[float]] = None
    format: str = "JPEG"  # "JPEG" or "PNG"
    jpeg_quality: int = 95
    prefix: str = "panorama_slice"
    tilt_angle: float = 0.0
    smart_seams: bool = False
    infinite_loop: bool = False
    split_orientation: str = "horizontal"
    before_after_mode: bool = False

    def __post_init__(self) -> None:
        """Validate and clamp configuration parameters."""
        if self.slice_weights:
            try:
                valid_weights = [float(w) for w in self.slice_weights if float(w) > 0]
                if valid_weights:
                    self.slice_weights = valid_weights
                    self.num_slices = max(2, min(10, len(valid_weights)))
                    if len(self.slice_weights) != self.num_slices:
                        self.slice_weights = self.slice_weights[:self.num_slices]
                else:
                    self.slice_weights = None
            except Exception:
                self.slice_weights = None

        self.num_slices = max(2, min(10, int(self.num_slices)))
        self.pan_offset_x = max(-1.0, min(1.0, float(self.pan_offset_x)))
        self.pan_offset_y = max(-1.0, min(1.0, float(self.pan_offset_y)))
        self.jpeg_quality = max(1, min(100, int(self.jpeg_quality)))
        self.format = "PNG" if self.format.upper() == "PNG" else "JPEG"
        self.tilt_angle = max(-10.0, min(10.0, float(self.tilt_angle)))
        self.smart_seams = bool(self.smart_seams)
        self.infinite_loop = bool(self.infinite_loop)
        self.split_orientation = "vertical" if str(self.split_orientation).strip().lower() == "vertical" else "horizontal"
        self.before_after_mode = bool(self.before_after_mode)

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
    def _load_dng_or_raw(file_path: Union[str, Path]) -> Image.Image:
        """Parse DNG/RAW image files, falling back to embedded full-resolution JPEG extraction."""
        path_str = str(file_path)
        with open(path_str, "rb") as f:
            raw_bytes = f.read()

        try:
            candidate = Image.open(io.BytesIO(raw_bytes))
            # Check TIFF tag 0x0201 (JPEGInterchangeFormat)
            if hasattr(candidate, "tag_v2") and 0x0201 in candidate.tag_v2:
                offset = candidate.tag_v2[0x0201]
                length = candidate.tag_v2.get(0x0202, None)
                jpeg_data = raw_bytes[offset : offset + length] if length else raw_bytes[offset:]
                return Image.open(io.BytesIO(jpeg_data))
            if candidate.mode in ("RGB", "RGBA", "L"):
                candidate.load()
                return candidate
        except Exception:
            pass

        # Scan for embedded full-resolution JPEG stream (0xFFD8FF ... 0xFFD9)
        idx = 0
        best_img = None
        best_pixels = 0
        while True:
            idx = raw_bytes.find(b"\xff\xd8\xff", idx)
            if idx == -1:
                break
            end_idx = raw_bytes.find(b"\xff\xd9", idx + 2)
            if end_idx != -1:
                chunk = raw_bytes[idx : end_idx + 2]
                try:
                    cand = Image.open(io.BytesIO(chunk))
                    cand.load()
                    pixels = cand.width * cand.height
                    if pixels > best_pixels:
                        best_pixels = pixels
                        best_img = cand
                except Exception:
                    pass
                idx = end_idx + 2
            else:
                idx += 3

        if best_img is not None:
            return best_img

        return Image.open(path_str)

    @staticmethod
    def load_image(source: Union[str, Path, Image.Image]) -> Image.Image:
        """
        Load an image from file path or PIL Image object.
        Supports HEIC/HEIF (via pillow_heif) and DNG/RAW files with embedded JPEG fallback.
        Applies pre-decompression dimension checks and EXIF orientation normalization.
        """
        Image.MAX_IMAGE_PIXELS = None

        # Register HEIC/HEIF opener if pillow_heif is available
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:
            pass

        if isinstance(source, (str, Path)):
            src_str = str(source).lower()
            if src_str.endswith((".dng", ".raw", ".cr2", ".nef", ".arw")):
                img = ImageEngine._load_dng_or_raw(source)
            else:
                try:
                    img = Image.open(str(source))
                except Exception:
                    try:
                        img = ImageEngine._load_dng_or_raw(source)
                    except Exception:
                        raise
        elif isinstance(source, Image.Image):
            img = source
        else:
            raise TypeError(f"Expected file path or PIL Image, got {type(source).__name__}")

        # Memory safety guard for cloud containers (Render 512MB RAM limit):
        # We check dimensions BEFORE decompressing the full bitmap or rotating.
        # Huge smartphone/drone panoramas (30-100MP) allocate multiple 100MB+ buffers.
        # Using reduce() decodes directly at a safe, crisp resolution (capped at ~4500px),
        # keeping peak RAM under 180MB while maintaining 100% retina clarity for 1080px slices.
        max_dim = 4500
        largest_dim = max(img.width, img.height)
        if largest_dim > max_dim:
            import math
            factor = max(1, math.ceil(largest_dim / max_dim))
            if factor > 1:
                try:
                    img = img.reduce(factor)
                except Exception:
                    pass

        # Correct smartphone rotation metadata on the safe, reduced image
        try:
            transposed = ImageOps.exif_transpose(img)
            if transposed is not None:
                img = transposed
        except Exception:
            pass

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

    @staticmethod
    def apply_color_filter(img: Image.Image, filter_name: str) -> Image.Image:
        """
        Apply color grading and film presets using memory-efficient PIL transformations.
        Supported filters:
          - 'None': Unmodified image
          - 'Cinematic Moody': Cool shadows, warm highlights, high contrast
          - 'Kodak Warmth': Warm golden cast, gentle red/yellow boost
          - 'Vintage 35mm': Raised blacks (faded matte shadows), warm analog tone
          - 'B&W High Contrast': Rich monochrome with punchy contrast
          - 'Film Grain': Subtle randomized noise texture overlay
        """
        name = (filter_name or "").strip().lower()
        if not name or name == "none":
            return img

        orig_mode = img.mode
        working_img = img.convert("RGB")

        if name == "cinematic moody":
            lut_r = [int(min(255, max(0, ((i / 255.0) ** 1.2) * 255 * 1.08 + (6 if i > 128 else -8)))) for i in range(256)]
            lut_g = [int(min(255, max(0, ((i / 255.0) ** 1.15) * 255))) for i in range(256)]
            lut_b = [int(min(255, max(0, ((i / 255.0) ** 1.1) * 255 * 0.92 + (16 if i < 128 else -10)))) for i in range(256)]
            r, g, b = working_img.split()
            working_img = Image.merge("RGB", (r.point(lut_r), g.point(lut_g), b.point(lut_b)))
            working_img = ImageEnhance.Contrast(working_img).enhance(1.15)

        elif name == "kodak warmth":
            lut_r = [int(min(255, max(0, i * 1.06 + 6))) for i in range(256)]
            lut_g = [int(min(255, max(0, i * 1.02 + 2))) for i in range(256)]
            lut_b = [int(min(255, max(0, i * 0.90 - 4))) for i in range(256)]
            r, g, b = working_img.split()
            working_img = Image.merge("RGB", (r.point(lut_r), g.point(lut_g), b.point(lut_b)))
            working_img = ImageEnhance.Color(working_img).enhance(1.12)

        elif name == "vintage 35mm":
            lut_r = [int(min(255, max(0, 30 + (i / 255.0) * 218))) for i in range(256)]
            lut_g = [int(min(255, max(0, 26 + (i / 255.0) * 216))) for i in range(256)]
            lut_b = [int(min(255, max(0, 36 + (i / 255.0) * 200))) for i in range(256)]
            r, g, b = working_img.split()
            working_img = Image.merge("RGB", (r.point(lut_r), g.point(lut_g), b.point(lut_b)))

        elif name == "b&w high contrast":
            gray = working_img.convert("L")
            contrast_lut = [int(min(255, max(0, 255.0 / (1.0 + math.exp(-0.035 * (i - 128)))))) for i in range(256)]
            gray = gray.point(contrast_lut)
            working_img = ImageEnhance.Contrast(gray.convert("RGB")).enhance(1.25)

        elif name == "film grain":
            w, h = working_img.size
            tile_size = 512
            noise_bytes = bytes([min(255, max(0, int(random.gauss(128, 16)))) for _ in range(tile_size * tile_size)])
            tile = Image.frombytes("L", (tile_size, tile_size), noise_bytes).convert("RGB")
            noise_img = Image.new("RGB", (w, h))
            for x in range(0, w, tile_size):
                for y in range(0, h, tile_size):
                    noise_img.paste(tile, (x, y))
            working_img = ImageChops.soft_light(working_img, noise_img)

        if orig_mode in ("RGBA", "LA"):
            alpha = img.split()[-1]
            working_img.putalpha(alpha)
            return working_img
        return working_img

    @staticmethod
    def extract_exif_metadata(source: Union[str, Path, Image.Image]) -> Dict[str, str]:
        """
        Extract photography EXIF metadata from an image path or PIL Image.
        Returns a dictionary containing camera make/model, lens, focal length,
        aperture, shutter speed, ISO, and date.
        """
        img: Optional[Image.Image] = None
        should_close = False
        if isinstance(source, (str, Path)):
            try:
                img = Image.open(str(source))
                should_close = True
            except Exception:
                img = None
        elif isinstance(source, Image.Image):
            img = source

        exif_raw: Dict[str, Any] = {}
        if img is not None:
            try:
                exif = img.getexif()
                if exif:
                    for k, v in exif.items():
                        tag_name = ExifTags.TAGS.get(k, str(k))
                        exif_raw[tag_name] = v
                    if hasattr(ExifTags, "IFD") and hasattr(ExifTags.IFD, "Exif"):
                        try:
                            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
                            if exif_ifd:
                                for k, v in exif_ifd.items():
                                    tag_name = ExifTags.TAGS.get(k, str(k))
                                    exif_raw[tag_name] = v
                        except Exception:
                            pass
            except Exception:
                pass
            finally:
                if should_close and img is not None:
                    try:
                        img.close()
                    except Exception:
                        pass

        meta: Dict[str, str] = {}
        make = str(exif_raw.get("Make", "")).strip()
        model = str(exif_raw.get("Model", "")).strip()
        if make and model:
            if model.lower().startswith(make.lower()):
                camera = model
            else:
                camera = f"{make} {model}"
        elif model:
            camera = model
        elif make:
            camera = make
        else:
            camera = "Unknown Camera"

        meta["camera"] = camera
        meta["make"] = make or "Unknown"
        meta["model"] = model or "Unknown"

        lens = str(exif_raw.get("LensModel", "")).strip()
        meta["lens"] = lens or "Standard Lens"

        fl = exif_raw.get("FocalLength")
        if fl is not None:
            try:
                fl_val = float(fl)
                if fl_val.is_integer():
                    meta["focal_length"] = f"{int(fl_val)}mm"
                else:
                    meta["focal_length"] = f"{fl_val:.1f}mm"
            except Exception:
                meta["focal_length"] = f"{fl}mm"
        else:
            meta["focal_length"] = "Unknown FL"

        fn = exif_raw.get("FNumber")
        if fn is not None:
            try:
                fn_val = float(fn)
                if fn_val.is_integer():
                    meta["aperture"] = f"f/{int(fn_val)}"
                else:
                    meta["aperture"] = f"f/{fn_val:.1f}"
            except Exception:
                meta["aperture"] = f"f/{fn}"
        else:
            meta["aperture"] = "Unknown Aperture"

        et = exif_raw.get("ExposureTime")
        if et is not None:
            try:
                et_val = float(et)
                if 0 < et_val < 1.0:
                    meta["shutter_speed"] = f"1/{int(round(1.0 / et_val))}s"
                else:
                    meta["shutter_speed"] = f"{et_val:.1f}s"
            except Exception:
                meta["shutter_speed"] = f"{et}s"
        else:
            meta["shutter_speed"] = "Unknown Shutter"

        iso = (
            exif_raw.get("ISOSpeedRatings")
            or exif_raw.get("PhotographicSensitivity")
            or exif_raw.get("ISO")
        )
        if iso is not None:
            meta["iso"] = f"ISO {iso}"
        else:
            meta["iso"] = "Unknown ISO"

        dt = str(exif_raw.get("DateTimeOriginal") or exif_raw.get("DateTime") or "").strip()
        if dt:
            meta["date"] = dt.split()[0].replace(":", "-")
        else:
            meta["date"] = "Unknown Date"

        return meta

    @staticmethod
    def generate_camera_card(
        exif_data: Dict[str, str],
        width: int = 1080,
        height: int = 1350,
    ) -> Image.Image:
        """
        Generate a minimalist dark aesthetic photography card with camera specs and shooting details.
        """
        card = Image.new("RGB", (width, height), (13, 15, 18))
        draw = ImageDraw.Draw(card)

        # Inset minimalist border
        pad = max(20, int(width * 0.037))
        draw.rounded_rectangle(
            [(pad, pad), (width - pad, height - pad)],
            radius=20,
            fill=(19, 21, 26),
            outline=(38, 42, 53),
            width=2,
        )

        font_badge = get_pil_font(size=16, bold=True)
        font_cam = get_pil_font(size=42, bold=True)
        font_lens = get_pil_font(size=22, bold=False)
        font_lbl = get_pil_font(size=15, bold=True)
        font_val = get_pil_font(size=34, bold=True)
        font_foot = get_pil_font(size=16, bold=False)

        # Header tag
        draw.text((width // 2, pad + 55), "CAMERA & EXPOSURE DATA", fill=(148, 163, 184), font=font_badge, anchor="mm")

        # Camera name
        cam_name = exif_data.get("camera") or "Unknown Camera"
        draw.text((width // 2, pad + 115), cam_name, fill=(255, 255, 255), font=font_cam, anchor="mm")

        # Lens name
        lens_name = exif_data.get("lens") or "Standard Lens"
        draw.text((width // 2, pad + 170), lens_name, fill=(156, 163, 175), font=font_lens, anchor="mm")

        # Subtle divider line
        div_y = pad + 215
        draw.line([(pad + 50, div_y), (width - pad - 50, div_y)], fill=(45, 50, 62), width=1)

        # 2x2 grid of key shooting parameters
        params = [
            ("FOCAL LENGTH", exif_data.get("focal_length", "-")),
            ("APERTURE", exif_data.get("aperture", "-")),
            ("SHUTTER SPEED", exif_data.get("shutter_speed", "-")),
            ("ISO SPEED", exif_data.get("iso", "-")),
        ]

        grid_top = div_y + 35
        grid_bot = height - pad - 110
        row_h = max(60, (grid_bot - grid_top - 20) // 2)
        col_w = max(100, (width - 2 * pad - 120) // 2)

        for idx, (label, val) in enumerate(params):
            r = idx // 2
            c = idx % 2
            bx0 = pad + 50 + c * (col_w + 20)
            by0 = grid_top + r * (row_h + 20)
            bx1 = bx0 + col_w
            by1 = by0 + row_h

            draw.rounded_rectangle(
                [(bx0, by0), (bx1, by1)],
                radius=14,
                fill=(26, 29, 36),
                outline=(48, 53, 66),
                width=1,
            )

            cx = (bx0 + bx1) // 2
            draw.text((cx, by0 + int(row_h * 0.32)), label, fill=(148, 163, 184), font=font_lbl, anchor="mm")
            draw.text((cx, by0 + int(row_h * 0.68)), str(val), fill=(255, 255, 255), font=font_val, anchor="mm")

        # Footer date stamp
        dt = exif_data.get("date", "Unknown Date")
        foot_text = f"DATE: {dt}  •  INSTAPANORAMA PHOTO CARD"
        draw.text((width // 2, height - pad - 45), foot_text, fill=(100, 116, 139), font=font_foot, anchor="mm")

        return card

    # -----------------------------------------------------------------------
    # Advanced Geometry & Smart Seam Tools
    # -----------------------------------------------------------------------

    @staticmethod
    def detect_horizon_tilt(image: Image.Image) -> float:
        """
        Calculate horizon tilt angle in [-10.0, 10.0] degrees using horizontal gradient / projection profile analysis.
        """
        import numpy as np
        orig_w, orig_h = image.size
        proxy_w = 600
        if orig_w > proxy_w:
            proxy_h = max(10, int(round(orig_h * (proxy_w / orig_w))))
            proxy_img = image.resize((proxy_w, proxy_h), Image.Resampling.BILINEAR)
        else:
            proxy_img = image

        gray = proxy_img.convert("L")
        arr = np.array(gray, dtype=float)
        h, w = arr.shape
        if h < 20 or w < 20:
            return 0.0

        gy = np.abs(arr[2:, 1:-1] - arr[:-2, 1:-1])
        if float(np.max(gy)) < 1.0 or float(np.sum(gy)) < 10.0:
            return 0.0

        coarse_angles = np.linspace(-10.0, 10.0, 41)
        best_coarse = 0.0
        max_var = -1.0
        zero_var = 0.0

        edge_img = Image.fromarray(gy)
        ch, cw = gy.shape

        for a in coarse_angles:
            rot = edge_img.rotate(a, resample=Image.Resampling.BILINEAR)
            rot_arr = np.array(rot)
            crop = rot_arr[int(ch * 0.15) : int(ch * 0.85), int(cw * 0.15) : int(cw * 0.85)]
            row_sums = np.sum(crop, axis=1)
            v = float(np.var(row_sums))
            if abs(a) < 1e-4:
                zero_var = v
            if v > max_var:
                max_var = v
                best_coarse = a

        if max_var < 1.0:
            return 0.0

        fine_angles = np.linspace(best_coarse - 0.6, best_coarse + 0.6, 25)
        best_fine = best_coarse
        for a in fine_angles:
            if a < -10.0 or a > 10.0:
                continue
            rot = edge_img.rotate(a, resample=Image.Resampling.BILINEAR)
            rot_arr = np.array(rot)
            crop = rot_arr[int(ch * 0.15) : int(ch * 0.85), int(cw * 0.15) : int(cw * 0.85)]
            v = float(np.var(np.sum(crop, axis=1)))
            if v > max_var:
                max_var = v
                best_fine = a

        if zero_var > 0 and (max_var / zero_var) < 1.03:
            return 0.0

        return round(float(np.clip(best_fine, -10.0, 10.0)), 2)

    @staticmethod
    def rotate_and_crop(image: Image.Image, angle: float) -> Image.Image:
        """
        Rotate image by `angle` degrees and crop to the maximum inscribed rectangle
        so no black corners or borders appear.
        """
        if abs(angle) < 1e-4:
            return image.copy()

        w0, h0 = image.size
        rad = math.radians(abs(angle))
        sin_a = math.sin(rad)
        cos_a = math.cos(rad)

        w_rot = w0 * cos_a + h0 * sin_a
        h_rot = w0 * sin_a + h0 * cos_a

        s = min(w0 / w_rot, h0 / h_rot)
        crop_w = max(1, int(math.floor(w0 * s)))
        crop_h = max(1, int(math.floor(h0 * s)))

        rotated = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        rot_w, rot_h = rotated.size

        left = max(0, int((rot_w - crop_w) / 2))
        top = max(0, int((rot_h - crop_h) / 2))
        right = min(rot_w, left + crop_w)
        bottom = min(rot_h, top + crop_h)

        return rotated.crop((left, top, right, bottom))

    @staticmethod
    def compute_smart_seams(
        image: Image.Image,
        num_slices: int,
        search_margin_ratio: float = 0.08,
    ) -> List[int]:
        """
        Compute vertical gradient energy around default equidistant seams to find minimum valley seams,
        avoiding cutting through high-energy subjects like faces or buildings.
        Returns:
            List of (num_slices - 1) seam X coordinates.
        """
        import numpy as np
        if num_slices <= 1:
            return []

        w, h = image.size
        proxy_h = 300
        scale = proxy_h / max(1, h)
        proxy_w = max(num_slices, int(round(w * scale)))

        gray = image.convert("L").resize((proxy_w, proxy_h), Image.Resampling.BILINEAR)
        arr = np.array(gray, dtype=float)

        gx = np.zeros_like(arr)
        gy = np.zeros_like(arr)
        gx[:, 1:-1] = (arr[:, 2:] - arr[:, :-2]) / 2.0
        gy[1:-1, :] = (arr[2:, :] - arr[:-2, :]) / 2.0
        energy = np.sqrt(gx**2 + gy**2)

        col_energy = np.sum(energy, axis=0)
        margin = max(1, int(round(proxy_w * search_margin_ratio)))
        seams = []

        for i in range(1, num_slices):
            default_x = int(round(i * proxy_w / num_slices))
            x_start = max(0, default_x - margin)
            x_end = min(proxy_w - 1, default_x + margin)

            if seams:
                x_start = max(x_start, seams[-1] + 1)
            if x_start >= x_end:
                seams.append(default_x)
                continue

            window = col_energy[x_start : x_end + 1]
            best_local_x = int(np.argmin(window))
            seams.append(int(x_start + best_local_x))

        orig_seams = [int(round(s / scale)) for s in seams]
        clamped_seams = []
        prev = 0
        for s in orig_seams:
            s_clamped = max(prev + 1, min(w - 1, s))
            clamped_seams.append(s_clamped)
            prev = s_clamped

        return clamped_seams

    @staticmethod
    def _apply_infinite_loop_wrap(img: Image.Image, pan_offset_x: float = 0.0) -> Image.Image:
        """Seamlessly blend left and right boundaries for 360-degree panoramas, with cyclic shift."""
        import numpy as np
        arr = np.array(img).astype(np.float32)
        h, w = arr.shape[:2]
        if w < 20:
            return img

        if abs(pan_offset_x) > 1e-4:
            shift_x = int(round(w * (pan_offset_x / 2.0)))
            arr = np.roll(arr, shift_x, axis=1)

        blend_width = max(10, min(int(round(w * 0.04)), w // 4))
        for k in range(blend_width):
            alpha = k / float(blend_width)
            left_col = arr[:, k]
            right_col = arr[:, w - blend_width + k]
            blended = (1.0 - alpha) * right_col + alpha * left_col
            arr[:, k] = blended
            arr[:, w - blend_width + k] = blended

        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

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

        # 1. Apply horizon tilt angle correction if specified
        if abs(config.tilt_angle) > 1e-4:
            img = cls.rotate_and_crop(img, config.tilt_angle)

        # 2. Apply infinite loop wrap if 360 panorama
        if config.infinite_loop and config.split_orientation != "vertical":
            img = cls._apply_infinite_loop_wrap(img, config.pan_offset_x)

        orig_w, orig_h = img.size

        target_w, target_h = config.get_target_dimensions()
        n_slices = config.num_slices
        fit_mode = config.fit_mode.strip()

        # Handle Vertical Split Orientation (top to bottom stacked slides)
        if config.split_orientation == "vertical":
            total_target_w = target_w
            total_target_h = target_h * n_slices

            if "proportional" in fit_mode.lower():
                scale = target_w / orig_w
                new_w = target_w
                new_h = max(n_slices, int(round(orig_h * scale)))
                carousel_canvas = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                slice_boundaries_y = [
                    (
                        int(round(i * new_h / n_slices)),
                        int(round((i + 1) * new_h / n_slices)),
                    )
                    for i in range(n_slices)
                ]
            elif "blurred" in fit_mode.lower():
                carousel_canvas = cls._build_blurred_fill_canvas(
                    img, total_target_w, total_target_h, config.pan_offset_x, config.pan_offset_y
                )
                slice_boundaries_y = [(i * target_h, (i + 1) * target_h) for i in range(n_slices)]
            elif "gallery" in fit_mode.lower() or "solid" in fit_mode.lower() or "border" in fit_mode.lower():
                carousel_canvas = cls._build_gallery_border_canvas(
                    img,
                    total_target_w,
                    total_target_h,
                    config.border_color,
                    config.border_padding,
                    config.pan_offset_x,
                    config.pan_offset_y,
                )
                slice_boundaries_y = [(i * target_h, (i + 1) * target_h) for i in range(n_slices)]
            else:
                carousel_canvas = cls._build_standard_fit_canvas(
                    img, total_target_w, total_target_h, config.pan_offset_x, config.pan_offset_y
                )
                slice_boundaries_y = [(i * target_h, (i + 1) * target_h) for i in range(n_slices)]

            if config.color_filter and config.color_filter.strip().lower() != "none":
                carousel_canvas = cls.apply_color_filter(carousel_canvas, config.color_filter)

            total_display_slices = n_slices + 1 if config.include_camera_card else n_slices

            slices = []
            for i, (y0, y1) in enumerate(slice_boundaries_y):
                slice_img = carousel_canvas.crop((0, y0, target_w, y1))
                if slice_img.size != (target_w, target_h) and "proportional" not in fit_mode.lower():
                    slice_img = slice_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                slice_img = cls._apply_slide_overlays(slice_img, i, total_display_slices, config)
                slices.append(slice_img)

            if config.include_camera_card:
                exif_data = cls.extract_exif_metadata(image)
                card_img = cls.generate_camera_card(exif_data, width=target_w, height=target_h)
                slices.append(card_img)

            return slices

        # Horizontal Carousel Canvas Construction
        total_target_w = target_w * n_slices

        # Build carousel canvas according to the requested fit mode
        if "proportional" in fit_mode.lower():
            # Strategy: Proportional Full Width (No Crop)
            scale = target_h / orig_h
            new_w = max(n_slices, int(round(orig_w * scale)))
            new_h = target_h

            carousel_canvas = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Apply color filter
            if config.color_filter and config.color_filter.strip().lower() != "none":
                carousel_canvas = cls.apply_color_filter(carousel_canvas, config.color_filter)

            if config.smart_seams and not config.slice_weights:
                seams = cls.compute_smart_seams(carousel_canvas, n_slices)
                slice_boundaries = []
                prev_x = 0
                for s in seams:
                    slice_boundaries.append((prev_x, s))
                    prev_x = s
                slice_boundaries.append((prev_x, new_w))
            elif config.slice_weights:
                W = sum(config.slice_weights)
                widths = [int(round(new_w * (w / W))) for w in config.slice_weights]
                widths[-1] = new_w - sum(widths[:-1])
                slice_boundaries = []
                curr = 0
                for w in widths:
                    slice_boundaries.append((curr, curr + w))
                    curr += w
            else:
                slice_boundaries = [
                    (
                        int(round(i * new_w / n_slices)),
                        int(round((i + 1) * new_w / n_slices)),
                    )
                    for i in range(n_slices)
                ]

            # Split-seam headline across boundary 1
            if config.split_headline and len(slice_boundaries) >= 2:
                seam_x = slice_boundaries[0][1]
                carousel_canvas = cls._draw_split_headline(
                    carousel_canvas, seam_x, target_h, config.split_headline
                )

            # Draw Seam Arrow across slide boundaries if requested
            if config.swipe_indicator == "Seam Arrow":
                carousel_canvas = cls._draw_seam_arrows_proportional(
                    carousel_canvas, slice_boundaries, target_h
                )

            total_display_slices = n_slices + 1 if config.include_camera_card else n_slices

            # Extract individual slices
            slices: List[Image.Image] = []
            for i, (x0, x1) in enumerate(slice_boundaries):
                slice_img = carousel_canvas.crop((x0, 0, x1, new_h))
                slice_img = cls._apply_slide_overlays(slice_img, i, total_display_slices, config)
                slices.append(slice_img)

            # Append camera card if requested
            if config.include_camera_card:
                exif_data = cls.extract_exif_metadata(image)
                card_w = slice_boundaries[-1][1] - slice_boundaries[-1][0] if slice_boundaries else target_w
                card_img = cls.generate_camera_card(exif_data, width=card_w, height=target_h)
                slices.append(card_img)

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

        # Apply color filter
        if config.color_filter and config.color_filter.strip().lower() != "none":
            carousel_canvas = cls.apply_color_filter(carousel_canvas, config.color_filter)

        # Determine slice boundaries (uniform, custom weights, or smart seams)
        if config.smart_seams and not config.slice_weights:
            seams = cls.compute_smart_seams(carousel_canvas, n_slices)
            slice_boundaries = []
            prev_x = 0
            for s in seams:
                slice_boundaries.append((prev_x, s))
                prev_x = s
            slice_boundaries.append((prev_x, total_target_w))
        elif config.slice_weights:
            W = sum(config.slice_weights)
            widths = [int(round(total_target_w * (w / W))) for w in config.slice_weights]
            widths[-1] = total_target_w - sum(widths[:-1])
            slice_boundaries = []
            curr = 0
            for w in widths:
                slice_boundaries.append((curr, curr + w))
                curr += w
        else:
            slice_boundaries = [
                (i * target_w, (i + 1) * target_w)
                for i in range(n_slices)
            ]

        # Draw Split-Seam Headline across boundary between Slide 1 and Slide 2
        if config.split_headline and len(slice_boundaries) >= 2:
            seam_x = slice_boundaries[0][1]
            carousel_canvas = cls._draw_split_headline(
                carousel_canvas, seam_x, target_h, config.split_headline
            )

        # Draw Seam Arrows on unified canvas before slicing to guarantee exact seam alignment
        if config.swipe_indicator == "Seam Arrow":
            carousel_canvas = cls._draw_seam_arrows_proportional(
                carousel_canvas, slice_boundaries, target_h
            )

        total_display_slices = n_slices + 1 if config.include_camera_card else n_slices

        # Slice into slides
        slices = []
        for i, (x0, x1) in enumerate(slice_boundaries):
            slice_img = carousel_canvas.crop((x0, 0, x1, target_h))
            if slice_img.size != (target_w, target_h) and not config.slice_weights and "proportional" not in fit_mode.lower():
                slice_img = slice_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            slice_img = cls._apply_slide_overlays(slice_img, i, total_display_slices, config)
            slices.append(slice_img)

        # Append camera card if requested
        if config.include_camera_card:
            exif_data = cls.extract_exif_metadata(image)
            card_img = cls.generate_camera_card(exif_data, width=target_w, height=target_h)
            slices.append(card_img)

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
        """
        Scale and crop image to fill exact carousel dimensions with pan offsets.
        Uses a crop-first strategy to crop directly from the original image before resizing.
        This reduces peak RAM consumption by ~70% and prevents cloud OOM errors.
        """
        orig_w, orig_h = img.size
        scale = max(total_w / orig_w, target_h / orig_h)

        # Region dimensions in original image coordinates
        crop_region_w = total_w / scale
        crop_region_h = target_h / scale

        excess_orig_x = max(0.0, orig_w - crop_region_w)
        excess_orig_y = max(0.0, orig_h - crop_region_h)

        crop_x0 = int(round(excess_orig_x * (pan_x + 1.0) / 2.0))
        crop_y0 = int(round(excess_orig_y * (pan_y + 1.0) / 2.0))
        crop_x0 = max(0, min(crop_x0, int(round(excess_orig_x))))
        crop_y0 = max(0, min(crop_y0, int(round(excess_orig_y))))
        crop_x1 = min(orig_w, int(round(crop_x0 + crop_region_w)))
        crop_y1 = min(orig_h, int(round(crop_y0 + crop_region_h)))

        cropped = img.crop((crop_x0, crop_y0, crop_x1, crop_y1))
        resized = cropped.resize((total_w, target_h), Image.Resampling.LANCZOS)

        if resized.mode in ("RGBA", "LA") or (resized.mode == "P" and "transparency" in resized.info):
            bg = Image.new("RGBA", resized.size, (255, 255, 255, 255))
            return Image.alpha_composite(bg, resized.convert("RGBA")).convert("RGB")
        return resized

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

        # 5. Instagram Story Tap-Through Mode (9:16)
        if config.story_mode:
            cls._draw_story_progress_bars(draw, sw, sh, slide_index, total_slices)
            cls._draw_story_tap_cue(draw, sw, sh, slide_index, total_slices)

        # 6. Before / After Mode Badges
        if config.before_after_mode:
            if slide_index == 0:
                cls._draw_before_badge(draw, sw, sh)
            elif slide_index == 1:
                cls._draw_after_badge(draw, sw, sh)

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
    def _draw_before_badge(draw: ImageDraw.ImageDraw, sw: int, sh: int) -> None:
        """Render a modern 'BEFORE ➔' badge on Slide 1."""
        font = get_pil_font(size=26, bold=True)
        text = "BEFORE ➔"

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

        draw.rounded_rectangle(
            [(bx0, by0), (bx1, by1)],
            radius=badge_h // 2,
            fill=(15, 15, 20, 195),
            outline=(255, 255, 255, 160),
            width=2,
        )

        draw.text(
            (bx0 + pad_x, by0 + pad_y - 2),
            text,
            fill=(255, 255, 255, 245),
            font=font,
        )

    @staticmethod
    def _draw_after_badge(draw: ImageDraw.ImageDraw, sw: int, sh: int) -> None:
        """Render a modern '✨ AFTER' badge on Slide 2."""
        font = get_pil_font(size=26, bold=True)
        text = "✨ AFTER"

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x = 24
        pad_y = 14
        badge_w = text_w + pad_x * 2
        badge_h = text_h + pad_y * 2

        margin_left = 45
        margin_bottom = 60

        bx0 = margin_left
        by0 = sh - margin_bottom - badge_h
        bx1 = bx0 + badge_w
        by1 = by0 + badge_h

        draw.rounded_rectangle(
            [(bx0, by0), (bx1, by1)],
            radius=badge_h // 2,
            fill=(15, 15, 20, 195),
            outline=(255, 215, 0, 200),
            width=2,
        )

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

    @staticmethod
    def _draw_split_headline(
        canvas: Image.Image,
        seam_x: int,
        target_h: int,
        headline: str,
    ) -> Image.Image:
        """
        Render large bold headline text positioned across the cut boundary between
        Slide 1 and Slide 2 (centered horizontally on X = seam_x).
        When sliced, the first half of the phrase is on Slide 1 and the second
        half is on Slide 2, forming a seamless swipe prompt!
        """
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font = get_pil_font(size=64, bold=True)
        bbox = draw.textbbox((0, 0), headline, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        tx = seam_x - tw // 2
        ty = int(target_h * 0.48) - th // 2

        pad_x = 24
        pad_y = 14
        # Translucent contrast backing pill
        draw.rounded_rectangle(
            [(tx - pad_x, ty - pad_y), (tx + tw + pad_x, ty + th + pad_y)],
            radius=12,
            fill=(10, 10, 15, 175),
            outline=(255, 255, 255, 120),
            width=2,
        )

        # Drop shadow for crisp readability
        draw.text((tx + 2, ty + 2), headline, fill=(0, 0, 0, 220), font=font)
        draw.text((tx, ty), headline, fill=(255, 255, 255, 255), font=font)

        canvas_rgba = canvas.convert("RGBA")
        result = Image.alpha_composite(canvas_rgba, overlay)
        return result.convert("RGB")

    @staticmethod
    def _draw_story_progress_bars(
        draw: ImageDraw.ImageDraw,
        sw: int,
        sh: int,
        slide_index: int,
        total_slices: int,
    ) -> None:
        """Draw segmented Instagram Story progress bars along the top edge."""
        bar_y = 32
        bar_h = 5
        margin_x = 28
        gap = 8
        avail_w = max(10, sw - 2 * margin_x - (total_slices - 1) * gap)
        seg_w = max(1, avail_w // total_slices)

        for j in range(total_slices):
            x0 = margin_x + j * (seg_w + gap)
            x1 = x0 + seg_w
            # Drop shadow
            draw.rounded_rectangle(
                [(x0, bar_y + 1), (x1, bar_y + bar_h + 1)],
                radius=max(1, bar_h // 2),
                fill=(0, 0, 0, 120),
            )
            # Active/past vs upcoming segment color
            if j <= slide_index:
                color = (255, 255, 255, 255)
            else:
                color = (255, 255, 255, 90)
            draw.rounded_rectangle(
                [(x0, bar_y), (x1, bar_y + bar_h)],
                radius=max(1, bar_h // 2),
                fill=color,
            )

    @staticmethod
    def _draw_story_tap_cue(
        draw: ImageDraw.ImageDraw,
        sw: int,
        sh: int,
        slide_index: int,
        total_slices: int,
    ) -> None:
        """Draw subtle 'Tap to continue ➔' cue on the right border."""
        if slide_index >= total_slices - 1:
            return

        text = "Tap to continue ➔"
        font = get_pil_font(size=18, bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        pad_x = 16
        pad_y = 10
        pill_w = tw + pad_x * 2
        pill_h = th + pad_y * 2

        bx0 = sw - 24 - pill_w
        by0 = int(sh * 0.5) - pill_h // 2

        # Translucent glass pill
        draw.rounded_rectangle(
            [(bx0, by0), (bx0 + pill_w, by0 + pill_h)],
            radius=pill_h // 2,
            fill=(15, 15, 20, 180),
            outline=(255, 255, 255, 120),
            width=1,
        )
        draw.text(
            (bx0 + pad_x, by0 + pad_y - 1),
            text,
            fill=(255, 255, 255, 245),
            font=font,
        )

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


def apply_color_filter(img: Image.Image, filter_name: str) -> Image.Image:
    """Convenience functional wrapper for ImageEngine.apply_color_filter."""
    return ImageEngine.apply_color_filter(img, filter_name)


def extract_exif_metadata(source: Union[str, Path, Image.Image]) -> Dict[str, str]:
    """Convenience functional wrapper for ImageEngine.extract_exif_metadata."""
    return ImageEngine.extract_exif_metadata(source)


def generate_camera_card(
    exif_data: Dict[str, str],
    width: int = 1080,
    height: int = 1350,
) -> Image.Image:
    """Convenience functional wrapper for ImageEngine.generate_camera_card."""
    return ImageEngine.generate_camera_card(exif_data, width=width, height=height)


def detect_horizon_tilt(image: Image.Image) -> float:
    """Convenience functional wrapper for ImageEngine.detect_horizon_tilt."""
    return ImageEngine.detect_horizon_tilt(image)


def rotate_and_crop(image: Image.Image, angle: float) -> Image.Image:
    """Convenience functional wrapper for ImageEngine.rotate_and_crop."""
    return ImageEngine.rotate_and_crop(image, angle)


def compute_smart_seams(
    image: Image.Image,
    num_slices: int,
    search_margin_ratio: float = 0.08,
) -> List[int]:
    """Convenience functional wrapper for ImageEngine.compute_smart_seams."""
    return ImageEngine.compute_smart_seams(
        image=image, num_slices=num_slices, search_margin_ratio=search_margin_ratio
    )

