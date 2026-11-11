"""
Batch Panorama Processing Engine.
Allows queuing and processing multiple panoramic photos sequentially in background threads.
"""

import os
from typing import List, Tuple, Callable, Optional, Dict, Any
from PIL import Image, ImageOps

from core.image_engine import SlicingConfig, slice_panorama, save_slices, generate_upload_guide


class BatchProcessor:
    """Manages batch processing for a queue of panoramic photos."""

    def __init__(
        self,
        file_paths: List[str],
        output_dir: str,
        config: SlicingConfig,
        generate_guide: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        item_completed_callback: Optional[Callable[[str, List[str]], None]] = None,
    ) -> None:
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.config = config
        self.generate_guide = generate_guide
        self.progress_callback = progress_callback
        self.item_completed_callback = item_completed_callback
        self.is_cancelled = False

    def cancel(self) -> None:
        """Signal batch processor to cancel remaining queue."""
        self.is_cancelled = True

    def process(self) -> Dict[str, Any]:
        """Execute the batch process synchronously (intended to run inside a worker thread)."""
        total = len(self.file_paths)
        successful: List[str] = []
        failed: List[Tuple[str, str]] = []

        for idx, path in enumerate(self.file_paths):
            if self.is_cancelled:
                break

            filename = os.path.basename(path)
            stem, _ = os.path.splitext(filename)

            if self.progress_callback:
                self.progress_callback(idx, total, f"Processing {idx + 1}/{total}: {filename}")

            try:
                raw_img = Image.open(path)
                img = ImageOps.exif_transpose(raw_img)

                # Each panorama gets its own organized subfolder
                target_subfolder = os.path.join(self.output_dir, f"{stem}_carousel")
                os.makedirs(target_subfolder, exist_ok=True)

                # Slice
                slices = slice_panorama(img, self.config)

                ext = "png" if self.config.format.upper() == "PNG" else "jpg"
                prefix = f"{stem}_slice"

                saved = save_slices(
                    slices=slices,
                    export_dir=target_subfolder,
                    prefix=prefix,
                    ext=ext,
                    jpeg_quality=self.config.jpeg_quality,
                )

                if self.generate_guide:
                    guide_path = os.path.join(target_subfolder, f"{stem}_upload_guide.jpg")
                    generate_upload_guide(slices, guide_path, title=f"Upload Guide — {filename}")
                    saved.append(guide_path)

                successful.append(path)
                if self.item_completed_callback:
                    self.item_completed_callback(path, saved)

            except Exception as e:
                failed.append((path, str(e)))

        if self.progress_callback:
            self.progress_callback(total, total, f"Finished! {len(successful)} succeeded, {len(failed)} failed.")

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "cancelled": self.is_cancelled,
        }
