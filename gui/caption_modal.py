"""
Caption and Hashtag Generator Modal for Instagram Carousels & Panoramas.
"""

from typing import Dict, List, Optional, Union
from PIL import Image
import customtkinter as ctk

from core.caption_engine import generate_smart_captions, format_full_caption


HASHTAG_CATEGORIES: Dict[str, List[str]] = {
    "Panorama & Carousels": [
        "#panoramic", "#panorama", "#seamlesscarousel", "#panoramaphotography",
        "#swipeleft", "#swipeleftformore", "#carouselpost", "#wideangle",
        "#panoramicview", "#ultrawide", "#multiphoto", "#seamlessswipe"
    ],
    "Landscape & Nature": [
        "#landscapephotography", "#earthpix", "#naturephotography", "#optoutside",
        "#scenicviews", "#wildernessculture", "#roamtheplanet", "#artofvisuals",
        "#beautifuldestinations", "#discoverearth", "#ourplanetdaily", "#stayandwander"
    ],
    "City & Architecture": [
        "#cityscape", "#streetphotography", "#urbanexploration", "#citylights",
        "#architecturephotography", "#skyline", "#metropolis", "#cityviews",
        "#urbanphotography", "#dronephotography", "#nightphotography"
    ],
    "Mobile & Gear": [
        "#shotoniphone", "#shotonpixel", "#shotonsamsung", "#mobilephotography",
        "#sonyalpha", "#fujifilm", "#canonphotography", "#nikonphotography",
        "#leicacamera", "#mirrorlessphotography"
    ],
}

DEFAULT_CAPTION_TEMPLATES = [
    (
        "Standard Swipe Prompt",
        "Swipe left to explore the full panoramic view! 👉\n\n"
        "📍 Location:\n"
        "📷 Gear:\n"
        "✨ Which slide is your favorite? (1, 2, or 3?)\n\n"
        "• • •\n"
    ),
    (
        "Minimalist / Fine Art",
        "A wider perspective.\n"
        "Swipe across for the continuous panorama ➔\n\n"
        "📍 \n\n"
        "• • •\n"
    ),
    (
        "Travel & Adventure Story",
        "Standing at the edge of something massive.\n"
        "Swipe through to take in the full landscape 🏔️👉\n\n"
        "Captured during golden hour.\n"
        "📍 \n\n"
        "• • •\n"
    ),
]


