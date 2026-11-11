"""
QR Code Modal for Instant Phone Transfer.
Spins up a temporary local Wi-Fi HTTP server and displays a QR code for camera roll download.
"""

from typing import List, Optional
import customtkinter as ctk
from PIL import Image

from core.web_share import PhoneTransferServer


class QRTransferModal(ctk.CTkToplevel):
    """Modal displaying QR code for mobile Wi-Fi download."""

    def __init__(
        self,
        parent: ctk.CTk,
        directory_to_serve: str,
        file_list: Optional[List[str]] = None,
    ) -> None:
        super().__init__(parent)
        self.directory_to_serve = directory_to_serve
        self.file_list = file_list
        self.server: Optional[PhoneTransferServer] = None
        self.server_url: str = ""

        self.title("📲 Scan-to-Phone Transfer")
        self.geometry("480x620")
        self.minsize(440, 560)
        self.transient(parent)
        self.grab_set()

        self._center_window(parent)
        self._start_server_and_build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center_window(self, parent: ctk.CTk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = 480
        h = 620
        x = max(0, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _start_server_and_build_ui(self) -> None:
        # Start server
        try:
            self.server = PhoneTransferServer()
            self.server_url = self.server.start(self.directory_to_serve, self.file_list)
            qr_pil = self.server.generate_qr_code(box_size=8, border=2)
        except Exception as e:
            self._build_error_ui(str(e))
            return

        self._build_success_ui(qr_pil)

    def _build_error_ui(self, err: str) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="❌ Server Error",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=("#dc2626", "#ef4444"),
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            frame,
            text=f"Could not start local transfer server:\n{err}",
            wraplength=400,
            text_color=("gray30", "gray70"),
        ).pack(pady=10)

        ctk.CTkButton(frame, text="Close", command=self._on_close).pack(pady=20)

    def _build_success_ui(self, qr_pil: Image.Image) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container,
            text="📲 Scan to Download on Phone",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            container,
            text="Point your iPhone or Android camera at this QR code.\nMake sure your phone is connected to the same Wi-Fi.",
            font=ctk.CTkFont(size=12),
            text_color=("gray45", "gray60"),
            justify="center",
        ).pack(pady=(0, 14))

        # QR Card
        qr_card = ctk.CTkFrame(container, fg_color="white", corner_radius=12)
        qr_card.pack(pady=(0, 14))

        qw, qh = qr_pil.size
        # Scale to nice display size (e.g. 260x260)
        display_size = 250
        qr_display = qr_pil.resize((display_size, display_size), Image.Resampling.NEAREST)
        self.qr_ctk = ctk.CTkImage(light_image=qr_display, dark_image=qr_display, size=(display_size, display_size))

        lbl_qr = ctk.CTkLabel(qr_card, image=self.qr_ctk, text="")
        lbl_qr.pack(padx=14, pady=14)

        # URL pill & copy
        url_frame = ctk.CTkFrame(container, fg_color=("gray90", "gray17"), corner_radius=8)
        url_frame.pack(fill="x", pady=(0, 16))

        self.lbl_url = ctk.CTkLabel(
            url_frame,
            text=self.server_url,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#2563eb", "#60a5fa"),
        )
        self.lbl_url.pack(side="left", padx=12, pady=8)

        btn_copy = ctk.CTkButton(
            url_frame,
            text="Copy Link",
            font=ctk.CTkFont(size=11),
            width=80,
            height=26,
            command=self._copy_link,
        )
        btn_copy.pack(side="right", padx=8, pady=6)

        # Server Active Badge
        status_row = ctk.CTkFrame(container, fg_color="transparent")
        status_row.pack(fill="x", pady=(0, 10))

        self.lbl_status = ctk.CTkLabel(
            status_row,
            text="🟢 Server active • Ready for phone connection",
            font=ctk.CTkFont(size=11),
            text_color=("#16a34a", "#22c55e"),
        )
        self.lbl_status.pack(side="left")

        btn_done = ctk.CTkButton(
            status_row,
            text="Done & Stop",
            font=ctk.CTkFont(size=11),
            width=90,
            height=28,
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray38"),
            command=self._on_close,
        )
        btn_done.pack(side="right")

    def _copy_link(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.server_url)
        self.lbl_status.configure(text="✅ Link copied to clipboard!")
        self.after(2000, lambda: self.lbl_status.configure(text="🟢 Server active • Ready for phone connection"))

    def _on_close(self) -> None:
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        self.destroy()
