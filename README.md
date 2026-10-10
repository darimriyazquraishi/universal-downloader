# YouTube Downloader

A modern, fast, and feature-rich YouTube Audio and Video Downloader built with a sleek dark interface, live progress streaming, and support for standalone one-file executable deployment.

![UI Preview](https://raw.githubusercontent.com/darimriyazquraishi/youtube-downloader/main/static/preview.png)

---

## 🌟 Key Features

- **📻 Old Speaker / USB Compatibility Mode**:
  - Encodes directly to **128 kbps Constant Bitrate (CBR)** at **44.1 kHz** stereo.
  - Generates clean ASCII-sanitized filenames (FAT32 compatible) without special characters.
  - Strips unsupported embedded album artwork to prevent older MP3 boomboxes, car stereos, and SD/USB players from skipping or freezing.
- **🎵 High Fidelity Audio Formats**:
  - MP3 Maximum Quality (320 kbps)
  - MP3 High Quality (192 kbps)
  - M4A / AAC original audio stream
- **🎬 Full HD Video Downloads**:
  - MP4 Video (1080p Full HD, 720p HD, Best Available, 480p)
  - Seamless audio + video muxing via embedded FFmpeg.
- **⚡ Streamlined Selection**:
  - No complex toggle buttons. Paste your YouTube link and select your download option directly from the dropdown.
  - Automatically calculates track counts, durations, and estimated download sizes.
- **🖥️ 3-Panel Dark Theme Layout**:
  - **Explorer** (Left): Quick folder navigation (`songs`, `videos`, root) and system disk storage meter.
  - **Downloader Card** (Center): URL input, format selector, duplicate skip toggle, and download actions.
  - **Terminal** (Bottom): Live download progress bar, speed, ETA, and real-time color-coded console logs.
- **📦 100% Standalone One-File Executable**:
  - Bundles Python server, web UI, `yt-dlp`, and **FFmpeg 7.1** into a single portable `.exe`.

---

## 🚀 Quick Start

### Option 1: Standalone Portable Executable (Recommended)
[![Download Executable](https://img.shields.io/badge/Download-YouTube__Downloader.exe%20(v1.0.0)-blue?style=for-the-badge&logo=windows)](https://github.com/darimriyazquraishi/youtube-downloader/releases/download/v1.0.0/YouTube_Downloader.exe)

Direct Download: **[YouTube_Downloader.exe (85 MB)](https://github.com/darimriyazquraishi/youtube-downloader/releases/download/v1.0.0/YouTube_Downloader.exe)** or visit the [Releases](https://github.com/darimriyazquraishi/youtube-downloader/releases) page.
1. Download and double-click `YouTube_Downloader.exe` (no installation, Python, or FFmpeg needed).
2. It immediately launches and opens `http://127.0.0.1:5000` in your default browser.
3. Paste any YouTube link, choose your format from the dropdown, and click **▶ Start Download**.

### Option 2: Running from Source

#### Prerequisites
- Python 3.10+
- FFmpeg (automatically handled via `imageio-ffmpeg` or system path)

#### Installation
```bash
# Clone the repository
git clone https://github.com/darimriyazquraishi/youtube-downloader.git
cd youtube-downloader

# Install dependencies
pip install -r requirements.txt

# Run the server
python server.py 5000
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## 🔨 Building the Standalone `.exe`

To compile the entire application into a single `.exe` with embedded FFmpeg:

```bash
python build_exe.py
```
The compiled binary will be generated in `dist/YouTube_Downloader.exe`.

---

## 📁 Project Structure

```
├── server.py              # Backend HTTP server and downloader controller
├── build_exe.py           # PyInstaller build automation script
├── run_app.bat            # One-click Windows batch launcher
├── requirements.txt       # Python dependencies
├── .gitignore             # Git ignore rules
└── static/
    ├── index.html         # Modern web interface layout
    ├── style.css          # Dark design system
    └── app.js             # Real-time state polling & event controller
```

---

## 📄 License
This project is released under the [MIT License](LICENSE).
