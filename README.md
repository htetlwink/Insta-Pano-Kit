# 📸 InstaPanoramaSplitter — Instagram Panorama & Creator Suite

[![Live Web App](https://img.shields.io/badge/🌐_Live_Web_App-instapano.onrender.com-00c853?style=for-the-badge&logo=render&logoColor=white)](https://instapano.onrender.com/)
[![Tests](https://img.shields.io/badge/Tests-52%20Passed-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://github.com/htetlwink/Insta-Pano-Kit)
[![Python](https://img.shields.io/badge/Python-3.8+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

> **Live Web Application:** [**https://instapano.onrender.com/**](https://instapano.onrender.com/)  
> Seamless, 100% private, client-side panoramic carousel splitter. No installation required.

---

## 🌟 Overview

**InstaPanoramaSplitter** (`Insta-Pano-Kit`) is an all-in-one panoramic creator suite available both as an **instant, zero-install web application** and a **feature-packed desktop application** (built with CustomTkinter & FFmpeg).

It turns wide panoramic landscapes, cityscapes, architecture, and adventure photography into high-engagement **seamless Instagram swipe carousels**, **Ken Burns animated Reels videos**, and **cross-platform social packs**.

```
  ┌──────────────────────────────────────────────────────────────┐
  │                 Wide Panoramic Photography                   │
  └──────────────────────────────┬───────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
 📱 Instagram Carousel    🎬 Reels Video Pan     📦 Omni-Channel Pack
 (4:5 / 1:1 / 9:16)       (Ken Burns + Audio)    (Feed + Stories + PDF + Header)
```

---

## 🌐 Try It in Your Browser (No Install Needed)

Launch the web version immediately from any device:  
👉 [**https://instapano.onrender.com/**](https://instapano.onrender.com/)

* **100% Client-Side & Private**: Your photos never leave your device. All slicing, color adjustments, and ZIP packaging happen locally inside your browser via HTML5 Canvas and JSZip.
* **Apple iPhone HEIC & ProRAW DNG Support**: Seamless drag-and-drop ingestion with client-side conversion.
* **Instantaneous**: Zero cold-start waiting times, hosted on high-speed global CDN.

---

## ✨ Key Features

### 1. ✂️ Seamless Instagram Carousel Slicer
- **Optimized Aspect Ratios**:
  - **Portrait (4:5)**: Targets $1080 \times 1350\text{ px}$ per slide (maximizes vertical mobile screen real estate for peak engagement).
  - **Square (1:1)**: Targets $1080 \times 1080\text{ px}$ per slide (classic Instagram square carousel).
  - **Story / Reels (9:16)**: Targets $1080 \times 1920\text{ px}$ per slide (tap-through panoramic stories with progress indicators).
- **Interactive Framing & Pan Offsets**:
  - Sliders allowing $-100\%$ to $+100\%$ offset adjustment along horizontal and vertical axes to keep horizons or subjects perfectly framed.
- **Multiple Framing Modes**:
  - **Standard 1080px (Fit & Crop)**: Auto-scales and crops according to your Pan X/Y offsets.
  - **Proportional (Full Width • No Crop)**: Keeps 100% of the panorama's width divided equally.
  - **Blurred Background Fill**: Places the panorama on an ambient Gaussian-blurred backdrop of itself.
  - **Solid Gallery Border**: Fits the panorama within clean minimalist white or dark borders.

### 2. 📐 Auto-Horizon Leveling & Tilt Correction
- **Automatic Horizon Leveling**: Computes gradient projection variance across angles to automatically detect and straighten tilted horizons within $\pm 10^\circ$.
- **Maximum Inscribed Corner Crop**: Uses trigonometric inscribed scaling to crop out black boundary triangles after rotation.
- **Manual Straightening Slider**: Real-time slider from $-10.0^\circ$ to $+10.0^\circ$ with live preview updates.

### 3. 🧠 Smart Seam Placement & Creative Formats
- **Smart Seam Placement**: Gradient energy valley detection places seams along low-contrast regions to avoid cutting directly through people, faces, or architectural focal points.
- **Vertical Waterfall Split**: Slices ultra-tall vertical panoramas top-to-bottom into stacked 4:5 or 9:16 slides.
- **360° Infinite Seamless Loop**: Crossfades and blends left and right boundaries so Slide $N$ flows cyclically back into Slide 1.
- **Before & After Seam Transition**: Renders an aesthetic `"BEFORE ➔"` prompt badge on Slide 1 and `"✨ AFTER"` on Slide 2+ for high-engagement editing showcases.

### 4. 📱 Interactive Mobile Carousel Simulator
- Inspect the swipe flow with an interactive Instagram phone mockup directly inside the desktop app and web app.
- Swipe left/right or hit **"▶ Auto Swipe"** to verify seam continuity before exporting.

### 5. 🎯 Seamless Engagement Overlays
- **Seam Arrow Indicator (`➔`)**: Draws an arrow cut in half across slide seams that joins together as viewers swipe.
- **Swipe Left Badge**: Aesthetic `"SWIPE ➔"` prompt pill on Slide 1.
- **Numbered Upload Guide Contact Sheet**: Automatically generates a visual `upload_guide.jpg` contact sheet (`[1] ➔ [2] ➔ [3]`) so you never post slides out of order.

### 6. 🎨 Instagram Color & Sharpness Optimizer
- **sRGB Color Space Conversion**: Embedded LittleCMS (`ImageCms`) sRGB transformation to prevent desaturated or washed-out colors when uploading to Instagram on iOS and Android.
- **Smart 1080px Sharpening**: Mobile-tuned unsharp mask filter that restores crisp micro-textures lost during downsampling.

### 7. 🎬 Animated Panning Video Generator (Reels & Stories)
- Creates smooth **Ken Burns panning MP4 videos** for Instagram Reels, TikTok, and YouTube Shorts.
- Configurable ratio (9:16, 4:5, 1:1), duration (4s to 20s), and framerate (30 or 60 FPS).
- **Cinematic Speed Ramping**: *Ease In & Out*, *Linear*, and *Slow-mo Climax*.
- **Ambient Soundscapes**: Synthesizes soothing C Major 9 harmonic chord drones with stereo LFO breathing (zero external audio libraries needed).

### 8. 📦 1-Click Omni-Channel Social Export Pack
- With one click, exports a structured distribution archive containing:
  - `1_instagram_feed/`: 4:5 or 1:1 slices + `upload_guide.jpg`
  - `2_instagram_stories/`: 9:16 vertical tap-through sequence with story progress bars
  - `3_twitter_threads_header/`: 3:1 landscape header banner ($1500 \times 500\text{ px}$)
  - `linkedin_lookbook.pdf`: Multi-page swipeable PDF portfolio lookbook
  - `reels_video.mp4`: Animated Ken Burns panning video with ambient audio

### 9. 📲 Scan-to-Phone Instant QR Transfer
- No cables, AirDrop, or cloud drive syncing required.
- Spins up a secure, lightweight local Wi-Fi server and displays a **QR code**.
- Scan with your phone's camera to download all slides directly to your camera roll.

### 10. 🔲 Instagram Profile Grid Splitter
- Slice photos into **3×1 Banners**, **3×2**, or **3×3 Giant Grids** (9 tiles forming one massive image on your profile).
- Numbered in reverse upload order (`grid_09_upload_1st.jpg` to `grid_01_upload_last.jpg`).

---

## 💻 Desktop Application Setup

For offline desktop usage with the CustomTkinter GUI:

### 1. Prerequisites
- Python 3.8+
- FFmpeg (for video pan generation)

### 2. Install Dependencies
```bash
pip install customtkinter pillow qrcode
```

### 3. Launch Desktop App
```bash
python3 app.py
```

---

## 🧪 Automated Test Suite

Run the full test suite covering image processing, video panning, and export engines:

```bash
python3 -m unittest discover tests
```

```text
Ran 52 tests in ~20s
OK (100% passing)
```

---

## 📁 Repository Structure

```
Insta-Pano-Kit/
├── app.py                          # Main CustomTkinter desktop application
├── index.html                      # Standalone client-side web application
├── web_app.py                      # Flask web application for Render / cloud deployment
├── render.yaml                     # Render Blueprint specification (Static Site + Web Service)
├── Dockerfile                      # Production container recipe with FFmpeg
├── README.md                       # Comprehensive project documentation
├── SETUP.md                        # Step-by-step setup and deployment guide
├── core/
│   ├── image_engine.py             # Slicing, tilt straighten, smart seams, sRGB, unsharp mask, RAW/DNG
│   ├── video_engine.py             # FFmpeg Ken Burns video generator with ambient audio & speed ramping
│   ├── export_engine.py            # Omni-channel multi-platform ZIP & lookbook PDF pack exporter
│   ├── web_share.py                # Local HTTP server + QR code generator + mobile web UI
│   └── batch_engine.py             # Bulk queue batch processing
├── gui/
│   ├── phone_simulator.py          # Interactive Instagram Phone Carousel swipe simulator
│   ├── qr_modal.py                 # QR transfer dialog with live local Wi-Fi server
│   ├── video_modal.py              # Reel / Story panning video with audio & speed ramping
│   ├── grid_modal.py               # 3x1 / 3x2 / 3x3 Profile Grid post dialog
│   └── batch_modal.py              # Batch panorama slicer queue modal
└── tests/
    ├── test_image_engine.py        # Automated tests for image slicing, tilt, smart seams & RAW
    ├── test_video_engine.py        # Automated tests for video pan generator & ambient audio
    ├── test_export_engine.py       # Automated tests for omni-channel pack & lookbook PDF
    └── test_web_share.py           # Automated tests for mobile QR server & download
```

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
