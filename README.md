# 🌐 Universal Downloader (v2.2.0)
High-performance, luxury-styled universal media downloader for **Windows Desktop** and **Android** devices, powered by **Python**, **CustomTkinter**, **Kivy**, and **yt-dlp**.

[![Version](https://img.shields.io/badge/Release-v2.2.0-gold.svg)](https://github.com/darimriyazquraishi/universal-downloader/releases/tag/v2.2.0)
[![Windows](https://img.shields.io/badge/Platform-Windows%20x64%20(EXE)-blue.svg?logo=windows)](https://github.com/darimriyazquraishi/universal-downloader/releases/download/v2.2.0/Universal_Downloader.exe)
[![Android](https://img.shields.io/badge/Platform-Android%20(APK)-green.svg?logo=android)](https://github.com/darimriyazquraishi/universal-downloader/releases/download/v2.2.0/UniversalDownloader-v2.2.0.apk)
[![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)

---

## 📥 Direct Downloads (v2.2.0)

| Platform | File | Type | Details | Download Link |
| :--- | :--- | :--- | :--- | :--- |
| **💻 Windows Desktop** | `Universal_Downloader.exe` | Standalone Portable EXE | Bundled with FFmpeg + CustomTkinter | [**Download for Windows**](https://github.com/darimriyazquraishi/universal-downloader/releases/download/v2.2.0/Universal_Downloader.exe) |
| **📱 Android** | `UniversalDownloader-v2.2.0.apk` | Release APK | 16 KB Page-Aligned · TargetSdk 36 (Android 16/15) | [**Download for Android**](https://github.com/darimriyazquraishi/universal-downloader/releases/download/v2.2.0/UniversalDownloader-v2.2.0.apk) |

---

## 🌟 Key Highlights & Features

### 1. Dual-Platform Native Design
- **Windows Desktop (`gui_app.py`)**: Native x64 desktop application with custom CustomTkinter dark obsidian & gold aesthetic, multi-threaded telemetry HUD, and zero external dependency requirements (FFmpeg is bundled inside the onefile EXE).
- **Android App (`main.py`)**: 120 FPS high-refresh AMOLED fluid mobile app with hardware-accelerated 2D rendering, touch gestures, and social media share menu hook.

### 2. ⏸️ Pause & ✕ Terminate Download Controls
- **Pause & Resume**: Clean, thread-safe pause mechanism allowing on-the-fly pausing and resuming of downloads across network chunks and post-processing.
- **Terminate & Clean Up**: Instant cancellation button that halts threads, unblocks locks, and automatically sweeps partial staging files (`*.part`, `*.ytdl`).
- **Vector Icons**: Custom anti-aliased luxury gold action icons (`#D4AF37`) matching the app theme without emoji fallbacks.

### 3. 📂 Integrated Download Manager
- **`OPEN FILE`**: Directly launches the completed audio or video file in your preferred default system player (VLC, Windows Media Player, MX Player, etc.).
- **`FOLDER`**:
  - **Windows**: Opens Windows File Explorer highlighting and selecting the exact downloaded media file (`explorer /select`).
  - **Android**: Multi-app chooser enabling quick exploration with OEM file managers (Samsung My Files, Xiaomi, OnePlus, Oppo, Vivo) and third-party managers (ZArchiver, ES File Explorer, Cx File Explorer, Google Files).

### 4. 🌐 1000+ Sites & MukaPlay Support
- **Full Compatibility**: YouTube (Videos, Playlists, Channels, Audio), MukaPlay share links, Instagram (Reels, Posts, Stories), TikTok (watermark-free), X / Twitter, Facebook, Reddit, Pinterest, SoundCloud, Vimeo, and 1000+ sources.
- **Smart Mix & Radio Protection**: Intelligently detects and separates YouTube radio mixes to prevent endless queue traps unless explicitly requested.

### 5. 🎧 Audio & Video Formats
- **Video Profiles**: MP4 Best Quality, 1080p Full HD, 720p HD, 480p SD.
- **Audio Profiles**: MP3 320 kbps (Maximum Quality), MP3 192 kbps (High Quality), MP3 128 kbps (Standard CBR, ID3v2.3 tags for car/USB stereos), and AAC M4A (Original audio stream).

### 6. 🔒 Strict Security & Scoped Storage
- Strict TLS certificate verification backed by standard Mozilla CA bundles (`certifi`). Insecure SSL bypasses are completely disabled.
- Full compliance with Android Scoped Storage & MediaStore (no invasive storage permissions required).

---

## 📂 Repository Architecture

```text
universal-downloader/
├── .github/
│   └── workflows/
│       ├── build_apk.yml            # Automated Android APK CI/CD pipeline
│       └── build_exe.yml            # Automated Windows EXE CI/CD pipeline
├── assets/
│   ├── app_icon.ico                 # Windows application icon
│   ├── icon_gold.png                # Luxury vector gold brand mark
│   ├── intent_filter.xml            # Android social share-menu hook
│   └── fonts/                       # Embedded typography
├── tests/
│   ├── test_regression.py           # Comprehensive unit & regression test suite
│   └── test_elf_alignment.py        # 16 KB ELF segment alignment verifier
├── gui_app.py                       # Windows Desktop Client (CustomTkinter)
├── main.py                          # Android Mobile App (Kivy)
├── downloader_engine.py             # Core download & extraction engine
├── build_exe.py                     # Windows PyInstaller compilation script
├── buildozer.spec                   # Android packaging specification
├── requirements.txt                 # Android simulator requirements
├── requirements-desktop.txt         # Windows desktop requirements
└── README.md                        # Documentation
```

---

## 🚀 Running Locally from Source

### Windows Desktop App
```bash
git clone https://github.com/darimriyazquraishi/universal-downloader.git
cd universal-downloader

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements-desktop.txt
python gui_app.py
```

### Android Mobile Simulator
```bash
pip install -r requirements.txt
python main.py
```

---

## 🛠️ Building Binaries

### Build Windows Onefile Executable
```bash
python build_exe.py
# Produces dist/Universal_Downloader.exe (110.9 MB with bundled FFmpeg)
```

### Build Android Production APK
```bash
buildozer android release
# Or trigger via GitHub Actions under the "Build Android APK" workflow
```

---

## 📜 License
This project is licensed under the [MIT License](LICENSE).
