#!/usr/bin/env python3
"""
InstaPanoramaSplitter
======================
The ultimate Instagram panoramic content suite:
- Seamless multi-slide carousel splitter (Portrait 4:5, Square 1:1, Story 9:16)
- Interactive framing with horizontal & vertical Pan Offset controls
- In-app interactive Instagram Mobile Carousel Swipe Simulator
- Seamless Seam Arrows, Swipe Badges, and Cover Title overlays
- Ambient Blurred Background Fill & Solid Gallery Borders
- sRGB Color Space conversion to prevent washed-out Instagram colors
- Smart 1080px unsharp mask sharpening for crisp retina mobile screens
- Visual Numbered Upload Guide contact sheet generation
- Scan-to-Phone instant local Wi-Fi QR code transfer
- Animated Ken Burns panning MP4 video generator for Instagram Reels & Stories
- Instagram Profile Puzzle Grid splitter (3x1, 3x2, 3x3) with reverse upload sequence
- Categorized photography captions & hashtags scratchpad
- Bulk batch panorama queue processor
"""

import os
import sys
import threading
import subprocess
import traceback
from typing import Optional, List
from PIL import Image, ImageOps, ImageDraw, ImageFont

import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.image_engine import (
    ASPECT_RATIOS,
    SlicingConfig,
    slice_panorama,
    save_slices,
    generate_upload_guide,
    apply_color_filter,
)
from gui.phone_simulator import PhoneSimulatorModal
from gui.qr_modal import QRTransferModal
from gui.video_modal import VideoExportModal
from gui.grid_modal import ProfileGridModal
from gui.caption_modal import CaptionHashtagsModal
from gui.batch_modal import BatchModal

# ---------------------------------------------------------------------------
# Appearance & Theme Configuration
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def open_directory(path: str) -> None:
    """Open the file explorer at the specified directory path."""
    if not os.path.exists(path):
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"Failed to open directory {path}: {e}")


def get_default_font(size: int = 12, bold: bool = True) -> ImageFont.ImageFont:
    """Load a TrueType font if available, fallback to default."""
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "LiberationSans-Bold.ttf" if bold else "LiberationSans.ttf",
        "Arial.ttf",
        "Helvetica.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Core Application Class
