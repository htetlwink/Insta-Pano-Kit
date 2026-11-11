"""
Video Panning Animation Engine for Instagram Reels, Shorts, and Stories.
Converts wide panoramic images into smooth Ken Burns panning MP4 videos using FFmpeg.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional, Tuple, Callable, Union
from PIL import Image, ImageOps


@dataclass
class VideoPanConfig:
    """Configuration for animated panorama panning video generation."""
    target_ratio: str = "Reels/Story (9:16)"
    duration_seconds: float = 8.0
    fps: int = 30
    direction: str = "Left to Right"  # "Left to Right", "Right to Left", "Ping-Pong (Boomerang)", "Zoom and Reveal"
    motion_blur: bool = False
    output_path: Optional[str] = None
    easing: bool = True
    crf: int = 18
    preset: str = "medium"


def get_ffmpeg_path() -> Optional[str]:
    """Return path to ffmpeg executable or None if not found."""
    # Check PATH first
    path = shutil.which("ffmpeg")
    if path and os.path.isfile(path) and os.access(path, os.X_OK):
        return path

    # Check common system locations
    candidates = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    return None


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg executable is available on the system."""
    return get_ffmpeg_path() is not None


def get_target_resolution(ratio: str) -> Tuple[int, int]:
    """
    Resolve aspect ratio string into (width, height) pixel dimensions.

    Supported presets:
      - 'Reels/Story (9:16)' -> (1080, 1920)
      - 'Feed (4:5)'         -> (1080, 1350)
      - 'Square (1:1)'       -> (1080, 1080)
    """
    r_lower = ratio.lower().strip()
    if "9:16" in r_lower or "reels" in r_lower or "story" in r_lower or "vertical" in r_lower:
        return (1080, 1920)
    elif "4:5" in r_lower or "feed" in r_lower or "portrait" in r_lower:
        return (1080, 1350)
    elif "1:1" in r_lower or "square" in r_lower:
        return (1080, 1080)
    elif "16:9" in r_lower or "landscape" in r_lower:
        return (1920, 1080)

    # Fallback to default Reels/Story 9:16
    return (1080, 1920)


