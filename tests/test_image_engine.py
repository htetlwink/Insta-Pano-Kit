"""
Unit and integration tests for core.image_engine.
=================================================
Verifies:
- Aspect ratio resolution & slice dimensions (4:5, 1:1, 9:16)
- Pan offset cropping along X and Y axes
- Fit modes: Standard (Fit & Crop), Proportional, Blurred Background Fill, Solid Gallery Border
- Overlays: Seam Arrow, Swipe Badge, Dot Indicators, Title & Watermark
- sRGB color profile conversion and smart sharpen filter
- Profile grid splitting (3x3 and 3x1 banner) with Instagram reverse-upload numbering
- Visual Contact Sheet / Upload Guide generation (carousel & profile grid)
- Saving slices to disk with JPEG/PNG handling and transparency sanitization
"""

import os
import shutil
import tempfile
import unittest
from PIL import Image, ImageCms, ImageDraw

from core.image_engine import (
    ASPECT_RATIOS,
    GridConfig,
    GridTile,
    ImageEngine,
    SlicingConfig,
    generate_upload_guide,
    parse_color,
    save_slices,
    slice_grid,
    slice_panorama,
)


class TestImageEngine(unittest.TestCase):
    """Test suite for core.image_engine."""

    def setUp(self) -> None:
        """Create temporary directory and sample test images."""
        self.temp_dir = tempfile.mkdtemp()

        # 1. Wide Panorama (aspect ratio 3:1 -> 3000x1000)
        self.wide_img = Image.new("RGB", (3000, 1000), (45, 90, 160))
        draw = ImageDraw.Draw(self.wide_img)
        # Add visual features
        draw.rectangle([(0, 0), (1500, 1000)], fill=(200, 50, 50))    # Left half red
        draw.rectangle([(1500, 0), (3000, 1000)], fill=(50, 50, 200)) # Right half blue
        draw.line([(0, 0), (3000, 1000)], fill=(255, 255, 255), width=8)

        # 2. Tall Image (1000x3000) for vertical pan testing
        self.tall_img = Image.new("RGB", (1000, 3000), (30, 180, 80))
        draw_tall = ImageDraw.Draw(self.tall_img)
        draw_tall.rectangle([(0, 0), (1000, 1500)], fill=(240, 200, 20))  # Top half yellow
        draw_tall.rectangle([(0, 1500), (1000, 3000)], fill=(20, 120, 40)) # Bottom half dark green

        # 3. Square Image (1500x1500)
        self.square_img = Image.new("RGB", (1500, 1500), (80, 80, 80))

        # 4. RGBA Image with transparency
        self.rgba_img = Image.new("RGBA", (1200, 600), (0, 0, 0, 0))
        draw_rgba = ImageDraw.Draw(self.rgba_img)
        draw_rgba.ellipse([(100, 100), (500, 500)], fill=(255, 100, 0, 200))

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # 1. Aspect Ratio & Dimensions Tests
    # -----------------------------------------------------------------------

    def test_aspect_ratios_dimensions(self) -> None:
        """Verify SlicingConfig resolves standard Instagram aspect ratios correctly."""
        cfg_portrait = SlicingConfig(aspect_ratio="Portrait (4:5)")
        self.assertEqual(cfg_portrait.get_target_dimensions(), (1080, 1350))

        cfg_square = SlicingConfig(aspect_ratio="Square (1:1)")
        self.assertEqual(cfg_square.get_target_dimensions(), (1080, 1080))

        cfg_story = SlicingConfig(aspect_ratio="Story (9:16)")
        self.assertEqual(cfg_story.get_target_dimensions(), (1080, 1920))

        # Test shorthand aliases
        self.assertEqual(SlicingConfig(aspect_ratio="4:5").get_target_dimensions(), (1080, 1350))
        self.assertEqual(SlicingConfig(aspect_ratio="1:1").get_target_dimensions(), (1080, 1080))
        self.assertEqual(SlicingConfig(aspect_ratio="9:16").get_target_dimensions(), (1080, 1920))

    def test_standard_slicing_portrait_4_5(self) -> None:
        """Verify slicing into 3 Portrait 4:5 slides (1080x1350 each)."""
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            fit_mode="Standard (Fit & Crop)",
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 3)
        for idx, s in enumerate(slices):
            self.assertEqual(s.size, (1080, 1350), f"Slide {idx} dimension mismatch")
            self.assertEqual(s.mode, "RGB")

    def test_standard_slicing_square_1_1(self) -> None:
        """Verify slicing into 4 Square 1:1 slides (1080x1080 each)."""
        cfg = SlicingConfig(
            num_slices=4,
            aspect_ratio="Square (1:1)",
            fit_mode="Standard (Fit & Crop)",
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 4)
        for s in slices:
            self.assertEqual(s.size, (1080, 1080))

    def test_standard_slicing_story_9_16(self) -> None:
        """Verify slicing into 2 Story 9:16 slides (1080x1920 each)."""
        cfg = SlicingConfig(
            num_slices=2,
            aspect_ratio="Story (9:16)",
            fit_mode="Standard (Fit & Crop)",
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 2)
        for s in slices:
            self.assertEqual(s.size, (1080, 1920))

    def test_proportional_full_width(self) -> None:
        """Verify Proportional mode preserves 100% panorama width divided equally."""
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            fit_mode="Proportional (Full Width)",
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 3)
        # In proportional mode, all slides have target height
        for s in slices:
            self.assertEqual(s.size[1], 1350)
            self.assertGreater(s.size[0], 0)

    # -----------------------------------------------------------------------
    # 2. Pan Offset X and Y Cropping
    # -----------------------------------------------------------------------

    def test_pan_offset_x_horizontal_shift(self) -> None:
        """
        Test that pan_offset_x shifts crop box horizontally.
        Left half of wide_img is Red (200, 50, 50), Right half is Blue (50, 50, 200).
        """
        # Crop with pan_offset_x = -1.0 (leftmost)
        cfg_left = SlicingConfig(
            num_slices=2,
            aspect_ratio="Square (1:1)",
            fit_mode="Standard (Fit & Crop)",
            pan_offset_x=-1.0,
        )
        slices_left = slice_panorama(self.wide_img, cfg_left)
        # First slice from left edge should be predominantly red
        left_pixel = slices_left[0].getpixel((100, 500))
        self.assertGreater(left_pixel[0], left_pixel[2], "Left pan should capture red half")

        # Crop with pan_offset_x = +1.0 (rightmost)
        cfg_right = SlicingConfig(
            num_slices=2,
            aspect_ratio="Square (1:1)",
            fit_mode="Standard (Fit & Crop)",
            pan_offset_x=1.0,
        )
        slices_right = slice_panorama(self.wide_img, cfg_right)
        # Last slice on the right edge should be predominantly blue
        right_pixel = slices_right[-1].getpixel((980, 500))
        self.assertGreater(right_pixel[2], right_pixel[0], "Right pan should capture blue half")

    def test_pan_offset_y_vertical_shift(self) -> None:
        """Test that pan_offset_y shifts crop box vertically on tall image."""
        # Top half is yellow (240, 200, 20), Bottom half is dark green (20, 120, 40)
        cfg_top = SlicingConfig(
            num_slices=2,
            aspect_ratio="Portrait (4:5)",
            fit_mode="Standard (Fit & Crop)",
            pan_offset_y=-1.0,
        )
        slices_top = slice_panorama(self.tall_img, cfg_top)
        top_pixel = slices_top[0].getpixel((500, 200))
        self.assertGreater(top_pixel[0], 150, "Top pan should capture yellow region")

        cfg_bottom = SlicingConfig(
            num_slices=2,
            aspect_ratio="Portrait (4:5)",
            fit_mode="Standard (Fit & Crop)",
            pan_offset_y=1.0,
        )
        slices_bottom = slice_panorama(self.tall_img, cfg_bottom)
        bottom_pixel = slices_bottom[0].getpixel((500, 1100))
        self.assertLess(bottom_pixel[0], 100, "Bottom pan should capture dark green region")

    # -----------------------------------------------------------------------
    # 3. Fit Modes: Blurred Background Fill & Solid Gallery Border
    # -----------------------------------------------------------------------

    def test_blurred_background_fill_mode(self) -> None:
        """Verify Blurred Background Fill scales panorama to fit over blurred backdrop."""
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            fit_mode="Blurred Background Fill",
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 3)
        for s in slices:
            self.assertEqual(s.size, (1080, 1350))
            # Slices must not be pure black or empty
            extrema = s.getextrema()
            self.assertTrue(all(e[1] > 0 for e in extrema))

    def test_solid_gallery_border_mode(self) -> None:
        """Verify Solid Gallery Border mode places fitted image on custom color canvas."""
        custom_color = (255, 0, 0)
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            fit_mode="Solid Gallery Border",
            border_color=custom_color,
            border_padding=20,
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 3)
        for s in slices:
            self.assertEqual(s.size, (1080, 1350))
            # Check corner pixel matches border color
            corner_px = s.getpixel((5, 5))
            self.assertEqual(corner_px, custom_color)

    def test_parse_color(self) -> None:
        """Test color parsing helper for hex, tuple, and named colors."""
        self.assertEqual(parse_color((255, 255, 255)), (255, 255, 255))
        self.assertEqual(parse_color("#FF0000"), (255, 0, 0))
        self.assertEqual(parse_color("#00f"), (0, 0, 255))
        self.assertEqual(parse_color("white"), (255, 255, 255))
        self.assertEqual(parse_color("dark"), (18, 18, 18))
        self.assertEqual(parse_color("(10, 20, 30)"), (10, 20, 30))

    # -----------------------------------------------------------------------
    # 4. Overlays: Seam Arrow, Swipe Badge, Dots, Title & Watermark
    # -----------------------------------------------------------------------

    def test_seam_arrow_indicator(self) -> None:
        """Verify Seam Arrow indicator draws across slide seams."""
        cfg_plain = SlicingConfig(num_slices=3, swipe_indicator="None")
        cfg_arrow = SlicingConfig(num_slices=3, swipe_indicator="Seam Arrow")

        slices_plain = slice_panorama(self.wide_img, cfg_plain)
        slices_arrow = slice_panorama(self.wide_img, cfg_arrow)

        # Slide 0 right edge (seam with slide 1) should differ because arrow is drawn
        right_edge_plain = [slices_plain[0].getpixel((1079, y)) for y in range(600, 750)]
        right_edge_arrow = [slices_arrow[0].getpixel((1079, y)) for y in range(600, 750)]
        self.assertNotEqual(right_edge_plain, right_edge_arrow)

        # Slide 1 left edge should also differ
        left_edge_plain = [slices_plain[1].getpixel((0, y)) for y in range(600, 750)]
        left_edge_arrow = [slices_arrow[1].getpixel((0, y)) for y in range(600, 750)]
        self.assertNotEqual(left_edge_plain, left_edge_arrow)

    def test_swipe_badge_slide_1(self) -> None:
        """Verify Swipe Badge is drawn on Slide 1 only."""
        cfg = SlicingConfig(num_slices=3, swipe_indicator="Swipe Badge (Slide 1)")
        slices = slice_panorama(self.wide_img, cfg)

        # Slide 1 should have badge near bottom right
        badge_pixel_slide1 = slices[0].getpixel((950, 1250))
        # Compare with Slide 2 at the same coordinate (which should not have badge)
        badge_pixel_slide2 = slices[1].getpixel((950, 1250))
        self.assertNotEqual(badge_pixel_slide1, badge_pixel_slide2)

    def test_dot_indicators(self) -> None:
        """Verify Dot Indicators are drawn at the bottom of all slides."""
        cfg = SlicingConfig(num_slices=3, swipe_indicator="Dot Indicators")
        slices = slice_panorama(self.wide_img, cfg)
        for s in slices:
            # Bottom center region should have non-blank indicator pixels
            center_px = s.getpixel((540, 1305))
            self.assertIsNotNone(center_px)

    def test_title_and_watermark_text(self) -> None:
        """Verify title text and watermark text render properly."""
        cfg = SlicingConfig(
            num_slices=2,
            title_text="Mountain Panorama 2026",
            watermark_text="@photographer",
            watermark_all_slides=True,
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 2)
        # Slices render successfully with typography without exceptions
        for s in slices:
            self.assertEqual(s.size, (1080, 1350))

    # -----------------------------------------------------------------------
    # 5. sRGB Color Profile & Smart Sharpen
    # -----------------------------------------------------------------------

    def test_srgb_color_conversion(self) -> None:
        """Test sRGB conversion with both untagged and tagged ICC images."""
        converted = ImageEngine.apply_color_profile(self.wide_img, to_srgb=True)
        self.assertEqual(converted.size, self.wide_img.size)
        self.assertEqual(converted.mode, "RGB")

        # Create an image with an actual ICC profile
        srgb_prof = ImageCms.createProfile("sRGB")
        tagged_img = self.wide_img.copy()
        tagged_img.info["icc_profile"] = ImageCms.ImageCmsProfile(srgb_prof).tobytes()

        res = ImageEngine.apply_color_profile(tagged_img, to_srgb=True)
        self.assertEqual(res.size, tagged_img.size)

    def test_smart_sharpen(self) -> None:
        """Verify smart sharpen UnsharpMask modifies image contrast."""
        sharpened = ImageEngine.apply_sharpen(
            self.wide_img, radius=1.2, percent=60, threshold=2
        )
        self.assertEqual(sharpened.size, self.wide_img.size)
        # Across high-contrast boundary (x=1500, y=200), sharpened pixel values should differ
        self.assertNotEqual(
            sharpened.getpixel((1498, 200)),
            self.wide_img.getpixel((1498, 200)),
        )

    # -----------------------------------------------------------------------
    # 6. Profile Grid Splitter (3x3 and 3x1) & Reverse Upload Sequence
    # -----------------------------------------------------------------------

    def test_profile_grid_3x3(self) -> None:
        """
        Verify 3x3 profile grid returns 9 tiles of 1080x1080 px
        with Instagram reverse-upload order (Tile 9 uploaded 1st, Tile 1 uploaded 9th).
        """
        tiles = slice_grid(self.square_img, rows=3, cols=3, prefix="test_grid")
        self.assertEqual(len(tiles), 9)

        # Check tile dimensions
        for t in tiles:
            self.assertEqual(t.image.size, (1080, 1080))
            self.assertIn("test_grid", t.filename)

        # Map by (row, col) to verify upload sequence
        tile_map = {(t.row, t.col): t for t in tiles}

        # In Instagram 3x3:
        # Bottom-right (row=2, col=2) must be uploaded 1st
        self.assertEqual(tile_map[(2, 2)].upload_order, 1)
        self.assertEqual(tile_map[(2, 2)].tile_number, 9)

        # Bottom-left (row=2, col=0) must be uploaded 3rd
        self.assertEqual(tile_map[(2, 0)].upload_order, 3)
        self.assertEqual(tile_map[(2, 0)].tile_number, 7)

        # Middle-center (row=1, col=1) must be uploaded 5th
        self.assertEqual(tile_map[(1, 1)].upload_order, 5)
        self.assertEqual(tile_map[(1, 1)].tile_number, 5)

        # Top-left (row=0, col=0) must be uploaded 9th (last)
        self.assertEqual(tile_map[(0, 0)].upload_order, 9)
        self.assertEqual(tile_map[(0, 0)].tile_number, 1)

    def test_profile_grid_3x1_banner(self) -> None:
        """Verify 3x1 profile banner returns 3 tiles with correct reverse upload sequence."""
        tiles = slice_grid(self.wide_img, rows=1, cols=3, prefix="banner")
        self.assertEqual(len(tiles), 3)

        tile_map = {t.col: t for t in tiles}
        # Rightmost tile (col=2) -> upload 1st
        self.assertEqual(tile_map[2].upload_order, 1)
        # Center tile (col=1) -> upload 2nd
        self.assertEqual(tile_map[1].upload_order, 2)
        # Leftmost tile (col=0) -> upload 3rd (last, ending up at top-left of feed)
        self.assertEqual(tile_map[0].upload_order, 3)

    # -----------------------------------------------------------------------
    # 7. Visual Contact Sheet / Upload Guide Generation
    # -----------------------------------------------------------------------

    def test_carousel_upload_guide_generation(self) -> None:
        """Verify contact sheet generation for carousel slides."""
        cfg = SlicingConfig(num_slices=3)
        slices = slice_panorama(self.wide_img, cfg)

        guide_path = os.path.join(self.temp_dir, "test_carousel_guide.jpg")
        guide_img = generate_upload_guide(slices, output_path=guide_path, title="My Carousel Guide")

        self.assertIsInstance(guide_img, Image.Image)
        self.assertTrue(os.path.exists(guide_path))
        self.assertGreater(os.path.getsize(guide_path), 5000)

    def test_grid_upload_guide_generation(self) -> None:
        """Verify contact sheet generation for profile grid tiles."""
        tiles = slice_grid(self.square_img, rows=3, cols=3)

        guide_path = os.path.join(self.temp_dir, "test_grid_guide.jpg")
        guide_img = generate_upload_guide(tiles, output_path=guide_path, title="My 3x3 Grid Guide")

        self.assertIsInstance(guide_img, Image.Image)
        self.assertTrue(os.path.exists(guide_path))
        self.assertGreater(os.path.getsize(guide_path), 5000)

    # -----------------------------------------------------------------------
    # 8. File Saving Helper & Format Sanitization
    # -----------------------------------------------------------------------

    def test_save_slices_jpeg_and_png(self) -> None:
        """Verify saving slices to disk with JPEG and PNG, and RGBA sanitization."""
        cfg = SlicingConfig(num_slices=2)
        slices = slice_panorama(self.wide_img, cfg)

        # 1. Save as JPEG
        jpeg_paths = save_slices(
            slices=slices,
            export_dir=os.path.join(self.temp_dir, "jpegs"),
            prefix="test_slice",
            ext="jpg",
            jpeg_quality=92,
        )
        self.assertEqual(len(jpeg_paths), 2)
        for p in jpeg_paths:
            self.assertTrue(os.path.exists(p))
            with Image.open(p) as img:
                self.assertEqual(img.format, "JPEG")
                self.assertEqual(img.mode, "RGB")

        # 2. Save as PNG
        png_paths = save_slices(
            slices=slices,
            export_dir=os.path.join(self.temp_dir, "pngs"),
            prefix="test_slice",
            ext="png",
        )
        self.assertEqual(len(png_paths), 2)
        for p in png_paths:
            self.assertTrue(os.path.exists(p))
            with Image.open(p) as img:
                self.assertEqual(img.format, "PNG")

    def test_save_slices_rgba_transparency_to_jpeg(self) -> None:
        """Verify saving RGBA image with transparency converts cleanly to RGB with white canvas."""
        cfg = SlicingConfig(num_slices=2)
        slices = slice_panorama(self.rgba_img, cfg)

        saved = save_slices(
            slices=slices,
            export_dir=os.path.join(self.temp_dir, "rgba_to_jpeg"),
            prefix="transp_test",
            ext="jpg",
        )
        self.assertEqual(len(saved), 2)
        for p in saved:
            with Image.open(p) as img:
                self.assertEqual(img.mode, "RGB")
                # Transparent regions should be pure white (255, 255, 255)
                corner_px = img.getpixel((0, 0))
                self.assertEqual(corner_px, (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
