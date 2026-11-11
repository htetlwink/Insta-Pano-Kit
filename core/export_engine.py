"""
Insta-Pano-Kit — Omni-Channel Social Export Engine
=================================================
Automates full multi-platform distribution pack exports:
- Instagram Feed: 4:5 / 1:1 slices + upload sequence guide
- Instagram Stories: 9:16 vertical tap-through sequence
- LinkedIn Lookbook: Multi-page swipeable PDF document
- Twitter / X Threads Header: 3:1 landscape header banner (1500x500 px)
- Instagram Reels / Shorts: Panning MP4 video with ambient audio
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from PIL import Image, ImageOps

from core.image_engine import (
    ImageEngine,
    SlicingConfig,
    generate_upload_guide,
    save_slices,
)
from core.video_engine import VideoConfig, VideoPanConfig, generate_panning_video, is_ffmpeg_available


def export_omni_pack(
    image: Union[str, Path, Image.Image],
    config: Optional[SlicingConfig] = None,
    output_dir: str = "omni_pack_export",
    include_video: bool = False,
    video_config: Optional[Union[VideoConfig, VideoPanConfig]] = None,
) -> Dict[str, Any]:
    """
    Generate an all-in-one cross-platform publishing pack from a single panoramic photo.

    Creates:
      - `instagram_feed/`: 4:5 or 1:1 slices + upload_guide.jpg
      - `instagram_stories/`: 9:16 vertical tap-through sequence
      - `linkedin_lookbook.pdf`: Multi-page swipeable PDF lookbook
      - `twitter_threads_header/`: 3:1 landscape header banner (1500x500 px)
      - `reels_video.mp4`: (if include_video=True and FFmpeg is available)

    Args:
        image: Path to image or PIL Image object.
        config: SlicingConfig for base carousel layout and styling.
        output_dir: Root directory where pack subdirectories and files will be saved.
        include_video: Whether to render an animated Ken Burns Reels video.
        video_config: Optional VideoConfig for video rendering parameters.

    Returns:
        Summary dictionary of created files, directories, and captions.
    """
    if config is None:
        config = SlicingConfig()

    out_root = os.path.abspath(output_dir)
    os.makedirs(out_root, exist_ok=True)

    feed_dir = os.path.join(out_root, "instagram_feed")
    stories_dir = os.path.join(out_root, "instagram_stories")
    twitter_dir = os.path.join(out_root, "twitter_threads_header")
    os.makedirs(feed_dir, exist_ok=True)
    os.makedirs(stories_dir, exist_ok=True)
    os.makedirs(twitter_dir, exist_ok=True)

    # 1. Load base image
    loaded_img = ImageEngine.load_image(image)

    # 2. Instagram Feed Carousel Slices & Upload Guide
    feed_slices = ImageEngine.slice_panorama(loaded_img, config)
    ext = "jpg" if config.format.upper() == "JPEG" else "png"
    feed_paths = save_slices(
        feed_slices,
        export_dir=feed_dir,
        prefix=config.prefix or "panorama_slice",
        ext=ext,
        jpeg_quality=config.jpeg_quality,
    )
    guide_path = os.path.join(feed_dir, "upload_guide.jpg")
    generate_upload_guide(feed_slices, output_path=guide_path, title="INSTAGRAM CAROUSEL UPLOAD GUIDE")

    # 3. Instagram Stories 9:16 Tap-Through Sequence
    stories_cfg = copy.copy(config)
    stories_cfg.aspect_ratio = "Story (9:16)"
    stories_cfg.story_mode = True
    stories_cfg.prefix = "story_slide"
    story_slices = ImageEngine.slice_panorama(loaded_img, stories_cfg)
    story_paths = save_slices(
        story_slices,
        export_dir=stories_dir,
        prefix="story_slide",
        ext=ext,
        jpeg_quality=config.jpeg_quality,
    )

    # 4. LinkedIn Lookbook PDF
    pdf_path = os.path.join(out_root, "linkedin_lookbook.pdf")
    pdf_slices = [s.convert("RGB") for s in feed_slices]
    if pdf_slices:
        pdf_slices[0].save(
            pdf_path,
            "PDF",
            save_all=True,
            append_images=pdf_slices[1:],
            resolution=150.0,
        )

    # 5. Twitter / Threads 3:1 Header Banner (1500 x 500 px)
    header_w, header_h = 1500, 500
    # Center centering tuple based on pan offsets
    center_x = (config.pan_offset_x + 1.0) / 2.0
    center_y = (config.pan_offset_y + 1.0) / 2.0
    # Apply tilt if requested
    banner_source = loaded_img
    if abs(config.tilt_angle) > 1e-4:
        banner_source = ImageEngine.rotate_and_crop(banner_source, config.tilt_angle)
    twitter_banner = ImageOps.fit(
        banner_source,
        (header_w, header_h),
        method=Image.Resampling.LANCZOS,
        centering=(center_x, center_y),
    )
    if twitter_banner.mode != "RGB":
        twitter_banner = twitter_banner.convert("RGB")
    header_path = os.path.join(twitter_dir, "twitter_header_1500x500.jpg")
    header_alias = os.path.join(twitter_dir, "header_banner.jpg")
    twitter_banner.save(header_path, format="JPEG", quality=95)
    twitter_banner.save(header_alias, format="JPEG", quality=95)

    # 6. Animated Reels Video (if requested)
    reels_video_path: Optional[str] = None
    if include_video and is_ffmpeg_available():
        if video_config is None:
            video_config = VideoPanConfig(
                target_ratio="Reels/Story (9:16)",
                duration_seconds=8.0,
                direction="Left to Right",
                audio_path="ambient",
            )
        target_video_path = os.path.join(out_root, "reels_video.mp4")
        video_config.output_path = target_video_path
        try:
            reels_video_path = generate_panning_video(loaded_img, config=video_config)
        except Exception:
            reels_video_path = None

    # Count total generated files
    total_files = len(feed_paths) + 1 + len(story_paths) + 2 + 1  # feed + guide + stories + headers + pdf
    if reels_video_path and os.path.exists(reels_video_path):
        total_files += 1

    return {
        "output_dir": out_root,
        "instagram_feed": {
            "directory": feed_dir,
            "slices": feed_paths,
            "upload_guide": guide_path,
        },
        "instagram_stories": {
            "directory": stories_dir,
            "slices": story_paths,
        },
        "linkedin_lookbook": pdf_path,
        "twitter_threads_header": {
            "directory": twitter_dir,
            "file": header_path,
        },
        "reels_video": reels_video_path,
        "total_files": total_files,
    }
