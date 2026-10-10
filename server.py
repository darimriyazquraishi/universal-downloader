import os
import sys
import re
import json
import time
import shutil
import threading
import unicodedata
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse
import yt_dlp
import imageio_ffmpeg

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
import webbrowser

# Determine base directory (handles PyInstaller bundle vs standard Python execution)
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))

STATIC_DIR = os.path.join(BASE_DIR, "static")

# Find FFmpeg binary (bundled or system)
bundled_ffmpeg_meipass = os.path.join(BASE_DIR, "ffmpeg.exe")
local_ffmpeg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe")
if os.path.exists(bundled_ffmpeg_meipass):
    FFMPEG_EXE = bundled_ffmpeg_meipass
elif os.path.exists(local_ffmpeg):
    FFMPEG_EXE = local_ffmpeg
else:
    try:
        import imageio_ffmpeg
        FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        FFMPEG_EXE = shutil.which("ffmpeg")

# Default destination
if os.path.exists(r"e:\deleteme\songs"):
    DEFAULT_DEST = r"e:\deleteme\songs"
elif os.path.exists(os.path.join(EXE_DIR, "songs")):
    DEFAULT_DEST = os.path.join(EXE_DIR, "songs")
else:
    DEFAULT_DEST = os.path.join(EXE_DIR, "songs")

# Global Download State & Lock
state_lock = threading.Lock()
download_state = {
    "state": "idle",  # idle, analyzing, downloading, completed, stopped, error
    "status_message": "Ready to download",
    "progress": {
        "percent": 0.0,
        "current_track_idx": 0,
        "total_tracks": 0,
        "track_name": "",
        "speed": "",
        "eta": "",
        "downloaded_bytes": 0,
        "target_max_bytes": 0,
        "downloaded_count": 0,
        "skipped_count": 0
    },
    "analysis": None,
    "logs": [],
    "last_log_id": 0
}

stop_event = threading.Event()
active_download_thread = None

def add_log(level, message):
    with state_lock:
        download_state["last_log_id"] += 1
        log_entry = {
            "id": download_state["last_log_id"],
            "time": time.strftime("%H:%M:%S"),
            "level": level,  # info, download, convert, success, warn, error
            "message": message
        }
        download_state["logs"].append(log_entry)
        if len(download_state["logs"]) > 500:
            download_state["logs"].pop(0)

def clean_filename(title, idx, max_len=75):
    """Sanitize title for FAT32 USB/SD MP3 player compatibility (ASCII only)."""
    title = unicodedata.normalize('NFKD', title)
    title = title.replace('|', '-').replace('/', '-').replace('\\', '-').replace(':', ' -')
    title = title.replace('?', '').replace('*', '').replace('"', '').replace('<', '').replace('>', '')
    title = title.replace('｜', '-').replace('／', '-').replace('＼', '-').replace('：', ' -')
    title = title.replace('@', '').replace('#', '')
    
    ascii_chars = [c for c in title if ord(c) < 128 and (c.isalnum() or c in ' -_()[].,&')]
    ascii_title = ''.join(ascii_chars)
    ascii_title = re.sub(r'\s+', ' ', ascii_title).strip(' .-_')
    
    if len(ascii_title) < 3:
        ascii_title = f"Track_{idx:03d}"
    elif len(ascii_title) > max_len:
        ascii_title = ascii_title[:max_len].rstrip(' .-_')
        
    return ascii_title

def get_core_title_key(title):
    t_clean = re.sub(r'\(.*?\)|\[.*?\]', '', title)
    t_clean = re.sub(r'\b(full video|lyric video|lyrics|lyrical|full song|official audio song|official audio|audio song|song|audio|hd|official|video|timeless classics|remastered|4k)\b', '', t_clean, flags=re.IGNORECASE)
    parts = re.split(r'[-|:]', t_clean)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    candidate = re.sub(r'[^a-zA-Z0-9]', '', parts[0].lower())
    if len(candidate) < 3 and len(parts) > 1:
        candidate = re.sub(r'[^a-zA-Z0-9]', '', (parts[0] + parts[1]).lower())
    return candidate

