"""
Web Application for InstaPanoramaSplitter on Render.com.
Engineered for low-memory environments (Render Free Tier 512MB RAM ceiling).
Includes interactive client-side preview with real-time Pan X/Y crop sliders.
"""

import os
import gc
import uuid
import time
import shutil
import tempfile
from typing import List, Dict, Any
from flask import Flask, request, render_template_string, send_file, jsonify
from PIL import Image, ImageOps

from core.image_engine import SlicingConfig, slice_panorama, save_slices, generate_upload_guide
from core.video_engine import is_ffmpeg_available

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # 40 MB max upload

# Base directory for temporary session exports
TEMP_BASE = os.path.join(tempfile.gettempdir(), "instapano_sessions")
os.makedirs(TEMP_BASE, exist_ok=True)


def cleanup_old_sessions(max_age_seconds: int = 1800) -> None:
    """Remove session folders older than 30 minutes to free disk space."""
    now = time.time()
    try:
        for folder in os.listdir(TEMP_BASE):
            folder_path = os.path.join(TEMP_BASE, folder)
            if os.path.isdir(folder_path):
                if now - os.path.getmtime(folder_path) > max_age_seconds:
                    shutil.rmtree(folder_path, ignore_errors=True)
    except Exception:
        pass


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📸 InstaPanoramaSplitter — Web Creator Suite</title>
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
                Split panoramas into seamless Instagram carousels with live interactive crop framing.
            </p>
        </header>

        <!-- Main Form Card -->
        <div class="card rounded-2xl p-6 sm:p-8 shadow-xl space-y-6">
            <form id="sliceForm" class="space-y-6">
                
                <!-- 1. Upload Area -->
                <div>
                    <label class="block text-sm font-semibold text-gray-300 mb-2">1. Choose Panorama Photo</label>
                    <div id="dropZone" class="border-2 border-dashed border-gray-700 hover:border-blue-500 rounded-xl p-6 text-center cursor-pointer transition bg-gray-900/50" onclick="document.getElementById('fileInput').click()">
                        <input type="file" id="fileInput" name="image" accept="image/*" class="hidden" onchange="handleFileSelect(event)" required>
                        <div id="uploadPrompt" class="space-y-1">
                            <span class="text-4xl">🌄</span>
                            <p class="text-sm font-medium text-gray-300">Click or Drag & Drop Panorama Here</p>
                            <p class="text-xs text-gray-500">Supports JPG, PNG, WEBP</p>
                        </div>
                        <div id="fileInfo" class="hidden text-sm font-semibold text-blue-400"></div>
                    </div>
                </div>

                <!-- 2. Live Interactive Canvas Preview Card -->
                <div id="previewCard" class="hidden space-y-4">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                            <span>🎯</span> Live Slicing & Pan Framing Preview
                        </span>
                        <span id="ratioBadge" class="text-xs font-mono text-blue-400 bg-blue-950/60 px-2.5 py-1 rounded-md border border-blue-800/40"></span>
                    </div>

                    <!-- Canvas Container -->
                    <div class="relative bg-black rounded-xl overflow-hidden border border-gray-800 flex items-center justify-center p-2 min-h-[160px]">
                        <canvas id="previewCanvas" class="max-w-full max-h-[320px] rounded shadow-lg"></canvas>
                    </div>

                    <!-- Interactive Pan Sliders (X & Y) -->
                    <div id="panControls" class="bg-gray-900/70 p-4 rounded-xl border border-gray-800 space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="text-xs font-bold text-gray-300">Crop Position Framing</span>
                            <button type="button" onclick="resetPan()" class="text-xs text-blue-400 hover:text-blue-300 font-semibold bg-gray-800 px-2 py-0.5 rounded">
                                Reset Center (0, 0)
                            </button>
                        </div>
                        
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div>
                                <div class="flex justify-between text-xs text-gray-400 mb-1">
                                    <span>Horizontal Pan (X)</span>
                                    <span id="panXVal" class="font-mono">0%</span>
                                </div>
                                <input type="range" id="panX" name="pan_x" min="-1" max="1" step="0.02" value="0" oninput="updatePanPreview()" class="w-full accent-blue-500 cursor-pointer">
                            </div>
                            <div>
                                <div class="flex justify-between text-xs text-gray-400 mb-1">
                                    <span>Vertical Pan (Y)</span>
                                    <span id="panYVal" class="font-mono">0%</span>
                                </div>
                                <input type="range" id="panY" name="pan_y" min="-1" max="1" step="0.02" value="0" oninput="updatePanPreview()" class="w-full accent-blue-500 cursor-pointer">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 3. Slicing Settings -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <!-- Slices -->
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Number of Carousel Slices</label>
                        <select name="slices" id="sliceCount" onchange="updatePanPreview()" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500">
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
                        <select name="aspect" id="aspectRatio" onchange="updatePanPreview()" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500">
                            <option value="Portrait (4:5)" selected>Portrait 4:5 (1080×1350 px — Feed Optimal)</option>
                            <option value="Square (1:1)">Square 1:1 (1080×1080 px — Classic)</option>
                            <option value="Story (9:16)">Story 9:16 (1080×1920 px — Reels / Stories)</option>
                        </select>
                    </div>

                    <!-- Framing Mode -->
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Framing & Fill Strategy</label>
                        <select name="fit_mode" id="fitMode" onchange="updatePanPreview()" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500">
                            <option value="Standard (Fit & Crop)" selected>Standard 1080px (Fit & Center Crop)</option>
                            <option value="Proportional (Full Width)">Proportional Full Width (No Crop)</option>
                            <option value="Blurred Background Fill">Blurred Background Fill (No Cropping)</option>
                            <option value="Solid Gallery Border">Gallery Border (White Frame)</option>
                        </select>
                    </div>

                    <!-- Engagement Cue -->
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Seamless Engagement Cue</label>
                        <select name="indicator" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500">
                            <option value="None" selected>None</option>
                            <option value="Seam Arrow">Seam Arrow ➔ (Spans Slices)</option>
                            <option value="Swipe Badge (Slide 1)">"Swipe Left 👉" Badge (Slide 1)</option>
                            <option value="Dot Indicators">Pagination Dots</option>
                        </select>
                    </div>
                </div>

                <!-- Text Overlays -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Slide 1 Title (Optional)</label>
                        <input type="text" name="title" placeholder="e.g. Alpine Sunset" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Photographer Credit</label>
                        <input type="text" name="watermark" placeholder="e.g. @your_account" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
                    </div>
                </div>

                <!-- Instagram Quality Toggles -->
                <div class="flex flex-wrap gap-4 text-xs font-medium text-gray-300">
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" name="srgb" checked class="rounded bg-gray-800 border-gray-700 text-blue-500">
                        sRGB Color Conversion (Fix washed out colors)
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
                <button type="button" onclick="submitSlicing()" id="submitBtn" class="w-full py-3.5 px-6 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl shadow-lg transition duration-150 flex items-center justify-center gap-2">
                    <span>✂️ Slice Panorama & Generate Carousel</span>
                </button>
            </form>
        </div>

        <!-- Result / Gallery Section -->
        <div id="resultsCard" class="hidden card rounded-2xl p-6 sm:p-8 space-y-6">
            <div class="flex items-center justify-between">
                <h2 class="text-xl font-bold text-white flex items-center gap-2">
                    <span>✅</span> Generated Carousel Slices
                </h2>
                <a id="downloadZipBtn" href="#" class="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm rounded-xl shadow transition flex items-center gap-2">
                    <span>⬇️</span> Download All as ZIP
                </a>
            </div>

            <!-- Carousel Gallery Container -->
            <div id="galleryGrid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4"></div>
        </div>
    </div>

    <script>
        let loadedImage = null;

        function handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;

            document.getElementById('uploadPrompt').classList.add('hidden');
            const info = document.getElementById('fileInfo');
            info.textContent = `📄 ${file.name} (${(file.size / (1024*1024)).toFixed(2)} MB)`;
            info.classList.remove('hidden');

            // Load into memory client-side using FileReader for instant zero-server preview
            const reader = new FileReader();
            reader.onload = function(e) {
                loadedImage = new Image();
                loadedImage.onload = function() {
                    document.getElementById('previewCard').classList.remove('hidden');
                    updatePanPreview();
                };
                loadedImage.src = e.target.result;
            };
            reader.readAsDataURL(file);
        }

        function resetPan() {
            document.getElementById('panX').value = 0;
            document.getElementById('panY').value = 0;
            updatePanPreview();
        }

        function updatePanPreview() {
            if (!loadedImage) return;

            const canvas = document.getElementById('previewCanvas');
            const ctx = canvas.getContext('2d');

            const nSlices = parseInt(document.getElementById('sliceCount').value) || 3;
            const aspectVal = document.getElementById('aspectRatio').value;
            const fitMode = document.getElementById('fitMode').value;
            const panX = parseFloat(document.getElementById('panX').value) || 0;
            const panY = parseFloat(document.getElementById('panY').value) || 0;

            document.getElementById('panXVal').textContent = `${Math.round(panX * 100)}%`;
            document.getElementById('panYVal').textContent = `${Math.round(panY * 100)}%`;

            // Aspect targets
            let targetW = 1080, targetH = 1350;
            if (aspectVal.includes('1:1')) { targetW = 1080; targetH = 1080; }
            else if (aspectVal.includes('9:16')) { targetW = 1080; targetH = 1920; }

            const totalTargetW = targetW * nSlices;
            const targetRatio = totalTargetW / targetH;
            const origW = loadedImage.naturalWidth;
            const origH = loadedImage.naturalHeight;
            const origRatio = origW / origH;

            document.getElementById('ratioBadge').textContent = 
                `${origW}×${origH} px (${origRatio.toFixed(2)}:1) ➔ ${nSlices} Slices @ ${targetW}×${targetH}`;

            // Scale canvas to fit max width
            const maxDisplayW = Math.min(760, window.innerWidth - 60);
            const scale = maxDisplayW / origW;
            const cw = Math.max(20, Math.round(origW * scale));
            const ch = Math.max(20, Math.round(origH * scale));

            canvas.width = cw;
            canvas.height = ch;

            // Draw full base photo
            ctx.drawImage(loadedImage, 0, 0, cw, ch);

            // Calculate active crop rectangle
            let activeX0 = 0, activeX1 = cw, activeY0 = 0, activeY1 = ch;

            if (fitMode.includes('Standard')) {
                document.getElementById('panControls').classList.remove('opacity-50', 'pointer-events-none');
                if (origRatio >= targetRatio) {
                    // Wider than carousel: crop left/right
                    const activeW = ch * targetRatio;
                    const excessW = cw - activeW;
                    const offsetX = excessW * (panX + 1) / 2;
                    activeX0 = Math.max(0, Math.min(excessW, offsetX));
                    activeX1 = activeX0 + activeW;

                    // Darken cropped side margins
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.65)';
                    ctx.fillRect(0, 0, activeX0, ch);
                    ctx.fillRect(activeX1, 0, cw - activeX1, ch);
                } else {
                    // Taller than carousel: crop top/bottom
                    const activeH = cw / targetRatio;
                    const excessH = ch - activeH;
                    const offsetY = excessH * (panY + 1) / 2;
                    activeY0 = Math.max(0, Math.min(excessH, offsetY));
                    activeY1 = activeY0 + activeH;

                    // Darken cropped top/bottom margins
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.65)';
                    ctx.fillRect(0, 0, cw, activeY0);
                    ctx.fillRect(0, activeY1, cw, ch - activeY1);
                }
            } else {
                document.getElementById('panControls').classList.add('opacity-50', 'pointer-events-none');
            }

            const activeSpanW = activeX1 - activeX0;
            const sliceSpanW = activeSpanW / nSlices;

            // Draw divider lines and numbered slice badges
            for (let i = 0; i < nSlices; i++) {
                const x0 = activeX0 + i * sliceSpanW;
                const x1 = activeX0 + (i + 1) * sliceSpanW;

                // Vertical separator
                if (i > 0) {
                    ctx.strokeStyle = '#00ebff';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.moveTo(x0, activeY0);
                    ctx.lineTo(x0, activeY1);
                    ctx.stroke();
                }

                // Number badge
                const cx = (x0 + x1) / 2;
                const cy = activeY0 + 16;
                if (cy + 12 < activeY1) {
                    ctx.fillStyle = '#2563eb';
                    ctx.beginPath();
                    ctx.arc(cx, cy, 11, 0, 2 * Math.PI);
                    ctx.fill();
                    ctx.strokeStyle = '#ffffff';
                    ctx.lineWidth = 1.5;
                    ctx.stroke();

                    ctx.fillStyle = '#ffffff';
                    ctx.font = 'bold 11px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText((i + 1).toString(), cx, cy);
                }
            }

            // Outline of active frame
            ctx.strokeStyle = '#00ebff';
            ctx.lineWidth = 2.5;
            ctx.strokeRect(activeX0, activeY0, activeSpanW, activeY1 - activeY0);
        }

        async function submitSlicing() {
            const form = document.getElementById('sliceForm');
            const fileInput = document.getElementById('fileInput');
            if (!fileInput.files.length) {
                alert('Please choose a panoramic image first.');
                return;
            }

            const btn = document.getElementById('submitBtn');
            btn.disabled = true;
            btn.innerHTML = `<span class="animate-spin inline-block mr-2">⏳</span> Processing on Cloud Server...`;

            const formData = new FormData(form);

            try {
                const response = await fetch('/api/slice', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Server error occurred');
                }

                const data = await response.json();
                displayResults(data);
            } catch (err) {
                alert('Slicing failed: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = `<span>✂️ Slice Panorama & Generate Carousel</span>`;
            }
        }

        function displayResults(data) {
            const resultsCard = document.getElementById('resultsCard');
            const gallery = document.getElementById('galleryGrid');
            const downloadZipBtn = document.getElementById('downloadZipBtn');

            gallery.innerHTML = '';
            resultsCard.classList.remove('hidden');
            downloadZipBtn.href = data.zip_url;

            data.slices.forEach((slice) => {
                const card = document.createElement('div');
                card.className = 'card rounded-xl p-2 space-y-2 border border-gray-700/60';
                card.innerHTML = `
                    <div class="relative overflow-hidden rounded-lg bg-black">
                        <img src="${slice.url}" class="w-full h-auto object-cover" loading="lazy">
                        <span class="absolute top-2 left-2 bg-blue-600 text-white text-xs font-bold px-2 py-0.5 rounded shadow">
                            #${slice.index}
                        </span>
                    </div>
                    <div class="flex items-center justify-between text-xs px-1">
                        <span class="text-gray-400 font-mono truncate max-w-[110px]">${slice.filename}</span>
                        <a href="${slice.url}" download="${slice.filename}" class="text-blue-400 hover:text-blue-300 font-semibold">Save</a>
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
    """
    Streamlined, memory-efficient slicing endpoint.
    Processes image and writes slices directly to disk, avoiding RAM exhaustion.
    """
    cleanup_old_sessions()

    session_id = uuid.uuid4().hex
    session_dir = os.path.join(TEMP_BASE, session_id)
    os.makedirs(session_dir, exist_ok=True)

    temp_input_path = os.path.join(session_dir, "input_source.img")

    try:
        if "image" not in request.files:
            return jsonify({"error": "No image file provided"}), 400

        file = request.files["image"]
        if not file.filename:
            return jsonify({"error": "Empty filename"}), 400

        # Stream directly to disk to prevent loading raw bytes in RAM
        file.save(temp_input_path)

        # Load with orientation normalization
        raw_img = Image.open(temp_input_path)
        img = ImageOps.exif_transpose(raw_img)

        # Parse form config
        num_slices = int(request.form.get("slices", 3))
        aspect_ratio = request.form.get("aspect", "Portrait (4:5)")
        fit_mode = request.form.get("fit_mode", "Standard (Fit & Crop)")
        indicator = request.form.get("indicator", "None")
        pan_x = float(request.form.get("pan_x", 0.0))
        pan_y = float(request.form.get("pan_y", 0.0))
        title_text = request.form.get("title", "").strip() or None
        watermark_text = request.form.get("watermark", "").strip() or None
        apply_srgb = "srgb" in request.form
        smart_sharpen = "sharpen" in request.form
        generate_guide = "guide" in request.form

        config = SlicingConfig(
            num_slices=num_slices,
            aspect_ratio=aspect_ratio,
            fit_mode=fit_mode,
            pan_offset_x=pan_x,
            pan_offset_y=pan_y,
            swipe_indicator=indicator,
            title_text=title_text,
            watermark_text=watermark_text,
            apply_srgb=apply_srgb,
            smart_sharpen=smart_sharpen,
            format="JPEG",
            jpeg_quality=95,
        )

        # Slice panorama
        slices = slice_panorama(img, config)

        # Immediately free original image buffers
        del raw_img
        del img
        gc.collect()

        # Save slices directly to disk in session folder
        saved_paths = save_slices(
            slices=slices,
            export_dir=session_dir,
            prefix="panorama_slice",
            ext="jpg",
            jpeg_quality=95,
        )

        # Build response slice references
        slice_info: List[Dict[str, Any]] = []
        for idx, fpath in enumerate(saved_paths):
            fname = os.path.basename(fpath)
            slice_info.append({
                "index": idx + 1,
                "filename": fname,
                "url": f"/api/session/{session_id}/slice/{idx + 1}",
            })

        # Generate optional upload guide
        if generate_guide:
            guide_path = os.path.join(session_dir, "upload_guide.jpg")
            generate_upload_guide(slices, guide_path, title="Instagram Carousel Upload Guide")
            saved_paths.append(guide_path)
            slice_info.append({
                "index": "Guide",
                "filename": "upload_guide.jpg",
                "url": f"/api/session/{session_id}/slice/guide",
            })

        # Free slice objects from memory
        del slices
        gc.collect()

        # Create zip directly on disk
        import zipfile
        zip_path = os.path.join(session_dir, "instagram_carousel.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in saved_paths:
                zf.write(fpath, arcname=os.path.basename(fpath))

        # Remove temporary raw input to save disk space
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)

        return jsonify({
            "session_id": session_id,
            "slices": slice_info,
            "zip_url": f"/api/session/{session_id}/download-zip",
        })

    except Exception as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/<session_id>/slice/<slice_id>")
def get_slice(session_id, slice_id):
    """Stream individual slice from disk without holding it in memory."""
    safe_sid = os.path.basename(session_id)
    session_dir = os.path.join(TEMP_BASE, safe_sid)

    if slice_id == "guide":
        target_file = os.path.join(session_dir, "upload_guide.jpg")
    else:
        target_file = os.path.join(session_dir, f"panorama_slice_{slice_id}.jpg")

    if os.path.exists(target_file):
        return send_file(target_file, mimetype="image/jpeg")
    return "Slice not found", 404


@app.route("/api/session/<session_id>/download-zip")
def get_zip(session_id):
    """Stream carousel zip file from disk."""
    safe_sid = os.path.basename(session_id)
    zip_path = os.path.join(TEMP_BASE, safe_sid, "instagram_carousel.zip")

    if os.path.exists(zip_path):
        return send_file(
            zip_path,
            as_attachment=True,
            download_name="instagram_carousel_slices.zip",
            mimetype="application/zip",
        )
    return "Archive not found", 404


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "ffmpeg": is_ffmpeg_available(),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
