# Universal Media Downloader

A native Windows desktop app for downloading videos and audio from YouTube, Facebook, Instagram, TikTok, X (Twitter), Reddit, and thousands of other platforms. The interface is built with **CustomTkinter** featuring an Artcraft/Watermelon-inspired gold aesthetic, and the download engine uses **yt-dlp** with an embedded FFmpeg binary for conversion and stream merging.

## Key Features

- **Multi-Platform Support**: Download clips, reels, posts, playlists, and tracks from YouTube, Instagram, TikTok, Facebook, X/Twitter, Reddit, Pinterest, Vimeo, SoundCloud, and more.
- **Dedicated Download Manager**: Built-in sidebar manager displaying live downloads, completed items, and instant folder location buttons.
- **Smart URL Inspector**: Deep-inspect links before downloading to inspect item counts, duration, platform tags, and estimated file sizes.
- **Format Flexibility**:
  - MP4 Video (Best available up to 4K/1080p, 720p HD, 480p).
  - High-Fidelity Audio (320 kbps MP3, 192 kbps MP3, AAC M4A).
  - Speaker / Car USB Mode (128 kbps CBR MP3, 44.1 kHz stereo, ID3v2.3 tags, FAT32-safe filenames).
- **Clipboard Auto-Inspection**: Automatically detects pasted or copied media URLs.
- **Dynamic File Management**: Saves to user's `Downloads/Media Downloads` by default with custom folder persistence in `%APPDATA%`.
- **Duplicate Skipping & Item Limits**: Skip already downloaded items and set custom download limits for playlists/batches.
- **Zero Browser Involvement**: 100% self-contained native Windows desktop executable with embedded FFmpeg and yt-dlp.

> Download only media you own or have permission to save, and follow applicable platform terms of service.

## Run from source

**Requirements:** Windows 10/11 and Python 3.10 or newer.

```powershell
python -m pip install -r requirements.txt
python gui_app.py
```

If FFmpeg is installed separately, the app can use it from `PATH`. Otherwise `imageio-ffmpeg` provides a bundled FFmpeg binary when running from source.

## Build a standalone `.exe`

```powershell
python build_exe.py
```

The script builds `dist/YouTube_Downloader.exe`. It no longer copies the output to a machine-specific folder. The executable includes the desktop UI, yt-dlp, and FFmpeg.

## Project layout

```text
gui_app.py       # Main native desktop application and download engine
build_exe.py     # PyInstaller build script
requirements.txt # Python dependencies
run_app.bat      # One-click source launcher
server.py        # Older local-server prototype; not used by gui_app.py
static/          # Older browser UI prototype; not used by gui_app.py
```

The current app entry point is `gui_app.py`. The `server.py` and `static/` files are retained from an earlier browser-based prototype; they are not used when launching the native desktop app.

## License

MIT — see [LICENSE](LICENSE).
