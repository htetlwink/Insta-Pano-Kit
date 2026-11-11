"""
Instagram Mobile Carousel Simulator.
Provides an interactive phone mockup with smooth slide navigation, pagination dots,
and swipe simulation for desktop preview before exporting.
"""

from typing import List, Optional
import customtkinter as ctk
from PIL import Image


class PhoneSimulatorModal(ctk.CTkToplevel):
    """Interactive Instagram mobile mockup preview dialog."""

    def __init__(
        self,
        parent: ctk.CTk,
        slice_images: List[Image.Image],
        aspect_ratio: str = "Portrait (4:5)",
        username: str = "your_panorama",
        caption: str = "Swipe left to explore the full seamless panorama! 👉",
    ) -> None:
        super().__init__(parent)
        self.slice_images = slice_images
        self.aspect_ratio = aspect_ratio
        self.username = username
        self.caption = caption
        self.current_index = 0
        self.is_playing = False
        self._play_timer: Optional[str] = None

        self.title("📱 Instagram Mobile Carousel Simulator")
        self.geometry("480x820")
        self.minsize(440, 750)
        self.transient(parent)
        self.grab_set()

        self._center_window(parent)
        self._build_ui()
        self._bind_keys()
        self._display_current_slice()

    def _center_window(self, parent: ctk.CTk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = 480
        h = 820
        x = max(0, px + (pw - w) // 2)
        y = max(10, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _bind_keys(self) -> None:
        self.bind("<Left>", lambda e: self._prev_slide())
        self.bind("<Right>", lambda e: self._next_slide())
        self.bind("<space>", lambda e: self._toggle_autoplay())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        self.is_playing = False
        if self._play_timer:
            self.after_cancel(self._play_timer)
        self.destroy()

    def _build_ui(self) -> None:
        # Outer phone bezel frame
        self.phone_bezel = ctk.CTkFrame(
            self,
            corner_radius=28,
            fg_color=("gray95", "#0e1117"),
            border_width=3,
            border_color=("gray75", "#262b35"),
        )
        self.phone_bezel.pack(fill="both", expand=True, padx=16, pady=16)

        # Phone Notch / Speaker Bar
        notch_bar = ctk.CTkFrame(self.phone_bezel, height=22, fg_color="transparent")
        notch_bar.pack(fill="x", padx=20, pady=(8, 4))
        notch = ctk.CTkFrame(notch_bar, width=90, height=8, corner_radius=4, fg_color=("gray60", "gray30"))
        notch.pack(anchor="center")

        # Instagram App Header
        header = ctk.CTkFrame(self.phone_bezel, height=44, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(2, 6))

        # Avatar circle
        avatar_ring = ctk.CTkFrame(header, width=34, height=34, corner_radius=17, fg_color=("#e1306c", "#fd1d1d"))
        avatar_ring.pack(side="left", padx=(0, 10))
        avatar_ring.pack_propagate(False)

        avatar_inner = ctk.CTkFrame(avatar_ring, width=28, height=28, corner_radius=14, fg_color=("#ffffff", "#1a1a1a"))
        avatar_inner.pack(expand=True)
        avatar_inner.pack_propagate(False)

        lbl_av = ctk.CTkLabel(avatar_inner, text="📷", font=ctk.CTkFont(size=14))
        lbl_av.pack(expand=True)

        user_info = ctk.CTkFrame(header, fg_color="transparent")
        user_info.pack(side="left", fill="y")

        lbl_user = ctk.CTkLabel(
            user_info,
            text=self.username,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray10", "gray95"),
        )
        lbl_user.pack(anchor="w")

        lbl_loc = ctk.CTkLabel(
            user_info,
            text="Panoramic Carousel",
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray55"),
        )
        lbl_loc.pack(anchor="w")

        lbl_dots = ctk.CTkLabel(header, text="•••", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_dots.pack(side="right", padx=6)

        # Main Photo Canvas Box
        # Height dynamically based on 4:5 or 1:1
        if "Square" in self.aspect_ratio:
            canvas_h = 340
            canvas_w = 340
        elif "Story" in self.aspect_ratio:
            canvas_h = 420
            canvas_w = 236
        else:
            # 4:5 portrait
            canvas_h = 400
            canvas_w = 320

        self.canvas_container = ctk.CTkFrame(
            self.phone_bezel,
            width=canvas_w,
            height=canvas_h,
            corner_radius=0,
            fg_color="black",
        )
        self.canvas_container.pack(pady=4)
        self.canvas_container.pack_propagate(False)

        # Image display label
        self.lbl_image = ctk.CTkLabel(self.canvas_container, text="")
        self.lbl_image.pack(fill="both", expand=True)

        # Slide badge in top-right
        self.lbl_counter = ctk.CTkLabel(
            self.canvas_container,
            text="1/3",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("gray20", "black"),
            text_color="white",
            corner_radius=10,
            width=42,
            height=22,
        )
        self.lbl_counter.place(relx=0.96, rely=0.04, anchor="ne")

        # Overlay Left and Right arrow buttons
        self.btn_overlay_left = ctk.CTkButton(
            self.canvas_container,
            text="‹",
            font=ctk.CTkFont(size=22, weight="bold"),
            width=32,
            height=32,
            corner_radius=16,
            fg_color=("gray90", "rgba(20,20,20,0.6)"),
            hover_color=("gray80", "rgba(50,50,50,0.8)"),
            text_color=("gray10", "white"),
            command=self._prev_slide,
        )
        self.btn_overlay_left.place(relx=0.04, rely=0.5, anchor="w")

        self.btn_overlay_right = ctk.CTkButton(
            self.canvas_container,
            text="›",
            font=ctk.CTkFont(size=22, weight="bold"),
            width=32,
            height=32,
            corner_radius=16,
            fg_color=("gray90", "rgba(20,20,20,0.6)"),
            hover_color=("gray80", "rgba(50,50,50,0.8)"),
            text_color=("gray10", "white"),
            command=self._next_slide,
        )
        self.btn_overlay_right.place(relx=0.96, rely=0.5, anchor="e")

        # Action row (Like, Comment, Share, Dots, Bookmark)
        actions = ctk.CTkFrame(self.phone_bezel, height=36, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(8, 2))

        left_icons = ctk.CTkFrame(actions, fg_color="transparent")
        left_icons.pack(side="left")

        ctk.CTkLabel(left_icons, text="❤️", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(left_icons, text="💬", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(left_icons, text="✈️", font=ctk.CTkFont(size=14)).pack(side="left")

        # Centered Pagination Dots
        self.dots_frame = ctk.CTkFrame(actions, fg_color="transparent")
        self.dots_frame.pack(side="left", expand=True)

        ctk.CTkLabel(actions, text="🔖", font=ctk.CTkFont(size=14)).pack(side="right")

        # Likes & Caption
        caption_box = ctk.CTkFrame(self.phone_bezel, fg_color="transparent")
        caption_box.pack(fill="x", padx=16, pady=(4, 6))

        lbl_likes = ctk.CTkLabel(
            caption_box,
            text="Liked by photography.daily and 2,419 others",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray20", "gray85"),
        )
        lbl_likes.pack(anchor="w")

        cap_text = f"{self.username} {self.caption}"
        lbl_cap = ctk.CTkLabel(
            caption_box,
            text=cap_text,
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray75"),
            wraplength=380,
            justify="left",
        )
        lbl_cap.pack(anchor="w", pady=(2, 0))

        # Bottom Controls (Autoplay, Slide Selector, Close)
        control_card = ctk.CTkFrame(self.phone_bezel, fg_color=("gray88", "#171c24"), corner_radius=12)
        control_card.pack(fill="x", padx=14, pady=(8, 8))

        ctrl_row = ctk.CTkFrame(control_card, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=10, pady=8)

        self.btn_play = ctk.CTkButton(
            ctrl_row,
            text="▶ Auto Swipe",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=100,
            height=28,
            command=self._toggle_autoplay,
        )
        self.btn_play.pack(side="left", padx=(0, 8))

        lbl_hint = ctk.CTkLabel(
            ctrl_row,
            text="Use ◀ ▶ keys or click arrows",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray55"),
        )
        lbl_hint.pack(side="left")

        btn_close = ctk.CTkButton(
            ctrl_row,
            text="Done",
            font=ctk.CTkFont(size=11),
            width=70,
            height=28,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            command=self._on_close,
        )
        btn_close.pack(side="right")

    def _display_current_slice(self) -> None:
        if not self.slice_images:
            return

        total = len(self.slice_images)
        self.current_index = max(0, min(self.current_index, total - 1))
        img = self.slice_images[self.current_index]

        # Determine target display size
        target_h = self.canvas_container.winfo_height() or 400
        target_w = self.canvas_container.winfo_width() or 320

        # Preserve aspect ratio while fitting into canvas
        w_orig, h_orig = img.size
        scale = min(target_w / w_orig, target_h / h_orig)
        dw = int(round(w_orig * scale))
        dh = int(round(h_orig * scale))

        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(dw, dh))
        self.lbl_image.configure(image=ctk_img, text="")
        self.lbl_image.image = ctk_img

        # Counter text
        self.lbl_counter.configure(text=f"{self.current_index + 1}/{total}")

        # Update pagination dots
        for child in self.dots_frame.winfo_children():
            child.destroy()

        for i in range(total):
            dot_color = ("#2563eb", "#3b82f6") if i == self.current_index else ("gray65", "gray40")
            dot_size = 8 if i == self.current_index else 6
            f = ctk.CTkFrame(
                self.dots_frame,
                width=dot_size,
                height=dot_size,
                corner_radius=dot_size // 2,
                fg_color=dot_color,
            )
            f.pack(side="left", padx=2)

        # Update overlay button visibility
        self.btn_overlay_left.configure(state="normal" if self.current_index > 0 else "disabled")
        self.btn_overlay_right.configure(state="normal" if self.current_index < total - 1 else "disabled")

    def _prev_slide(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self._display_current_slice()

    def _next_slide(self) -> None:
        if self.current_index < len(self.slice_images) - 1:
            self.current_index += 1
            self._display_current_slice()
        elif self.is_playing:
            # Loop around during autoplay
            self.current_index = 0
            self._display_current_slice()

    def _toggle_autoplay(self) -> None:
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_play.configure(text="⏸ Pause", fg_color=("#16a34a", "#22c55e"))
            self._run_autoplay()
        else:
            self.btn_play.configure(text="▶ Auto Swipe", fg_color=("#2563eb", "#3b82f6"))
            if self._play_timer:
                self.after_cancel(self._play_timer)

    def _run_autoplay(self) -> None:
        if not self.is_playing:
            return
        self._next_slide()
        self._play_timer = self.after(2200, self._run_autoplay)