def analyze_url(url):
    add_log("info", f"Analyzing YouTube URL: {url}")
    ydl_opts = {'quiet': True, 'extract_flat': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        is_playlist = 'entries' in info
        entries = list(info.get('entries', [])) if is_playlist else [info]
        
        valid_entries = []
        total_duration = 0
        for e in entries:
            t = e.get('title')
            dur = e.get('duration') or 0
            if t and not t.startswith('['):
                valid_entries.append({
                    'id': e.get('id'),
                    'title': t,
                    'duration': dur,
                    'duration_str': time.strftime('%H:%M:%S', time.gmtime(dur)) if dur >= 3600 else time.strftime('%M:%S', time.gmtime(dur))
                })
                total_duration += dur

        total_hours = total_duration / 3600
        # Estimates:
        # Audio:
        mp3_128_mb = (16000 * total_duration) / (1024 * 1024)
        mp3_192_mb = (24000 * total_duration) / (1024 * 1024)
        m4a_mb = (16200 * total_duration) / (1024 * 1024)
        # Video estimates (720p ~2.5Mbps, 1080p ~4.5Mbps):
        video_720_mb = (320000 * total_duration) / (1024 * 1024)
        video_1080_mb = (580000 * total_duration) / (1024 * 1024)

        result = {
            "title": info.get('title') or "YouTube Media",
            "is_playlist": is_playlist,
            "track_count": len(valid_entries),
            "total_duration": total_duration,
            "duration_str": f"{int(total_hours)}h {int((total_duration%3600)/60)}m" if total_hours >= 1 else f"{int(total_duration/60)}m {int(total_duration%60)}s",
            "tracks": valid_entries[:50],
            "estimates": {
                "mp3_128k": f"{mp3_128_mb / 1024:.2f} GB" if mp3_128_mb >= 1024 else f"{mp3_128_mb:.1f} MB",
                "mp3_192k": f"{mp3_192_mb / 1024:.2f} GB" if mp3_192_mb >= 1024 else f"{mp3_192_mb:.1f} MB",
                "m4a_128k": f"{m4a_mb / 1024:.2f} GB" if m4a_mb >= 1024 else f"{m4a_mb:.1f} MB",
                "video_720p": f"{video_720_mb / 1024:.2f} GB" if video_720_mb >= 1024 else f"{video_720_mb:.1f} MB",
                "video_1080p": f"{video_1080_mb / 1024:.2f} GB" if video_1080_mb >= 1024 else f"{video_1080_mb:.1f} MB"
            }
        }
        add_log("success", f"Analysis complete: '{result['title']}' ({result['track_count']} tracks, {result['duration_str']})")
        return result

def download_worker(params):
    url = params.get('url')
    dest_dir = params.get('destDir') or DEFAULT_DEST
    download_type = params.get('downloadType', 'mp3_speaker')
    
    if download_type == 'mp3_speaker':
        media_type = 'audio'
        speaker_mode = True
        fmt = 'mp3'
        bitrate = '128'
        video_quality = '1080'
    elif download_type == 'mp3_192':
        media_type = 'audio'
        speaker_mode = False
        fmt = 'mp3'
        bitrate = '192'
        video_quality = '1080'
    elif download_type == 'mp3_320':
        media_type = 'audio'
        speaker_mode = False
        fmt = 'mp3'
        bitrate = '320'
        video_quality = '1080'
    elif download_type == 'm4a':
        media_type = 'audio'
        speaker_mode = False
        fmt = 'm4a'
        bitrate = '128'
        video_quality = '1080'
    elif download_type.startswith('video_'):
        media_type = 'video'
        speaker_mode = False
        fmt = 'mp4'
        bitrate = '128'
        video_quality = download_type.replace('video_', '')
    else:
        media_type = params.get('mediaType', 'audio')
        video_quality = params.get('videoQuality', '1080')
        speaker_mode = params.get('speakerMode', True) if media_type == 'audio' else False
        fmt = params.get('format', 'mp3')
        bitrate = params.get('bitrate', '128')

    ignore_duplicates = params.get('ignoreDuplicates', True)
    max_tracks = int(params.get('maxTracks', 0)) if params.get('maxTracks') else 0
    max_size_mb = float(params.get('maxSizeMb', 0)) if params.get('maxSizeMb') else 0
    max_bytes = max_size_mb * 1024 * 1024 if max_size_mb > 0 else 0

    os.makedirs(dest_dir, exist_ok=True)

    with state_lock:
        download_state["state"] = "downloading"
        download_state["status_message"] = "Initializing download..."
        download_state["progress"]["downloaded_bytes"] = 0
        download_state["progress"]["target_max_bytes"] = max_bytes
        download_state["progress"]["downloaded_count"] = 0
        download_state["progress"]["skipped_count"] = 0

    add_log("info", f"Starting download to: {dest_dir} (Selection: {download_type})")
    if media_type == 'video':
        add_log("info", f"Video Format: {video_quality}p MP4")
    elif speaker_mode:
        add_log("info", "Old Speaker Mode: ON (128k CBR MP3, 44.1kHz, Stereo, ID3v2.3+v1, FAT32 clean names)")
    else:
        add_log("info", f"Audio Format: {fmt.upper()} | Bitrate: {bitrate}k")

    # Fetch entries
    ydl_flat_opts = {'quiet': True, 'extract_flat': True}
    with yt_dlp.YoutubeDL(ydl_flat_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            add_log("error", f"Failed to fetch metadata: {e}")
            with state_lock:
                download_state["state"] = "error"
                download_state["status_message"] = f"Error: {e}"
            return

    is_playlist = 'entries' in info
    raw_entries = list(info.get('entries', [])) if is_playlist else [info]

    # Inspect existing tracks in folder for numbering & duplicates
    if media_type == 'video':
        existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(('.mp4', '.mkv', '.webm'))]
    else:
        existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(('.mp3', '.m4a', '.opus'))]
    existing_keys = set()
    max_existing_idx = 0
    for f in existing_files:
        m = re.match(r'^(\d+)\s*-\s*(.+)\.[a-z0-9]+$', f, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            if num > max_existing_idx:
                max_existing_idx = num
            existing_keys.add(get_core_title_key(m.group(2)))
        else:
            existing_keys.add(get_core_title_key(os.path.splitext(f)[0]))

    queue = []
    seen_in_batch = set()

    for idx, e in enumerate(raw_entries, 1):
        vid = e.get('id')
        title = e.get('title')
        dur = e.get('duration') or 0
        if not vid or not title or title.startswith('['):
            continue
        k = get_core_title_key(title)
        if ignore_duplicates:
            if k in existing_keys:
                add_log("warn", f"Skipping duplicate already in folder: {title}")
                continue
            if k in seen_in_batch:
                add_log("warn", f"Skipping duplicate in playlist: {title}")
                continue
        seen_in_batch.add(k)
        queue.append({'id': vid, 'title': title, 'duration': dur, 'key': k})
        if max_tracks > 0 and len(queue) >= max_tracks:
            break

    total_queue = len(queue)
    with state_lock:
        download_state["progress"]["total_tracks"] = total_queue
    add_log("info", f"Prepared {total_queue} tracks for download.")

    if total_queue == 0:
        add_log("warn", "No new unique tracks to download.")
        with state_lock:
            download_state["state"] = "completed"
            download_state["status_message"] = "All tracks were already downloaded or ignored as duplicates."
        return

    # Download loop
    current_folder_size = sum(os.path.getsize(os.path.join(dest_dir, f)) for f in os.listdir(dest_dir) if os.path.isfile(os.path.join(dest_dir, f)))
    start_num = max_existing_idx + 1

    def ydl_progress_hook(d):
        if stop_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Download cancelled by user.")
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            speed_val = d.get('speed') or 0
            speed_str = f"{speed_val / (1024*1024):.1f} MB/s" if speed_val else ""
            eta_val = d.get('eta') or 0
            eta_str = f"{eta_val}s" if eta_val else ""
            with state_lock:
                download_state["progress"]["speed"] = speed_str
                download_state["progress"]["eta"] = eta_str
                if total > 0:
                    sub_pct = (downloaded / total) * 100
                    base_pct = ((download_state["progress"]["current_track_idx"] - 1) / total_queue) * 100
                    download_state["progress"]["percent"] = round(base_pct + (sub_pct / total_queue), 1)

    for i, item in enumerate(queue):
        if stop_event.is_set():
            add_log("warn", "Download stopped by user.")
            with state_lock:
                download_state["state"] = "stopped"
                download_state["status_message"] = "Download stopped by user."
            return

        # Check total size cap
        if max_bytes > 0 and current_folder_size >= max_bytes:
            add_log("success", f"Target size limit reached ({current_folder_size / (1024*1024):.1f} MB). Stopping.")
            break

        track_num = start_num + i
        raw_title = item['title']
        cleaned = clean_filename(raw_title, track_num)
        filename_base = f"{track_num:03d} - {cleaned}"
        if media_type == 'video':
            target_ext = "mp4"
            final_file_path = os.path.join(dest_dir, f"{filename_base}.mp4")
            if video_quality == 'best':
                fmt_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
            elif video_quality == '720':
                fmt_str = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]'
            elif video_quality == '480':
                fmt_str = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]'
            else:
                fmt_str = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]'

            opts = {
                'quiet': True,
                'no_warnings': True,
                'ffmpeg_location': FFMPEG_EXE,
                'format': fmt_str,
                'merge_output_format': 'mp4',
                'outtmpl': os.path.join(dest_dir, f"{filename_base}.%(ext)s"),
                'progress_hooks': [ydl_progress_hook],
            }
        else:
            target_ext = "mp3" if (speaker_mode or fmt == "mp3") else fmt
            final_file_path = os.path.join(dest_dir, f"{filename_base}.{target_ext}")
            postprocessors = []
            postprocessor_args = []

            if speaker_mode:
                postprocessors.append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                })
                postprocessor_args = [
                    '-ar', '44100',
                    '-ac', '2',
                    '-id3v2_version', '3',
                    '-write_id3v1', '1',
                    '-vn'
                ]
            elif fmt == 'mp3':
                postprocessors.append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': bitrate,
                })
                postprocessor_args = ['-ar', '44100', '-id3v2_version', '3', '-vn']
            elif fmt == 'm4a':
                postprocessors.append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': bitrate,
                })

            opts = {
                'quiet': True,
                'no_warnings': True,
                'ffmpeg_location': FFMPEG_EXE,
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(dest_dir, f"{filename_base}.%(ext)s"),
                'progress_hooks': [ydl_progress_hook],
            }
            if postprocessors:
                opts['postprocessors'] = postprocessors
            if postprocessor_args:
                opts['postprocessor_args'] = postprocessor_args

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={item['id']}"])

            # Verify downloaded file
            if os.path.exists(final_file_path):
                f_size = os.path.getsize(final_file_path)
                current_folder_size += f_size
                with state_lock:
                    download_state["progress"]["downloaded_count"] += 1
                    download_state["progress"]["downloaded_bytes"] += f_size
                add_log("success", f"Completed: {filename_base}.{target_ext} ({f_size / (1024*1024):.1f} MB)")
            else:
                matches = [f for f in os.listdir(dest_dir) if f.startswith(f"{track_num:03d} - ") and f.endswith(f".{target_ext}")]
                if matches:
                    f_size = os.path.getsize(os.path.join(dest_dir, matches[0]))
                    current_folder_size += f_size
                    with state_lock:
                        download_state["progress"]["downloaded_count"] += 1
                        download_state["progress"]["downloaded_bytes"] += f_size
                    add_log("success", f"Completed: {matches[0]} ({f_size / (1024*1024):.1f} MB)")
                else:
                    add_log("warn", f"Could not verify file output for {filename_base}")
        except yt_dlp.utils.DownloadCancelled:
            add_log("warn", "Download task cancelled.")
            with state_lock:
                download_state["state"] = "stopped"
                download_state["status_message"] = "Download stopped by user."
            return
        except Exception as err:
            add_log("error", f"Error on '{raw_title[:40]}': {err}")
            with state_lock:
                download_state["progress"]["skipped_count"] += 1

    final_count = download_state["progress"]["downloaded_count"]
    final_bytes = download_state["progress"]["downloaded_bytes"]
    with state_lock:
        download_state["state"] = "completed"
        download_state["progress"]["percent"] = 100.0
        download_state["status_message"] = f"Finished! {final_count} song(s) downloaded ({final_bytes / (1024*1024):.1f} MB)."

    add_log("success", f"Batch complete! {final_count} songs saved to {dest_dir} ({final_bytes / (1024*1024):.1f} MB).")

class AppRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default HTTP server console log spam
        return

    def send_json(self, data, code=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            path = "/index.html"

        if path == "/api/status":
            with state_lock:
                # Return snapshot
                data = {
                    "state": download_state["state"],
                    "status_message": download_state["status_message"],
                    "progress": download_state["progress"],
                    "analysis": download_state["analysis"],
                    "logs": download_state["logs"],
                    "last_log_id": download_state["last_log_id"]
                }
            self.send_json(data)
            return

        if path == "/api/system":
            drive = os.path.splitdrive(DEFAULT_DEST)[0] or "C:"
            total, used, free = shutil.disk_usage(drive)
            data = {
                "default_dest": DEFAULT_DEST,
                "ffmpeg_ok": bool(FFMPEG_EXE and os.path.exists(FFMPEG_EXE)),
                "ffmpeg_path": FFMPEG_EXE,
                "free_gb": round(free / (1024**3), 1),
                "drive": drive
            }
            self.send_json(data)
            return

        # Static file delivery
        file_path = os.path.join(STATIC_DIR, path.lstrip("/"))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            content_type = {
                '.html': 'text/html; charset=utf-8',
                '.css': 'text/css; charset=utf-8',
                '.js': 'application/javascript; charset=utf-8',
                '.json': 'application/json; charset=utf-8',
                '.svg': 'image/svg+xml',
                '.png': 'image/png',
                '.ico': 'image/x-icon'
            }.get(ext, 'application/octet-stream')

            with open(file_path, 'rb') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(length) if length > 0 else b'{}'
        try:
            body = json.loads(post_data.decode('utf-8'))
        except Exception:
            body = {}

        if path == "/api/analyze":
            url = body.get('url', '').strip()
            if not url:
                self.send_json({"error": "Please provide a valid YouTube URL."}, 400)
                return

            def run_analysis():
                with state_lock:
                    download_state["state"] = "analyzing"
                    download_state["status_message"] = "Analyzing YouTube URL..."
                try:
                    res = analyze_url(url)
                    with state_lock:
                        download_state["analysis"] = res
                        download_state["state"] = "idle"
                        download_state["status_message"] = f"Analyzed: {res['title']}"
                except Exception as err:
                    add_log("error", f"Analysis error: {err}")
                    with state_lock:
                        download_state["state"] = "error"
                        download_state["status_message"] = f"Analysis failed: {err}"

            t = threading.Thread(target=run_analysis, daemon=True)
            t.start()
            self.send_json({"status": "analyzing_started"})
            return

        if path == "/api/download":
            global active_download_thread
            with state_lock:
                if download_state["state"] == "downloading":
                    self.send_json({"error": "A download is already in progress."}, 400)
                    return

            url = body.get('url', '').strip()
            if not url:
                self.send_json({"error": "URL cannot be empty."}, 400)
                return

            stop_event.clear()
            active_download_thread = threading.Thread(target=download_worker, args=(body,), daemon=True)
            active_download_thread.start()
            self.send_json({"status": "download_started"})
            return

        if path == "/api/stop":
            stop_event.set()
            add_log("warn", "User requested download stop.")
            with state_lock:
                download_state["status_message"] = "Stopping download..."
            self.send_json({"status": "stopping"})
            return

        self.send_response(404)
        self.end_headers()

def run_server(preferred_port=5000):
    server = None
    actual_port = preferred_port
    for p in [preferred_port, 5000, 5001, 5002, 5003, 8080]:
        try:
            server = ThreadingHTTPServer(('127.0.0.1', p), AppRequestHandler)
            actual_port = p
            break
        except OSError:
            continue
    if not server:
        print("[ERROR] Could not bind to any local port.")
        sys.exit(1)

    print(f"==================================================")
    print(f"            YouTube Downloader Server             ")
    print(f" Running at: http://127.0.0.1:{actual_port}")
    print(f"==================================================")

    # Automatically launch default browser in background
    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(f"http://127.0.0.1:{actual_port}")
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()

if __name__ == '__main__':
    port = 5000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
