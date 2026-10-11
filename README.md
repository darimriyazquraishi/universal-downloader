# YouTube Downloader

A Windows desktop app for downloading audio or video from YouTube links and playlists. The interface is built with **CustomTkinter** and the download engine uses **yt-dlp** with FFmpeg for conversion and merging.

## What it does

- Modern dark desktop interface with quick destination shortcuts.
- Inspect a video or playlist before downloading; show item count, total duration, and a rough size estimate.
- Export MP3 at 128, 192, or 320 kbps; M4A audio; or MP4 video up to 1080p.
- Optional duplicate skipping and playlist item limit.
- Live progress, speed/ETA where available, and an activity log.
- USB / older-player MP3 mode: 128 kbps CBR, 44.1 kHz stereo, ID3v2.3 tags, and sanitized file names.
- Build a portable one-file Windows executable with FFmpeg bundled.

> Download only media you own or have permission to save, and follow the applicable platform terms and copyright rules.

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
