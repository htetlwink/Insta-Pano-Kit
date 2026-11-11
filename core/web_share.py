"""
Scan-to-Phone Local Transfer Server & QR Generator.
Allows instant transfer of sliced panoramic carousels to iOS and Android phones over local Wi-Fi.
"""

import io
import mimetypes
import os
import re
import socket
import threading
import urllib.parse
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Optional
from PIL import Image
import qrcode


def natural_sort_key(text: str) -> list:
    """Sort strings containing numbers in human/numerical order (e.g. slice_1, slice_2, slice_10)."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]


def format_file_size(size_bytes: int) -> str:
    """Format bytes into readable string (KB, MB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


class TransferRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for serving mobile gallery, individual slices, and ZIP download."""

    server_instance: "PhoneTransferServer"

    def log_message(self, format: str, *args) -> None:
        """Suppress standard HTTP server logging to keep terminal clean."""
        pass

    def do_HEAD(self) -> None:
        self._handle_request(send_body=False)

    def do_GET(self) -> None:
        self._handle_request(send_body=True)

    def _handle_request(self, send_body: bool = True) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ("", "/"):
            self._serve_gallery(send_body)
        elif path == "/download-all.zip":
            self._serve_zip(send_body)
        elif path.startswith("/download/"):
            filename = urllib.parse.unquote(path[len("/download/"):])
            self._serve_file(filename, as_attachment=True, send_body=send_body)
        elif path.startswith("/files/"):
            filename = urllib.parse.unquote(path[len("/files/"):])
            self._serve_file(filename, as_attachment=False, send_body=send_body)
        else:
            self.send_error(404, "Page Not Found")

    def _serve_gallery(self, send_body: bool = True) -> None:
        """Generate and serve modern responsive mobile gallery HTML."""
        files = self.server_instance.get_served_files()
        total = len(files)

        cards_html = []
        for idx, file_path in enumerate(files):
            fname = os.path.basename(file_path)
            escaped_fname = urllib.parse.quote(fname)
            try:
                fsize = os.path.getsize(file_path)
                fsize_str = format_file_size(fsize)
            except OSError:
                fsize_str = "Unknown size"

            is_video = fname.lower().endswith((".mp4", ".mov", ".m4v"))

            if is_video:
                media_tag = f"""
                <video controls playsinline preload="metadata" class="slice-img">
                    <source src="/files/{escaped_fname}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
                """
            else:
                media_tag = f"""
                <img src="/files/{escaped_fname}" alt="Slice {idx + 1}" class="slice-img" loading="lazy" />
                """

            cards_html.append(f"""
            <div class="slice-card">
                <div class="card-header">
                    <span class="slice-badge">Slice {idx + 1} of {total}</span>
                    <span class="file-name">{fname}</span>
                </div>
                <div class="media-container">
                    {media_tag}
                </div>
                <div class="card-footer">
                    <span class="file-size">{fsize_str}</span>
                    <a href="/download/{escaped_fname}" class="btn-download" download="{fname}">
                        ⬇️ Save Slice {idx + 1}
                    </a>
                </div>
            </div>
            """)

        all_cards = "\n".join(cards_html) if cards_html else "<div class='empty-state'>No images found to serve.</div>"

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover" />
    <title>📸 InstaPanorama Mobile Download</title>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-primary: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #3b82f6;
            --accent-blue-hover: #2563eb;
            --accent-green: #10b981;
            --btn-bg: #334155;
            --btn-hover: #475569;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-tap-highlight-color: transparent;
        }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            padding: 20px 16px 48px;
            display: flex;
            justify-content: center;
        }}
        .container {{
            width: 100%;
            max-width: 580px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}
        header {{
            text-align: center;
            padding: 12px 8px 8px;
        }}
        header h1 {{
            font-size: 24px;
            font-weight: 800;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
            color: #ffffff;
        }}
        header p.instructions {{
            font-size: 14px;
            color: var(--text-muted);
            line-height: 1.5;
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.25);
            padding: 10px 14px;
            border-radius: 10px;
            margin-top: 10px;
        }}
        .action-bar {{
            position: sticky;
            top: 12px;
            z-index: 100;
        }}
        .btn-zip {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            color: #ffffff;
            font-size: 16px;
            font-weight: 700;
            text-decoration: none;
            padding: 14px 20px;
            border-radius: 12px;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
            transition: transform 0.15s ease, opacity 0.15s ease;
        }}
        .btn-zip:active {{
            transform: scale(0.98);
            opacity: 0.9;
        }}
        .gallery {{
            display: flex;
            flex-direction: column;
            gap: 22px;
        }}
        .slice-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            border-bottom: 1px solid var(--card-border);
        }}
        .slice-badge {{
            background: rgba(59, 130, 246, 0.2);
            color: #60a5fa;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 20px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .file-name {{
            font-size: 12px;
            color: var(--text-muted);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 55%;
        }}
        .media-container {{
            width: 100%;
            background-color: #000000;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .slice-img {{
            width: 100%;
            height: auto;
            max-height: 80vh;
            display: block;
            object-fit: contain;
            user-select: auto;
            -webkit-user-select: auto;
            -webkit-touch-callout: default;
        }}
        .card-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            background: #172033;
        }}
        .file-size {{
            font-size: 13px;
            color: var(--text-muted);
        }}
        .btn-download {{
            background-color: var(--btn-bg);
            color: var(--text-primary);
            text-decoration: none;
            font-size: 14px;
            font-weight: 600;
            padding: 9px 16px;
            border-radius: 8px;
            transition: background 0.15s ease, transform 0.15s ease;
        }}
        .btn-download:active {{
            background-color: var(--btn-hover);
            transform: scale(0.97);
        }}
        .empty-state {{
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
            font-size: 15px;
        }}
        footer {{
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📸 InstaPanorama Mobile Download</h1>
            <p class="instructions">
                💡 Tap and hold images to 'Save to Photos' or tap the Download button below.
            </p>
        </header>

        <div class="action-bar">
            <a href="/download-all.zip" class="btn-zip">
                ⬇️ Download All as ZIP ({total} { 'item' if total == 1 else 'items' })
            </a>
        </div>

        <main class="gallery">
            {all_cards}
        </main>

        <footer>
            InstaPanorama Mobile Transfer • Connected via Local Wi-Fi
        </footer>
    </div>
</body>
</html>
"""
        encoded = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if send_body:
            self.wfile.write(encoded)

    def _serve_zip(self, send_body: bool = True) -> None:
        """Dynamically create in-memory zip of all served files and stream it."""
        files = self.server_instance.get_served_files()
        if not files:
            self.send_error(404, "No files available to package into ZIP")
            return

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fpath in files:
                if os.path.isfile(fpath):
                    arcname = os.path.basename(fpath)
                    zf.write(fpath, arcname=arcname)

        data = zip_buffer.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="instapanorama_slices.zip"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _serve_file(self, filename: str, as_attachment: bool = False, send_body: bool = True) -> None:
        """Serve an individual image or video file."""
        file_path = self.server_instance.resolve_file(filename)
        if not file_path or not os.path.isfile(file_path):
            self.send_error(404, f"File not found: {filename}")
            return

        try:
            file_size = os.path.getsize(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))

            if as_attachment:
                safe_name = os.path.basename(file_path)
                self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
            else:
                self.send_header("Cache-Control", "public, max-age=3600")

            self.end_headers()

            if send_body:
                with open(file_path, "rb") as f:
                    # Stream in 64KB chunks
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")


