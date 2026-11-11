"""
Profile Grid Modal for Instagram 3x1, 3x2, and 3x3 profile puzzle grids.
"""

import os
import threading
from typing import Optional, List
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageOps, ImageDraw

from core.image_engine import slice_grid, save_slices


class ProfileGridModal(ctk.CTkToplevel):
    """Dialog for creating Instagram profile puzzle grids (3x1, 3x2, 3x3)."""

    def __init__(self, parent: ctk.CTk, image_path: str, pil_image: Image.Image) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.pil_image = pil_image
        self.is_processing = False

        self.title("🔲 Instagram Profile Grid Splitter")
        self.geometry("640x760")
        self.minsize(560, 680)
        self.transient(parent)
        self.grab_set()

        self.grid_mode_var = ctk.StringVar(value="3x1 Banner (1 Row • 3 Tiles)")
        self.format_var = ctk.StringVar(value="JPEG")

        self._center_window(parent)
        self._build_ui()
        self._update_preview()

    def _center_window(self, parent: ctk.CTk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = 640
        h = 760
        x = max(0, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        ctk.CTkLabel(
            container,
            text="🔲 Instagram Profile Grid Maker",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            container,
            text="Split photos into multi-tile profile grids that seamlessly align on your Instagram profile feed.",
            font=ctk.CTkFont(size=12),
            text_color=("gray45", "gray60"),
        ).pack(anchor="w", pady=(0, 16))

        # Config Card
        card = ctk.CTkFrame(container, corner_radius=12)
        card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            card,
            text="Grid Layout Format:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        self.seg_grid = ctk.CTkSegmentedButton(
            card,
            values=[
                "3x1 Banner (3 Tiles)",
                "3x2 Grid (6 Tiles)",
                "3x3 Giant (9 Tiles)",
            ],
            variable=self.grid_mode_var,
            command=lambda v: self._update_preview(),
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.seg_grid.pack(fill="x", padx=16, pady=(0, 12))

        # Explanation box about Instagram reverse upload ordering
        info_box = ctk.CTkFrame(card, fg_color=("gray90", "gray17"), corner_radius=8)
        info_box.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkLabel(
            info_box,
            text="💡 Instagram Upload Order Magic:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#2563eb", "#60a5fa"),
        ).pack(anchor="w", padx=10, pady=(8, 2))

        self.lbl_explanation = ctk.CTkLabel(
            info_box,
            text="Files are named in reverse upload sequence (e.g. tile_03_upload_1st.jpg ... tile_01_upload_last.jpg) so your profile grid appears in exact alignment!",
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray70"),
            wraplength=520,
            justify="left",
        )
        self.lbl_explanation.pack(anchor="w", padx=10, pady=(0, 8))

        # Preview Container
        prev_card = ctk.CTkFrame(container, corner_radius=12)
        prev_card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            prev_card,
            text="Live Grid Layout & Upload Sequence Preview:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 6))

        self.preview_box = ctk.CTkFrame(prev_card, height=240, fg_color=("gray85", "gray14"), corner_radius=8)
        self.preview_box.pack(fill="x", padx=16, pady=(0, 14))
        self.preview_box.pack_propagate(False)

        self.lbl_preview = ctk.CTkLabel(self.preview_box, text="")
        self.lbl_preview.pack(fill="both", expand=True, padx=8, pady=8)

        # Action Card
        act_card = ctk.CTkFrame(container, corner_radius=12)
        act_card.pack(fill="x", pady=(0, 10))

        self.btn_export = ctk.CTkButton(
            act_card,
            text="✂️ Slice & Export Grid Tiles",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            corner_radius=8,
            command=self._start_export,
        )
        self.btn_export.pack(fill="x", padx=16, pady=(14, 10))

        self.progress_bar = ctk.CTkProgressBar(act_card, height=8)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 10))

        self.lbl_status = ctk.CTkLabel(
            act_card,
            text="Ready to export.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self.lbl_status.pack(fill="x", padx=16, pady=(0, 12))

    def _get_rows_cols(self) -> (int, int):
        val = self.grid_mode_var.get()
        if "3x3" in val:
            return 3, 3
        elif "3x2" in val:
            return 2, 3
        else:
            return 1, 3

    def _update_preview(self) -> None:
        if not self.pil_image:
            return

        rows, cols = self._get_rows_cols()
        total_tiles = rows * cols

        # Calculate crop aspect ratio: width = cols * 1080, height = rows * 1080
        target_aspect = cols / rows
        w_orig, h_orig = self.pil_image.size
        orig_aspect = w_orig / h_orig

        # Crop to target grid aspect ratio
        if orig_aspect >= target_aspect:
            # Crop width
            crop_w = int(round(h_orig * target_aspect))
            crop_h = h_orig
            crop_x = (w_orig - crop_w) // 2
            crop_y = 0
        else:
            # Crop height
            crop_w = w_orig
            crop_h = int(round(w_orig / target_aspect))
            crop_x = 0
            crop_y = (h_orig - crop_h) // 2

        cropped = self.pil_image.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))

        # Create thumbnail fitting preview box
        max_pw = 520
        max_ph = 220
        scale = min(max_pw / crop_w, max_ph / crop_h)
        tw = max(10, int(round(crop_w * scale)))
        th = max(10, int(round(crop_h * scale)))

        thumb = cropped.resize((tw, th), Image.Resampling.LANCZOS).convert("RGBA")
        overlay = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        tile_w = tw / cols
        tile_h = th / rows

        tile_idx = 1
        for r in range(rows):
            for c in range(cols):
                x0 = int(round(c * tile_w))
                y0 = int(round(r * tile_h))
                x1 = int(round((c + 1) * tile_w))
                y1 = int(round((r + 1) * tile_h))

                # Border
                draw.rectangle([(x0, y0), (x1 - 1, y1 - 1)], outline=(0, 235, 255, 240), width=2)

                # Reverse upload sequence number
                upload_order = total_tiles - tile_idx + 1

                # Badge
                cx = (x0 + x1) / 2
                cy = (y0 + y1) / 2
                badge_r = 14
                draw.ellipse(
                    [(cx - badge_r, cy - badge_r), (cx + badge_r, cy + badge_r)],
                    fill=(37, 99, 235, 220),
                    outline=(255, 255, 255, 255),
                    width=1,
                )
                draw.text((cx, cy), f"#{upload_order}", fill="white", anchor="mm")
                tile_idx += 1

        res = Image.alpha_composite(thumb, overlay)
        ctk_img = ctk.CTkImage(light_image=res, dark_image=res, size=(tw, th))
        self.lbl_preview.configure(image=ctk_img, text="")
        self.lbl_preview.image = ctk_img

    def _start_export(self) -> None:
        if self.is_processing:
            return

        default_dir = os.path.dirname(self.image_path)
        dest_dir = filedialog.askdirectory(
            title="Select Destination Folder for Profile Grid Tiles",
            initialdir=default_dir,
        )
        if not dest_dir:
            return

        rows, cols = self._get_rows_cols()
        self.is_processing = True
        self.btn_export.configure(state="disabled", text="⏳ Slicing Grid...")
        self.progress_bar.set(0.2)

        threading.Thread(
            target=self._export_worker,
            args=(dest_dir, rows, cols),
            daemon=True,
        ).start()

    def _export_worker(self, dest_dir: str, rows: int, cols: int) -> None:
        try:
            tiles = slice_grid(self.pil_image, rows=rows, cols=cols)

            saved = []
            total = len(tiles)
            for idx, (tile_img, filename) in enumerate(tiles):
                fpath = os.path.join(dest_dir, filename)
                tile_img.convert("RGB").save(fpath, "JPEG", quality=95, optimize=True)
                saved.append(fpath)
                p = 0.2 + 0.8 * ((idx + 1) / total)
                self.after(0, lambda progress=p, count=idx + 1: self._update_export_progress(progress, count, total))

            self.after(0, lambda: self._on_export_success(dest_dir, len(saved)))
        except Exception as e:
            self.after(0, lambda err=str(e): self._on_export_error(err))

    def _update_export_progress(self, p: float, count: int, total: int) -> None:
        self.progress_bar.set(p)
        self.lbl_status.configure(text=f"Saving tile {count} of {total}...")

    def _on_export_success(self, dest_dir: str, count: int) -> None:
        self.is_processing = False
        self.btn_export.configure(state="normal", text="✂️ Slice & Export Grid Tiles")
        self.progress_bar.set(1.0)
        self.lbl_status.configure(text=f"✅ Saved {count} grid tiles successfully!", text_color=("#16a34a", "#22c55e"))
        messagebox.showinfo(
            "Grid Export Complete",
            f"Successfully saved {count} grid tiles to:\n{dest_dir}\n\n"
            "Remember to upload in the reverse numbering order (#1st first, #last last) so it displays correctly on your profile!",
        )

    def _on_export_error(self, err: str) -> None:
        self.is_processing = False
        self.btn_export.configure(state="normal", text="✂️ Slice & Export Grid Tiles")
        self.progress_bar.set(0.0)
        self.lbl_status.configure(text=f"❌ Error: {err}", text_color=("#dc2626", "#ef4444"))
        messagebox.showerror("Grid Export Failed", f"An error occurred:\n{err}")
