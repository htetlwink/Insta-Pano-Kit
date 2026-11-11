# 🛠️ InstaPanoramaSplitter — Setup & Deployment Guide

This guide covers everything you need to set up, run, test, and deploy **InstaPanoramaSplitter**:
* **Mode 1:** [Local Desktop GUI Application](#-mode-1-local-desktop-gui-setup) (CustomTkinter)
* **Mode 2:** [Local Web Browser Application](#-mode-2-local-web-application-setup) (Flask / Gunicorn)
* **Mode 3:** [Cloud Deployment on Render.com](#-mode-3-cloud-deployment-on-rendercom) (Docker Web Service)

---

## 📋 System Prerequisites

Before starting, ensure your system has the following installed:

| Requirement | Recommended Version | Purpose |
|---|---|---|
| **Python** | 3.8+ (tested on 3.12) | Core runtime environment |
| **FFmpeg** | 4.x / 5.x / 6.x | Video rendering for Instagram Reels panning |
| **Git** | Any modern version | Version control & Render deployment |

### Installing FFmpeg (if not already installed)
* **Ubuntu / Debian:**
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```
* **macOS (Homebrew):**
  ```bash
  brew install ffmpeg
  ```
* **Windows (Chocolatey / Scoop):**
  ```powershell
  choco install ffmpeg
  # or scoop install ffmpeg
  ```

---

## 💻 Mode 1: Local Desktop GUI Setup

Use this mode for the desktop experience with live preview, pan sliders, and mobile simulator.

### 1. Create and Activate a Virtual Environment
```bash
# Navigate to project directory
cd "pano maker"

# Create a virtual environment
python3 -m venv venv

# Activate it:
# On Linux / macOS:
source venv/bin/activate

# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Launch Desktop App
```bash
python3 app.py
```

---

## 🌐 Mode 2: Local Web Application Setup

Use this mode to test the browser interface locally before deploying to the cloud.

### 1. Run with Flask Development Server
```bash
python3 web_app.py
```
Open your browser and navigate to:
```
http://localhost:8080
```

### 2. Run with Production Gunicorn (Linux / macOS)
```bash
gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 4 --timeout 120 web_app:app
```

---

## ☁️ Mode 3: Cloud Deployment on Render.com

Render is a cloud platform that runs containerized web services. Follow these steps to host your app with public URL access:

### Step 1: Initialize Git and Push to GitHub

If you haven't initialized Git yet:
```bash
# 1. Initialize git
git init

# 2. Stage all project files
git add .

# 3. Commit
git commit -m "Initial commit of InstaPanoramaSplitter"

# 4. Set branch to main
git branch -M main

# 5. Connect to your GitHub repository
git remote add origin https://github.com/<your-username>/<your-repo-name>.git

# 6. Push code
git push -u origin main
```

---

### Step 2: Deploy to Render.com

#### ⚡ Option A: Instant Static Site (Zero Loading Screen • Instantaneous 0s Cold Start)
> **Why this option?** Because `index.html` runs 100% inside the user's browser (HTML5 Canvas + JSZip + Web Audio API), a **Render Static Site** is hosted on Render's global CDN:
> - **Never sleeps / never spins down** (unlike Render free Docker web services which sleep after 15 min).
> - **Loads instantly in <100ms with ZERO loading screen**.
> - **100% Free** forever.

1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** ➔ Select **Static Site**.
3. Connect your GitHub repository.
4. Set the fields:
   * **Name:** `instapano-web`
   * **Branch:** `main`
   * **Build Command:** *(leave empty)*
   * **Publish Directory:** `.` *(a single dot for the repository root)*
5. Click **Create Static Site**.
Your website URL (e.g. `https://instapano.onrender.com/`) is live immediately with 0s loading time!

---

#### 🐋 Option B: Full Blueprint Deployment (Both Static App + Python Docker API)
1. In [dashboard.render.com](https://dashboard.render.com), click **New +** ➔ **Blueprint**.
2. Select your GitHub repository.
3. Render automatically detects **`render.yaml`** and provisions:
   * `instapano-instant-web`: Global CDN Static Site (instant loading, no sleep).
   * `instapanorama-splitter-api`: Docker/Flask backend with FFmpeg.
4. Click **Apply**.

---

#### 🌐 Option C: GitHub Pages (Instant Free Hosting)
You can also host `index.html` completely free on GitHub with zero external accounts:
1. Open your repository on GitHub.
2. Go to **Settings** ➔ **Pages**.
3. Under **Branch**, select `main` and folder `/ (root)`.
4. Click **Save**. Your site will be live instantly at `https://<your-username>.github.io/<repo-name>/`!

---

### Step 3: Verify Your Deployment

1. Render will build the Docker container using our **`Dockerfile`**.
2. Once the build finishes and the log shows `Running 'gunicorn ...'`, click the assigned public URL (e.g., `https://instapanorama-splitter.onrender.com`).
3. Verify the `/health` endpoint:
   ```
   https://instapanorama-splitter.onrender.com/health
   ```
   It will return:
   ```json
   {"ffmpeg": true, "status": "healthy"}
   ```

---

## 🧪 Running the Automated Test Suite

We have 33 comprehensive unit and integration tests covering image transformations, aspect ratios, seam indicators, grid splitting, and server lifecycles:

```bash
python3 -m unittest discover tests
```

Expected output:
```
.................................
----------------------------------------------------------------------
Ran 33 tests in ~11s

OK
```

---

## ⚙️ Advanced Configuration & Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Port for the web server to listen on (assigned automatically by Render). |
| `MAX_CONTENT_LENGTH` | `67108864` (64 MB) | Maximum upload file size in bytes (configured inside `web_app.py`). |
| `GUNICORN_WORKERS` | `2` | Number of worker processes (configured in `Dockerfile`). |
| `GUNICORN_TIMEOUT` | `120` | Maximum request duration in seconds before timeout (allows high-res rendering). |

---

## ❓ Frequently Asked Questions (FAQ)

#### Q1: Why does the Render app take ~45 seconds to load the first time?
* **Answer:** On Render's **Free tier**, containers spin down after 15 minutes of inactivity. When a new visitor opens the URL, Render automatically wakes the service up within 30–45 seconds. Subsequent requests are instant. Upgrading to Render's $7/mo Starter plan keeps it running 24/7 without spin-down.

#### Q2: Can I upload 50MB+ drone or camera panoramas?
* **Answer:** Yes. The web app is tuned with a 64MB upload ceiling and uses chunked streaming with Pillow and Lanczos downsampling.

#### Q3: Does the video panning feature work on Render?
* **Answer:** Yes. The included `Dockerfile` installs system `ffmpeg`, which the backend detects and uses automatically.
