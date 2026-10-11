import os
import sys
import re
import time
import shutil
import threading
import unicodedata
import queue
import yt_dlp
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Resolve base directory (PyInstaller bundled vs source)
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))

# Find FFmpeg binary
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

# Default folders
DEFAULT_SONGS = r"e:\deleteme\songs" if os.path.exists(r"e:\deleteme\songs") else os.path.join(EXE_DIR, "songs")
DEFAULT_VIDEOS = r"e:\deleteme\videos" if os.path.exists(r"e:\deleteme\videos") else os.path.join(EXE_DIR, "videos")
DEFAULT_ROOT = r"e:\deleteme" if os.path.exists(r"e:\deleteme") else EXE_DIR

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


class YouTubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Appearance & Geometry
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.title("YouTube Downloader")
        self.geometry("1060x720")
        self.minsize(920, 640)

        # State Variables
        self.stop_event = threading.Event()
        self.download_thread = None
        self.analysis_thread = None
        self.log_queue = queue.Queue()
        self.current_analysis = None
        self.is_downloading = False

        # Build UI Components
        self.create_layout()
        self.update_storage_info()
        self.poll_log_queue()

        # Handle clean exit
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_layout(self):
        # Configure root grid (Titlebar / Header + Main Workbench)
        self.grid_rowconfigure(0, weight=0) # Title header
        self.grid_rowconfigure(1, weight=1) # Workbench
        self.grid_columnconfigure(0, weight=1)

        # Top Bar
        top_bar = ctk.CTkFrame(self, height=36, corner_radius=0, fg_color="#2b2b2b")
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)

        lbl_app = ctk.CTkLabel(top_bar, text="▶  YouTube Downloader", font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff")
        lbl_app.grid(row=0, column=0, padx=(14, 10), pady=6, sticky="w")

        lbl_sub = ctk.CTkLabel(top_bar, text="Desktop Application", font=ctk.CTkFont(size=11), text_color="#888888")
        lbl_sub.grid(row=0, column=1, padx=4, pady=6, sticky="w")

        self.lbl_header_status = ctk.CTkLabel(top_bar, text="● Ready", font=ctk.CTkFont(size=11), text_color="#4ec9b0")
        self.lbl_header_status.grid(row=0, column=2, padx=16, pady=6, sticky="e")

        # Main Workbench: Sidebar (left) + Center/Bottom (right)
        workbench = ctk.CTkFrame(self, corner_radius=0, fg_color="#1e1e1e")
        workbench.grid(row=1, column=0, sticky="nsew")
        workbench.grid_rowconfigure(0, weight=1)
        workbench.grid_columnconfigure(0, weight=0) # Sidebar
        workbench.grid_columnconfigure(1, weight=1) # Center area

        # ---------------- 1. EXPLORER (Left Sidebar) ----------------
        sidebar = ctk.CTkFrame(workbench, width=220, corner_radius=0, fg_color="#252526")
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 1), pady=0)
        sidebar.grid_propagate(False)

        lbl_sidebar = ctk.CTkLabel(sidebar, text="EXPLORER", font=ctk.CTkFont(size=11, weight="bold"), text_color="#aaaaaa")
        lbl_sidebar.pack(anchor="w", padx=14, pady=(14, 8))

        lbl_folders_hdr = ctk.CTkLabel(sidebar, text="DOWNLOAD FOLDERS", font=ctk.CTkFont(size=10, weight="bold"), text_color="#777777")
        lbl_folders_hdr.pack(anchor="w", padx=14, pady=(8, 4))

        self.btn_dest_songs = ctk.CTkButton(
            sidebar, text="📁 songs", anchor="w", fg_color="#333333", hover_color="#3e3e42",
            height=28, font=ctk.CTkFont(size=12), command=lambda: self.set_destination(DEFAULT_SONGS)
        )
        self.btn_dest_songs.pack(fill="x", padx=10, pady=3)

        self.btn_dest_videos = ctk.CTkButton(
            sidebar, text="📁 videos", anchor="w", fg_color="#2d2d30", hover_color="#3e3e42",
            height=28, font=ctk.CTkFont(size=12), command=lambda: self.set_destination(DEFAULT_VIDEOS)
        )
        self.btn_dest_videos.pack(fill="x", padx=10, pady=3)

        self.btn_dest_root = ctk.CTkButton(
            sidebar, text="📁 deleteme (Root)", anchor="w", fg_color="#2d2d30", hover_color="#3e3e42",
            height=28, font=ctk.CTkFont(size=12), command=lambda: self.set_destination(DEFAULT_ROOT)
        )
        self.btn_dest_root.pack(fill="x", padx=10, pady=3)

        btn_browse_custom = ctk.CTkButton(
            sidebar, text="📂 Choose Folder...", anchor="w", fg_color="#2d2d30", hover_color="#3e3e42",
            height=28, font=ctk.CTkFont(size=12), command=self.browse_folder
        )
        btn_browse_custom.pack(fill="x", padx=10, pady=3)

        # Storage & System
        lbl_sys_hdr = ctk.CTkLabel(sidebar, text="SYSTEM & STORAGE", font=ctk.CTkFont(size=10, weight="bold"), text_color="#777777")
        lbl_sys_hdr.pack(anchor="w", padx=14, pady=(20, 4))

        self.lbl_free_space = ctk.CTkLabel(sidebar, text="Free Space: --", font=ctk.CTkFont(size=11), text_color="#cccccc", anchor="w")
        self.lbl_free_space.pack(fill="x", padx=14, pady=2)

        self.lbl_drive = ctk.CTkLabel(sidebar, text="Drive: --", font=ctk.CTkFont(size=11), text_color="#999999", anchor="w")
        self.lbl_drive.pack(fill="x", padx=14, pady=2)

        self.lbl_ffmpeg_status = ctk.CTkLabel(sidebar, text="Encoder: Ready", font=ctk.CTkFont(size=11), text_color="#4ec9b0", anchor="w")
        self.lbl_ffmpeg_status.pack(fill="x", padx=14, pady=2)

        # ---------------- Right Area (Center Form + Terminal) ----------------
        right_panel = ctk.CTkFrame(workbench, corner_radius=0, fg_color="#1e1e1e")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_rowconfigure(0, weight=0) # Downloader Card
        right_panel.grid_rowconfigure(1, weight=1) # Terminal Panel
        right_panel.grid_columnconfigure(0, weight=1)

        # ---------------- 2. MIDDLE SECTION (Downloader Card) ----------------
        card = ctk.CTkFrame(right_panel, corner_radius=6, fg_color="#252526", border_width=1, border_color="#333333")
        card.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))

        # 1. URL Row
        lbl_url = ctk.CTkLabel(card, text="YOUTUBE LINK (VIDEO OR PLAYLIST)", font=ctk.CTkFont(size=11, weight="bold"), text_color="#cccccc")
        lbl_url.pack(anchor="w", padx=16, pady=(14, 4))

        url_row = ctk.CTkFrame(card, fg_color="transparent")
        url_row.pack(fill="x", padx=16, pady=(0, 10))

        self.entry_url = ctk.CTkEntry(url_row, placeholder_text="Paste YouTube link here...", height=34, font=ctk.CTkFont(size=12))
        self.entry_url.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_url.bind("<Return>", lambda e: self.trigger_analyze())

        btn_paste = ctk.CTkButton(url_row, text="Paste", width=70, height=34, fg_color="#3a3d41", hover_color="#45494e", command=self.paste_from_clipboard)
        btn_paste.pack(side="left", padx=(0, 6))

        self.btn_analyze = ctk.CTkButton(url_row, text="Analyze", width=80, height=34, fg_color="#0e639c", hover_color="#1177bb", command=self.trigger_analyze)
        self.btn_analyze.pack(side="left")

        # 2. Single Format & Quality Selection Option
        lbl_opt = ctk.CTkLabel(card, text="DOWNLOAD OPTION", font=ctk.CTkFont(size=11, weight="bold"), text_color="#cccccc")
        lbl_opt.pack(anchor="w", padx=16, pady=(4, 4))

        self.format_options_map = {
            "📻 MP3 — Old Speaker / USB Mode (128k CBR, 44.1kHz)": "mp3_speaker",
            "🎵 MP3 — Maximum Quality (320 kbps)": "mp3_320",
            "🎵 MP3 — High Quality (192 kbps)": "mp3_192",
            "🎬 Video — 1080p Full HD (MP4)": "video_1080",
            "🎬 Video — 720p HD (MP4)": "video_720",
            "🎬 Video — Best Available (MP4)": "video_best",
            "🎬 Video — 480p (MP4)": "video_480",
            "🎧 Audio — Original Stream (AAC / M4A)": "m4a"
        }

        self.combo_format = ctk.CTkComboBox(
            card, values=list(self.format_options_map.keys()),
            height=34, font=ctk.CTkFont(size=12),
            dropdown_font=ctk.CTkFont(size=12),
            command=self.on_format_changed
        )
        self.combo_format.pack(fill="x", padx=16, pady=(0, 6))
        self.combo_format.set("📻 MP3 — Old Speaker / USB Mode (128k CBR, 44.1kHz)")

        self.lbl_format_hint = ctk.CTkLabel(
            card, text="Recommended: Formatted for older car USBs, boomboxes, and SD card MP3 players.",
            font=ctk.CTkFont(size=11), text_color="#888888", anchor="w"
        )
        self.lbl_format_hint.pack(fill="x", padx=16, pady=(0, 10))

        # 3. Analysis Preview Info Bar
        self.frame_analysis = ctk.CTkFrame(card, fg_color="#1e1e1e", corner_radius=4, border_width=1, border_color="#3c3c3c")
        self.lbl_an_title = ctk.CTkLabel(self.frame_analysis, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffffff", anchor="w")
        self.lbl_an_meta = ctk.CTkLabel(self.frame_analysis, text="", font=ctk.CTkFont(size=11), text_color="#4ec9b0", anchor="w")
        self.lbl_an_title.pack(fill="x", padx=12, pady=(6, 2))
        self.lbl_an_meta.pack(fill="x", padx=12, pady=(0, 6))

        # 4. Destination & Options Row
        opts_grid = ctk.CTkFrame(card, fg_color="transparent")
        opts_grid.pack(fill="x", padx=16, pady=(4, 10))
        opts_grid.grid_columnconfigure(0, weight=3)
        opts_grid.grid_columnconfigure(1, weight=1)

        # Dest folder
        lbl_dest = ctk.CTkLabel(opts_grid, text="DESTINATION FOLDER", font=ctk.CTkFont(size=10, weight="bold"), text_color="#999999")
        lbl_dest.grid(row=0, column=0, sticky="w", pady=(0, 2))

        dest_row = ctk.CTkFrame(opts_grid, fg_color="transparent")
        dest_row.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        self.entry_dest = ctk.CTkEntry(dest_row, height=30, font=ctk.CTkFont(size=11))
        self.entry_dest.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.entry_dest.insert(0, DEFAULT_SONGS)

        btn_browse = ctk.CTkButton(dest_row, text="Browse", width=65, height=30, fg_color="#3a3d41", hover_color="#45494e", command=self.browse_folder)
        btn_browse.pack(side="left")

        # Track limit
        lbl_limit = ctk.CTkLabel(opts_grid, text="TRACK LIMIT (OPTIONAL)", font=ctk.CTkFont(size=10, weight="bold"), text_color="#999999")
        lbl_limit.grid(row=0, column=1, sticky="w", pady=(0, 2))

        self.entry_limit = ctk.CTkEntry(opts_grid, placeholder_text="All tracks", height=30, font=ctk.CTkFont(size=11))
        self.entry_limit.grid(row=1, column=1, sticky="ew")

        # Ignore duplicates checkbox
        self.var_ignore_dups = ctk.BooleanVar(value=True)
        self.chk_dups = ctk.CTkCheckBox(
            card, text="Ignore duplicate downloads (automatically skips files already in the folder)",
            variable=self.var_ignore_dups, font=ctk.CTkFont(size=11)
        )
        self.chk_dups.pack(anchor="w", padx=16, pady=(0, 12))

        # 5. Action Row
        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.pack(fill="x", padx=16, pady=(0, 16))

        self.btn_download = ctk.CTkButton(
            action_row, text="▶  Start Download", height=38, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0e639c", hover_color="#1177bb", command=self.start_download
        )
        self.btn_download.pack(side="left", padx=(0, 10))

        self.btn_stop = ctk.CTkButton(
            action_row, text="◼  Stop Download", height=38, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#a12626", hover_color="#c43131", state="disabled", command=self.stop_download
        )
        self.btn_stop.pack(side="left", padx=(0, 10))

        btn_clear = ctk.CTkButton(
            action_row, text="Clear Logs", height=38, width=90, fg_color="#3a3d41", hover_color="#45494e", command=self.clear_logs
        )
        btn_clear.pack(side="left")

        # ---------------- 3. TERMINAL PANEL (Bottom Section) ----------------
        term_frame = ctk.CTkFrame(right_panel, corner_radius=6, fg_color="#1e1e1e", border_width=1, border_color="#333333")
        term_frame.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        term_frame.grid_rowconfigure(1, weight=1)
        term_frame.grid_columnconfigure(0, weight=1)

        # Progress Status Header
        prog_header = ctk.CTkFrame(term_frame, fg_color="#252526", corner_radius=0)
        prog_header.grid(row=0, column=0, sticky="ew")

        prog_top_row = ctk.CTkFrame(prog_header, fg_color="transparent")
        prog_top_row.pack(fill="x", padx=12, pady=(6, 2))

        self.lbl_progress_status = ctk.CTkLabel(prog_top_row, text="Ready to download", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffffff", anchor="w")
        self.lbl_progress_status.pack(side="left")

        self.lbl_progress_meta = ctk.CTkLabel(prog_top_row, text="0%", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4ec9b0", anchor="e")
        self.lbl_progress_meta.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(prog_header, height=6, progress_color="#007acc")
        self.progress_bar.pack(fill="x", padx=12, pady=(2, 8))
        self.progress_bar.set(0)

        # Monospace Terminal Console
        self.txt_terminal = ctk.CTkTextbox(
            term_frame, corner_radius=0, fg_color="#181818", text_color="#cccccc",
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.txt_terminal.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))

        self.append_log("[SYSTEM] YouTube Downloader initialized.")
        self.append_log("[SYSTEM] Paste a YouTube link above, choose your download option, and click Start Download.")

    # ---------------- UI Event Handlers ----------------

    def paste_from_clipboard(self):
        try:
            txt = self.clipboard_get().strip()
            if txt:
                self.entry_url.delete(0, "end")
                self.entry_url.insert(0, txt)
                if "youtube.com" in txt or "youtu.be" in txt:
                    self.trigger_analyze()
        except Exception:
            pass

    def on_format_changed(self, choice):
        selected_code = self.format_options_map.get(choice, "mp3_speaker")
        current_dest = self.entry_dest.get().strip()

        if selected_code.startswith("video_"):
            if current_dest.lower().endswith("songs"):
                self.set_destination(DEFAULT_VIDEOS)
            self.lbl_format_hint.configure(text="Downloads video as merged MP4 format with audio.")
        else:
            if current_dest.lower().endswith("videos"):
                self.set_destination(DEFAULT_SONGS)
            if selected_code == "mp3_speaker":
                self.lbl_format_hint.configure(text="Old Speaker Mode: 128k CBR MP3, 44.1kHz, ID3v2.3, FAT32 clean names.")
            else:
                self.lbl_format_hint.configure(text=f"High quality audio extraction ({selected_code.upper()}).")

        if self.current_analysis:
            self.update_analysis_meta(self.current_analysis)

    def set_destination(self, path):
        self.entry_dest.delete(0, "end")
        self.entry_dest.insert(0, path)
        self.update_storage_info()
        self.append_log(f"[INFO] Destination folder set to: {path}")

    def browse_folder(self):
        curr = self.entry_dest.get().strip() or DEFAULT_ROOT
        selected = filedialog.askdirectory(initialdir=curr, title="Select Download Folder")
        if selected:
            self.set_destination(os.path.normpath(selected))

    def update_storage_info(self):
        try:
            target_path = self.entry_dest.get().strip() or DEFAULT_ROOT
            drive = os.path.splitdrive(target_path)[0] or "C:"
            total, used, free = shutil.disk_usage(drive)
            free_gb = free / (1024**3)
            self.lbl_free_space.configure(text=f"Free: {free_gb:.1f} GB")
            self.lbl_drive.configure(text=f"Drive: {drive}")
        except Exception:
            pass

        if FFMPEG_EXE and os.path.exists(FFMPEG_EXE):
            self.lbl_ffmpeg_status.configure(text="Encoder: Ready (FFmpeg)", text_color="#4ec9b0")
        else:
            self.lbl_ffmpeg_status.configure(text="Encoder: Not Found", text_color="#f48771")

    def append_log(self, msg):
        self.log_queue.put(msg)

    def poll_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            t_str = time.strftime("%H:%M:%S")
            self.txt_terminal.insert("end", f"[{t_str}] {msg}\n")
            self.txt_terminal.see("end")
        self.after(100, self.poll_log_queue)

    def clear_logs(self):
        self.txt_terminal.delete("1.0", "end")
        self.append_log("[SYSTEM] Console cleared. Ready.")

    # ---------------- Link Analysis ----------------

    def trigger_analyze(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Notice", "Please paste a YouTube link first.")
            return

        self.btn_analyze.configure(state="disabled", text="Inspecting...")
        self.lbl_header_status.configure(text="● Analyzing link...", text_color="#569cd6")
        self.append_log(f"[ANALYSIS] Inspecting link: {url}")

        def worker():
            try:
                res = self.fetch_analysis(url)
                self.after(0, lambda: self.on_analysis_success(res))
            except Exception as e:
                self.after(0, lambda: self.on_analysis_error(str(e)))

        self.analysis_thread = threading.Thread(target=worker, daemon=True)
        self.analysis_thread.start()

    def fetch_analysis(self, url):
        ydl_opts = {'quiet': True, 'extract_flat': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            is_playlist = 'entries' in info
            entries = list(info.get('entries', [])) if is_playlist else [info]

            valid = []
            total_dur = 0
            for e in entries:
                t = e.get('title')
                dur = e.get('duration') or 0
                if t and not t.startswith('['):
                    valid.append({'id': e.get('id'), 'title': t, 'duration': dur})
                    total_dur += dur

            total_hours = total_dur / 3600
            dur_str = f"{int(total_hours)}h {int((total_dur%3600)/60)}m" if total_hours >= 1 else f"{int(total_dur/60)}m {int(total_dur%60)}s"

            return {
                "title": info.get('title') or "YouTube Media",
                "is_playlist": is_playlist,
                "track_count": len(valid),
                "duration_str": dur_str,
                "total_duration": total_dur
            }

    def on_analysis_success(self, res):
        self.current_analysis = res
        self.btn_analyze.configure(state="normal", text="Analyze")
        self.lbl_header_status.configure(text="● Ready", text_color="#4ec9b0")
        self.frame_analysis.pack(fill="x", padx=16, pady=(0, 10))
        self.update_analysis_meta(res)
        self.append_log(f"[SUCCESS] Analyzed: '{res['title']}' ({res['track_count']} items, {res['duration_str']})")

    def update_analysis_meta(self, res):
        chosen_format = self.format_options_map.get(self.combo_format.get(), "mp3_speaker")
        dur = res["total_duration"]

        if chosen_format.startswith("video_"):
            if chosen_format in ("video_720", "video_480"):
                mb = (320000 * dur) / (1024 * 1024)
            else:
                mb = (580000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            label = f"{res['track_count']} Items  •  {res['duration_str']}  •  Estimated Size: {est_str} (MP4 Video)"
        elif chosen_format == "mp3_320":
            mb = (40000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            label = f"{res['track_count']} Items  •  {res['duration_str']}  •  Estimated Size: {est_str} (320k MP3)"
        elif chosen_format == "mp3_192":
            mb = (24000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            label = f"{res['track_count']} Items  •  {res['duration_str']}  •  Estimated Size: {est_str} (192k MP3)"
        else:
            mb = (16000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            label = f"{res['track_count']} Items  •  {res['duration_str']}  •  Estimated Size: {est_str} (128k CBR MP3)"

        self.lbl_an_title.configure(text=res['title'])
        self.lbl_an_meta.configure(text=label)

    def on_analysis_error(self, err):
        self.btn_analyze.configure(state="normal", text="Analyze")
        self.lbl_header_status.configure(text="● Error", text_color="#f48771")
        self.append_log(f"[ERROR] Failed to inspect link: {err}")

    # ---------------- Download Engine ----------------

    def start_download(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Notice", "Please paste a YouTube link before downloading.")
            return

        dest_dir = self.entry_dest.get().strip()
        if not dest_dir:
            dest_dir = DEFAULT_SONGS

        chosen_label = self.combo_format.get()
        download_type = self.format_options_map.get(chosen_label, "mp3_speaker")
        ignore_dups = self.var_ignore_dups.get()

        max_tracks = 0
        limit_txt = self.entry_limit.get().strip()
        if limit_txt.isdigit():
            max_tracks = int(limit_txt)

        self.is_downloading = True
        self.stop_event.clear()
        self.btn_download.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_header_status.configure(text="● Downloading...", text_color="#569cd6")
        self.progress_bar.set(0)
        self.lbl_progress_status.configure(text="Starting download queue...")
        self.lbl_progress_meta.configure(text="0%")

        params = {
            "url": url,
            "dest_dir": dest_dir,
            "download_type": download_type,
            "ignore_dups": ignore_dups,
            "max_tracks": max_tracks
        }

        self.download_thread = threading.Thread(target=self.run_download_worker, args=(params,), daemon=True)
        self.download_thread.start()

    def stop_download(self):
        if self.is_downloading:
            self.stop_event.set()
            self.append_log("[USER] Requesting download stop...")
            self.lbl_progress_status.configure(text="Stopping...")

    def run_download_worker(self, params):
        url = params["url"]
        dest_dir = params["dest_dir"]
        download_type = params["download_type"]
        ignore_dups = params["ignore_dups"]
        max_tracks = params["max_tracks"]

        os.makedirs(dest_dir, exist_ok=True)

        is_video = download_type.startswith("video_")
        is_speaker = (download_type == "mp3_speaker")
        video_quality = download_type.replace("video_", "") if is_video else "1080"
        bitrate = "320" if download_type == "mp3_320" else ("192" if download_type == "mp3_192" else "128")

        self.append_log(f"[INFO] Target Folder: {dest_dir}")
        self.append_log(f"[INFO] Download Option: {download_type}")

        # Fetch entries
        ydl_opts = {'quiet': True, 'extract_flat': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.append_log(f"[ERROR] Failed to fetch playlist info: {e}")
            self.after(0, self.finish_download)
            return

        entries = list(info.get('entries', [])) if 'entries' in info else [info]

        # Scan existing files for duplicate check & index numbering
        if is_video:
            existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(('.mp4', '.mkv', '.webm'))]
        else:
            existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(('.mp3', '.m4a', '.opus'))]

        existing_keys = set()
        max_idx = 0
        for f in existing_files:
            m = re.match(r'^(\d+)\s*-\s*(.+)\.[a-z0-9]+$', f, re.IGNORECASE)
            if m:
                num = int(m.group(1))
                if num > max_idx:
                    max_idx = num
                existing_keys.add(get_core_title_key(m.group(2)))
            else:
                existing_keys.add(get_core_title_key(os.path.splitext(f)[0]))

        queue_items = []
        seen_keys = set()
        for idx, e in enumerate(entries, 1):
            vid = e.get('id')
            title = e.get('title')
            dur = e.get('duration') or 0
            if not vid or not title or title.startswith('['):
                continue
            k = get_core_title_key(title)
            if ignore_dups:
                if k in existing_keys:
                    self.append_log(f"[SKIP] Existing in folder: {title}")
                    continue
                if k in seen_keys:
                    self.append_log(f"[SKIP] Duplicate in playlist: {title}")
                    continue
            seen_keys.add(k)
            queue_items.append({'id': vid, 'title': title, 'duration': dur, 'key': k})
            if max_tracks > 0 and len(queue_items) >= max_tracks:
                break

        total_queue = len(queue_items)
        self.append_log(f"[INFO] Ready to download {total_queue} items.")

        if total_queue == 0:
            self.append_log("[INFO] No new items to download (all skipped or up-to-date).")
            self.after(0, self.finish_download)
            return

        current_idx = 0
        def progress_hook(d):
            if self.stop_event.is_set():
                raise yt_dlp.utils.DownloadCancelled("Download stopped by user.")
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                speed = d.get('speed') or 0
                speed_str = f"{speed / (1024*1024):.1f} MB/s" if speed else ""
                eta = d.get('eta') or 0
                eta_str = f"ETA: {eta}s" if eta else ""
                if total > 0:
                    sub_pct = (downloaded / total) * 100
                    base_pct = ((current_idx - 1) / total_queue) * 100
                    total_pct = min(99.9, base_pct + (sub_pct / total_queue))
                    self.after(0, lambda: self.update_progress_ui(total_pct, speed_str, eta_str))

        start_num = max_idx + 1
        downloaded_count = 0

        for i, item in enumerate(queue_items):
            if self.stop_event.is_set():
                self.append_log("[WARN] Download stopped by user.")
                break

            current_idx = i + 1
            track_num = start_num + i
            cleaned = clean_filename(item['title'], track_num)
            filename_base = f"{track_num:03d} - {cleaned}"

            self.after(0, lambda n=current_idx, t=total_queue, name=item['title']: self.lbl_progress_status.configure(
                text=f"[{n}/{t}] Downloading: {name[:50]}"
            ))
            self.append_log(f"[DOWNLOAD] [{current_idx}/{total_queue}] Starting: {item['title']}")

            if is_video:
                if video_quality == 'best':
                    fmt_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
                elif video_quality == '720':
                    fmt_str = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best'
                elif video_quality == '480':
                    fmt_str = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best'
                else:
                    fmt_str = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best'

                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'ffmpeg_location': FFMPEG_EXE,
                    'format': fmt_str,
                    'merge_output_format': 'mp4',
                    'outtmpl': os.path.join(dest_dir, f"{filename_base}.%(ext)s"),
                    'progress_hooks': [progress_hook],
                }
            else:
                postprocessors = []
                postprocessor_args = []
                if is_speaker:
                    postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'})
                    postprocessor_args = ['-ar', '44100', '-ac', '2', '-id3v2_version', '3', '-write_id3v1', '1', '-vn']
                elif download_type == 'm4a':
                    postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a', 'preferredquality': '128'})
                else:
                    postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': bitrate})
                    postprocessor_args = ['-ar', '44100', '-id3v2_version', '3', '-vn']

                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'ffmpeg_location': FFMPEG_EXE,
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(dest_dir, f"{filename_base}.%(ext)s"),
                    'progress_hooks': [progress_hook],
                    'postprocessors': postprocessors,
                    'postprocessor_args': postprocessor_args
                }

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={item['id']}"])
                downloaded_count += 1
                self.append_log(f"[SUCCESS] Saved: {filename_base}")
            except Exception as e:
                if self.stop_event.is_set():
                    break
                self.append_log(f"[ERROR] Failed to download {item['title']}: {e}")

        self.append_log(f"[COMPLETE] Finished. Downloaded {downloaded_count} tracks.")
        self.after(0, self.finish_download)

    def update_progress_ui(self, pct, speed, eta):
        self.progress_bar.set(pct / 100.0)
        meta_str = f"{round(pct)}%"
        if speed:
            meta_str = f"{speed}  •  {meta_str}"
        if eta:
            meta_str = f"{meta_str}  •  {eta}"
        self.lbl_progress_meta.configure(text=meta_str)

    def finish_download(self):
        self.is_downloading = False
        self.btn_download.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_header_status.configure(text="● Ready", text_color="#4ec9b0")
        self.lbl_progress_status.configure(text="Download finished.")
        self.progress_bar.set(1.0)
        self.lbl_progress_meta.configure(text="100%")
        self.update_storage_info()

    def on_closing(self):
        if self.is_downloading:
            if messagebox.askyesno("Exit", "A download is currently running. Are you sure you want to exit?"):
                self.stop_event.set()
                self.destroy()
        else:
            self.destroy()


if __name__ == '__main__':
    app = YouTubeDownloaderApp()
    app.mainloop()
