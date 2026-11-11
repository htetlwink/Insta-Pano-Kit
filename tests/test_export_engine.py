"""
Unit and integration tests for Omni-Channel Social Export Engine and Smart Captions.
"""

import os
import shutil
import tempfile
import unittest
from PIL import Image

from core.caption_engine import format_full_caption, generate_smart_captions
from core.export_engine import export_omni_pack
from core.image_engine import SlicingConfig
from core.video_engine import VideoConfig, is_ffmpeg_available


class TestExportEngine(unittest.TestCase):
    """Test suite for core.export_engine and core.caption_engine."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="test_export_engine_")
        # Create a test panoramic image (2700 x 900)
        self.pano_img = Image.new("RGB", (2700, 900), color=(40, 100, 180))
        self.pano_path = os.path.join(self.temp_dir, "sample_panorama.jpg")
        self.pano_img.save(self.pano_path, "JPEG")

    def tearDown(self) -> None:
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_smart_captions_generation(self) -> None:
        """Verify smart captions generate all 4 core pillars across themes."""
        themes = ["General", "Landscape", "Urban / Architecture", "Cinematic", "Minimalist"]

        for theme in themes:
            captions = generate_smart_captions(
                image_path=self.pano_path,
                num_slices=4,
                theme=theme,
            )

            self.assertIn("aesthetic", captions)
            self.assertIn("technical", captions)
            self.assertIn("engagement", captions)
            self.assertIn("hashtags", captions)

            self.assertIn("4 slides", captions["aesthetic"])
            self.assertIn("Shot on", captions["technical"])
            self.assertIn("4-slide", captions["technical"])
            self.assertTrue(len(captions["hashtags"].split()) >= 8)

            full_formatted = format_full_caption(captions)
            self.assertIn(captions["aesthetic"], full_formatted)
            self.assertIn(captions["hashtags"], full_formatted)

    def test_export_omni_pack_directory_structure(self) -> None:
        """Verify export_omni_pack creates all required assets and directories."""
        export_out = os.path.join(self.temp_dir, "omni_bundle")
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            tilt_angle=2.0,
            smart_seams=True,
        )

        res = export_omni_pack(
            image=self.pano_img,
            config=cfg,
            output_dir=export_out,
            include_video=False,
        )

        # 1. Instagram Feed
        feed_dir = os.path.join(export_out, "instagram_feed")
        self.assertTrue(os.path.isdir(feed_dir))
        self.assertEqual(len(res["instagram_feed"]["slices"]), 3)
        for slice_file in res["instagram_feed"]["slices"]:
            self.assertTrue(os.path.exists(slice_file))
            with Image.open(slice_file) as s:
                self.assertEqual(s.size, (1080, 1350))

        guide_file = res["instagram_feed"]["upload_guide"]
        self.assertTrue(os.path.exists(guide_file))

        # 2. Instagram Stories (9:16)
        stories_dir = os.path.join(export_out, "instagram_stories")
        self.assertTrue(os.path.isdir(stories_dir))
        self.assertEqual(len(res["instagram_stories"]["slices"]), 3)
        for story_file in res["instagram_stories"]["slices"]:
            self.assertTrue(os.path.exists(story_file))
            with Image.open(story_file) as s:
                self.assertEqual(s.size, (1080, 1920))

        # 3. LinkedIn Lookbook PDF
        pdf_path = res["linkedin_lookbook"]
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 5000)

        # 4. Twitter / Threads Header Banner
        header_file = res["twitter_threads_header"]["file"]
        self.assertTrue(os.path.exists(header_file))
        with Image.open(header_file) as h:
            self.assertEqual(h.size, (1500, 500))

        # 5. Captions text file
        captions_file = res["captions_file"]
        self.assertTrue(os.path.exists(captions_file))
        with open(captions_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Shot on", content)
        self.assertIn("#panoramaphotography", content)

        # Total files count
        self.assertGreaterEqual(res["total_files"], 10)

    def test_export_omni_pack_with_video(self) -> None:
        """Verify export_omni_pack includes reels_video.mp4 when requested."""
        if not is_ffmpeg_available():
            self.skipTest("FFmpeg not available")

        export_out = os.path.join(self.temp_dir, "omni_bundle_video")
        cfg = SlicingConfig(num_slices=2, aspect_ratio="Square (1:1)")
        v_cfg = VideoConfig(
            duration_seconds=1.5,
            fps=24,
            audio_path="ambient",
            speed_ramping="Linear",
        )

        res = export_omni_pack(
            image=self.pano_path,
            config=cfg,
            output_dir=export_out,
            include_video=True,
            video_config=v_cfg,
        )

        self.assertIsNotNone(res["reels_video"])
        self.assertTrue(os.path.exists(res["reels_video"]))
        self.assertGreater(os.path.getsize(res["reels_video"]), 1000)


if __name__ == "__main__":
    unittest.main()
