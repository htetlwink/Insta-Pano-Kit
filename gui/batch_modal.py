"""
Batch Panorama Processing Modal.
Enables selecting multiple panoramic photos or a directory, slicing them in a queue,
and creating organized subfolders for each panorama.
"""

import os
import threading
from typing import List, Optional
import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.image_engine import SlicingConfig
from core.batch_engine import BatchProcessor


class BatchModal(ctk.CTkToplevel):
    """Dialog for bulk processing multiple panoramas."""

    def __init__(self, parent: ctk.CTk, current_config: SlicingConfig) -> None:
        super().__init__(parent)
        self.config = current_config
        self.selected_files: List[str] = []
        self.processor: Optional[BatchProcessor] = None
        self.is_running = False

        self.title("📦 Batch Panorama Slicer")
        self.geometry("640x700")
        self.minsize(560, 600)
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
        w = 640
        h = 700
        x = max(0, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container,
            text="📦 Batch Panorama Slicer",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            container,
            text="Queue multiple panoramic photos. Each panorama is sliced into its own dedicated subfolder.",
            font=ctk.CTkFont(size=12),
            text_color=("gray45", "gray60"),
        ).pack(anchor="w", pady=(0, 16))

        # Selection Card
        sel_card = ctk.CTkFrame(container, corner_radius=12)
        sel_card.pack(fill="x", pady=(0, 14))

        top_row = ctk.CTkFrame(sel_card, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(
            top_row,
            text="Selected Panorama Files:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        btn_files = ctk.CTkButton(
            top_row,
            text="+ Add Files",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=95,
            height=28,
            command=self._add_files,
        )
        btn_files.pack(side="right", padx=(6, 0))

        btn_folder = ctk.CTkButton(
            top_row,
            text="📂 Add Folder",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=95,
            height=28,
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._add_folder,
        )
        btn_folder.pack(side="right")

        # Listbox / Textbox of queued files
        self.txt_file_list = ctk.CTkTextbox(sel_card, height=180, font=ctk.CTkFont(size=11), corner_radius=8)
        self.txt_file_list.pack(fill="x", padx=16, pady=(0, 12))
        self.txt_file_list.insert("1.0", "No images queued yet.\nClick '+ Add Files' or 'Add Folder' to select panoramas.")
        self.txt_file_list.configure(state="disabled")

        clear_btn = ctk.CTkButton(
            sel_card,
            text="Clear List",
            font=ctk.CTkFont(size=11),
            width=80,
            height=24,
            fg_color="transparent",
            text_color=("gray40", "gray65"),
            command=self._clear_list,
        )
        clear_btn.pack(anchor="e", padx=16, pady=(0, 10))

        # Settings Card
        cfg_card = ctk.CTkFrame(container, corner_radius=12)
        cfg_card.pack(fill="x", pady=(0, 14))

        cfg_label = ctk.CTkLabel(
            cfg_card,
            text=f"Batch Slicing Configuration: {self.config.num_slices} Slices • {self.config.aspect_ratio} • {self.config.fit_mode}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#2563eb", "#60a5fa"),
        )
        cfg_label.pack(fill="x", padx=16, pady=12)

        # Output folder row
        out_row = ctk.CTkFrame(container, fg_color="transparent")
        out_row.pack(fill="x", pady=(0, 14))

        self.btn_start = ctk.CTkButton(
            out_row,
            text="🚀 Start Batch Processing",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            corner_radius=8,
            command=self._start_batch,
        )
        self.btn_start.pack(fill="x")

        # Progress Card
        prog_card = ctk.CTkFrame(container, corner_radius=12)
        prog_card.pack(fill="x", pady=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(prog_card, height=10)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=16, pady=(14, 8))

        self.lbl_status = ctk.CTkLabel(
            prog_card,
            text="Waiting for image selection.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self.lbl_status.pack(fill="x", padx=16, pady=(0, 14))

    def _add_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select Panoramic Photos",
            filetypes=[
                ("All Supported Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
                ("All Files", "*.*"),
            ],
        )
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
            self._update_display_list()

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Folder Containing Panoramas")
        if folder:
            valid_exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
            found = 0
            for root, _, filenames in os.walk(folder):
                for fname in sorted(filenames):
                    if fname.lower().endswith(valid_exts) and not fname.startswith("."):
                        fpath = os.path.join(root, fname)
                        if fpath not in self.selected_files:
                            self.selected_files.append(fpath)
                            found += 1
            self._update_display_list()

    def _clear_list(self) -> None:
        self.selected_files.clear()
        self._update_display_list()

    def _update_display_list(self) -> None:
        self.txt_file_list.configure(state="normal")
        self.txt_file_list.delete("1.0", "end")
        if not self.selected_files:
            self.txt_file_list.insert("1.0", "No images queued yet.")
        else:
            for i, p in enumerate(self.selected_files):
                self.txt_file_list.insert("end", f"{i + 1}. {os.path.basename(p)}  ({p})\n")
        self.txt_file_list.configure(state="disabled")

    def _start_batch(self) -> None:
        if not self.selected_files:
            messagebox.showwarning("No Files", "Please add one or more panorama images first.")
            return

        dest_dir = filedialog.askdirectory(title="Select Output Folder for Sliced Subdirectories")
        if not dest_dir:
            return

        self.is_running = True
        self.btn_start.configure(state="disabled", text="⏳ Processing Batch...")
        self.progress_bar.set(0.0)

        threading.Thread(
            target=self._worker,
            args=(dest_dir,),
            daemon=True,
        ).start()

    def _worker(self, dest_dir: str) -> None:
        def on_prog(curr: int, total: int, msg: str):
            p = curr / max(1, total)
            self.after(0, lambda: self._update_ui_progress(p, msg))

        self.processor = BatchProcessor(
            file_paths=self.selected_files,
            output_dir=dest_dir,
            config=self.config,
            generate_guide=True,
            progress_callback=on_prog,
        )

        res = self.processor.process()
        self.after(0, lambda: self._on_finish(res, dest_dir))

    def _update_ui_progress(self, p: float, msg: str) -> None:
        self.progress_bar.set(p)
        self.lbl_status.configure(text=msg)

    def _on_finish(self, res: dict, dest_dir: str) -> None:
        self.is_running = False
        self.btn_start.configure(state="normal", text="🚀 Start Batch Processing")
        self.progress_bar.set(1.0)
        succ = len(res["successful"])
        fail = len(res["failed"])
        msg = f"✅ Batch Complete! Successfully processed {succ} panoramas."
        if fail > 0:
            msg += f" ({fail} failed)"
        self.lbl_status.configure(text=msg, text_color=("#16a34a", "#22c55e"))
        messagebox.showinfo("Batch Finished", f"{msg}\n\nSaved to:\n{dest_dir}")
