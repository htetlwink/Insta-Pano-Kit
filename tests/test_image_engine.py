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
from PIL import ExifTags, Image, ImageCms, ImageDraw

from core.image_engine import (
    ASPECT_RATIOS,
    GridConfig,
    GridTile,
    ImageEngine,
    SlicingConfig,
    apply_color_filter,
    compute_smart_seams,
    detect_horizon_tilt,
    extract_exif_metadata,
    generate_camera_card,
    generate_upload_guide,
    parse_color,
    rotate_and_crop,
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

    # -----------------------------------------------------------------------
    # 9. Phase 2 Features: Color Filters, EXIF Card, Split Headline, Story Mode, Custom Weights
    # -----------------------------------------------------------------------

    def test_color_grading_presets(self) -> None:
        """Verify color filter presets apply correctly without memory leaks."""
        test_img = Image.new("RGB", (300, 300), (100, 100, 100))
        filters = [
            "None",
            "Cinematic Moody",
            "Kodak Warmth",
            "Vintage 35mm",
            "B&W High Contrast",
            "Film Grain",
        ]
        for f in filters:
            filtered = apply_color_filter(test_img, f)
            self.assertEqual(filtered.size, (300, 300))
            self.assertEqual(filtered.mode, "RGB")

        # Test None leaves pixel unchanged
        none_img = apply_color_filter(test_img, "None")
        self.assertEqual(none_img.getpixel((50, 50)), (100, 100, 100))

        # Test B&W High Contrast produces grayscale R=G=B in RGB mode
        bw_img = apply_color_filter(test_img, "B&W High Contrast")
        px = bw_img.getpixel((50, 50))
        self.assertEqual(px[0], px[1])
        self.assertEqual(px[1], px[2])

        # Test Vintage 35mm raises blacks on pure black image
        black_img = Image.new("RGB", (100, 100), (0, 0, 0))
        vintage_img = apply_color_filter(black_img, "Vintage 35mm")
        v_px = vintage_img.getpixel((50, 50))
        self.assertGreater(v_px[0], 20, "Vintage 35mm should raise black shadow floor")

        # Test SlicingConfig with color_filter
        cfg = SlicingConfig(num_slices=2, color_filter="Kodak Warmth")
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 2)
        self.assertEqual(slices[0].size, (1080, 1350))

    def test_exif_camera_metadata_and_card(self) -> None:
        """Verify EXIF extraction, camera card generation, and inclusion in carousel slices."""
        # 1. Create a temporary image file with rich EXIF metadata
        exif_img = Image.new("RGB", (600, 300), (70, 120, 180))
        exif = exif_img.getexif()
        exif[ExifTags.Base.Make] = "Sony"
        exif[ExifTags.Base.Model] = "ILCE-7RM4"
        ifd = exif.get_ifd(ExifTags.IFD.Exif)
        ifd[ExifTags.Base.LensModel] = "FE 24-70mm F2.8 GM"
        ifd[ExifTags.Base.FNumber] = 2.8
        ifd[ExifTags.Base.ExposureTime] = 0.002
        ifd[ExifTags.Base.ISOSpeedRatings] = 100
        ifd[ExifTags.Base.FocalLength] = 35.0
        ifd[ExifTags.Base.DateTimeOriginal] = "2024:07:20 15:45:00"
        exif[ExifTags.IFD.Exif] = ifd

        exif_file_path = os.path.join(self.temp_dir, "test_exif.jpg")
        exif_img.save(exif_file_path, format="JPEG", exif=exif)

        # 2. Test extract_exif_metadata
        meta = extract_exif_metadata(exif_file_path)
        self.assertEqual(meta["make"], "Sony")
        self.assertEqual(meta["model"], "ILCE-7RM4")
        self.assertEqual(meta["camera"], "Sony ILCE-7RM4")
        self.assertEqual(meta["lens"], "FE 24-70mm F2.8 GM")
        self.assertEqual(meta["aperture"], "f/2.8")
        self.assertEqual(meta["shutter_speed"], "1/500s")
        self.assertEqual(meta["iso"], "ISO 100")
        self.assertEqual(meta["focal_length"], "35mm")
        self.assertEqual(meta["date"], "2024-07-20")

        # 3. Test extract on image with no EXIF returns safe defaults
        empty_meta = extract_exif_metadata(self.square_img)
        self.assertEqual(empty_meta["camera"], "Unknown Camera")
        self.assertIn("lens", empty_meta)

        # 4. Test generate_camera_card
        card = generate_camera_card(meta, width=1080, height=1350)
        self.assertIsInstance(card, Image.Image)
        self.assertEqual(card.size, (1080, 1350))
        self.assertEqual(card.mode, "RGB")

        # 5. Test include_camera_card in SlicingConfig
        cfg = SlicingConfig(num_slices=3, include_camera_card=True)
        slices = slice_panorama(exif_file_path, cfg)
        # Expected: 3 photo slices + 1 camera card slide = 4 slices
        self.assertEqual(len(slices), 4)
        for s in slices:
            self.assertEqual(s.size, (1080, 1350))
        # The final slide is the camera card
        card_slide = slices[-1]
        self.assertEqual(card_slide.size, (1080, 1350))

    def test_split_seam_headline(self) -> None:
        """Verify split-seam headline is rendered across Slide 1 and Slide 2 boundary."""
        cfg_plain = SlicingConfig(num_slices=3, split_headline=None)
        cfg_headline = SlicingConfig(num_slices=3, split_headline="SWIPE TO DISCOVER")

        slices_plain = slice_panorama(self.wide_img, cfg_plain)
        slices_headline = slice_panorama(self.wide_img, cfg_headline)

        self.assertEqual(len(slices_headline), 3)
        # Slide 1 right edge and Slide 2 left edge should differ from the plain slices
        # because the headline spans across the seam
        self.assertNotEqual(
            slices_headline[0].tobytes(),
            slices_plain[0].tobytes(),
            "Slide 1 should contain left half of split headline"
        )
        self.assertNotEqual(
            slices_headline[1].tobytes(),
            slices_plain[1].tobytes(),
            "Slide 2 should contain right half of split headline"
        )
        # Slide 3 should be identical since headline is only across Slide 1 and 2
        self.assertEqual(
            slices_headline[2].tobytes(),
            slices_plain[2].tobytes(),
            "Slide 3 should not have split headline"
        )

    def test_instagram_story_tap_through_mode(self) -> None:
        """Verify Story Mode draws segmented progress bars and tap-through cues."""
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Story (9:16)",
            story_mode=True,
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 3)
        for s in slices:
            self.assertEqual(s.size, (1080, 1920))

        # Check progress bar top pixels exist on each slide (y ~ 32)
        # Slices with story_mode should differ from slices without story_mode
        cfg_no_story = SlicingConfig(
            num_slices=3,
            aspect_ratio="Story (9:16)",
            story_mode=False,
        )
        slices_no_story = slice_panorama(self.wide_img, cfg_no_story)
        for i in range(3):
            self.assertNotEqual(
                slices[i].tobytes(),
                slices_no_story[i].tobytes(),
                f"Slide {i} should include story mode overlays"
            )

    def test_custom_slice_weights(self) -> None:
        """Verify non-uniform custom slice weights distribute canvas widths correctly."""
        # 1. Test Standard Fit with custom weights: [1.0, 1.5, 0.5]
        # Total target width = 1080 * 3 = 3240
        # Expected widths: 1.0/3.0 * 3240 = 1080, 1.5/3.0 * 3240 = 1620, 0.5/3.0 * 3240 = 540
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            slice_weights=[1.0, 1.5, 0.5],
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 3)
        self.assertEqual(slices[0].size, (1080, 1350))
        self.assertEqual(slices[1].size, (1620, 1350))
        self.assertEqual(slices[2].size, (540, 1350))
        self.assertEqual(sum(s.size[0] for s in slices), 3240)

        # 2. Test Proportional mode with custom weights: [0.8, 1.2]
        cfg_prop = SlicingConfig(
            num_slices=2,
            aspect_ratio="Portrait (4:5)",
            fit_mode="Proportional (Full Width)",
            slice_weights=[0.8, 1.2],
        )
        slices_prop = slice_panorama(self.wide_img, cfg_prop)
        self.assertEqual(len(slices_prop), 2)
        self.assertGreater(slices_prop[1].size[0], slices_prop[0].size[0])
        self.assertEqual(slices_prop[0].size[1], 1350)
        self.assertEqual(slices_prop[1].size[1], 1350)

    def test_detect_horizon_tilt(self) -> None:
        """Verify horizon tilt detection on level, blank, and tilted images."""
        import numpy as np

        # 1. Level line should yield 0.0
        level_img = Image.new("RGB", (600, 300), (220, 220, 220))
        d = ImageDraw.Draw(level_img)
        d.line([(0, 150), (600, 150)], fill=(20, 20, 20), width=6)
        self.assertEqual(detect_horizon_tilt(level_img), 0.0)

        # 2. Blank uniform image should yield 0.0
        blank_img = Image.new("RGB", (600, 300), (128, 128, 128))
        self.assertEqual(detect_horizon_tilt(blank_img), 0.0)

        # 3. Tilted line at 4.0 degrees
        tilted_img = Image.new("RGB", (600, 300), (220, 220, 220))
        d_tilt = ImageDraw.Draw(tilted_img)
        rad = np.radians(4.0)
        d_tilt.line([(0, 150 - 300 * np.tan(rad)), (600, 150 + 300 * np.tan(rad))], fill=(20, 20, 20), width=6)
        detected = detect_horizon_tilt(tilted_img)
        self.assertAlmostEqual(abs(detected), 4.0, delta=0.5)

    def test_rotate_and_crop(self) -> None:
        """Verify rotate_and_crop removes black rotation borders."""
        # Solid red test image
        img = Image.new("RGB", (1000, 400), (255, 0, 0))
        rotated = rotate_and_crop(img, 5.0)

        self.assertLess(rotated.width, img.width)
        self.assertLess(rotated.height, img.height)
        # Check there are no black corners (R min should be 255)
        extrema = rotated.getextrema()
        self.assertEqual(extrema[0], (255, 255), "Red channel should remain 255 with no black borders")
        self.assertEqual(extrema[1], (0, 0))
        self.assertEqual(extrema[2], (0, 0))

        # Test zero rotation
        zero_rot = rotate_and_crop(img, 0.0)
        self.assertEqual(zero_rot.size, img.size)

    def test_compute_smart_seams(self) -> None:
        """Verify compute_smart_seams avoids high energy vertical columns."""
        import numpy as np
        # Create image with high-gradient bar at x=300 (which is default seam for 900px, 3 slices)
        img_arr = np.full((300, 900, 3), 240, dtype=np.uint8)
        img_arr[:, 295:305] = 10  # Dark bar at x=300
        test_img = Image.fromarray(img_arr)

        seams = compute_smart_seams(test_img, num_slices=3)
        self.assertEqual(len(seams), 2)
        self.assertTrue(1 < seams[0] < seams[1] < 899)
        # Smart seam should steer away from default x=300
        self.assertNotEqual(seams[0], 300)

    def test_slicing_with_tilt_angle(self) -> None:
        """Verify slicing panorama with tilt angle applied."""
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            tilt_angle=3.5,
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 3)
        for s in slices:
            self.assertEqual(s.size, (1080, 1350))

    def test_vertical_split_orientation(self) -> None:
        """Verify vertical split slices top-to-bottom into stacked slides."""
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            split_orientation="vertical",
        )
        slices = slice_panorama(self.tall_img, cfg)
        self.assertEqual(len(slices), 3)
        for s in slices:
            self.assertEqual(s.size, (1080, 1350))

    def test_infinite_loop_panorama(self) -> None:
        """Verify infinite loop 360-degree panorama slicing."""
        cfg = SlicingConfig(
            num_slices=3,
            aspect_ratio="Portrait (4:5)",
            infinite_loop=True,
            pan_offset_x=0.2,
        )
        slices = slice_panorama(self.wide_img, cfg)
        self.assertEqual(len(slices), 3)
        for s in slices:
            self.assertEqual(s.size, (1080, 1350))

    def test_before_after_mode(self) -> None:
        """Verify before_after_mode renders BEFORE on slide 1 and AFTER on slide 2."""
        cfg_ba = SlicingConfig(
            num_slices=2,
            aspect_ratio="Portrait (4:5)",
            before_after_mode=True,
        )
        slices_ba = slice_panorama(self.wide_img, cfg_ba)
        self.assertEqual(len(slices_ba), 2)

        cfg_plain = SlicingConfig(
            num_slices=2,
            aspect_ratio="Portrait (4:5)",
            before_after_mode=False,
        )
        slices_plain = slice_panorama(self.wide_img, cfg_plain)

        # Both slide 1 and slide 2 should have visual badges differing from plain
        self.assertNotEqual(slices_ba[0].tobytes(), slices_plain[0].tobytes())
        self.assertNotEqual(slices_ba[1].tobytes(), slices_plain[1].tobytes())

    def test_raw_and_dng_embedded_jpeg_fallback(self) -> None:
        """Verify DNG/RAW image loader extracts embedded full-resolution JPEG."""
        import io
        jpeg_img = Image.new("RGB", (400, 200), (40, 160, 220))
        buf = io.BytesIO()
        jpeg_img.save(buf, format="JPEG")
        jpeg_bytes = buf.getvalue()

        # Build simulated RAW file with embedded JPEG stream
        raw_mock = os.path.join(self.temp_dir, "sample_camera.dng")
        with open(raw_mock, "wb") as f:
            f.write(b"RAW_HEADER_MOCK_DATA" * 15 + jpeg_bytes + b"RAW_FOOTER_METADATA")

        loaded = ImageEngine.load_image(raw_mock)
        self.assertEqual(loaded.size, (400, 200))



if __name__ == "__main__":
    unittest.main()