# ---------------------------------------------------------------------------
class InstaPanoramaSplitter(ctk.CTk):
    """Main Application Window for InstaPanoramaSplitter."""

    FIT_MODES = [
        "Standard 1080px (Fit & Crop)",
        "Proportional (Full Width • No Crop)",
        "Blurred Background Fill (No Cropping)",
        "Solid Gallery Border (White)",
        "Solid Gallery Border (Black)",
    ]

    ASPECT_MODES = [
        "Portrait (4:5) — 1080×1350 px (Feed Optimal)",
        "Square (1:1) — 1080×1080 px (Classic Feed)",
        "Story (9:16) — 1080×1920 px (Reels & Stories)",
    ]

    SWIPE_INDICATORS = [
        "None",
        "Seam Arrow ➔",
        "Swipe Badge (Slide 1)",
        "Dot Indicators",
    ]

    COLOR_PRESETS = [
        "None",
        "Cinematic Moody",
        "Kodak Warmth",
        "Vintage 35mm",
        "B&W High Contrast",
        "Film Grain",
    ]

    def __init__(self) -> None:
        super().__init__()

        # Window Metadata
        self.title("📸 InstaPanoramaSplitter — Instagram Panorama & Creator Suite")
        self.geometry("940x980")
        self.minsize(860, 760)
        self._center_window()

        # Application State
        self.image_path: Optional[str] = None
        self.pil_source_image: Optional[Image.Image] = None
        self.preview_ctk_image: Optional[ctk.CTkImage] = None
        self.cached_slices: List[Image.Image] = []
        self.last_export_dir: Optional[str] = None
        self.last_exported_files: List[str] = []
        self.is_processing: bool = False

        # Config Variables
        self.num_slices_var = ctk.IntVar(value=3)
        self.aspect_mode_var = ctk.StringVar(value=self.ASPECT_MODES[0])
        self.fit_mode_var = ctk.StringVar(value=self.FIT_MODES[0])
        self.pan_x_var = ctk.DoubleVar(value=0.0)
        self.pan_y_var = ctk.DoubleVar(value=0.0)
        self.swipe_indicator_var = ctk.StringVar(value="None")
        self.color_filter_var = ctk.StringVar(value="None")
        self.split_headline_var = ctk.StringVar(value="")
        self.title_text_var = ctk.StringVar(value="")
        self.watermark_text_var = ctk.StringVar(value="")
        self.format_var = ctk.StringVar(value="JPEG")
        self.prefix_var = ctk.StringVar(value="panorama_slice")

        # Instagram Optimization Checkboxes
        self.apply_srgb_var = ctk.BooleanVar(value=True)
        self.smart_sharpen_var = ctk.BooleanVar(value=True)
        self.upload_guide_var = ctk.BooleanVar(value=True)
        self.story_mode_var = ctk.BooleanVar(value=False)
        self.camera_card_var = ctk.BooleanVar(value=False)

        # Drag-to-pan state
        self._drag_start_x: Optional[float] = None
        self._drag_start_y: Optional[float] = None
        self._drag_start_pan_x: float = 0.0
        self._drag_start_pan_y: float = 0.0
        self._preview_excess_w: float = 0.0
        self._preview_excess_h: float = 0.0

        # Build UI
        self._build_ui()
        self._update_summary_info()

    def _center_window(self) -> None:
        """Center the window relative to primary monitor."""
        self.update_idletasks()
        w = 940
        h = 980
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(10, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # -----------------------------------------------------------------------
    # UI Construction
    # -----------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Construct the modern GUI layout."""
        self.scroll_container = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.scroll_container.pack(fill="both", expand=True, padx=20, pady=(15, 15))

        self._build_header(self.scroll_container)
        self._build_quick_tools_bar(self.scroll_container)
        self._build_image_source_card(self.scroll_container)
        self._build_configuration_card(self.scroll_container)
        self._build_action_card(self.scroll_container)

    def _build_header(self, parent: ctk.CTkBaseClass) -> None:
        """Header with App Title and Theme Switcher."""
        header_frame = ctk.CTkFrame(parent, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", fill="y")

        ctk.CTkLabel(
            title_box,
            text="📸 InstaPanoramaSplitter",
            font=ctk.CTkFont(size=23, weight="bold"),
            text_color=("gray10", "gray95"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text="Pro Instagram Panorama Slicer, Reels Video Pan & Mobile Creator Suite",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w")

        theme_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        theme_box.pack(side="right", fill="y")

        self.theme_menu = ctk.CTkSegmentedButton(
            theme_box,
            values=["🌙 Dark", "☀️ Light"],
            command=self._on_theme_toggle,
            width=130,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.theme_menu.set("🌙 Dark")
        self.theme_menu.pack(anchor="e", pady=4)

    def _build_quick_tools_bar(self, parent: ctk.CTkBaseClass) -> None:
        """Top Toolbar for Instagram Creator Power Tools."""
        bar = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray90", "#141822"))
        bar.pack(fill="x", pady=(0, 14), padx=2)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(
            inner,
            text="⚡ Instagram Tools:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#2563eb", "#60a5fa"),
        ).pack(side="left", padx=(0, 10))

        # Tool 1: Interactive Mobile Simulator
        self.btn_tool_sim = ctk.CTkButton(
            inner,
            text="📱 Mobile Preview",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            width=115,
            command=self._open_phone_simulator,
            state="disabled",
        )
        self.btn_tool_sim.pack(side="left", padx=3)

        # Tool 2: QR Transfer
        self.btn_tool_qr = ctk.CTkButton(
            inner,
            text="📲 Scan to Phone (QR)",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            width=135,
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._open_qr_modal,
            state="disabled",
        )
        self.btn_tool_qr.pack(side="left", padx=3)

        # Tool 3: Reels Video Pan
        self.btn_tool_video = ctk.CTkButton(
            inner,
            text="🎬 Video Pan (Reels)",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            width=130,
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._open_video_modal,
            state="disabled",
        )
        self.btn_tool_video.pack(side="left", padx=3)

        # Tool 4: Profile Grid Slicer
        self.btn_tool_grid = ctk.CTkButton(
            inner,
            text="🔲 Profile Grid (3×3)",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            width=130,
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._open_grid_modal,
            state="disabled",
        )
        self.btn_tool_grid.pack(side="left", padx=3)

        # Tool 5: Captions & Hashtags
        btn_tool_caption = ctk.CTkButton(
            inner,
            text="🏷️ Captions & Tags",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            width=120,
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._open_caption_modal,
        )
        btn_tool_caption.pack(side="left", padx=3)

        # Tool 6: Batch Processor
        btn_tool_batch = ctk.CTkButton(
            inner,
            text="📦 Batch Slicer",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            width=100,
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._open_batch_modal,
        )
        btn_tool_batch.pack(side="right", padx=(3, 0))

    def _build_image_source_card(self, parent: ctk.CTkBaseClass) -> None:
        """Card for Panorama Source, Live Preview, and Interactive Framing Sliders."""
        card = ctk.CTkFrame(parent, corner_radius=12, border_width=1, border_color=("gray80", "gray25"))
        card.pack(fill="x", pady=(0, 14), padx=2)

        # Card Title Row
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(
            top_row,
            text="1. Panorama Image & Interactive Framing",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("gray20", "gray90"),
        ).pack(side="left")

        self.btn_browse = ctk.CTkButton(
            top_row,
            text="📂 Browse Image",
            command=self._browse_image,
            width=135,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
        )
        self.btn_browse.pack(side="right")

        # File info banner
        self.file_info_frame = ctk.CTkFrame(card, fg_color=("gray90", "gray17"), corner_radius=8)
        self.file_info_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.lbl_filename = ctk.CTkLabel(
            self.file_info_frame,
            text="No image selected — Click 'Browse Image' to load a wide panorama (.jpg, .png, .jpeg)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray40", "gray65"),
            anchor="w",
        )
        self.lbl_filename.pack(fill="x", padx=12, pady=(8, 2))

        self.lbl_filepath = ctk.CTkLabel(
            self.file_info_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
            anchor="w",
        )
        self.lbl_filepath.pack(fill="x", padx=12, pady=(0, 8))

        # Live Thumbnail Preview
        self.preview_container = ctk.CTkFrame(
            card,
            fg_color=("gray85", "gray14"),
            corner_radius=10,
            height=210,
            border_width=1,
            border_color=("gray75", "gray22"),
        )
        self.preview_container.pack(fill="x", padx=16, pady=(0, 10))
        self.preview_container.pack_propagate(False)

        self.lbl_preview = ctk.CTkLabel(
            self.preview_container,
            text="🌄 Live Slice & Pan Preview\nLoad an image to visualize slice dividers and crop framing in real time\n(💡 Click & drag directly on preview to pan)",
            font=ctk.CTkFont(size=13),
            text_color=("gray45", "gray55"),
            cursor="hand2",
        )
        self.lbl_preview.pack(fill="both", expand=True, padx=8, pady=8)
        self.lbl_preview.bind("<ButtonPress-1>", self._on_preview_drag_start)
        self.lbl_preview.bind("<B1-Motion>", self._on_preview_drag_motion)
        self.lbl_preview.bind("<ButtonRelease-1>", self._on_preview_drag_end)

        # Pan Offset Controls (Horizontal & Vertical Framing Sliders)
        pan_card = ctk.CTkFrame(card, fg_color=("gray92", "#131720"), corner_radius=8)
        pan_card.pack(fill="x", padx=16, pady=(0, 14))

        pan_header = ctk.CTkFrame(pan_card, fg_color="transparent")
        pan_header.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            pan_header,
            text="🎯 Pan & Crop Framing Offset (or drag preview above):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#2563eb", "#60a5fa"),
        ).pack(side="left")

        btn_reset_pan = ctk.CTkButton(
            pan_header,
            text="Reset Center",
            font=ctk.CTkFont(size=10),
            height=20,
            width=75,
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray38"),
            command=self._reset_pan,
        )
        btn_reset_pan.pack(side="right")

        # Two Column Sliders: Pan X & Pan Y
        sliders_row = ctk.CTkFrame(pan_card, fg_color="transparent")
        sliders_row.pack(fill="x", padx=12, pady=(0, 8))
        sliders_row.columnconfigure(0, weight=1)
        sliders_row.columnconfigure(1, weight=1)

        # Pan X
        col_px = ctk.CTkFrame(sliders_row, fg_color="transparent")
        col_px.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self.lbl_pan_x = ctk.CTkLabel(
            col_px,
            text="Horizontal Pan (X): Center (0%)",
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray70"),
        )
        self.lbl_pan_x.pack(anchor="w")

        self.slider_pan_x = ctk.CTkSlider(
            col_px,
            from_=-1.0,
            to=1.0,
            variable=self.pan_x_var,
            command=self._on_pan_change,
            height=16,
        )
        self.slider_pan_x.set(0.0)
        self.slider_pan_x.pack(fill="x", pady=4)

        # Pan Y
        col_py = ctk.CTkFrame(sliders_row, fg_color="transparent")
        col_py.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        self.lbl_pan_y = ctk.CTkLabel(
            col_py,
            text="Vertical Pan (Y): Center (0%)",
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray70"),
        )
        self.lbl_pan_y.pack(anchor="w")

        self.slider_pan_y = ctk.CTkSlider(
            col_py,
            from_=-1.0,
            to=1.0,
            variable=self.pan_y_var,
            command=self._on_pan_change,
            height=16,
        )
        self.slider_pan_y.set(0.0)
        self.slider_pan_y.pack(fill="x", pady=4)

    def _build_configuration_card(self, parent: ctk.CTkBaseClass) -> None:
        """Card for Slices, Ratios, Framing Modes, Creative Overlays, and Instagram Quality."""
        card = ctk.CTkFrame(parent, corner_radius=12, border_width=1, border_color=("gray80", "gray25"))
        card.pack(fill="x", pady=(0, 14), padx=2)

        ctk.CTkLabel(
            card,
            text="2. Configuration & Instagram Enhancements",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("gray20", "gray90"),
        ).pack(anchor="w", padx=16, pady=(12, 10))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(0, 12))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # ---------------- Left: Number of Slices ----------------
        col_left = ctk.CTkFrame(grid, fg_color="transparent")
        col_left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        slice_hdr = ctk.CTkFrame(col_left, fg_color="transparent")
        slice_hdr.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            slice_hdr,
            text="Number of Carousel Slices:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        self.lbl_slice_badge = ctk.CTkLabel(
            slice_hdr,
            text="3 Slices",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#2563eb", "#1d4ed8"),
            text_color="white",
            corner_radius=6,
            width=68,
            height=22,
        )
        self.lbl_slice_badge.pack(side="right")

        self.slider_slices = ctk.CTkSlider(
            col_left,
            from_=2,
            to=10,
            number_of_steps=8,
            variable=self.num_slices_var,
            command=self._on_slice_slider_change,
            height=16,
        )
        self.slider_slices.set(3)
        self.slider_slices.pack(fill="x", pady=(4, 6))

        preset_row = ctk.CTkFrame(col_left, fg_color="transparent")
        preset_row.pack(fill="x")
        ctk.CTkLabel(preset_row, text="Presets:", font=ctk.CTkFont(size=11), text_color=("gray45", "gray55")).pack(side="left", padx=(0, 4))
        for n in [2, 3, 4, 5, 6, 7]:
            b = ctk.CTkButton(
                preset_row,
                text=str(n),
                width=26,
                height=22,
                font=ctk.CTkFont(size=11),
                fg_color=("gray80", "gray25"),
                hover_color=("gray70", "gray35"),
                command=lambda val=n: self._set_slice_count(val),
            )
            b.pack(side="left", padx=2)

        # ---------------- Right: Instagram Aspect Ratio ----------------
        col_right = ctk.CTkFrame(grid, fg_color="transparent")
        col_right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        ctk.CTkLabel(
            col_right,
            text="Instagram Aspect Ratio:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        self.opt_aspect = ctk.CTkOptionMenu(
            col_right,
            values=self.ASPECT_MODES,
            variable=self.aspect_mode_var,
            command=self._on_aspect_change,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.opt_aspect.pack(fill="x", pady=(0, 4))

        self.lbl_aspect_desc = ctk.CTkLabel(
            col_right,
            text="1080 × 1350 px per slide (Fills mobile screen, highest reach)",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray55"),
            anchor="w",
        )
        self.lbl_aspect_desc.pack(fill="x")

        # ---------------- Row 2: Framing Mode & Creative Overlay ----------------
        divider = ctk.CTkFrame(card, height=1, fg_color=("gray85", "gray25"))
        divider.pack(fill="x", padx=16, pady=(10, 12))

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 10))
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)

        # Framing mode
        col_fm = ctk.CTkFrame(row2, fg_color="transparent")
        col_fm.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(col_fm, text="Framing & Fill Strategy:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.opt_fit = ctk.CTkOptionMenu(
            col_fm,
            values=self.FIT_MODES,
            variable=self.fit_mode_var,
            command=self._on_fit_mode_change,
            height=30,
            font=ctk.CTkFont(size=11),
        )
        self.opt_fit.pack(fill="x")

        # Creative Swipe Indicators
        col_ind = ctk.CTkFrame(row2, fg_color="transparent")
        col_ind.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(col_ind, text="Seamless Engagement Cue:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.opt_indicator = ctk.CTkOptionMenu(
            col_ind,
            values=self.SWIPE_INDICATORS,
            variable=self.swipe_indicator_var,
            command=lambda v: self._update_preview(),
            height=30,
            font=ctk.CTkFont(size=11),
        )
        self.opt_indicator.pack(fill="x")

        # ---------------- Row 3: Cover Title & Watermark ----------------
        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.pack(fill="x", padx=16, pady=(0, 10))
        row3.columnconfigure(0, weight=1)
        row3.columnconfigure(1, weight=1)

        col_title = ctk.CTkFrame(row3, fg_color="transparent")
        col_title.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(col_title, text="Slide 1 Cover Title (Optional):", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(0, 2))
        self.entry_title = ctk.CTkEntry(
            col_title,
            textvariable=self.title_text_var,
            placeholder_text="e.g. Majestic Dolomites Panorama",
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.entry_title.pack(fill="x")

        col_wm = ctk.CTkFrame(row3, fg_color="transparent")
        col_wm.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(col_wm, text="Photographer Watermark / Handle:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(0, 2))
        self.entry_wm = ctk.CTkEntry(
            col_wm,
            textvariable=self.watermark_text_var,
            placeholder_text="e.g. @your_account",
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.entry_wm.pack(fill="x")

        # ---------------- Row 4: Color Grading Presets & Split-Seam Headline ----------------
        row4 = ctk.CTkFrame(card, fg_color="transparent")
        row4.pack(fill="x", padx=16, pady=(0, 10))
        row4.columnconfigure(0, weight=1)
        row4.columnconfigure(1, weight=1)

        col_color = ctk.CTkFrame(row4, fg_color="transparent")
        col_color.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(col_color, text="🎨 Film Color Grading Preset:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(0, 2))
        self.opt_color_filter = ctk.CTkOptionMenu(
            col_color,
            values=self.COLOR_PRESETS,
            variable=self.color_filter_var,
            command=lambda v: self._update_preview(),
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.opt_color_filter.pack(fill="x")

        col_headline = ctk.CTkFrame(row4, fg_color="transparent")
        col_headline.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(col_headline, text="🔤 Split-Seam Headline (Spans Slide 1 & 2):", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(0, 2))
        self.entry_headline = ctk.CTkEntry(
            col_headline,
            textvariable=self.split_headline_var,
            placeholder_text="e.g. DISCOVER THE UNKNOWN",
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.entry_headline.pack(fill="x")
        self.entry_headline.bind("<KeyRelease>", lambda e: self._update_preview())

        # ---------------- Row 5: Instagram Quality & Add-ons ----------------
        opt_box = ctk.CTkFrame(card, fg_color=("gray92", "#131720"), corner_radius=8)
        opt_box.pack(fill="x", padx=16, pady=(0, 12))

        opt_box_inner1 = ctk.CTkFrame(opt_box, fg_color="transparent")
        opt_box_inner1.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkCheckBox(
            opt_box_inner1,
            text="sRGB Color Space (Prevents washed out colors)",
            variable=self.apply_srgb_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=20,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkCheckBox(
            opt_box_inner1,
            text="Smart Sharpen (1080px Retina boost)",
            variable=self.smart_sharpen_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=20,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkCheckBox(
            opt_box_inner1,
            text="Numbered Upload Guide (upload_guide.jpg)",
            variable=self.upload_guide_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=20,
        ).pack(side="left")

        opt_box_inner2 = ctk.CTkFrame(opt_box, fg_color="transparent")
        opt_box_inner2.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkCheckBox(
            opt_box_inner2,
            text="Instagram Stories Mode (9:16 Tap-Through Prompts)",
            variable=self.story_mode_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=20,
            command=self._update_preview,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkCheckBox(
            opt_box_inner2,
            text="Append Photography Specs Card (Camera/Lens EXIF)",
            variable=self.camera_card_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=20,
        ).pack(side="left")

        # Format & Prefix
        fmt_row = ctk.CTkFrame(card, fg_color="transparent")
        fmt_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(fmt_row, text="Format:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.seg_format = ctk.CTkSegmentedButton(
            fmt_row,
            values=["JPEG", "PNG"],
            variable=self.format_var,
            command=lambda v: self._update_summary_info(),
            width=90,
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.seg_format.set("JPEG")
        self.seg_format.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(fmt_row, text="Prefix:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.entry_prefix = ctk.CTkEntry(
            fmt_row,
            textvariable=self.prefix_var,
            height=26,
            font=ctk.CTkFont(size=11),
            width=160,
        )
        self.entry_prefix.pack(side="left")

        # Dimension / Summary Pill
        self.summary_badge = ctk.CTkFrame(card, fg_color=("gray90", "#18202c"), corner_radius=8)
        self.summary_badge.pack(fill="x", padx=16, pady=(0, 14))

        self.lbl_summary = ctk.CTkLabel(
            self.summary_badge,
            text="📊 Output Summary: 3 slices • Ready",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#2563eb", "#60a5fa"),
            anchor="w",
        )
        self.lbl_summary.pack(fill="x", padx=12, pady=7)

    def _build_action_card(self, parent: ctk.CTkBaseClass) -> None:
        """Card for Primary Slicing Action, Progress, and Post-Export Workflow."""
        card = ctk.CTkFrame(parent, corner_radius=12, border_width=1, border_color=("gray80", "gray25"))
        card.pack(fill="x", pady=(0, 10), padx=2)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=16)

        # Primary Slice Button
        self.btn_slice = ctk.CTkButton(
            inner,
            text="✂️ Slice & Save Carousel Slices",
            command=self._start_slice_process,
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            corner_radius=8,
            fg_color=("#2563eb", "#3b82f6"),
            hover_color=("#1d4ed8", "#2563eb"),
        )
        self.btn_slice.pack(fill="x", pady=(0, 12))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(inner, height=10, corner_radius=5)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", pady=(0, 10))

        # Status & Action Buttons
        status_row = ctk.CTkFrame(inner, fg_color="transparent")
        status_row.pack(fill="x")

        self.lbl_status = ctk.CTkLabel(
            status_row,
            text="Ready. Load a panorama and click 'Slice & Save Carousel Slices'.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
            anchor="w",
        )
        self.lbl_status.pack(side="left", fill="x", expand=True)

        self.btn_open_folder = ctk.CTkButton(
            status_row,
            text="📁 Open Folder",
            command=self._open_export_folder,
            width=105,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            state="disabled",
        )
        self.btn_open_folder.pack(side="right", padx=(6, 0))

        self.btn_post_qr = ctk.CTkButton(
            status_row,
            text="📲 Phone QR",
            command=self._open_qr_modal,
            width=95,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            state="disabled",
        )
        self.btn_post_qr.pack(side="right")

    # -----------------------------------------------------------------------
    # Event Handlers & Dynamic Updates
    # -----------------------------------------------------------------------
    def _on_theme_toggle(self, value: str) -> None:
        mode = "Dark" if "Dark" in value else "Light"
        ctk.set_appearance_mode(mode)
        self._update_preview()

    def _set_slice_count(self, count: int) -> None:
        self.num_slices_var.set(count)
        self.slider_slices.set(count)
        self.lbl_slice_badge.configure(text=f"{count} Slices")
        self._update_summary_info()
        self._update_preview()

    def _on_slice_slider_change(self, value: float) -> None:
        count = int(round(value))
        self.lbl_slice_badge.configure(text=f"{count} Slices")
        self._update_summary_info()
        self._update_preview()

    def _on_aspect_change(self, value: str) -> None:
        if "4:5" in value:
            self.lbl_aspect_desc.configure(text="1080 × 1350 px per slide (Fills mobile screen, highest reach)")
        elif "1:1" in value:
            self.lbl_aspect_desc.configure(text="1080 × 1080 px per slide (Classic Instagram square format)")
        else:
            self.lbl_aspect_desc.configure(text="1080 × 1920 px per slide (Instagram Stories & Reels tap-through)")
        self._update_summary_info()
        self._update_preview()

    def _on_fit_mode_change(self, value: str) -> None:
        self._update_summary_info()
        self._update_preview()

    def _on_pan_change(self, _=None) -> None:
        px = self.pan_x_var.get()
        py = self.pan_y_var.get()
        self.lbl_pan_x.configure(text=f"Horizontal Pan (X): {int(round(px * 100)):+d}%")
        self.lbl_pan_y.configure(text=f"Vertical Pan (Y): {int(round(py * 100)):+d}%")
        self._update_preview()

    def _reset_pan(self) -> None:
        self.pan_x_var.set(0.0)
        self.pan_y_var.set(0.0)
        self.slider_pan_x.set(0.0)
        self.slider_pan_y.set(0.0)
        self.lbl_pan_x.configure(text="Horizontal Pan (X): Center (0%)")
        self.lbl_pan_y.configure(text="Vertical Pan (Y): Center (0%)")
        self._update_preview()

    def _on_preview_drag_start(self, event) -> None:
        """Record start position for pointer drag-to-pan."""
        if self.pil_source_image is None:
            return
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._drag_start_pan_x = self.pan_x_var.get()
        self._drag_start_pan_y = self.pan_y_var.get()

    def _on_preview_drag_motion(self, event) -> None:
        """Update horizontal/vertical pan dynamically as user drags the preview."""
        if self._drag_start_x is None or self.pil_source_image is None:
            return
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y

        scale_x = self._preview_excess_w if self._preview_excess_w > 0 else 120.0
        scale_y = self._preview_excess_h if self._preview_excess_h > 0 else 120.0

        delta_x = (dx / scale_x) * 2.0
        delta_y = (dy / scale_y) * 2.0

        new_px = max(-1.0, min(1.0, self._drag_start_pan_x + delta_x))
        new_py = max(-1.0, min(1.0, self._drag_start_pan_y + delta_y))

        self.pan_x_var.set(round(new_px, 3))
        self.slider_pan_x.set(new_px)
        self.pan_y_var.set(round(new_py, 3))
        self.slider_pan_y.set(new_py)
        self.lbl_pan_x.configure(text=f"Horizontal Pan (X): {int(round(new_px * 100)):+d}%")
        self.lbl_pan_y.configure(text=f"Vertical Pan (Y): {int(round(new_py * 100)):+d}%")
        self._update_preview()

    def _on_preview_drag_end(self, event) -> None:
        """Finalize drag-to-pan gesture."""
        self._drag_start_x = None
        self._drag_start_y = None

    def _update_summary_info(self) -> None:
        n = self.num_slices_var.get()
        aspect_val = self.aspect_mode_var.get()
        fmt = self.format_var.get()

        aspect_key = "Portrait (4:5)"
        if "1:1" in aspect_val:
            aspect_key = "Square (1:1)"
        elif "9:16" in aspect_val or "Story" in aspect_val:
            aspect_key = "Story (9:16)"

        dim = ASPECT_RATIOS.get(aspect_key, (1080, 1350))
        target_w, target_h = dim
        total_w = target_w * n

        self.lbl_summary.configure(
            text=f"📊 Output: {n} slices • Per slide: {target_w}×{target_h} px • Total: {total_w}×{target_h} px ({fmt}) • sRGB & Smart Sharpen"
        )

    # -----------------------------------------------------------------------
    # Image Loading & Live Preview Rendering
    # -----------------------------------------------------------------------
    def _browse_image(self) -> None:
        filetypes = [
            ("All Supported Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
            ("JPEG Images", "*.jpg *.jpeg"),
            ("PNG Images", "*.png"),
            ("All Files", "*.*"),
        ]
        chosen = filedialog.askopenfilename(title="Select Wide Panorama Image", filetypes=filetypes)
        if chosen:
            self._load_image(chosen)

    def _load_image(self, path: str) -> None:
        try:
            raw = Image.open(path)
            img = ImageOps.exif_transpose(raw)
            w, h = img.size
            if w <= 0 or h <= 0:
                raise ValueError("Invalid image dimensions.")

            self.pil_source_image = img
            self.image_path = path

            # Extract info
            filename = os.path.basename(path)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            ratio = w / h

            self.lbl_filename.configure(
                text=f"📄 {filename}  •  {w} × {h} px  (Ratio: {ratio:.2f}:1)  •  {size_mb:.2f} MB",
                text_color=("gray10", "gray95"),
            )
            self.lbl_filepath.configure(text=path)
            self.lbl_status.configure(
                text="Image loaded. Adjust pan sliders or settings, then slice or preview.",
                text_color=("gray30", "gray70"),
            )

            # Enable tool buttons
            self.btn_tool_sim.configure(state="normal")
            self.btn_tool_video.configure(state="normal")
            self.btn_tool_grid.configure(state="normal")

            self._reset_pan()
            self._update_summary_info()
            self._update_preview()

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Image Load Error", f"Could not load image:\n{e}")

    def _update_preview(self) -> None:
        """Render annotated thumbnail showing active crop region, dividers, and slide badges."""
        if self.pil_source_image is None:
            return

        try:
            orig = self.pil_source_image
            orig_w, orig_h = orig.size
            n_slices = self.num_slices_var.get()
            aspect_val = self.aspect_mode_var.get()
            fit_val = self.fit_mode_var.get()
            pan_x = self.pan_x_var.get()
            pan_y = self.pan_y_var.get()

            # Target dims
            aspect_key = "Portrait (4:5)"
            if "1:1" in aspect_val:
                aspect_key = "Square (1:1)"
            elif "9:16" in aspect_val or "Story" in aspect_val:
                aspect_key = "Story (9:16)"

            target_w, target_h = ASPECT_RATIOS.get(aspect_key, (1080, 1350))
            total_target_w = target_w * n_slices

            max_pw = 740
            max_ph = 185
            scale = min(max_pw / orig_w, max_ph / orig_h)
            pw = max(20, int(round(orig_w * scale)))
            ph = max(20, int(round(orig_h * scale)))

            thumb = orig.resize((pw, ph), Image.Resampling.LANCZOS).convert("RGBA")

            # Apply color filter preview if enabled
            cf = self.color_filter_var.get()
            if cf and cf != "None":
                thumb_rgb = apply_color_filter(thumb.convert("RGB"), cf)
                thumb = thumb_rgb.convert("RGBA")

            overlay = Image.new("RGBA", thumb.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Calculate crop or active region
            if "Standard" in fit_val:
                target_ratio = total_target_w / target_h
                orig_ratio = orig_w / orig_h

                if orig_ratio >= target_ratio:
                    # Panorama wider than carousel: crop left/right with pan_x
                    active_w = ph * target_ratio
                    excess_w = pw - active_w
                    self._preview_excess_w = excess_w
                    self._preview_excess_h = 0.0
                    # pan_x: -1.0 leftmost, 0.0 center, 1.0 rightmost
                    offset_x = excess_w * (pan_x + 1.0) / 2.0
                    offset_x = max(0.0, min(excess_w, offset_x))

                    active_x0 = offset_x
                    active_x1 = offset_x + active_w
                    active_y0 = 0.0
                    active_y1 = float(ph)

                    # Darken cropped margins
                    if active_x0 > 0:
                        draw.rectangle([(0, 0), (active_x0, ph)], fill=(0, 0, 0, 160))
                    if active_x1 < pw:
                        draw.rectangle([(active_x1, 0), (pw, ph)], fill=(0, 0, 0, 160))
                else:
                    # Panorama taller than carousel: crop top/bottom with pan_y
                    active_h = pw / target_ratio
                    excess_h = ph - active_h
                    self._preview_excess_w = 0.0
                    self._preview_excess_h = excess_h
                    offset_y = excess_h * (pan_y + 1.0) / 2.0
                    offset_y = max(0.0, min(excess_h, offset_y))

                    active_x0 = 0.0
                    active_x1 = float(pw)
                    active_y0 = offset_y
                    active_y1 = offset_y + active_h

                    if active_y0 > 0:
                        draw.rectangle([(0, 0), (pw, active_y0)], fill=(0, 0, 0, 160))
                    if active_y1 < ph:
                        draw.rectangle([(0, active_y1), (pw, ph)], fill=(0, 0, 0, 160))
            else:
                # Proportional or Blurred Fill: 100% is active
                self._preview_excess_w = 0.0
                self._preview_excess_h = 0.0
                active_x0 = 0.0
                active_x1 = float(pw)
                active_y0 = 0.0
                active_y1 = float(ph)

            active_w_span = active_x1 - active_x0
            slice_w = active_w_span / n_slices
            badge_font = get_default_font(size=11, bold=True)

            # Draw divider lines and badges
            for i in range(n_slices):
                x0 = active_x0 + i * slice_w
                x1 = active_x0 + (i + 1) * slice_w

                if i > 0:
                    draw.line([(x0, active_y0), (x0, active_y1)], fill=(0, 235, 255, 230), width=2)

                badge_cx = (x0 + x1) / 2.0
                badge_cy = active_y0 + 16.0
                badge_r = 11.0
                if badge_cy + badge_r < active_y1:
                    draw.ellipse(
                        [(badge_cx - badge_r, badge_cy - badge_r), (badge_cx + badge_r, badge_cy + badge_r)],
                        fill=(37, 99, 235, 225),
                        outline=(255, 255, 255, 255),
                        width=1,
                    )
                    draw.text((badge_cx, badge_cy), str(i + 1), fill="white", font=badge_font, anchor="mm")

            # Active frame outline
            draw.rectangle(
                [(active_x0, active_y0), (active_x1 - 1, active_y1 - 1)],
                outline=(0, 235, 255, 240),
                width=2,
            )

            # Draw split-seam headline preview if configured
            split_text = self.split_headline_var.get().strip()
            if split_text and n_slices >= 2:
                headline_font = get_default_font(size=9, bold=True)
                seam_x = active_x0 + slice_w
                mid_y = (active_y0 + active_y1) / 2.0
                pill_w = min(220, int(len(split_text) * 7.0 + 16))
                draw.rectangle(
                    [(seam_x - pill_w // 2, mid_y - 10), (seam_x + pill_w // 2, mid_y + 10)],
                    fill=(0, 0, 0, 195),
                    outline=(255, 215, 0, 240),
                    width=1,
                )
                draw.text((seam_x, mid_y), f"« {split_text[:20]} »", fill=(255, 235, 90, 255), font=headline_font, anchor="mm")

            # Draw Story Mode tap indicator if enabled
            if self.story_mode_var.get():
                story_font = get_default_font(size=8, bold=True)
                draw.rectangle([(active_x0 + 4, active_y1 - 18), (active_x0 + 95, active_y1 - 4)], fill=(0, 0, 0, 180), outline=(255, 255, 255, 200))
                draw.text((active_x0 + 49, active_y1 - 11), "Tap next ➔", fill="white", font=story_font, anchor="mm")

            res = Image.alpha_composite(thumb, overlay)
            self.preview_ctk_image = ctk.CTkImage(light_image=res, dark_image=res, size=(pw, ph))
            self.lbl_preview.configure(image=self.preview_ctk_image, text="")

        except Exception as e:
            traceback.print_exc()

    # -----------------------------------------------------------------------
    # Slicing Engine Execution
    # -----------------------------------------------------------------------
    def _build_slicing_config(self) -> SlicingConfig:
        aspect_val = self.aspect_mode_var.get()
        aspect_key = "Portrait (4:5)"
        if "1:1" in aspect_val:
            aspect_key = "Square (1:1)"
        elif "9:16" in aspect_val or "Story" in aspect_val:
            aspect_key = "Story (9:16)"

        fit_val = self.fit_mode_var.get()
        fit_key = "Standard (Fit & Crop)"
        border_col = "white"

        if "Proportional" in fit_val:
            fit_key = "Proportional (Full Width)"
        elif "Blurred" in fit_val:
            fit_key = "Blurred Background Fill"
        elif "Solid Gallery Border" in fit_val:
            fit_key = "Solid Gallery Border"
            if "Black" in fit_val:
                border_col = "black"

        ind = self.swipe_indicator_var.get()
        if "Arrow" in ind:
            ind_val = "Seam Arrow"
        elif "Badge" in ind:
            ind_val = "Swipe Badge (Slide 1)"
        elif "Dot" in ind:
            ind_val = "Dot Indicators"
        else:
            ind_val = "None"

        return SlicingConfig(
            num_slices=self.num_slices_var.get(),
            aspect_ratio=aspect_key,
            fit_mode=fit_key,
            border_color=border_col,
            pan_offset_x=self.pan_x_var.get(),
            pan_offset_y=self.pan_y_var.get(),
            apply_srgb=self.apply_srgb_var.get(),
            smart_sharpen=self.smart_sharpen_var.get(),
            swipe_indicator=ind_val,
            title_text=self.title_text_var.get().strip() or None,
            watermark_text=self.watermark_text_var.get().strip() or None,
            color_filter=self.color_filter_var.get(),
            include_camera_card=self.camera_card_var.get(),
            split_headline=self.split_headline_var.get().strip() or None,
            story_mode=self.story_mode_var.get(),
            format=self.format_var.get(),
            prefix=self.prefix_var.get().strip() or "panorama_slice",
        )

    def _start_slice_process(self) -> None:
        if self.is_processing:
            return

        if self.pil_source_image is None or not self.image_path:
            messagebox.showwarning("No Image", "Please select a panorama image before slicing.")
            return

        default_dir = os.path.dirname(self.image_path)
        dest_dir = filedialog.askdirectory(
            title="Select Destination Folder for Carousel Slices",
            initialdir=default_dir,
        )
        if not dest_dir:
            return

        config = self._build_slicing_config()
        self.is_processing = True
        self.btn_slice.configure(state="disabled", text="⏳ Generating & Optimizing Slices...")
        self.btn_browse.configure(state="disabled")
        self.btn_open_folder.configure(state="disabled")
        self.btn_post_qr.configure(state="disabled")
        self.progress_bar.set(0.1)
        self.lbl_status.configure(text="Processing panorama...", text_color=("gray20", "gray85"))

        threading.Thread(
            target=self._slice_worker,
            args=(self.pil_source_image.copy(), config, dest_dir),
            daemon=True,
        ).start()

    def _slice_worker(self, img: Image.Image, config: SlicingConfig, dest_dir: str) -> None:
        try:
            self._update_progress_from_thread(0.2, "Scaling, framing, and slicing image...")
            slices = slice_panorama(img, config)
            self.cached_slices = slices

            ext = "png" if config.format.upper() == "PNG" else "jpg"
            self._update_progress_from_thread(0.5, "Saving high-quality slices with sRGB color profile...")

            saved_files = save_slices(
                slices=slices,
                export_dir=dest_dir,
                prefix=config.prefix,
                ext=ext,
                jpeg_quality=config.jpeg_quality,
            )

            # Generate Upload Guide if requested
            if self.upload_guide_var.get():
                self._update_progress_from_thread(0.85, "Generating visual numbered upload guide...")
                guide_path = os.path.join(dest_dir, f"{config.prefix}_upload_guide.jpg")
                filename = os.path.basename(self.image_path or "Panorama")
                generate_upload_guide(slices, guide_path, title=f"Instagram Carousel Guide — {filename}")
                saved_files.append(guide_path)

            self.after(0, self._on_slice_success, dest_dir, len(slices), saved_files)

        except Exception as e:
            traceback.print_exc()
            self.after(0, self._on_slice_error, str(e))

    def _update_progress_from_thread(self, p: float, msg: str) -> None:
        self.after(0, lambda: self._apply_progress(p, msg))

    def _apply_progress(self, p: float, msg: str) -> None:
        self.progress_bar.set(p)
        self.lbl_status.configure(text=msg)

    def _on_slice_success(self, dest_dir: str, num_slices: int, saved_files: List[str]) -> None:
        self.is_processing = False
        self.last_export_dir = dest_dir
        self.last_exported_files = saved_files

        self.btn_slice.configure(state="normal", text="✂️ Slice & Save Carousel Slices")
        self.btn_browse.configure(state="normal")
        self.btn_open_folder.configure(state="normal")
        self.btn_post_qr.configure(state="normal")
        self.btn_tool_qr.configure(state="normal")
        self.progress_bar.set(1.0)

        msg = f"✅ Success! Saved {num_slices} carousel slides (+ Upload Guide) to:\n{dest_dir}"
        self.lbl_status.configure(text=msg, text_color=("#16a34a", "#22c55e"))

        messagebox.showinfo(
            "Carousel Ready!",
            f"Successfully generated {num_slices} Instagram carousel slices!\n\n"
            f"Folder: {dest_dir}\n\n"
            "Tip: Click '📲 Phone QR' to scan and download directly to your mobile camera roll!",
        )

    def _on_slice_error(self, err: str) -> None:
        self.is_processing = False
        self.btn_slice.configure(state="normal", text="✂️ Slice & Save Carousel Slices")
        self.btn_browse.configure(state="normal")
        self.progress_bar.set(0.0)
        self.lbl_status.configure(text=f"❌ Slicing error: {err}", text_color=("#dc2626", "#ef4444"))
        messagebox.showerror("Error", f"Failed to slice panorama:\n{err}")

    def _open_export_folder(self) -> None:
        if self.last_export_dir and os.path.exists(self.last_export_dir):
            open_directory(self.last_export_dir)

    # -----------------------------------------------------------------------
    # Modal Tool Openers
    # -----------------------------------------------------------------------
    def _open_phone_simulator(self) -> None:
        """Launch interactive Instagram Mobile Carousel Simulator."""
        if not self.cached_slices:
            if self.pil_source_image:
                # Generate on the fly for preview
                config = self._build_slicing_config()
                self.cached_slices = slice_panorama(self.pil_source_image, config)
            else:
                messagebox.showwarning("No Slices", "Please load an image first.")
                return

        aspect_val = self.aspect_mode_var.get()
        cap = self.entry_title.get().strip() or "Swipe left to explore the full seamless panorama! 👉"
        user = self.entry_wm.get().strip().lstrip("@") or "your_panorama"

        PhoneSimulatorModal(
            parent=self,
            slice_images=self.cached_slices,
            aspect_ratio=aspect_val,
            username=user,
            caption=cap,
        )

    def _open_qr_modal(self) -> None:
        """Launch Scan-to-Phone QR Transfer Dialog."""
        target_dir = self.last_export_dir
        if not target_dir or not os.path.exists(target_dir):
            if self.image_path:
                target_dir = os.path.dirname(self.image_path)
            else:
                target_dir = os.path.expanduser("~")

        QRTransferModal(
            parent=self,
            directory_to_serve=target_dir,
            file_list=self.last_exported_files if self.last_exported_files else None,
        )

    def _open_video_modal(self) -> None:
        """Launch Reels / Stories Panning Video Modal."""
        if not self.image_path:
            messagebox.showwarning("No Image", "Please load a panorama image first.")
            return
        VideoExportModal(parent=self, image_path=self.image_path)

    def _open_grid_modal(self) -> None:
        """Launch Instagram Profile Grid Maker (3x1, 3x2, 3x3)."""
        if not self.image_path or not self.pil_source_image:
            messagebox.showwarning("No Image", "Please load a panorama image first.")
            return
        ProfileGridModal(parent=self, image_path=self.image_path, pil_image=self.pil_source_image)

    def _open_caption_modal(self) -> None:
        """Launch Instagram Captions & Hashtags Scratchpad."""
        CaptionHashtagsModal(parent=self, num_slices=self.num_slices_var.get())

    def _open_batch_modal(self) -> None:
        """Launch Batch Processing Modal."""
        config = self._build_slicing_config()
        BatchModal(parent=self, current_config=config)


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    app = InstaPanoramaSplitter()
    app.mainloop()


if __name__ == "__main__":
    main()