class CaptionHashtagsModal(ctk.CTkToplevel):
    """Dialog for crafting Instagram captions and copying popular photography hashtags."""

    def __init__(
        self,
        parent: ctk.CTk,
        num_slices: int = 3,
        image: Optional[Image.Image] = None,
        image_path: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.num_slices = num_slices
        self.image = image
        self.image_path = image_path
        self.smart_captions: Dict[str, str] = {}
        try:
            self.smart_captions = generate_smart_captions(
                image_path=self.image_path,
                pil_image=self.image,
                num_slices=self.num_slices,
            )
        except Exception:
            pass

        self.title("Instagram Caption & Hashtags Assistant")
        self.geometry("700x750")
        self.minsize(620, 620)
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
        w = 700
        h = 720
        x = max(0, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        ctk.CTkLabel(
            container,
            text="🏷️ Instagram Caption & Hashtag Scratchpad",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            container,
            text="Choose templates, pick high-reach hashtags, and copy everything to your clipboard.",
            font=ctk.CTkFont(size=12),
            text_color=("gray45", "gray60"),
        ).pack(anchor="w", pady=(0, 16))

        # Caption Template Section
        template_card = ctk.CTkFrame(container, corner_radius=10)
        template_card.pack(fill="x", pady=(0, 16), padx=2)

        ctk.CTkLabel(
            template_card,
            text="1. Smart Storytelling Captions & Templates",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 6))

        # Smart AI Captions Bar
        if self.smart_captions:
            smart_row = ctk.CTkFrame(template_card, fg_color="transparent")
            smart_row.pack(fill="x", padx=16, pady=(0, 8))
            ctk.CTkLabel(
                smart_row,
                text="✨ AI Storytelling:",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#2563eb", "#60a5fa"),
            ).pack(side="left", padx=(0, 8))

            b_aes = ctk.CTkButton(
                smart_row,
                text="Aesthetic Story",
                font=ctk.CTkFont(size=11, weight="bold"),
                height=26,
                fg_color=("#3b82f6", "#2563eb"),
                command=lambda: self._apply_template(self.smart_captions.get("aesthetic", "")),
            )
            b_aes.pack(side="left", padx=(0, 6))

            b_tech = ctk.CTkButton(
                smart_row,
                text="EXIF Camera Specs",
                font=ctk.CTkFont(size=11),
                height=26,
                command=lambda: self._apply_template(self.smart_captions.get("technical", "")),
            )
            b_tech.pack(side="left", padx=(0, 6))

            b_eng = ctk.CTkButton(
                smart_row,
                text="Engagement Hook",
                font=ctk.CTkFont(size=11),
                height=26,
                command=lambda: self._apply_template(self.smart_captions.get("engagement", "")),
            )
            b_eng.pack(side="left", padx=(0, 6))

            b_all = ctk.CTkButton(
                smart_row,
                text="Full Post",
                font=ctk.CTkFont(size=11),
                height=26,
                command=lambda: self._apply_template(format_full_caption(self.smart_captions)),
            )
            b_all.pack(side="left")

        btn_row = ctk.CTkFrame(template_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkLabel(
            btn_row,
            text="Presets:",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray55"),
        ).pack(side="left", padx=(0, 8))

        for name, text in DEFAULT_CAPTION_TEMPLATES:
            b = ctk.CTkButton(
                btn_row,
                text=name,
                font=ctk.CTkFont(size=11),
                height=28,
                command=lambda t=text: self._apply_template(t),
            )
            b.pack(side="left", padx=(0, 8))

        # Caption Textbox
        self.txt_caption = ctk.CTkTextbox(
            template_card,
            height=160,
            font=ctk.CTkFont(size=13),
            corner_radius=8,
        )
        self.txt_caption.pack(fill="x", padx=16, pady=(0, 12))
        self._apply_template(DEFAULT_CAPTION_TEMPLATES[0][1])

        # Hashtags Selector Section
        tag_card = ctk.CTkFrame(container, corner_radius=10)
        tag_card.pack(fill="x", pady=(0, 16), padx=2)

        ctk.CTkLabel(
            tag_card,
            text="2. Tap Hashtags to Add to Caption",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 6))

        for category, tags in HASHTAG_CATEGORIES.items():
            cat_frame = ctk.CTkFrame(tag_card, fg_color="transparent")
            cat_frame.pack(fill="x", padx=16, pady=(4, 8))

            ctk.CTkLabel(
                cat_frame,
                text=category,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("gray30", "gray70"),
            ).pack(anchor="w", pady=(0, 4))

            chips_frame = ctk.CTkFrame(cat_frame, fg_color="transparent")
            chips_frame.pack(fill="x")

            col = 0
            row = 0
            for tag in tags:
                btn = ctk.CTkButton(
                    chips_frame,
                    text=tag,
                    font=ctk.CTkFont(size=11),
                    height=24,
                    width=90,
                    fg_color=("gray85", "gray22"),
                    hover_color=("gray75", "gray32"),
                    text_color=("gray10", "gray90"),
                    command=lambda t=tag: self._append_tag(t),
                )
                btn.grid(row=row, column=col, padx=3, pady=3, sticky="w")
                col += 1
                if col > 3:
                    col = 0
                    row += 1

            # Quick "Add All from Category" button
            add_all_btn = ctk.CTkButton(
                cat_frame,
                text=f"+ Add all {category} tags",
                font=ctk.CTkFont(size=10),
                height=20,
                fg_color="transparent",
                text_color=("#2563eb", "#60a5fa"),
                hover=False,
                command=lambda tg=tags: self._append_multiple_tags(tg),
            )
            add_all_btn.pack(anchor="w", pady=(2, 6))

        # Bottom Actions
        actions_card = ctk.CTkFrame(container, fg_color="transparent")
        actions_card.pack(fill="x", pady=(8, 0))

        self.lbl_copied = ctk.CTkLabel(
            actions_card,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#16a34a", "#22c55e"),
        )
        self.lbl_copied.pack(side="left", padx=8)

        btn_copy = ctk.CTkButton(
            actions_card,
            text="📋 Copy Full Caption to Clipboard",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            command=self._copy_to_clipboard,
        )
        btn_copy.pack(side="right")

    def _apply_template(self, template: str) -> None:
        self.txt_caption.delete("1.0", "end")
        self.txt_caption.insert("1.0", template)

    def _append_tag(self, tag: str) -> None:
        current_text = self.txt_caption.get("1.0", "end").strip()
        if tag not in current_text:
            if not current_text.endswith(("\n", " ")):
                self.txt_caption.insert("end", " ")
            self.txt_caption.insert("end", f"{tag} ")

    def _append_multiple_tags(self, tags: List[str]) -> None:
        current_text = self.txt_caption.get("1.0", "end")
        new_tags = [t for t in tags if t not in current_text]
        if new_tags:
            if not current_text.endswith(("\n", " ")):
                self.txt_caption.insert("end", "\n")
            self.txt_caption.insert("end", " ".join(new_tags) + "\n")

    def _copy_to_clipboard(self) -> None:
        text = self.txt_caption.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.lbl_copied.configure(text="✅ Copied to clipboard!")
        self.after(2500, lambda: self.lbl_copied.configure(text=""))