class PhoneTransferServer:
    """
    Local Wi-Fi HTTP transfer server for scanning and downloading panorama slices onto a phone.
    """

    def __init__(self, port: int = 0) -> None:
        self.port = port
        self.directory_to_serve: Optional[str] = None
        self.file_list: List[str] = []
        self.server_url: str = ""
        self.local_ip: str = ""
        self.httpd: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    @staticmethod
    def get_local_ip() -> str:
        """Detect local network LAN IP address."""
        # Method 1: Dummy UDP socket to public IP (doesn't send actual traffic)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            pass

        # Method 2: Hostname resolution
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass

        # Fallback to loopback
        return "127.0.0.1"

    def get_served_files(self) -> List[str]:
        """Return the sorted list of absolute file paths being served."""
        if self.file_list:
            existing = [f for f in self.file_list if os.path.isfile(f)]
            return sorted(existing, key=natural_sort_key)

        if self.directory_to_serve and os.path.isdir(self.directory_to_serve):
            valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}
            found = []
            for entry in os.listdir(self.directory_to_serve):
                ext = os.path.splitext(entry)[1].lower()
                if ext in valid_exts:
                    full_p = os.path.join(self.directory_to_serve, entry)
                    if os.path.isfile(full_p):
                        found.append(full_p)
            return sorted(found, key=natural_sort_key)

        return []

    def resolve_file(self, filename: str) -> Optional[str]:
        """Find the matching absolute path for a filename, preventing directory traversal."""
        clean_name = os.path.basename(filename)
        for fpath in self.get_served_files():
            if os.path.basename(fpath) == clean_name:
                return fpath
        return None

    def start(
        self,
        directory_to_serve: str,
        file_list: Optional[List[str]] = None,
        preferred_port: Optional[int] = None,
    ) -> str:
        """
        Start the transfer server on a background thread.

        Args:
            directory_to_serve: Path to folder containing image slices.
            file_list: Optional explicit list of filenames or paths to serve.
            preferred_port: Optional port number. If None or unavailable, binds ephemeral port.

        Returns:
            The full server URL (e.g. 'http://192.168.1.42:8080')
        """
        self.stop()

        self.directory_to_serve = os.path.abspath(directory_to_serve)
        if not os.path.isdir(self.directory_to_serve):
            raise NotADirectoryError(f"Directory not found: {directory_to_serve}")

        self.file_list = []
        if file_list:
            for item in file_list:
                if os.path.isabs(item):
                    p = item
                else:
                    p = os.path.join(self.directory_to_serve, item)
                if os.path.isfile(p):
                    self.file_list.append(os.path.abspath(p))
            self.file_list = sorted(self.file_list, key=natural_sort_key)

        self.local_ip = self.get_local_ip()

        # Create request handler with reference to this server
        server_self = self

        class BoundHandler(TransferRequestHandler):
            server_instance = server_self

        # Determine ports to attempt binding
        ports_to_try = []
        if preferred_port is not None and preferred_port > 0:
            ports_to_try.append(preferred_port)
        elif self.port > 0:
            ports_to_try.append(self.port)
        else:
            ports_to_try.extend([8080, 8081, 8088, 8888])

        # Port 0 (kernel auto-assigns ephemeral free port) as guaranteed fallback
        ports_to_try.append(0)

        httpd_instance = None
        for p in ports_to_try:
            try:
                httpd_instance = HTTPServer(("0.0.0.0", p), BoundHandler)
                break
            except OSError:
                continue

        if httpd_instance is None:
            raise RuntimeError("Could not bind HTTP server to any local port.")

        self.httpd = httpd_instance
        self.port = self.httpd.server_port
        self.server_url = f"http://{self.local_ip}:{self.port}"

        # Start server background daemon thread
        self.thread = threading.Thread(
            target=self.httpd.serve_forever,
            name=f"PhoneTransferServer-{self.port}",
            daemon=True,
        )
        self.thread.start()

        return self.server_url

    def generate_qr_code(self, box_size: int = 10, border: int = 2) -> Image.Image:
        """
        Generate a QR code pointing to the server URL.

        Args:
            box_size: Pixel size of each QR box/module.
            border: Border width in QR boxes.

        Returns:
            PIL Image instance of the QR code.
        """
        if not self.server_url:
            raise RuntimeError("Transfer server is not started yet. Call start() first.")

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(self.server_url)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")
        if hasattr(qr_img, "get_image"):
            return qr_img.get_image().convert("RGB")
        return qr_img.convert("RGB")

    def stop(self) -> None:
        """Cleanly stop the HTTP server and release all socket resources."""
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
            self.thread = None
