"""
Tests for Scan-to-Phone Local Transfer Server & QR Generator.
"""

import io
import os
import shutil
import tempfile
import unittest
import urllib.request
import zipfile
from PIL import Image

from core.web_share import PhoneTransferServer


class TestWebShare(unittest.TestCase):
    """Test suite for PhoneTransferServer and QR code generation."""

    def setUp(self) -> None:
        # Ensure proxy doesn't intercept loopback test requests
        os.environ["no_proxy"] = "localhost,127.0.0.1"
        os.environ["NO_PROXY"] = "localhost,127.0.0.1"

        self.temp_dir = tempfile.mkdtemp(prefix="test_web_share_")

        # Create dummy image slices
        self.slice_names = ["slice_1.jpg", "slice_2.jpg", "slice_3.jpg"]
        self.slice_paths = []
        for name in self.slice_names:
            p = os.path.join(self.temp_dir, name)
            img = Image.new("RGB", (300, 300), color=(100, 150, 200))
            img.save(p, "JPEG")
            self.slice_paths.append(p)

        self.server = PhoneTransferServer()

    def tearDown(self) -> None:
        if self.server:
            self.server.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _open_url(self, path: str):
        """Helper to open local URLs without environment proxy interference."""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        # Use loopback 127.0.0.1 with the bound port for deterministic testing
        url = f"http://127.0.0.1:{self.server.port}{path}"
        return opener.open(url, timeout=5.0)

    def test_server_lifecycle_and_qr_code(self) -> None:
        """Test server start, QR code generation, and clean shutdown."""
        url = self.server.start(self.temp_dir, self.slice_paths)
        self.assertTrue(url.startswith("http://"))
        self.assertGreater(self.server.port, 0)

        # Generate QR code
        qr_img = self.server.generate_qr_code(box_size=6, border=2)
        self.assertIsInstance(qr_img, Image.Image)
        self.assertGreater(qr_img.width, 50)
        self.assertGreater(qr_img.height, 50)

        # Stop server
        self.server.stop()
        self.assertIsNone(self.server.httpd)

    def test_gallery_html_endpoint(self) -> None:
        """Verify GET / returns 200 and expected responsive mobile HTML."""
        self.server.start(self.temp_dir, self.slice_paths)

        with self._open_url("/") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            html_content = resp.read().decode("utf-8")

        self.assertIn("InstaPanorama Mobile Download", html_content)
        self.assertIn("Download All as ZIP", html_content)
        self.assertIn("slice_1.jpg", html_content)
        self.assertIn("slice_2.jpg", html_content)
        self.assertIn("slice_3.jpg", html_content)

    def test_download_all_zip_endpoint(self) -> None:
        """Verify GET /download-all.zip streams a valid ZIP archive containing all slices."""
        self.server.start(self.temp_dir, self.slice_paths)

        with self._open_url("/download-all.zip") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/zip", resp.headers.get("Content-Type", ""))
            zip_bytes = resp.read()

        # Check standard ZIP header signature PK\x03\x04
        self.assertTrue(zip_bytes.startswith(b"PK\x03\x04"))

        # Verify ZIP contents
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            namelist = zf.namelist()
            self.assertIn("slice_1.jpg", namelist)
            self.assertIn("slice_2.jpg", namelist)
            self.assertIn("slice_3.jpg", namelist)
            self.assertEqual(len(namelist), 3)

    def test_individual_file_and_download_endpoints(self) -> None:
        """Verify GET /files/<name> and GET /download/<name>."""
        self.server.start(self.temp_dir, self.slice_paths)

        # 1. Inline file view
        with self._open_url("/files/slice_1.jpg") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "image/jpeg")
            data = resp.read()
            self.assertEqual(len(data), os.path.getsize(self.slice_paths[0]))

        # 2. Attachment download
        with self._open_url("/download/slice_1.jpg") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))
            self.assertIn("slice_1.jpg", resp.headers.get("Content-Disposition", ""))
            data = resp.read()
            self.assertEqual(len(data), os.path.getsize(self.slice_paths[0]))

    def test_directory_traversal_protection(self) -> None:
        """Verify accessing files outside served list/folder returns 404."""
        self.server.start(self.temp_dir, self.slice_paths)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._open_url("/files/../../etc/passwd")
        self.assertEqual(ctx.exception.code, 404)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._open_url("/nonexistent.jpg")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
