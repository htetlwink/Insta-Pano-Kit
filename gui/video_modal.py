"""
Video Export Modal for Instagram Reels / Stories Panning Animation.
"""

import os
import threading
from typing import Optional
import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.video_engine import VideoPanConfig, generate_panning_video


class VideoExportModal(ctk.CTkToplevel):
    """Dialog for configuring and rendering Ken Burns panorama panning MP4 videos."""

    def __init__(self, parent: ctk.CTk, image_path: str) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.output_video_path: Optional[str] = None
        self.is_rendering = False

        self.title("🎬 Export Panning Video (Instagram Reels / Stories)")
        self.geometry("560x650")
        self.minsize(500, 580)
        self.transient(parent)
        self.grab_set()

        self._center_window(parent)
        self._build_ui()

    def _center_window(self, parent: ctk.CTk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = 560
        h = 650
        x = max(0, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        ctk.CTkLabel(
            container,
            text="🎬 Animated Panorama Video Generator",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            container,
            text="Render a smooth Ken Burns panning MP4 video for Instagram Reels, Shorts, and Stories.",
            font=ctk.CTkFont(size=12),
            text_color=("gray45", "gray60"),
        ).pack(anchor="w", pady=(0, 16))

        # Config Card
        card = ctk.CTkFrame(container, corner_radius=12)
        card.pack(fill="x", pady=(0, 16))

        # Ratio selector
        r_box = ctk.CTkFrame(card, fg_color="transparent")
        r_box.pack(fill="x", padx=16, pady=(14, 10))

        ctk.CTkLabel(r_box, text="Target Aspect Ratio:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.seg_ratio = ctk.CTkSegmentedButton(
            r_box,
            values=["Reels/Story (9:16)", "Feed (4:5)", "Square (1:1)"],
            font=ctk.CTkFont(size=11, weight="bold"),
            height=30,
        )
        self.seg_ratio.set("Reels/Story (9:16)")
        self.seg_ratio.pack(fill="x")

        # Duration & FPS
        df_row = ctk.CTkFrame(card, fg_color="transparent")
        df_row.pack(fill="x", padx=16, pady=(0, 12))
        df_row.columnconfigure(0, weight=1)
        df_row.columnconfigure(1, weight=1)

        # Duration
        dur_col = ctk.CTkFrame(df_row, fg_color="transparent")
        dur_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.lbl_duration = ctk.CTkLabel(dur_col, text="Duration: 8.0s", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_duration.pack(anchor="w", pady=(0, 4))

        self.slider_duration = ctk.CTkSlider(
            dur_col,
            from_=4.0,
            to=20.0,
            number_of_steps=16,
            command=self._on_duration_change,
        )
        self.slider_duration.set(8.0)
        self.slider_duration.pack(fill="x")

        # FPS
        fps_col = ctk.CTkFrame(df_row, fg_color="transparent")
        fps_col.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        ctk.CTkLabel(fps_col, text="Framerate (FPS):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.seg_fps = ctk.CTkSegmentedButton(
            fps_col,
            values=["30 FPS (Standard)", "60 FPS (Smooth)"],
            font=ctk.CTkFont(size=11),
            height=28,
        )
        self.seg_fps.set("30 FPS (Standard)")
        self.seg_fps.pack(fill="x")

        # Direction
        dir_box = ctk.CTkFrame(card, fg_color="transparent")
        dir_box.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkLabel(dir_box, text="Panning Motion & Direction:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.seg_dir = ctk.CTkSegmentedButton(
            dir_box,
            values=["Left to Right", "Right to Left", "Ping-Pong (Boomerang)"],
            font=ctk.CTkFont(size=11),
            height=30,
        )
        self.seg_dir.set("Left to Right")
        self.seg_dir.pack(fill="x")

        # Action & Progress Card
        act_card = ctk.CTkFrame(container, corner_radius=12)
        act_card.pack(fill="x", pady=(0, 10))

        self.btn_render = ctk.CTkButton(
            act_card,
            text="⚡ Render MP4 Video",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            corner_radius=8,
            command=self._start_render,
        )
        self.btn_render.pack(fill="x", padx=16, pady=(16, 10))

        self.progress_bar = ctk.CTkProgressBar(act_card, height=8)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 10))

        self.lbl_status = ctk.CTkLabel(
            act_card,
            text="Ready. Select settings and click 'Render MP4 Video'.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            anchor="w",
        )
        self.lbl_status.pack(fill="x", padx=16, pady=(0, 14))

        # Bottom Buttons
        bottom_row = ctk.CTkFrame(container, fg_color="transparent")
        bottom_row.pack(fill="x", pady=(8, 0))

        self.btn_play = ctk.CTkButton(
            bottom_row,
            text="▶ Open Video",
            font=ctk.CTkFont(size=12),
            height=32,
            state="disabled",
            command=self._open_rendered_video,
        )
        self.btn_play.pack(side="left")

        btn_cancel = ctk.CTkButton(
            bottom_row,
            text="Close",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            command=self.destroy,
        )
        btn_cancel.pack(side="right")

    def _on_duration_change(self, val: float) -> None:
        v = round(val, 1)
        self.lbl_duration.configure(text=f"Duration: {v}s")

    def _start_render(self) -> None:
        if self.is_rendering:
            return

        stem, _ = os.path.splitext(os.path.basename(self.image_path))
        default_dir = os.path.dirname(self.image_path)
        default_filename = f"{stem}_reels_pan.mp4"

        save_path = filedialog.asksaveasfilename(
            title="Save Panning Video MP4",
            initialdir=default_dir,
            initialfile=default_filename,
            filetypes=[("MP4 Video", "*.mp4")],
        )
        if not save_path:
            return

        fps_val = 60 if "60" in self.seg_fps.get() else 30
        config = VideoPanConfig(
            target_ratio=self.seg_ratio.get(),
            duration_seconds=float(self.slider_duration.get()),
            fps=fps_val,
            direction=self.seg_dir.get(),
            output_path=save_path,
        )

        self.is_rendering = True
        self.btn_render.configure(state="disabled", text="⏳ Rendering Video...")
        self.lbl_status.configure(text="Processing frames with FFmpeg...", text_color=("gray20", "gray85"))
        self.progress_bar.set(0.1)

        threading.Thread(
            target=self._render_worker,
            args=(config,),
            daemon=True,
        ).start()

    def _render_worker(self, config: VideoPanConfig) -> None:
        try:
            def on_progress(p: float, msg: str):
                self.after(0, lambda: self._update_progress(p, msg))

            out_path = generate_panning_video(
                image_path_or_pil=self.image_path,
                config=config,
                progress_callback=on_progress,
            )
            self.after(0, lambda: self._on_render_success(out_path))
        except Exception as e:
            self.after(0, lambda: self._on_render_error(str(e)))

    def _update_progress(self, p: float, msg: str) -> None:
        self.progress_bar.set(p)
        self.lbl_status.configure(text=msg)

    def _on_render_success(self, out_path: str) -> None:
        self.is_rendering = False
        self.output_video_path = out_path
        self.btn_render.configure(state="normal", text="⚡ Render MP4 Video")
        self.btn_play.configure(state="normal")
        self.progress_bar.set(1.0)
        self.lbl_status.configure(text=f"✅ Video created: {os.path.basename(out_path)}", text_color=("#16a34a", "#22c55e"))
        messagebox.showinfo("Video Ready!", f"Successfully exported panning video to:\n{out_path}")

    def _on_render_error(self, err: str) -> None:
        self.is_rendering = False
        self.btn_render.configure(state="normal", text="⚡ Render MP4 Video")
        self.progress_bar.set(0.0)
        self.lbl_status.configure(text=f"❌ Error: {err}", text_color=("#dc2626", "#ef4444"))
        messagebox.showerror("Render Failed", f"Could not create video:\n{err}")

    def _open_rendered_video(self) -> None:
        if self.output_video_path and os.path.exists(self.output_video_path):
            import subprocess
            import sys
            try:
                if sys.platform == "win32":
                    os.startfile(self.output_video_path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", self.output_video_path])
                else:
                    subprocess.Popen(["xdg-open", self.output_video_path])
            except Exception as e:
                print(f"Could not open video: {e}")
