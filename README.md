# YouTube Downloader (Native Windows Desktop App)

A modern, fast, and feature-rich YouTube Audio and Video Downloader built as a **100% native Windows desktop application** with a sleek dark GUI, live progress streaming, and zero browser involvement.

---

## 🌟 Key Features

- **🚫 No Browser Involvement**:
  - Runs directly as a native Windows desktop GUI application.
  - Zero web servers, zero localhost ports, and zero browser tabs.
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
  - **Explorer** (Left): Quick folder navigation (`songs`, `videos`, custom folder) and system disk storage meter.
  - **Downloader Card** (Center): URL input, format selector, duplicate skip toggle, and download actions.
  - **Terminal** (Bottom): Live download progress bar, speed, ETA, and real-time color-coded console logs.
- **📦 100% Standalone One-File Executable**:
  - Bundles the native desktop GUI, `yt-dlp`, and **FFmpeg 7.1** into a single portable `.exe`.

---

## 🚀 Quick Start

### Option 1: Standalone Portable Executable (Recommended)
[![Download Executable](https://img.shields.io/badge/Download-YouTube__Downloader.exe%20(v1.1.0)-blue?style=for-the-badge&logo=windows)](https://github.com/darimriyazquraishi/youtube-downloader/releases/download/v1.1.0/YouTube_Downloader.exe)

Direct Download: **[YouTube_Downloader.exe](https://github.com/darimriyazquraishi/youtube-downloader/releases/download/v1.1.0/YouTube_Downloader.exe)** or visit the [Releases](https://github.com/darimriyazquraishi/youtube-downloader/releases) page.
1. Download and double-click `YouTube_Downloader.exe` (no installation, Python, or FFmpeg needed).
2. The desktop window opens immediately with zero browser involvement.
3. Paste any YouTube link, choose your format from the dropdown, and click **▶ Start Download**.

### Option 2: Running from Source

#### Prerequisites
- Windows 10/11
- Python 3.10+
- FFmpeg (automatically bundled or handled via `imageio-ffmpeg`)

#### Installation
```bash
# Clone the repository
git clone https://github.com/darimriyazquraishi/youtube-downloader.git
cd youtube-downloader

# Install dependencies
pip install -r requirements.txt

# Run the native desktop application
python gui_app.py
```

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
├── gui_app.py             # Native Windows Desktop GUI (CustomTkinter)
├── build_exe.py           # PyInstaller build automation script
├── run_app.bat            # One-click Windows batch launcher
├── requirements.txt       # Python dependencies
├── .gitignore             # Git ignore rules
└── LICENSE                # MIT License
```

---

## 📄 License
This project is released under the [MIT License](LICENSE).
