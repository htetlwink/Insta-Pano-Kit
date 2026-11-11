"""
Web Application for InstaPanoramaSplitter on Render.com.
Reuses the core image and video engines to deliver a full-featured browser experience.
"""

import os
import io
import zipfile
import tempfile
import base64
from typing import List
from flask import Flask, request, render_template_string, send_file, jsonify
from PIL import Image, ImageOps

from core.image_engine import SlicingConfig, slice_panorama, save_slices, generate_upload_guide, slice_grid
from core.video_engine import VideoPanConfig, generate_panning_video, is_ffmpeg_available

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB max upload

# Modern, mobile-responsive HTML/CSS template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📸 InstaPanoramaSplitter — Cloud Web Suite</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #0b0f19; color: #f3f4f6; }
        .card { background-color: #131927; border: 1px solid #1f293d; }
    </style>
</head>
<body class="min-h-screen py-8 px-4 font-sans">
    <div class="max-w-4xl mx-auto space-y-6">
        
        <!-- Header -->
        <header class="text-center space-y-2">
            <h1 class="text-3xl sm:text-4xl font-extrabold tracking-tight text-white flex items-center justify-center gap-3">
                📸 InstaPanoramaSplitter
            </h1>
            <p class="text-sm sm:text-base text-gray-400">
                Split panoramas into seamless Instagram carousels, profile puzzle grids, and Reels panning videos.
            </p>
        </header>

        <!-- Main Form Card -->
        <div class="card rounded-2xl p-6 sm:p-8 shadow-xl">
            <form id="sliceForm" class="space-y-6" enctype="multipart/form-data">
                
                <!-- Upload Area -->
                <div>
                    <label class="block text-sm font-semibold text-gray-300 mb-2">1. Select Panorama Photo</label>
                    <div class="border-2 border-dashed border-gray-700 hover:border-blue-500 rounded-xl p-6 text-center cursor-pointer transition bg-gray-900/50" onclick="document.getElementById('fileInput').click()">
                        <input type="file" id="fileInput" name="image" accept="image/*" class="hidden" onchange="handleFileSelect(event)" required>
                        <div id="uploadPrompt" class="space-y-1">
                            <span class="text-3xl">🌄</span>
                            <p class="text-sm font-medium text-gray-300">Tap or drag image here</p>
                            <p class="text-xs text-gray-500">Supports JPG, PNG, WEBP up to 60MB</p>
                        </div>
                        <div id="fileInfo" class="hidden text-sm font-semibold text-blue-400"></div>
                    </div>
                </div>

                <!-- Settings Grid -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    
                    <!-- Number of Slices -->
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Number of Slices</label>
                        <select name="slices" id="slices" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500">
                            <option value="2">2 Slices</option>
                            <option value="3" selected>3 Slices (Most Popular)</option>
                            <option value="4">4 Slices</option>
                            <option value="5">5 Slices</option>
                            <option value="6">6 Slices</option>
                            <option value="7">7 Slices</option>
                        </select>
                    </div>

                    <!-- Aspect Ratio -->
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Instagram Aspect Ratio</label>
                        <select name="aspect" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500">
                            <option value="Portrait (4:5)" selected>Portrait 4:5 (1080×1350 px — Feed Optimal)</option>
                            <option value="Square (1:1)">Square 1:1 (1080×1080 px — Classic)</option>
                            <option value="Story (9:16)">Story 9:16 (1080×1920 px — Reels / Stories)</option>
                        </select>
                    </div>

                    <!-- Framing Mode -->
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Framing & Fill Strategy</label>
                        <select name="fit_mode" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500">
                            <option value="Standard (Fit & Crop)" selected>Standard 1080px (Fit & Center Crop)</option>
                            <option value="Proportional (Full Width)">Proportional Full Width (No Crop)</option>
                            <option value="Blurred Background Fill">Blurred Background Fill (No Cropping)</option>
                            <option value="Solid Gallery Border">Gallery Border (White Frame)</option>
                        </select>
                    </div>

                    <!-- Creative Swipe Cue -->
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Engagement Cue</label>
                        <select name="indicator" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500">
                            <option value="None" selected>None</option>
                            <option value="Seam Arrow">Seam Arrow ➔ (Spans Slices)</option>
                            <option value="Swipe Badge (Slide 1)">"Swipe Left 👉" Badge (Slide 1)</option>
                            <option value="Dot Indicators">Pagination Dots</option>
                        </select>
                    </div>
                </div>

                <!-- Title & Watermark Inputs -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Slide 1 Cover Title (Optional)</label>
                        <input type="text" name="title" placeholder="e.g. Alpine Sunset" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Photographer Credit / Handle</label>
                        <input type="text" name="watermark" placeholder="e.g. @username" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    </div>
                </div>

                <!-- Toggles -->
                <div class="flex flex-wrap gap-4 text-xs font-medium text-gray-300">
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" name="srgb" checked class="rounded bg-gray-800 border-gray-700 text-blue-500">
                        sRGB Color Conversion (Fix desaturation)
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" name="sharpen" checked class="rounded bg-gray-800 border-gray-700 text-blue-500">
                        Smart 1080px Sharpening
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" name="guide" checked class="rounded bg-gray-800 border-gray-700 text-blue-500">
                        Numbered Upload Guide
                    </label>
                </div>

                <!-- Submit Button -->
                <button type="button" onclick="processSlicing()" id="submitBtn" class="w-full py-3.5 px-6 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl shadow-lg transition duration-150 flex items-center justify-center gap-2">
                    <span>✂️ Slice Panorama & Download ZIP</span>
                </button>
            </form>
        </div>

        <!-- Result / Preview Section -->
        <div id="resultsCard" class="hidden card rounded-2xl p-6 sm:p-8 space-y-6">
            <div class="flex items-center justify-between">
                <h2 class="text-xl font-bold text-white flex items-center gap-2">
                    <span>✅</span> Generated Slices
                </h2>
                <a id="downloadZipBtn" href="#" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm rounded-lg shadow transition">
                    ⬇️ Download All (.zip)
                </a>
            </div>

            <!-- Carousel Gallery Container -->
            <div id="galleryGrid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4"></div>
        </div>
    </div>

    <script>
        let currentZipUrl = null;

        function handleFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                document.getElementById('uploadPrompt').classList.add('hidden');
                const info = document.getElementById('fileInfo');
                info.textContent = `Selected: ${file.name} (${(file.size / (1024*1024)).toFixed(2)} MB)`;
                info.classList.remove('hidden');
            }
        }

        async function processSlicing() {
            const form = document.getElementById('sliceForm');
            const fileInput = document.getElementById('fileInput');
            if (!fileInput.files.length) {
                alert('Please choose a panoramic image first.');
                return;
            }

            const btn = document.getElementById('submitBtn');
            btn.disabled = true;
            btn.innerHTML = `<svg class="animate-spin h-5 w-5 mr-3 text-white" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Processing slices...`;

            const formData = new FormData(form);

            try {
                const response = await fetch('/api/slice', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Server error');
                }

                const data = await response.json();
                displayResults(data);
            } catch (err) {
                alert('Error processing image: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = `<span>✂️ Slice Panorama & Download ZIP</span>`;
            }
        }

        function displayResults(data) {
            const resultsCard = document.getElementById('resultsCard');
            const gallery = document.getElementById('galleryGrid');
            const downloadZipBtn = document.getElementById('downloadZipBtn');

            gallery.innerHTML = '';
            resultsCard.classList.remove('hidden');

            downloadZipBtn.href = data.zip_url;

            data.slices.forEach((slice, idx) => {
                const card = document.createElement('div');
                card.className = 'card rounded-xl p-2 space-y-2 border border-gray-700/60';
                card.innerHTML = `
                    <div class="relative overflow-hidden rounded-lg bg-black">
                        <img src="${slice.data_url}" class="w-full h-auto object-cover" loading="lazy">
                        <span class="absolute top-2 left-2 bg-blue-600/90 text-white text-xs font-bold px-2 py-0.5 rounded shadow">
                            #${idx + 1}
                        </span>
                    </div>
                    <div class="flex items-center justify-between text-xs px-1">
                        <span class="text-gray-400 font-mono">${slice.filename}</span>
                        <a href="${slice.data_url}" download="${slice.filename}" class="text-blue-400 hover:text-blue-300 font-semibold">Save</a>
                    </div>
                `;
                gallery.appendChild(card);
            });

            resultsCard.scrollIntoView({ behavior: 'smooth' });
        }
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/slice", methods=["POST"])
def api_slice():
    try:
        if "image" not in request.files:
            return jsonify({"error": "No image file uploaded"}), 400

        file = request.files["image"]
        if not file.filename:
            return jsonify({"error": "Empty filename"}), 400

        # Load image with orientation correction
        raw_img = Image.open(file.stream)
        img = ImageOps.exif_transpose(raw_img)

        # Parse form config
        num_slices = int(request.form.get("slices", 3))
        aspect_ratio = request.form.get("aspect", "Portrait (4:5)")
        fit_mode = request.form.get("fit_mode", "Standard (Fit & Crop)")
        indicator = request.form.get("indicator", "None")
        title_text = request.form.get("title", "").strip() or None
        watermark_text = request.form.get("watermark", "").strip() or None
        apply_srgb = "srgb" in request.form
        smart_sharpen = "sharpen" in request.form
        generate_guide = "guide" in request.form

        config = SlicingConfig(
            num_slices=num_slices,
            aspect_ratio=aspect_ratio,
            fit_mode=fit_mode,
            swipe_indicator=indicator,
            title_text=title_text,
            watermark_text=watermark_text,
            apply_srgb=apply_srgb,
            smart_sharpen=smart_sharpen,
            format="JPEG",
            jpeg_quality=95,
        )

        slices = slice_panorama(img, config)

        # Prepare ZIP file in memory
        zip_buffer = io.BytesIO()
        slice_data = []

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for i, slice_img in enumerate(slices):
                filename = f"panorama_slice_{i + 1}.jpg"

                # Save slice to byte buffer
                buf = io.BytesIO()
                slice_img.convert("RGB").save(buf, format="JPEG", quality=95, optimize=True)
                buf.seek(0)
                img_bytes = buf.getvalue()

                # Add to zip
                zip_file.writestr(filename, img_bytes)

                # Base64 for web display
                b64 = base64.b64encode(img_bytes).decode("ascii")
                slice_data.append({
                    "filename": filename,
                    "data_url": f"data:image/jpeg;base64,{b64}",
                })

            # Optional Upload Guide
            if generate_guide:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_guide:
                    tmp_guide_path = tmp_guide.name

                try:
                    generate_upload_guide(slices, tmp_guide_path, title=f"Upload Guide — {file.filename}")
                    with open(tmp_guide_path, "rb") as f:
                        guide_bytes = f.read()
                    zip_file.writestr("upload_guide.jpg", guide_bytes)
                    b64_guide = base64.b64encode(guide_bytes).decode("ascii")
                    slice_data.append({
                        "filename": "upload_guide.jpg",
                        "data_url": f"data:image/jpeg;base64,{b64_guide}",
                    })
                finally:
                    if os.path.exists(tmp_guide_path):
                        os.remove(tmp_guide_path)

        zip_buffer.seek(0)

        # Cache zip in a temporary location or serve directly
        temp_zip = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        temp_zip.write(zip_buffer.getvalue())
        temp_zip.close()

        zip_id = os.path.basename(temp_zip.name)

        return jsonify({
            "slices": slice_data,
            "zip_url": f"/download-zip/{zip_id}",
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download-zip/<zip_id>")
def download_zip(zip_id):
    # Sanitize filename
    safe_name = os.path.basename(zip_id)
    path = os.path.join(tempfile.gettempdir(), safe_name)
    if os.path.exists(path) and path.endswith(".zip"):
        return send_file(
            path,
            as_attachment=True,
            download_name="instagram_carousel_slices.zip",
            mimetype="application/zip",
        )
    return "Archive not found or expired.", 404


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "ffmpeg": is_ffmpeg_available(),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
