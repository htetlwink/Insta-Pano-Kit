# 📸 InstaPanoramaSplitter — Pro Instagram Creator Suite

A modern desktop application built with **CustomTkinter**, **Pillow (PIL)**, and **FFmpeg** that transforms wide panoramic photos into high-engagement **Instagram carousels**, **Reels panning videos**, and **Profile puzzle grids**.

---

## ✨ Features & Capabilities

### 1. ✂️ Seamless Instagram Carousel Slicer
- **Instagram Aspect Ratios**:
  - **Portrait (4:5)**: Targets $1080 \times 1350\text{ px}$ per slice (maximizes vertical screen estate on mobile feeds for higher reach).
  - **Square (1:1)**: Targets $1080 \times 1080\text{ px}$ per slice (classic Instagram square carousel).
  - **Story / Reels (9:16)**: Targets $1080 \times 1920\text{ px}$ per slice (tap-through panoramic stories).
- **Interactive Pan & Framing Offsets (Horizontal & Vertical)**:
  - Sliders allowing manual $-100\%$ to $+100\%$ offset adjustment along both axes to keep subjects, landmarks, or horizons perfectly framed across slices.
- **Multiple Framing & Fit Modes**:
  - **Standard 1080px (Fit & Crop)**: Auto-scales and crops according to your Pan X/Y offsets.
  - **Proportional (Full Width • No Crop)**: Keeps 100% of the panorama's width divided equally.
  - **Blurred Background Fill**: Places the panorama on an ambient Gaussian-blurred backdrop of itself (no cropping needed).
  - **Solid Gallery Border**: Fits the panorama within clean minimalist white or dark borders.

### 2. 📱 Interactive Mobile Carousel Simulator
- Test the seamless swipe experience right on your desktop with an interactive Instagram mobile mockup.
- Use arrow keys (`◀` / `▶`), overlay buttons, or click **"▶ Auto Swipe"** to inspect how seams flow across slides before exporting.

### 3. 🎯 Engagement Hooks & Seam Polish
- **Seam Arrow Indicator (`➔`)**: Draws an arrow cut in half across slide seams ($i$ and $i+1$) that joins together as viewers swipe.
- **Swipe Left Badge**: Aesthetic `"SWIPE ➔"` prompt pill on Slide 1 to maximize swipe-through rates.
- **Pagination Dot Indicators**: Active slide indicator dots along the bottom border.
- **Slide 1 Cover Title & Watermark**: Add an elegant typographic cover title and photographer credit (`@your_account`).

### 4. 🎨 Instagram Color & Quality Optimizer
- **sRGB Color Space Conversion**: Embedded LittleCMS (`ImageCms`) sRGB transformation to prevent desaturated/washed-out colors when uploading to Instagram on iOS and Android.
- **Smart 1080px Sharpening**: Mobile-tuned unsharp mask filter that restores crisp micro-textures lost during downsampling.
- **Numbered Upload Guide Contact Sheet**: Automatically generates a visual `upload_guide.jpg` showing `[Slide 1] ➔ [Slide 2] ➔ [Slide 3]` and posting instructions so you never post slides out of order.

### 5. 📲 Scan-to-Phone Instant QR Transfer
- No need for cables, AirDrop, or emailing photos to yourself.
- Spins up a secure, lightweight local Wi-Fi server and displays a **QR code**.
- Scan the QR code with your iPhone or Android camera to open a responsive mobile download page and save all slides directly to your camera roll (or download all as a ZIP).

### 6. 🎬 Animated Panning Video Generator (Reels & Stories)
- Creates smooth **Ken Burns panning MP4 videos** for Instagram Reels, Shorts, and Stories.
- Choose between **9:16 (Reels/Stories)**, **4:5 (Feed)**, or **1:1 (Square)**.
- Configure duration (4s to 20s), framerate (30 or 60 FPS), and motion direction (*Left to Right*, *Right to Left*, or *Ping-Pong Boomerang*).
- Uses smooth sinusoidal ease-in-out pacing and H.264 `faststart` for instant playback.

### 7. 🔲 Instagram Profile Grid Splitter
- Slice photos into **3×1 Banners** (profile header), **3×2**, or **3×3 Giant Grids** (9 tiles forming one massive image on your profile).
- Automatically exports tiles with **reverse upload numbering** (`grid_09_upload_1st.jpg` down to `grid_01_upload_last.jpg`) so your grid appears in alignment.

### 8. 🏷️ Captions & Hashtags Scratchpad
- Curated high-reach hashtags for *Panoramas & Carousels*, *Landscapes & Nature*, *Cityscapes & Architecture*, and *Mobile Photography*.
- Ready-to-use swipe-prompt caption templates with one-click clipboard copying.

### 9. 📦 Batch Panorama Slicer
- Queue multiple panorama photos or an entire folder to slice and organize each image into its own carousel subfolder.

---

## 🚀 Installation & Setup
> 📖 **Full setup & Render.com deployment manual:** See [SETUP.md](SETUP.md) for step-by-step instructions.

### 1. Requirements
- Python 3.8+
- FFmpeg (for video pan generation)

### 2. Install Python Dependencies
```bash
pip install customtkinter pillow qrcode
```

### 3. Launch the Application
```bash
python3 app.py
```

---

## 🧪 Testing & Verification
The codebase includes a comprehensive automated test suite covering all image transformations, video generation, and local Wi-Fi server lifecycle:

```bash
python3 -m unittest discover tests
```

---

## 📁 Project Structure

```
pano maker/
├── app.py                          # Main GUI application & unified interface
├── README.md                       # Documentation & feature manual
├── core/
│   ├── image_engine.py             # Slicing, sRGB, unsharp mask, borders, seam cues, grids
│   ├── video_engine.py             # FFmpeg Ken Burns panning video generator (Reels/Stories)
│   ├── web_share.py                # Local HTTP server + QR code generator + mobile web UI
│   └── batch_engine.py             # Bulk queue batch processing
├── gui/
│   ├── phone_simulator.py          # Interactive Instagram Phone Carousel swipe simulator
│   ├── qr_modal.py                 # QR transfer dialog with live local Wi-Fi server
│   ├── video_modal.py              # Reel / Story panning video configuration dialog
│   ├── grid_modal.py               # 3x1 / 3x2 / 3x3 Profile Grid post dialog
│   ├── caption_modal.py            # Caption & hashtag presets drawer
│   └── batch_modal.py              # Batch panorama slicer queue modal
└── tests/
    ├── test_image_engine.py        # 22 automated tests for image slicing & features
    ├── test_video_engine.py        # 6 automated tests for video pan generator
    └── test_web_share.py           # 5 automated tests for mobile QR server & download
```
