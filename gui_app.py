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
        self.geometry("1180x820")
        self.minsize(1000, 760)

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
        """Build the main desktop UI with a focused, consumer-app layout."""
        self.configure(fg_color="#0B1020")
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Palette is intentionally centralized here so the whole app feels cohesive.
        self.ui = {
            "bg": "#0B1020",
            "sidebar": "#0F172A",
            "panel": "#111827",
            "panel_alt": "#172033",
            "border": "#263247",
            "text": "#F8FAFC",
            "muted": "#94A3B8",
            "accent": "#6D7CFF",
            "accent_hover": "#5968F0",
            "green": "#34D399",
            "red": "#F87171",
            "amber": "#FBBF24",
        }

        # Top bar
        top_bar = ctk.CTkFrame(self, height=72, corner_radius=0, fg_color=self.ui["bg"])
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)
        top_bar.grid_propagate(False)

        logo = ctk.CTkFrame(top_bar, width=42, height=42, corner_radius=13,
                             fg_color=self.ui["accent"])
        logo.grid(row=0, column=0, padx=(22, 12), pady=14)
        logo.grid_propagate(False)
        ctk.CTkLabel(logo, text="↓", font=ctk.CTkFont(size=28, weight="bold"),
                     text_color="#FFFFFF").place(relx=0.5, rely=0.46, anchor="center")

        brand = ctk.CTkFrame(top_bar, fg_color="transparent")
        brand.grid(row=0, column=1, sticky="w", pady=10)
        ctk.CTkLabel(brand, text="YouTube Downloader",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=self.ui["text"]).pack(anchor="w")
        ctk.CTkLabel(brand, text="Audio and video, without the clutter",
                     font=ctk.CTkFont(size=11), text_color=self.ui["muted"]).pack(anchor="w", pady=(1, 0))

        status_pill = ctk.CTkFrame(top_bar, corner_radius=11, fg_color=self.ui["panel_alt"])
        status_pill.grid(row=0, column=2, padx=22, pady=18, sticky="e")
        self.lbl_header_status = ctk.CTkLabel(
            status_pill, text="● Ready", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.ui["green"]
        )
        self.lbl_header_status.pack(padx=13, pady=7)

        # Workspace: compact destination sidebar + main download flow.
        workbench = ctk.CTkFrame(self, corner_radius=0, fg_color=self.ui["bg"])
        workbench.grid(row=1, column=0, sticky="nsew")
        workbench.grid_rowconfigure(0, weight=1)
        workbench.grid_columnconfigure(0, weight=0)
        workbench.grid_columnconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(workbench, width=220, corner_radius=0, fg_color=self.ui["sidebar"])
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        sidebar.grid_propagate(False)

        ctk.CTkLabel(sidebar, text="LIBRARY", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self.ui["muted"]).pack(anchor="w", padx=18, pady=(22, 10))
        ctk.CTkLabel(sidebar, text="Quick destinations", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=self.ui["text"]).pack(anchor="w", padx=18, pady=(0, 8))

        self.btn_dest_songs = ctk.CTkButton(
            sidebar, text="♫   Music folder", anchor="w", height=39, corner_radius=10,
            font=ctk.CTkFont(size=12), fg_color=self.ui["panel_alt"], hover_color="#26334B",
            text_color=self.ui["text"], command=lambda: self.set_destination(DEFAULT_SONGS)
        )
        self.btn_dest_songs.pack(fill="x", padx=10, pady=3)

        self.btn_dest_videos = ctk.CTkButton(
            sidebar, text="▣   Video folder", anchor="w", height=39, corner_radius=10,
            font=ctk.CTkFont(size=12), fg_color="transparent", hover_color="#1B2940",
            text_color="#CBD5E1", command=lambda: self.set_destination(DEFAULT_VIDEOS)
        )
        self.btn_dest_videos.pack(fill="x", padx=10, pady=3)

        self.btn_dest_root = ctk.CTkButton(
            sidebar, text="⌂   Main folder", anchor="w", height=39, corner_radius=10,
            font=ctk.CTkFont(size=12), fg_color="transparent", hover_color="#1B2940",
            text_color="#CBD5E1", command=lambda: self.set_destination(DEFAULT_ROOT)
        )
        self.btn_dest_root.pack(fill="x", padx=10, pady=3)

        ctk.CTkButton(
            sidebar, text="＋   Choose another folder", anchor="w", height=37, corner_radius=10,
            font=ctk.CTkFont(size=11), fg_color="transparent", hover_color="#1B2940",
            text_color=self.ui["muted"], border_width=1, border_color=self.ui["border"],
            command=self.browse_folder
        ).pack(fill="x", padx=10, pady=(12, 4))

        # Storage information is secondary, so it lives in a quiet card at the bottom.
        storage_card = ctk.CTkFrame(sidebar, corner_radius=13, fg_color=self.ui["panel"],
                                     border_width=1, border_color=self.ui["border"])
        storage_card.pack(side="bottom", fill="x", padx=12, pady=16)
        ctk.CTkLabel(storage_card, text="SYSTEM STATUS", font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=self.ui["muted"]).pack(anchor="w", padx=12, pady=(12, 7))
        self.lbl_free_space = ctk.CTkLabel(storage_card, text="Free space: --",
                                           font=ctk.CTkFont(size=11, weight="bold"),
                                           text_color=self.ui["text"], anchor="w")
        self.lbl_free_space.pack(fill="x", padx=12, pady=2)
        self.lbl_drive = ctk.CTkLabel(storage_card, text="Drive: --",
                                      font=ctk.CTkFont(size=10), text_color=self.ui["muted"], anchor="w")
        self.lbl_drive.pack(fill="x", padx=12, pady=2)
        self.lbl_ffmpeg_status = ctk.CTkLabel(storage_card, text="FFmpeg: Checking…",
                                              font=ctk.CTkFont(size=10), text_color=self.ui["green"], anchor="w")
        self.lbl_ffmpeg_status.pack(fill="x", padx=12, pady=(2, 12))

        # Main workspace area.
        right_panel = ctk.CTkFrame(workbench, corner_radius=0, fg_color=self.ui["bg"])
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(2, weight=1)

        hero = ctk.CTkFrame(right_panel, fg_color="transparent")
        hero.grid(row=0, column=0, sticky="ew", padx=24, pady=(17, 14))
        ctk.CTkLabel(hero, text="What would you like to save?",
                     font=ctk.CTkFont(size=24, weight="bold"), text_color=self.ui["text"]).pack(anchor="w")
        ctk.CTkLabel(hero, text="Paste a video or playlist link, choose a format, and you're set.",
                     font=ctk.CTkFont(size=12), text_color=self.ui["muted"]).pack(anchor="w", pady=(4, 0))

        # The main action card keeps the key decisions in a single, clear sequence.
        card = ctk.CTkFrame(right_panel, corner_radius=16, fg_color=self.ui["panel"],
                            border_width=1, border_color=self.ui["border"])
        card.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        ctk.CTkLabel(card, text="01  /  SOURCE LINK", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self.ui["muted"]).pack(anchor="w", padx=18, pady=(16, 7))

        url_row = ctk.CTkFrame(card, fg_color="transparent")
        url_row.pack(fill="x", padx=18, pady=(0, 14))
        self.entry_url = ctk.CTkEntry(
            url_row, placeholder_text="Paste a YouTube video or playlist URL…", height=42,
            corner_radius=10, border_width=1, border_color=self.ui["border"],
            fg_color="#0B1220", text_color=self.ui["text"],
            placeholder_text_color="#64748B", font=ctk.CTkFont(size=12)
        )
        self.entry_url.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_url.bind("<Return>", lambda _event: self.trigger_analyze())
        ctk.CTkButton(
            url_row, text="Paste", width=68, height=42, corner_radius=10,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color=self.ui["panel_alt"],
            hover_color="#26334B", text_color=self.ui["text"], command=self.paste_from_clipboard
        ).pack(side="left", padx=(0, 8))
        self.btn_analyze = ctk.CTkButton(
            url_row, text="Inspect link", width=104, height=42, corner_radius=10,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color=self.ui["accent"],
            hover_color=self.ui["accent_hover"], text_color="#FFFFFF", command=self.trigger_analyze
        )
        self.btn_analyze.pack(side="left")

        # Preview is only shown after successful inspection.
        self.frame_analysis = ctk.CTkFrame(card, corner_radius=11, fg_color="#0E1D2A",
                                            border_width=1, border_color="#1E4A45")
        preview_inner = ctk.CTkFrame(self.frame_analysis, fg_color="transparent")
        preview_inner.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(preview_inner, text="LINK DETAILS", font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=self.ui["green"]).pack(anchor="w", pady=(0, 3))
        self.lbl_an_title = ctk.CTkLabel(preview_inner, text="", font=ctk.CTkFont(size=12, weight="bold"),
                                         text_color=self.ui["text"], anchor="w", justify="left", wraplength=650)
        self.lbl_an_title.pack(fill="x", anchor="w")
        self.lbl_an_meta = ctk.CTkLabel(preview_inner, text="", font=ctk.CTkFont(size=10),
                                        text_color="#A7F3D0", anchor="w", justify="left", wraplength=650)
        self.lbl_an_meta.pack(fill="x", anchor="w", pady=(3, 0))
        self.frame_analysis.pack_forget()

        self.lbl_output_section = ctk.CTkLabel(
            card, text="02  /  OUTPUT FORMAT", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.ui["muted"]
        )
        self.lbl_output_section.pack(anchor="w", padx=18, pady=(1, 7))
        self.format_options_map = {
            "MP3 · USB / Speaker (128 kbps)": "mp3_speaker",
            "MP3 · Maximum quality (320 kbps)": "mp3_320",
            "MP3 · High quality (192 kbps)": "mp3_192",
            "M4A · Original audio stream": "m4a",
            "MP4 · 1080p Full HD": "video_1080",
            "MP4 · 720p HD": "video_720",
            "MP4 · Best available quality": "video_best",
            "MP4 · 480p": "video_480",
        }
        self.combo_format = ctk.CTkComboBox(
            card, values=list(self.format_options_map.keys()), height=40, corner_radius=10,
            border_width=1, border_color=self.ui["border"], fg_color="#0B1220",
            button_color=self.ui["panel_alt"], button_hover_color="#26334B",
            dropdown_fg_color=self.ui["panel"], dropdown_hover_color=self.ui["panel_alt"],
            text_color=self.ui["text"], font=ctk.CTkFont(size=12),
            dropdown_font=ctk.CTkFont(size=11), command=self.on_format_changed
        )
        self.combo_format.pack(fill="x", padx=18)
        self.combo_format.set("MP3 · USB / Speaker (128 kbps)")
        self.lbl_format_hint = ctk.CTkLabel(
            card, text="Made for older car stereos, USB speakers, and MP3 players.",
            font=ctk.CTkFont(size=10), text_color=self.ui["muted"], anchor="w"
        )
        self.lbl_format_hint.pack(fill="x", padx=20, pady=(5, 12))

        # Save location + optional playlist cap.
        opts_grid = ctk.CTkFrame(card, fg_color="transparent")
        opts_grid.pack(fill="x", padx=18, pady=(0, 12))
        opts_grid.grid_columnconfigure(0, weight=3)
        opts_grid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(opts_grid, text="SAVE TO", font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=self.ui["muted"]).grid(row=0, column=0, sticky="w", pady=(0, 5))
        ctk.CTkLabel(opts_grid, text="ITEM LIMIT", font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=self.ui["muted"]).grid(row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 5))

        dest_row = ctk.CTkFrame(opts_grid, fg_color="transparent")
        dest_row.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.entry_dest = ctk.CTkEntry(
            dest_row, height=36, corner_radius=9, border_width=1,
            border_color=self.ui["border"], fg_color="#0B1220", text_color=self.ui["text"],
            font=ctk.CTkFont(size=10)
        )
        self.entry_dest.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_dest.insert(0, DEFAULT_SONGS)
        self.entry_dest.bind("<FocusOut>", lambda _event: (self.update_storage_info(), self.update_sidebar_selection()))
        ctk.CTkButton(
            dest_row, text="Browse", width=68, height=36, corner_radius=9,
            font=ctk.CTkFont(size=10, weight="bold"), fg_color=self.ui["panel_alt"],
            hover_color="#26334B", text_color=self.ui["text"], command=self.browse_folder
        ).pack(side="left")

        self.entry_limit = ctk.CTkEntry(
            opts_grid, placeholder_text="All items", height=36, corner_radius=9,
            border_width=1, border_color=self.ui["border"], fg_color="#0B1220",
            text_color=self.ui["text"], placeholder_text_color="#64748B", font=ctk.CTkFont(size=11)
        )
        self.entry_limit.grid(row=1, column=1, sticky="ew", padx=(10, 0))

        self.var_ignore_dups = ctk.BooleanVar(value=True)
        self.chk_dups = ctk.CTkCheckBox(
            card, text="Skip files that already exist in the destination folder",
            variable=self.var_ignore_dups, font=ctk.CTkFont(size=11),
            text_color="#CBD5E1", fg_color=self.ui["accent"], hover_color=self.ui["accent_hover"],
            border_color="#64748B", checkmark_color="#FFFFFF"
        )
        self.chk_dups.pack(anchor="w", padx=18, pady=(0, 13))

        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.pack(fill="x", padx=18, pady=(0, 16))
        self.btn_download = ctk.CTkButton(
            action_row, text="↓   Start download", height=43, corner_radius=11,
            font=ctk.CTkFont(size=13, weight="bold"), fg_color=self.ui["accent"],
            hover_color=self.ui["accent_hover"], text_color="#FFFFFF", command=self.start_download
        )
        self.btn_download.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.btn_stop = ctk.CTkButton(
            action_row, text="Stop", width=94, height=43, corner_radius=11,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color="#3A1D2A",
            hover_color="#582438", text_color="#FDA4AF", state="disabled", command=self.stop_download
        )
        self.btn_stop.pack(side="left")

        # Progress and logs are grouped into one quieter activity panel.
        term_frame = ctk.CTkFrame(right_panel, corner_radius=16, fg_color=self.ui["panel"],
                                  border_width=1, border_color=self.ui["border"])
        term_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 18))
        term_frame.grid_columnconfigure(0, weight=1)
        term_frame.grid_rowconfigure(3, weight=1)

        prog_top_row = ctk.CTkFrame(term_frame, fg_color="transparent")
        prog_top_row.grid(row=0, column=0, sticky="ew", padx=15, pady=(12, 4))
        prog_top_row.grid_columnconfigure(0, weight=1)
        self.lbl_progress_status = ctk.CTkLabel(
            prog_top_row, text="Ready for your first download", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.ui["text"], anchor="w"
        )
        self.lbl_progress_status.grid(row=0, column=0, sticky="w")
        self.lbl_progress_meta = ctk.CTkLabel(
            prog_top_row, text="0%", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.ui["green"], anchor="e"
        )
        self.lbl_progress_meta.grid(row=0, column=1, sticky="e", padx=(12, 0))

        self.progress_bar = ctk.CTkProgressBar(
            term_frame, height=7, corner_radius=4, progress_color=self.ui["accent"],
            fg_color="#253047"
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        self.progress_bar.set(0)

        log_header = ctk.CTkFrame(term_frame, fg_color="transparent")
        log_header.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 5))
        log_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_header, text="ACTIVITY", font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=self.ui["muted"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            log_header, text="Clear", width=52, height=23, corner_radius=7,
            font=ctk.CTkFont(size=9), fg_color="transparent", hover_color=self.ui["panel_alt"],
            text_color=self.ui["muted"], command=self.clear_logs
        ).grid(row=0, column=1, sticky="e")
        self.txt_terminal = ctk.CTkTextbox(
            term_frame, corner_radius=9, fg_color="#0A101D", text_color="#C4D0E0",
            border_width=1, border_color="#202B40", font=ctk.CTkFont(family="Consolas", size=10),
            activate_scrollbars=True
        )
        self.txt_terminal.grid(row=3, column=0, sticky="nsew", padx=15, pady=(0, 13))

        self.append_log("[SYSTEM] YouTube Downloader is ready.")
        self.append_log("[TIP] Paste a YouTube link, inspect it, then start your download.")
        self.update_sidebar_selection()

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
            if current_dest.lower().endswith(("songs", "music")):
                self.set_destination(DEFAULT_VIDEOS)
            hints = {
                "video_1080": "Full HD video. FFmpeg merges video and audio into MP4.",
                "video_720": "HD video. A good balance of quality and file size.",
                "video_480": "Smaller MP4 files for slower connections or limited storage.",
                "video_best": "Choose the best available quality; final resolution depends on the source.",
            }
            self.lbl_format_hint.configure(text=hints.get(selected_code, "Downloads video as MP4."))
        else:
            if current_dest.lower().endswith(("videos", "video")):
                self.set_destination(DEFAULT_SONGS)
            if selected_code == "mp3_speaker":
                hint = "Made for older car stereos, USB speakers, and MP3 players."
            elif selected_code == "mp3_320":
                hint = "Higher-bitrate MP3 for maximum everyday audio quality."
            elif selected_code == "mp3_192":
                hint = "A smaller MP3 file with good audio quality."
            else:
                hint = "Keeps the source audio stream in M4A where available."
            self.lbl_format_hint.configure(text=hint)

        if self.current_analysis:
            self.update_analysis_meta(self.current_analysis)
        self.update_sidebar_selection()

    def set_destination(self, path):
        self.entry_dest.delete(0, "end")
        self.entry_dest.insert(0, path)
        self.update_storage_info()
        self.update_sidebar_selection()
        self.append_log(f"[INFO] Destination folder set to: {path}")

    def update_sidebar_selection(self):
        """Highlight the quick destination that matches the current output path."""
        if not hasattr(self, "entry_dest"):
            return
        try:
            current = os.path.normcase(os.path.abspath(self.entry_dest.get().strip()))
            presets = [
                (self.btn_dest_songs, DEFAULT_SONGS),
                (self.btn_dest_videos, DEFAULT_VIDEOS),
                (self.btn_dest_root, DEFAULT_ROOT),
            ]
            for button, path in presets:
                active = current == os.path.normcase(os.path.abspath(path))
                button.configure(
                    fg_color=self.ui["panel_alt"] if active else "transparent",
                    text_color=self.ui["text"] if active else "#CBD5E1"
                )
        except Exception:
            pass

    def browse_folder(self):
        curr = self.entry_dest.get().strip() or DEFAULT_ROOT
        selected = filedialog.askdirectory(initialdir=curr, title="Select Download Folder")
        if selected:
            self.set_destination(os.path.normpath(selected))

    def update_storage_info(self):
        try:
            target_path = self.entry_dest.get().strip() or DEFAULT_ROOT
            absolute_path = os.path.abspath(target_path)
            drive = os.path.splitdrive(absolute_path)[0]
            usage_path = f"{drive}{os.sep}" if drive else (target_path or os.getcwd())
            total, used, free = shutil.disk_usage(usage_path)
            free_gb = free / (1024 ** 3)
            self.lbl_free_space.configure(text=f"Free space: {free_gb:.1f} GB")
            self.lbl_drive.configure(text=f"Drive: {drive or os.path.split(absolute_path)[0] or os.sep}")
        except Exception:
            self.lbl_free_space.configure(text="Free space: unavailable")
            self.lbl_drive.configure(text="Drive: unavailable")

        if FFMPEG_EXE and os.path.exists(FFMPEG_EXE):
            self.lbl_ffmpeg_status.configure(text="FFmpeg: Ready", text_color=self.ui["green"])
        else:
            self.lbl_ffmpeg_status.configure(text="FFmpeg: Not found", text_color=self.ui["red"])

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

        self.btn_analyze.configure(state="disabled", text="Inspecting…")
        self.lbl_header_status.configure(text="● Inspecting", text_color=self.ui["accent"])
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
            raw_entries = info.get('entries')
            is_playlist = raw_entries is not None
            entries = list(raw_entries) if is_playlist else [info]

            valid = []
            total_dur = 0
            for e in entries:
                if not isinstance(e, dict):
                    continue
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
        self.btn_analyze.configure(state="normal", text="Inspect link")
        self.lbl_header_status.configure(text="● Ready", text_color=self.ui["green"])
        self.frame_analysis.pack(fill="x", padx=18, pady=(0, 14), before=self.lbl_output_section)
        self.update_analysis_meta(res)
        self.append_log(f"[SUCCESS] Analyzed: '{res['title']}' ({res['track_count']} items, {res['duration_str']})")

    def update_analysis_meta(self, res):
        chosen_format = self.format_options_map.get(self.combo_format.get(), "mp3_speaker")
        dur = res["total_duration"]

        # These are intentionally presented as rough estimates, not exact file sizes.
        if chosen_format.startswith("video_"):
            bitrate_bps = {
                "video_480": 900_000,
                "video_720": 2_500_000,
                "video_1080": 4_500_000,
                "video_best": 5_000_000,
            }.get(chosen_format, 2_500_000)
            suffix = "MP4 video"
        elif chosen_format == "mp3_320":
            bitrate_bps, suffix = 320000, "MP3 audio"
        elif chosen_format == "mp3_192":
            bitrate_bps, suffix = 192000, "MP3 audio"
        elif chosen_format == "m4a":
            bitrate_bps, suffix = 160000, "M4A audio"
        else:
            bitrate_bps, suffix = 128000, "MP3 audio"

        mb = (bitrate_bps * dur) / (8 * 1024 * 1024)
        est_str = f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
        kind = "Playlist" if res.get("is_playlist") else "Video"
        self.lbl_an_title.configure(text=res["title"])
        self.lbl_an_meta.configure(
            text=f"{kind}  ·  {res['track_count']} item(s)  ·  {res['duration_str']}  ·  Approx. {est_str} ({suffix})"
        )

    def on_analysis_error(self, err):
        self.btn_analyze.configure(state="normal", text="Inspect link")
        self.lbl_header_status.configure(text="● Link error", text_color=self.ui["red"])
        self.current_analysis = None
        self.frame_analysis.pack_forget()
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
        self.lbl_header_status.configure(text="● Downloading", text_color=self.ui["accent"])
        self.progress_bar.set(0)
        self.lbl_progress_status.configure(text="Preparing download queue…")
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
            self.lbl_progress_status.configure(text="Stopping download…")

    def run_download_worker(self, params):
        url = params["url"]
        dest_dir = params["dest_dir"]
        download_type = params["download_type"]
        ignore_dups = params["ignore_dups"]
        max_tracks = params["max_tracks"]

        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            self.append_log(f"[ERROR] Cannot create destination folder: {e}")
            self.after(0, lambda: self.finish_download("error", "Cannot create the destination folder."))
            return

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
            self.after(0, lambda: self.finish_download("error", "Could not read the media link."))
            return

        raw_entries = info.get('entries')
        entries = list(raw_entries) if raw_entries is not None else [info]

        # Scan existing files for duplicate check & index numbering.
        try:
            if is_video:
                existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(('.mp4', '.mkv', '.webm'))]
            else:
                existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(('.mp3', '.m4a', '.opus'))]
        except Exception as e:
            self.append_log(f"[ERROR] Cannot inspect destination folder: {e}")
            self.after(0, lambda: self.finish_download("error", "Cannot inspect the destination folder."))
            return

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
            if not isinstance(e, dict):
                continue
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
            self.after(0, lambda: self.finish_download("idle", "Nothing new to download."))
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
                    self.after(0, lambda pct=total_pct, sp=speed_str, et=eta_str: self.update_progress_ui(pct, sp, et))

        start_num = max_idx + 1
        downloaded_count = 0
        failed_count = 0
        was_stopped = False

        for i, item in enumerate(queue_items):
            if self.stop_event.is_set():
                was_stopped = True
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
                    was_stopped = True
                    break
                failed_count += 1
                self.append_log(f"[ERROR] Failed to download {item['title']}: {e}")

        if was_stopped or self.stop_event.is_set():
            self.append_log(f"[STOPPED] Download stopped. Saved {downloaded_count} item(s) before stopping.")
            self.after(0, lambda: self.finish_download("stopped", "Download stopped."))
        elif failed_count and downloaded_count:
            self.append_log(f"[PARTIAL] Saved {downloaded_count}; failed {failed_count} item(s).")
            self.after(0, lambda: self.finish_download("partial", "Finished with some errors."))
        elif failed_count:
            self.append_log(f"[ERROR] Could not download any items ({failed_count} failed).")
            self.after(0, lambda: self.finish_download("error", "Downloads failed. Check the activity log."))
        else:
            self.append_log(f"[COMPLETE] Finished. Downloaded {downloaded_count} item(s).")
            self.after(0, lambda: self.finish_download("complete", f"Finished — {downloaded_count} item(s) saved."))

    def update_progress_ui(self, pct, speed, eta):
        self.progress_bar.set(max(0.0, min(1.0, pct / 100.0)))
        meta_str = f"{round(pct)}%"
        if speed:
            meta_str = f"{speed}  ·  {meta_str}"
        if eta:
            meta_str = f"{meta_str}  ·  {eta}"
        self.lbl_progress_meta.configure(text=meta_str)

    def finish_download(self, outcome="complete", message=None):
        self.is_downloading = False
        self.btn_download.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.update_storage_info()

        if outcome == "complete":
            self.lbl_header_status.configure(text="● Complete", text_color=self.ui["green"])
            self.lbl_progress_status.configure(text=message or "Download finished.")
            self.progress_bar.set(1.0)
            self.lbl_progress_meta.configure(text="100%")
        elif outcome == "partial":
            self.lbl_header_status.configure(text="● Partial", text_color=self.ui["amber"])
            self.lbl_progress_status.configure(text=message or "Finished with some errors.")
            self.progress_bar.set(1.0)
            self.lbl_progress_meta.configure(text="Done · partial")
        elif outcome == "stopped":
            self.lbl_header_status.configure(text="● Stopped", text_color=self.ui["amber"])
            self.lbl_progress_status.configure(text=message or "Download stopped.")
            self.lbl_progress_meta.configure(text="Stopped")
        elif outcome == "idle":
            self.lbl_header_status.configure(text="● Ready", text_color=self.ui["green"])
            self.lbl_progress_status.configure(text=message or "Nothing new to download.")
            self.progress_bar.set(0)
            self.lbl_progress_meta.configure(text="0%")
        else:
            self.lbl_header_status.configure(text="● Error", text_color=self.ui["red"])
            self.lbl_progress_status.configure(text=message or "Download failed. Check the activity log.")
            self.lbl_progress_meta.configure(text="Error")

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
