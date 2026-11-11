"""
Tests for Animated Ken Burns Video Panning Engine.
"""

import os
import shutil
import tempfile
import unittest
import subprocess
from PIL import Image

from core.video_engine import (
    VideoPanConfig,
    generate_panning_video,
    is_ffmpeg_available,
    get_target_resolution,
)


class TestVideoEngine(unittest.TestCase):
    """Test suite for video panning generation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="test_video_engine_")
        self.pano_path = os.path.join(self.temp_dir, "test_pano.jpg")
        # Create a sample wide panoramic image (2400 x 800)
        img = Image.new("RGB", (2400, 800), color=(80, 140, 210))
        img.save(self.pano_path, "JPEG")

    def tearDown(self) -> None:
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ffmpeg_availability(self) -> None:
        """Verify that ffmpeg is detected on the test machine."""
        self.assertTrue(is_ffmpeg_available(), "FFmpeg should be detected on the system.")

    def test_target_resolution(self) -> None:
        """Verify resolution presets."""
        self.assertEqual(get_target_resolution("Reels/Story (9:16)"), (1080, 1920))
        self.assertEqual(get_target_resolution("Feed (4:5)"), (1080, 1350))
        self.assertEqual(get_target_resolution("Square (1:1)"), (1080, 1080))
        self.assertEqual(get_target_resolution("unknown"), (1080, 1920))

    def test_generate_panning_video_basic(self) -> None:
        """Test generating a short 2-second Reels video from file path."""
        out_mp4 = os.path.join(self.temp_dir, "reels_basic.mp4")
        progress_events = []

        def on_progress(p: float, msg: str):
            progress_events.append((p, msg))

        config = VideoPanConfig(
            target_ratio="Reels/Story (9:16)",
            duration_seconds=2.0,
            fps=30,
            direction="Left to Right",
            output_path=out_mp4,
        )

        res_path = generate_panning_video(
            self.pano_path,
            config=config,
            progress_callback=on_progress,
        )

        self.assertEqual(res_path, out_mp4)
        self.assertTrue(os.path.exists(out_mp4))
        self.assertGreater(os.path.getsize(out_mp4), 1000)
        self.assertTrue(len(progress_events) > 0)
        self.assertEqual(progress_events[-1][0], 1.0)

        # Verify using ffprobe
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name",
            "-of", "csv=p=0",
            out_mp4,
        ]
        probe_res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(probe_res.returncode, 0, f"ffprobe error: {probe_res.stderr}")
        output = probe_res.stdout.strip()
        self.assertIn("h264", output)
        self.assertIn("1080", output)
        self.assertIn("1920", output)

    def test_generate_from_pil_image(self) -> None:
        """Test generating video by passing PIL Image directly."""
        img = Image.new("RGB", (2000, 700), color=(220, 120, 90))
        out_mp4 = os.path.join(self.temp_dir, "pil_video.mp4")

        config = VideoPanConfig(
            target_ratio="Feed (4:5)",
            duration_seconds=1.5,
            fps=30,
            direction="Right to Left",
            output_path=out_mp4,
        )

        res_path = generate_panning_video(img, config=config)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 500)

        # Check resolution matches 1080x1350
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            out_mp4,
        ]
        probe_res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(probe_res.returncode, 0)
        self.assertEqual(probe_res.stdout.strip(), "1080,1350")

    def test_generate_ping_pong_with_motion_blur(self) -> None:
        """Test ping-pong boomerang direction with motion blur enabled."""
        out_mp4 = os.path.join(self.temp_dir, "ping_pong.mp4")
        config = VideoPanConfig(
            target_ratio="Square (1:1)",
            duration_seconds=1.0,
            fps=30,
            direction="Ping-Pong (Boomerang)",
            motion_blur=True,
            output_path=out_mp4,
        )

        res_path = generate_panning_video(self.pano_path, config=config)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 500)

    def test_missing_file_raises_error(self) -> None:
        """Verify error raised for non-existent image file."""
        config = VideoPanConfig(output_path=os.path.join(self.temp_dir, "dummy.mp4"))
        with self.assertRaises(FileNotFoundError):
            generate_panning_video("/path/to/nonexistent/image.jpg", config=config)


if __name__ == "__main__":
    unittest.main()