def generate_panning_video(
    image_path_or_pil: Union[str, Image.Image],
    config: Optional[VideoPanConfig] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    Generate an animated Ken Burns panning MP4 video from a panoramic image.

    Args:
        image_path_or_pil: Path to the image file on disk or an existing PIL Image.
        config: VideoPanConfig instance with animation parameters.
        progress_callback: Optional callback receiving (progress_fraction: float, message: str).

    Returns:
        Absolute path to the generated MP4 video.

    Raises:
        RuntimeError: If FFmpeg is missing or fails during encoding.
        ValueError: If input image is invalid or has zero dimensions.
    """
    ffmpeg_bin = get_ffmpeg_path()
    if not ffmpeg_bin:
        raise RuntimeError(
            "FFmpeg executable not found on the system. "
            "Please install FFmpeg to enable video export."
        )

    if config is None:
        config = VideoPanConfig()

    temp_image_path: Optional[str] = None
    input_file_for_ffmpeg: str = ""

    try:
        # Load and validate PIL Image
        if isinstance(image_path_or_pil, Image.Image):
            pil_img = image_path_or_pil
            orig_path = None
        elif isinstance(image_path_or_pil, (str, os.PathLike)):
            orig_path = str(image_path_or_pil)
            if not os.path.exists(orig_path):
                raise FileNotFoundError(f"Source image not found: {orig_path}")
            pil_img = Image.open(orig_path)
        else:
            raise TypeError(f"Expected str or PIL.Image, got {type(image_path_or_pil)}")

        # Normalize orientation using EXIF
        transposed_img = ImageOps.exif_transpose(pil_img)
        if transposed_img is not None:
            pil_img = transposed_img

        orig_w, orig_h = pil_img.size
        if orig_w <= 0 or orig_h <= 0:
            raise ValueError(f"Invalid image dimensions: {orig_w}x{orig_h}")

        # Ensure image is in RGB mode for libx264 compatibility
        needs_rgb_save = False
        if pil_img.mode != "RGB":
            needs_rgb_save = True
            if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
                bg = Image.new("RGB", pil_img.size, (0, 0, 0))
                bg.paste(pil_img, mask=pil_img.split()[-1] if pil_img.mode in ("RGBA", "LA") else None)
                pil_img = bg
            else:
                pil_img = pil_img.convert("RGB")

        # Determine input file path for ffmpeg
        if orig_path and not needs_rgb_save and transposed_img is None:
            input_file_for_ffmpeg = os.path.abspath(orig_path)
        else:
            # Write normalized image to temporary PNG
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temp_image_path = tmp.name
            tmp.close()
            pil_img.save(temp_image_path, format="PNG")
            input_file_for_ffmpeg = temp_image_path

        # Determine target output dimensions
        tw, th = get_target_resolution(config.target_ratio)

        duration = max(0.5, float(config.duration_seconds))
        fps = max(1, int(config.fps))
        total_frames = max(1, int(round(fps * duration)))

        dir_lower = config.direction.lower().strip()
        is_zoom_reveal = "zoom" in dir_lower

        if is_zoom_reveal:
            # Memory safety: cap image width to 3840px
            max_input_w = 3840
            if orig_w > max_input_w:
                scale_ratio = max_input_w / orig_w
                new_w = max_input_w
                new_h = max(2, int(round(orig_h * scale_ratio)))
                if new_h % 2 != 0:
                    new_h += 1
                pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                orig_w, orig_h = pil_img.size
                if temp_image_path:
                    pil_img.save(temp_image_path, format="PNG")
                else:
                    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    temp_image_path = tmp.name
                    tmp.close()
                    pil_img.save(temp_image_path, format="PNG")
                    input_file_for_ffmpeg = temp_image_path

            w_orig, h_orig = orig_w, orig_h
            if w_orig % 2 != 0:
                w_orig -= 1
            if h_orig % 2 != 0:
                h_orig -= 1

            # Pad height to match target aspect ratio (e.g. 9:16)
            h_pad = int(round(w_orig * th / tw))
            if h_pad % 2 != 0:
                h_pad += 1
            y_center = max(0, (h_pad - h_orig) // 2)
            z_max = max(1.0, h_pad / h_orig)
            w_crop_max = w_orig / z_max
            max_x = max(0.0, w_orig - w_crop_max)

            f1 = min(int(round(1.5 * fps)), int(0.35 * total_frames))
            f_zoom = min(int(round(1.5 * fps)), int(0.35 * total_frames))
            f1 = max(1, f1)
            f_zoom = max(1, f_zoom)
            f2 = f1 + f_zoom
            f_pan = max(1, total_frames - f2)

            pad_filter = f"pad={w_orig}:{h_pad}:0:{y_center}:black"
            z_expr = f"if(lte(on,{f1}),1,if(lte(on,{f2}),1+({z_max:.4f}-1)*(0.5-0.5*cos(PI*(on-{f1})/{f_zoom})),{z_max:.4f}))"
            y_expr = "(ih-ih/zoom)/2"
            x_expr = f"if(lte(on,{f1}),(iw-iw/zoom)/2,if(lte(on,{f2}),((iw-iw/zoom)/2)*(1-(0.5-0.5*cos(PI*(on-{f1})/{f_zoom}))),{max_x:.2f}*(0.5-0.5*cos(PI*(on-{f2})/{f_pan}))))"
            zp_filter = f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s={tw}x{th}:fps={fps}"

            filter_parts = [pad_filter, zp_filter]
            if config.motion_blur:
                filter_parts.append("tmix=frames=3:weights='1 2 1'")

            vf_str = ",".join(filter_parts)

            # Determine output file path
            if config.output_path:
                out_path = os.path.abspath(config.output_path)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
            else:
                if orig_path:
                    stem, _ = os.path.splitext(orig_path)
                    out_path = f"{stem}_reels_pan.mp4"
                else:
                    tmp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                    out_path = tmp_out.name
                    tmp_out.close()

            # Build FFmpeg command for Zoom and Reveal (without input loop)
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i", input_file_for_ffmpeg,
                "-vf", vf_str,
                "-c:v", "libx264",
                "-preset", config.preset or "medium",
                "-crf", str(config.crf or 18),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-t", f"{duration:.3f}",
                "-progress", "pipe:1",
                out_path,
            ]
        else:
            # Scale image so target height and width are both fully covered
            scale_factor = max(tw / orig_w, th / orig_h)
            scaled_w = int(round(orig_w * scale_factor))
            scaled_h = int(round(orig_h * scale_factor))

            # Ensure dimensions are even numbers (requirement for libx264 yuv420p)
            if scaled_w % 2 != 0:
                scaled_w += 1
            if scaled_h % 2 != 0:
                scaled_h += 1

            # Determine panning movement
            max_delta_x = max(0, scaled_w - tw)
            max_delta_y = max(0, scaled_h - th)
            y_expr = str(max_delta_y // 2)

            if max_delta_x == 0:
                x_expr = "0"
            else:
                if "ping-pong" in dir_lower or "boomerang" in dir_lower:
                    # Boomerang / Ping-Pong: 0 -> 1 -> 0 using smooth cosine
                    x_expr = f"(in_w-{tw})*(0.5-0.5*cos(2*PI*t/{duration:.4f}))"
                elif "right to left" in dir_lower or "rtl" in dir_lower:
                    if config.easing:
                        x_expr = f"(in_w-{tw})*(0.5+0.5*cos(PI*t/{duration:.4f}))"
                    else:
                        x_expr = f"(in_w-{tw})*(1-t/{duration:.4f})"
                else:
                    # Left to Right (default)
                    if config.easing:
                        x_expr = f"(in_w-{tw})*(0.5-0.5*cos(PI*t/{duration:.4f}))"
                    else:
                        x_expr = f"(in_w-{tw})*(t/{duration:.4f})"

            # Build FFmpeg video filter chain
            filter_parts = [
                f"scale={scaled_w}:{scaled_h}",
                f"crop=w={tw}:h={th}:x='{x_expr}':y='{y_expr}'",
            ]

            if config.motion_blur:
                filter_parts.append("tmix=frames=3:weights='1 2 1'")

            vf_str = ",".join(filter_parts)

            # Determine output file path
            if config.output_path:
                out_path = os.path.abspath(config.output_path)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
            else:
                if orig_path:
                    stem, _ = os.path.splitext(orig_path)
                    out_path = f"{stem}_reels_pan.mp4"
                else:
                    tmp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                    out_path = tmp_out.name
                    tmp_out.close()

            # Build FFmpeg command
            cmd = [
                ffmpeg_bin,
                "-y",
                "-loop", "1",
                "-framerate", str(fps),
                "-t", f"{duration:.3f}",
                "-i", input_file_for_ffmpeg,
                "-vf", vf_str,
                "-c:v", "libx264",
                "-preset", config.preset or "medium",
                "-crf", str(config.crf or 18),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-progress", "pipe:1",
                out_path,
            ]

        if progress_callback:
            progress_callback(0.05, "Initializing video render...")

        # Run FFmpeg process and monitor progress
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        current_frame = 0
        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("frame="):
                    try:
                        val = line.split("=")[1].strip()
                        current_frame = int(val)
                        fraction = min(0.98, max(0.05, current_frame / total_frames))
                        pct = int(fraction * 100)
                        if progress_callback:
                            progress_callback(fraction, f"Rendering video... {pct}% (frame {current_frame}/{total_frames})")
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("out_time_us="):
                    try:
                        us_val = line.split("=")[1].strip()
                        if us_val.isdigit():
                            rendered_sec = int(us_val) / 1_000_000.0
                            fraction = min(0.98, max(0.05, rendered_sec / duration))
                            pct = int(fraction * 100)
                            if progress_callback:
                                progress_callback(fraction, f"Rendering video... {pct}%")
                    except (ValueError, IndexError):
                        pass

        _, stderr_data = proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg encoding failed (exit code {proc.returncode}):\n{stderr_data}"
            )

        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            raise RuntimeError(f"FFmpeg completed but output video is empty or missing: {out_path}")

        if progress_callback:
            progress_callback(1.0, f"✅ Video ready: {os.path.basename(out_path)}")

        return out_path

    finally:
        # Clean up temporary source image file
        if temp_image_path and os.path.exists(temp_image_path):
            try:
                os.unlink(temp_image_path)
            except Exception:
                pass
