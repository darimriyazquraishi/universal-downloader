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

# Primary Font Configuration
FONT_FAMILY = "Sebino Soft Regular"

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
        self.geometry("1160x820")
        self.minsize(1020, 720)

        # State Variables
        self.stop_event = threading.Event()
        self.download_thread = None
        self.analysis_thread = None
        self.log_queue = queue.Queue()
        self.current_analysis = None
        self.is_downloading = False
        self.current_mode = "audio" # "audio" or "video"

        # Download Manager items state
        self.manager_items = {} # title -> dict(card_widget, status_lbl, path)

        # Format mappings
        self.audio_formats = {
            "MP3 · Old Speaker / USB (128 kbps CBR, 44.1kHz, ID3v2.3)": "mp3_speaker",
            "MP3 · Maximum Quality (320 kbps)": "mp3_320",
            "MP3 · High Quality (192 kbps)": "mp3_192",
            "M4A · Original AAC Audio Stream": "m4a"
        }
        self.video_formats = {
            "MP4 Video · 1080p Full HD": "video_1080",
            "MP4 Video · 720p HD": "video_720",
            "MP4 Video · Best Available Quality": "video_best",
            "MP4 Video · 480p": "video_480"
        }
        self.all_formats = {**self.audio_formats, **self.video_formats}

        # Build UI Components
        self.create_layout()
        self.load_initial_downloads()
        self.poll_log_queue()

        # Handle clean exit
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_layout(self):
        """
        Luxurious Gold + Sebino Soft Design System:
        - Primary typography: Sebino Soft Regular
        - Color palette: Deep obsidian canvas (#09090B) with rich gold accents (#D4AF37, #E5C158)
        - Absolutely no red colors anywhere
        - Top header is clean and minimal (no engine online pill)
        - Left sidebar is a dedicated Download Manager (active downloads & saved history)
        - Quick destination selector in main panel
        - 3-Column live telemetry HUD (Speed, ETA, Progress) in Gold
        """
        self.configure(fg_color="#09090B")
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Workbench
        self.grid_columnconfigure(0, weight=1)

        # Style Tokens
        self.tokens = {
            "bg": "#09090B",
            "sidebar": "#0C0A0E",
            "surface": "#121217",
            "surface_elevated": "#181820",
            "surface_hover": "#22222D",
            "border": "#27272A",
            "border_strong": "#3F3F46",
            "text_primary": "#FAFAFA",
            "text_secondary": "#A1A1AA",
            "text_muted": "#71717A",
            # Luxurious Gold Accent Palette
            "gold": "#D4AF37",
            "gold_bright": "#E5C158",
            "gold_hover": "#F0CE68",
            "gold_dark": "#261F0E",
            "gold_subtle": "#17140B",
            "gold_border": "#63501E",
            "gold_border_bright": "#D4AF37",
            "gold_text_dark": "#0E0C06",
            "emerald": "#10B981",
            "cyan": "#06B6D4",
            "amber": "#F59E0B",
            "pill_bg": "#16161D",
        }

        # ---------------- 1. TOP HEADER (Clean, Minimal, No Engine Status) ----------------
        top_bar = ctk.CTkFrame(
            self, height=52, corner_radius=0,
            fg_color=self.tokens["bg"],
            border_width=1, border_color=self.tokens["border"]
        )
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)
        top_bar.grid_propagate(False)

        # Brand Mark
        brand_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=18, pady=9, sticky="w")

        lbl_logo = ctk.CTkLabel(
            brand_frame, text="⚡",
            font=ctk.CTkFont(size=15)
        )
        lbl_logo.pack(side="left", padx=(0, 8))

        lbl_title = ctk.CTkLabel(
            brand_frame, text="YOUTUBE DOWNLOADER",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=self.tokens["text_primary"]
        )
        lbl_title.pack(side="left")

        lbl_tag = ctk.CTkLabel(
            brand_frame, text="· NATIVE DESKTOP SUITE",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=self.tokens["text_muted"]
        )
        lbl_tag.pack(side="left", padx=8)

        # Right side: Minimal version mark (Engine Online removed as requested)
        lbl_ver = ctk.CTkLabel(
            top_bar, text="v1.3.0",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=self.tokens["text_muted"]
        )
        lbl_ver.grid(row=0, column=2, padx=18, pady=9, sticky="e")

        # ---------------- 2. WORKBENCH ----------------
        workbench = ctk.CTkFrame(self, corner_radius=0, fg_color=self.tokens["bg"])
        workbench.grid(row=1, column=0, sticky="nsew")
        workbench.grid_rowconfigure(0, weight=1)
        workbench.grid_columnconfigure(0, weight=0) # Sidebar: Download Manager
        workbench.grid_columnconfigure(1, weight=1) # Main Viewport

        # ---------------- LEFT SIDEBAR: DOWNLOAD MANAGER ----------------
        sidebar = ctk.CTkFrame(
            workbench, width=280, corner_radius=0,
            fg_color=self.tokens["sidebar"],
            border_width=1, border_color=self.tokens["border"]
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(1, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        # Header for Download Manager
        dm_header = ctk.CTkFrame(sidebar, fg_color="transparent")
        dm_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(16, 8))
        dm_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dm_header, text="DOWNLOAD MANAGER",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=self.tokens["gold"]
        ).grid(row=0, column=0, sticky="w")

        self.lbl_dm_count = ctk.CTkLabel(
            dm_header, text="0 items",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=self.tokens["text_muted"]
        )
        self.lbl_dm_count.grid(row=0, column=1, sticky="e")

        # Scrollable List of Downloads
        self.scroll_manager = ctk.CTkScrollableFrame(
            sidebar, corner_radius=0,
            fg_color="transparent",
            scrollbar_button_color=self.tokens["surface_elevated"],
            scrollbar_button_hover_color=self.tokens["gold_dark"]
        )
        self.scroll_manager.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        self.scroll_manager.grid_columnconfigure(0, weight=1)

        # Empty State Label
        self.lbl_dm_empty = ctk.CTkLabel(
            self.scroll_manager, text="No active downloads yet.\nPaste a link to start downloading.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=self.tokens["text_muted"], justify="center"
        )
        self.lbl_dm_empty.pack(pady=40)

        # Bottom Actions in Download Manager
        dm_footer = ctk.CTkFrame(
            sidebar, corner_radius=4,
            fg_color=self.tokens["surface"],
            border_width=1, border_color=self.tokens["border"]
        )
        dm_footer.grid(row=2, column=0, sticky="ew", padx=12, pady=14)

        btn_open_folder = ctk.CTkButton(
            dm_footer, text="📁 OPEN DOWNLOADS", height=32, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=self.tokens["gold_subtle"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border"],
            text_color=self.tokens["gold_bright"],
            command=self.open_current_destination
        )
        btn_open_folder.pack(fill="x", padx=8, pady=(8, 4))

        btn_clear_dm = ctk.CTkButton(
            dm_footer, text="CLEAR LIST", height=26, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            fg_color="transparent", hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_muted"],
            command=self.clear_manager_list
        )
        btn_clear_dm.pack(fill="x", padx=8, pady=(0, 8))

        # ---------------- MAIN CONTENT VIEWPORT ----------------
        main_viewport = ctk.CTkFrame(workbench, corner_radius=0, fg_color=self.tokens["bg"])
        main_viewport.grid(row=0, column=1, sticky="nsew")
        main_viewport.grid_columnconfigure(0, weight=1)
        main_viewport.grid_rowconfigure(0, weight=0) # Controls section
        main_viewport.grid_rowconfigure(1, weight=1) # Activity & Terminal section

        # --- UPPER CONTROLS SECTION ---
        controls_panel = ctk.CTkFrame(main_viewport, corner_radius=0, fg_color=self.tokens["bg"])
        controls_panel.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 8))
        controls_panel.grid_columnconfigure(0, weight=1)

        # 1. URL Input Block
        ctk.CTkLabel(
            controls_panel, text="01 / SOURCE LINK",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(anchor="w", pady=(0, 6))

        url_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        url_row.pack(fill="x", pady=(0, 10))

        self.entry_url = ctk.CTkEntry(
            url_row, placeholder_text="Paste YouTube video or playlist URL...",
            height=40, corner_radius=4,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"], text_color=self.tokens["text_primary"],
            placeholder_text_color="#52525B", font=ctk.CTkFont(family=FONT_FAMILY, size=12)
        )
        self.entry_url.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_url.bind("<Return>", lambda _event: self.trigger_analyze())

        ctk.CTkButton(
            url_row, text="PASTE", width=68, height=40, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.tokens["gold_subtle"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border"],
            text_color=self.tokens["gold_bright"], command=self.paste_from_clipboard
        ).pack(side="left", padx=(0, 6))

        self.btn_analyze = ctk.CTkButton(
            url_row, text="INSPECT", width=90, height=40, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.tokens["gold_subtle"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border_bright"],
            text_color=self.tokens["gold_bright"], command=self.trigger_analyze
        )
        self.btn_analyze.pack(side="left")

        # Media Inspection Card (Revealed upon inspection)
        self.frame_analysis = ctk.CTkFrame(
            controls_panel, corner_radius=6,
            fg_color=self.tokens["surface"],
            border_width=1, border_color=self.tokens["gold_border"]
        )
        
        an_header = ctk.CTkFrame(self.frame_analysis, fg_color="transparent")
        an_header.pack(fill="x", padx=12, pady=(10, 6))

        self.lbl_an_badge = ctk.CTkLabel(
            an_header, text="▶ VERIFIED MEDIA",
            font=ctk.CTkFont(family=FONT_FAMILY, size=9, weight="bold"),
            text_color=self.tokens["gold"]
        )
        self.lbl_an_badge.pack(anchor="w")

        self.lbl_an_title = ctk.CTkLabel(
            an_header, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=self.tokens["text_primary"], anchor="w", justify="left", wraplength=780
        )
        self.lbl_an_title.pack(fill="x", pady=(2, 0))

        # Inspection Metric Chips Container (Gold accented)
        self.chips_row = ctk.CTkFrame(self.frame_analysis, fg_color="transparent")
        self.chips_row.pack(fill="x", padx=12, pady=(0, 10))

        self.chip_items = self.create_metric_pill(self.chips_row, "ITEMS", "0")
        self.chip_duration = self.create_metric_pill(self.chips_row, "DURATION", "0m")
        self.chip_size = self.create_metric_pill(self.chips_row, "EST. SIZE", "--")
        self.chip_spec = self.create_metric_pill(self.chips_row, "PROFILE", "128k MP3")

        self.frame_analysis.pack_forget()

        # 2. Output Specification Block with Gold Segmented Switcher
        spec_header = ctk.CTkFrame(controls_panel, fg_color="transparent")
        spec_header.pack(fill="x", pady=(4, 6))

        ctk.CTkLabel(
            spec_header, text="02 / OUTPUT SPECIFICATION",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(side="left")

        # Gold Segmented Switcher ([ ♫ AUDIO ] / [ 🎬 VIDEO ])
        segmented_switcher = ctk.CTkFrame(
            spec_header, corner_radius=4,
            fg_color=self.tokens["surface"],
            border_width=1, border_color=self.tokens["border"]
        )
        segmented_switcher.pack(side="right")

        self.btn_mode_audio = ctk.CTkButton(
            segmented_switcher, text="♫ AUDIO", width=76, height=26, corner_radius=3,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=self.tokens["gold"], hover_color=self.tokens["gold_hover"],
            text_color=self.tokens["gold_text_dark"], command=lambda: self.switch_mode("audio")
        )
        self.btn_mode_audio.pack(side="left", padx=2, pady=2)

        self.btn_mode_video = ctk.CTkButton(
            segmented_switcher, text="🎬 VIDEO", width=76, height=26, corner_radius=3,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color="transparent", hover_color=self.tokens["surface_hover"],
            text_color=self.tokens["text_secondary"], command=lambda: self.switch_mode("video")
        )
        self.btn_mode_video.pack(side="left", padx=2, pady=2)

        # Format selector dropdown
        self.combo_format = ctk.CTkComboBox(
            controls_panel, values=list(self.audio_formats.keys()),
            height=38, corner_radius=4,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"],
            button_color=self.tokens["surface_elevated"], button_hover_color=self.tokens["surface_hover"],
            dropdown_fg_color=self.tokens["surface"], dropdown_hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_primary"], font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=11), command=self.on_format_changed
        )
        self.combo_format.pack(fill="x", pady=(0, 4))
        self.combo_format.set("MP3 · Old Speaker / USB (128 kbps CBR, 44.1kHz, ID3v2.3)")

        self.lbl_format_hint = ctk.CTkLabel(
            controls_panel, text="[SPEC] 128k Constant Bitrate · 44.1kHz Stereo · Stripped Artwork · FAT32 Clean Filenames",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10), text_color=self.tokens["text_muted"], anchor="w"
        )
        self.lbl_format_hint.pack(fill="x", pady=(0, 10))

        # 3. Parameters Row: Quick Destination Pills + Save Path + Limit
        params_header = ctk.CTkFrame(controls_panel, fg_color="transparent")
        params_header.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            params_header, text="03 / SAVE LOCATION & LIMITS",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(side="left")

        # Quick Destination Preset Pills
        quick_dest_row = ctk.CTkFrame(params_header, fg_color="transparent")
        quick_dest_row.pack(side="right")

        self.btn_pill_songs = ctk.CTkButton(
            quick_dest_row, text="♫ songs", width=62, height=22, corner_radius=3,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border"],
            text_color=self.tokens["gold_bright"], command=lambda: self.set_destination(DEFAULT_SONGS)
        )
        self.btn_pill_songs.pack(side="left", padx=2)

        self.btn_pill_videos = ctk.CTkButton(
            quick_dest_row, text="▣ videos", width=62, height=22, corner_radius=3,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["border"],
            text_color=self.tokens["text_secondary"], command=lambda: self.set_destination(DEFAULT_VIDEOS)
        )
        self.btn_pill_videos.pack(side="left", padx=2)

        self.btn_pill_root = ctk.CTkButton(
            quick_dest_row, text="⌂ root", width=52, height=22, corner_radius=3,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["border"],
            text_color=self.tokens["text_secondary"], command=lambda: self.set_destination(DEFAULT_ROOT)
        )
        self.btn_pill_root.pack(side="left", padx=2)

        # Path input and limit row
        params_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        params_row.pack(fill="x", pady=(0, 10))
        params_row.grid_columnconfigure(0, weight=3)
        params_row.grid_columnconfigure(1, weight=1)

        dest_inner = ctk.CTkFrame(params_row, fg_color="transparent")
        dest_inner.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.entry_dest = ctk.CTkEntry(
            dest_inner, height=36, corner_radius=4,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"], text_color=self.tokens["text_primary"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=11)
        )
        self.entry_dest.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_dest.insert(0, DEFAULT_SONGS)
        self.entry_dest.bind("<FocusOut>", lambda _event: self.update_quick_pills())

        ctk.CTkButton(
            dest_inner, text="BROWSE", width=74, height=36, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["surface_hover"],
            border_width=1, border_color=self.tokens["border"],
            text_color=self.tokens["text_primary"], command=self.browse_folder
        ).pack(side="left")

        self.entry_limit = ctk.CTkEntry(
            params_row, placeholder_text="Item limit (optional)", height=36, corner_radius=4,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"], text_color=self.tokens["text_primary"],
            placeholder_text_color="#52525B", font=ctk.CTkFont(family=FONT_FAMILY, size=11)
        )
        self.entry_limit.grid(row=0, column=1, sticky="ew")

        # Checkbox: Skip duplicates
        self.var_ignore_dups = ctk.BooleanVar(value=True)
        self.chk_dups = ctk.CTkCheckBox(
            controls_panel, text="Skip files already present in destination folder",
            variable=self.var_ignore_dups, corner_radius=3,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=self.tokens["text_secondary"],
            fg_color=self.tokens["gold"], hover_color=self.tokens["gold_hover"],
            checkmark_color=self.tokens["gold_text_dark"], border_color=self.tokens["border_strong"]
        )
        self.chk_dups.pack(anchor="w", pady=(0, 14))

        # 4. Action Row (Gold CTA & Subtle Dark Gold Stop Button)
        action_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 4))

        self.btn_download = ctk.CTkButton(
            action_row, text="START DOWNLOAD", height=44, corner_radius=5,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=self.tokens["gold"], hover_color=self.tokens["gold_hover"],
            text_color=self.tokens["gold_text_dark"], command=self.start_download
        )
        self.btn_download.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            action_row, text="STOP", width=90, height=44, corner_radius=5,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.tokens["gold_subtle"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border"],
            text_color=self.tokens["gold_bright"], state="disabled", command=self.stop_download
        )
        self.btn_stop.pack(side="left")

        # --- LOWER ACTIVITY & TELEMETRY SECTION ---
        term_frame = ctk.CTkFrame(
            main_viewport, corner_radius=6,
            fg_color=self.tokens["bg"],
            border_width=1, border_color=self.tokens["border"]
        )
        term_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        term_frame.grid_columnconfigure(0, weight=1)
        term_frame.grid_rowconfigure(2, weight=1)

        # 3-Stat Live Telemetry Header (Speed, ETA, Progress in Gold)
        telemetry_strip = ctk.CTkFrame(term_frame, fg_color=self.tokens["surface"], height=42, corner_radius=0)
        telemetry_strip.grid(row=0, column=0, sticky="ew")
        telemetry_strip.grid_columnconfigure(0, weight=2)
        telemetry_strip.grid_columnconfigure(1, weight=1)
        telemetry_strip.grid_columnconfigure(2, weight=1)
        telemetry_strip.grid_columnconfigure(3, weight=1)

        self.lbl_progress_status = ctk.CTkLabel(
            telemetry_strip, text="Ready to download",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=self.tokens["text_primary"]
        )
        self.lbl_progress_status.grid(row=0, column=0, sticky="w", padx=14, pady=10)

        self.lbl_hud_speed = ctk.CTkLabel(
            telemetry_strip, text="SPEED: --",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["gold_bright"]
        )
        self.lbl_hud_speed.grid(row=0, column=1, sticky="e", padx=10, pady=10)

        self.lbl_hud_eta = ctk.CTkLabel(
            telemetry_strip, text="ETA: --",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["gold_bright"]
        )
        self.lbl_hud_eta.grid(row=0, column=2, sticky="e", padx=10, pady=10)

        self.lbl_progress_meta = ctk.CTkLabel(
            telemetry_strip, text="0%",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=self.tokens["gold"]
        )
        self.lbl_progress_meta.grid(row=0, column=3, sticky="e", padx=14, pady=10)

        # Gold Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            term_frame, height=4, corner_radius=0,
            progress_color=self.tokens["gold"], fg_color=self.tokens["border"]
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar.set(0)

        # Monospace Telemetry Screen
        term_body = ctk.CTkFrame(term_frame, fg_color=self.tokens["bg"], corner_radius=0)
        term_body.grid(row=2, column=0, sticky="nsew")
        term_body.grid_columnconfigure(0, weight=1)
        term_body.grid_rowconfigure(1, weight=1)

        console_toolbar = ctk.CTkFrame(term_body, fg_color="transparent", height=24)
        console_toolbar.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 2))
        console_toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            console_toolbar, text="ACTIVITY LOG",
            font=ctk.CTkFont(family=FONT_FAMILY, size=9, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            console_toolbar, text="[CLEAR]", width=48, height=20, corner_radius=2,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            fg_color="transparent", hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_muted"], command=self.clear_logs
        ).grid(row=0, column=1, sticky="e")

        self.txt_terminal = ctk.CTkTextbox(
            term_body, corner_radius=0, fg_color="#060608", text_color="#D4D4D8",
            border_width=1, border_color=self.tokens["border"],
            font=ctk.CTkFont(family="Consolas", size=10),
            activate_scrollbars=True
        )
        self.txt_terminal.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.append_log("[SYS] YouTube Downloader initialized.")
        self.append_log("[SYS] Paste a YouTube link above, choose format, and click START DOWNLOAD.")

    def create_metric_pill(self, parent, label, initial_val):
        """Helper to create a Gold-accented metric badge pill."""
        pill = ctk.CTkFrame(
            parent, corner_radius=4,
            fg_color=self.tokens["pill_bg"],
            border_width=1, border_color=self.tokens["border"]
        )
        pill.pack(side="left", padx=(0, 6), pady=4)

        ctk.CTkLabel(
            pill, text=label,
            font=ctk.CTkFont(family=FONT_FAMILY, size=8, weight="bold"),
            text_color=self.tokens["gold"]
        ).pack(side="left", padx=(8, 4), pady=3)

        val_lbl = ctk.CTkLabel(
            pill, text=initial_val,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["text_primary"]
        )
        val_lbl.pack(side="left", padx=(0, 8), pady=3)
        return val_lbl

    # ---------------- Download Manager Methods ----------------

    def add_manager_item(self, item_id, title, status_text, format_label="", filepath=None):
        """Add or update an item in the sidebar Download Manager list."""
        if hasattr(self, 'lbl_dm_empty') and self.lbl_dm_empty.winfo_exists():
            self.lbl_dm_empty.pack_forget()

        if item_id in self.manager_items:
            data = self.manager_items[item_id]
            data["status_lbl"].configure(text=status_text)
            if "Saved" in status_text or "Done" in status_text:
                data["status_lbl"].configure(text_color=self.tokens["gold_bright"])
            elif "Downloading" in status_text:
                data["status_lbl"].configure(text_color=self.tokens["gold"])
            else:
                data["status_lbl"].configure(text_color=self.tokens["text_muted"])
            if filepath:
                data["path"] = filepath
            return

        # Create card widget
        card = ctk.CTkFrame(
            self.scroll_manager, corner_radius=4,
            fg_color=self.tokens["surface"],
            border_width=1, border_color=self.tokens["border"]
        )
        card.pack(fill="x", padx=4, pady=3)

        # Title
        t_short = title if len(title) <= 32 else title[:30] + "..."
        lbl_t = ctk.CTkLabel(
            card, text=t_short,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["text_primary"], anchor="w"
        )
        lbl_t.pack(fill="x", padx=8, pady=(6, 2))

        # Bottom row: Format + Status
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 6))

        fmt_short = format_label.split("·")[0].strip() if "·" in format_label else (format_label[:14] if format_label else "Audio")
        ctk.CTkLabel(
            row, text=fmt_short,
            font=ctk.CTkFont(family=FONT_FAMILY, size=8),
            text_color=self.tokens["text_muted"], anchor="w"
        ).pack(side="left")

        status_color = self.tokens["gold_bright"] if "Saved" in status_text else self.tokens["gold"]
        lbl_status = ctk.CTkLabel(
            row, text=status_text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=8, weight="bold"),
            text_color=status_color, anchor="e"
        )
        lbl_status.pack(side="right")

        # Double click to open folder/file
        card.bind("<Double-Button-1>", lambda _e, p=filepath: self.locate_file(p))
        lbl_t.bind("<Double-Button-1>", lambda _e, p=filepath: self.locate_file(p))

        self.manager_items[item_id] = {
            "card": card,
            "status_lbl": lbl_status,
            "path": filepath
        }

        self.update_manager_count()

    def update_manager_count(self):
        count = len(self.manager_items)
        self.lbl_dm_count.configure(text=f"{count} items")

    def clear_manager_list(self):
        for data in self.manager_items.values():
            data["card"].destroy()
        self.manager_items.clear()
        self.lbl_dm_count.configure(text="0 items")
        self.lbl_dm_empty.pack(pady=40)

    def open_current_destination(self):
        p = self.entry_dest.get().strip() or DEFAULT_SONGS
        if os.path.exists(p):
            os.startfile(p)
        else:
            messagebox.showinfo("Notice", f"Folder does not exist yet:\n{p}")

    def locate_file(self, filepath):
        if filepath and os.path.exists(filepath):
            subprocess_dir = os.path.dirname(filepath)
            os.startfile(subprocess_dir)
        else:
            self.open_current_destination()

    def load_initial_downloads(self):
        """Populate the download manager with existing recent downloads from destination folders."""
        dest = DEFAULT_SONGS if os.path.exists(DEFAULT_SONGS) else EXE_DIR
        try:
            if os.path.exists(dest):
                files = [f for f in os.listdir(dest) if f.lower().endswith(('.mp3', '.m4a', '.mp4', '.mkv'))]
                # Sort by modification time descending
                files.sort(key=lambda f: os.path.getmtime(os.path.join(dest, f)), reverse=True)
                for f in files[:12]:
                    full_p = os.path.join(dest, f)
                    fmt_tag = "MP4 Video" if f.lower().endswith(('.mp4', '.mkv')) else "MP3 Audio"
                    self.add_manager_item(f, f, "✓ Saved", fmt_tag, full_p)
        except Exception:
            pass

    # ---------------- UI Event Handlers ----------------

    def switch_mode(self, mode):
        """Toggle between Audio and Video mode via Gold segmented pills."""
        self.current_mode = mode
        if mode == "audio":
            self.btn_mode_audio.configure(
                fg_color=self.tokens["gold"],
                hover_color=self.tokens["gold_hover"],
                text_color=self.tokens["gold_text_dark"]
            )
            self.btn_mode_video.configure(
                fg_color="transparent",
                hover_color=self.tokens["surface_hover"],
                text_color=self.tokens["text_secondary"]
            )
            self.combo_format.configure(values=list(self.audio_formats.keys()))
            self.combo_format.set("MP3 · Old Speaker / USB (128 kbps CBR, 44.1kHz, ID3v2.3)")
            self.on_format_changed("MP3 · Old Speaker / USB (128 kbps CBR, 44.1kHz, ID3v2.3)")
        else:
            self.btn_mode_video.configure(
                fg_color=self.tokens["gold"],
                hover_color=self.tokens["gold_hover"],
                text_color=self.tokens["gold_text_dark"]
            )
            self.btn_mode_audio.configure(
                fg_color="transparent",
                hover_color=self.tokens["surface_hover"],
                text_color=self.tokens["text_secondary"]
            )
            self.combo_format.configure(values=list(self.video_formats.keys()))
            self.combo_format.set("MP4 Video · 1080p Full HD")
            self.on_format_changed("MP4 Video · 1080p Full HD")

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
        selected_code = self.all_formats.get(choice, "mp3_speaker")
        current_dest = self.entry_dest.get().strip()

        if selected_code.startswith("video_"):
            if current_dest.lower().endswith("songs"):
                self.set_destination(DEFAULT_VIDEOS)
            self.lbl_format_hint.configure(
                text=f"[SPEC] {selected_code.replace('video_', '').upper()} MP4 Video · Audio Muxed · FFmpeg Encoded"
            )
        else:
            if current_dest.lower().endswith("videos"):
                self.set_destination(DEFAULT_SONGS)
            if selected_code == "mp3_speaker":
                self.lbl_format_hint.configure(
                    text="[SPEC] 128k Constant Bitrate · 44.1kHz Stereo · Stripped Artwork · FAT32 Clean Filenames"
                )
            elif selected_code == "m4a":
                self.lbl_format_hint.configure(text="[SPEC] Original AAC Audio Stream · Direct Demux without Re-encoding")
            else:
                self.lbl_format_hint.configure(text=f"[SPEC] MP3 High Fidelity · {selected_code.replace('mp3_', '')} kbps CBR · 44.1kHz Stereo")

        if self.current_analysis:
            self.update_analysis_meta(self.current_analysis)

    def set_destination(self, path):
        self.entry_dest.delete(0, "end")
        self.entry_dest.insert(0, path)
        self.update_quick_pills()
        self.append_log(f"[DIR] Destination set: {path}")

    def update_quick_pills(self):
        curr = os.path.normpath(self.entry_dest.get().strip()).lower()
        songs_norm = os.path.normpath(DEFAULT_SONGS).lower()
        videos_norm = os.path.normpath(DEFAULT_VIDEOS).lower()
        root_norm = os.path.normpath(DEFAULT_ROOT).lower()

        self.btn_pill_songs.configure(
            border_color=self.tokens["gold_border_bright"] if curr == songs_norm else self.tokens["border"],
            text_color=self.tokens["gold_bright"] if curr == songs_norm else self.tokens["text_secondary"]
        )
        self.btn_pill_videos.configure(
            border_color=self.tokens["gold_border_bright"] if curr == videos_norm else self.tokens["border"],
            text_color=self.tokens["gold_bright"] if curr == videos_norm else self.tokens["text_secondary"]
        )
        self.btn_pill_root.configure(
            border_color=self.tokens["gold_border_bright"] if curr == root_norm else self.tokens["border"],
            text_color=self.tokens["gold_bright"] if curr == root_norm else self.tokens["text_secondary"]
        )

    def browse_folder(self):
        curr = self.entry_dest.get().strip() or DEFAULT_ROOT
        selected = filedialog.askdirectory(initialdir=curr, title="Select Download Folder")
        if selected:
            self.set_destination(os.path.normpath(selected))

    def append_log(self, msg):
        self.log_queue.put(msg)

    def poll_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            t_str = time.strftime("%H:%M:%S")
            self.txt_terminal.insert("end", f"[{t_str}] {msg}\n")
            self.txt_terminal.see("end")
        self.after(80, self.poll_log_queue)

    def clear_logs(self):
        self.txt_terminal.delete("1.0", "end")
        self.append_log("[SYS] Activity log cleared.")

    # ---------------- Link Analysis ----------------

    def trigger_analyze(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Notice", "Please paste a YouTube link first.")
            return

        self.btn_analyze.configure(state="disabled", text="CHECKING")
        self.append_log(f"[GET] Inspecting link: {url}")

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
        self.btn_analyze.configure(state="normal", text="INSPECT")
        self.frame_analysis.pack(fill="x", pady=(0, 10))
        self.update_analysis_meta(res)
        self.append_log(f"[OK] Link verified: '{res['title']}' ({res['track_count']} items, {res['duration_str']})")

    def update_analysis_meta(self, res):
        chosen_format = self.all_formats.get(self.combo_format.get(), "mp3_speaker")
        dur = res["total_duration"]

        if chosen_format.startswith("video_"):
            if chosen_format in ("video_720", "video_480"):
                mb = (320000 * dur) / (1024 * 1024)
            else:
                mb = (580000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = f"{chosen_format.replace('video_', '').upper()} MP4"
        elif chosen_format == "mp3_320":
            mb = (40000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = "320k MP3"
        elif chosen_format == "mp3_192":
            mb = (24000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = "192k MP3"
        elif chosen_format == "m4a":
            mb = (16000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = "AAC M4A"
        else:
            mb = (16000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = "128k CBR MP3"

        self.lbl_an_title.configure(text=res['title'])
        self.chip_items.configure(text=f"{res['track_count']} items")
        self.chip_duration.configure(text=res['duration_str'])
        self.chip_size.configure(text=est_str)
        self.chip_spec.configure(text=profile_str)

    def on_analysis_error(self, err):
        self.btn_analyze.configure(state="normal", text="INSPECT")
        self.append_log(f"[ERR] Inspection failed: {err}")

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
        download_type = self.all_formats.get(chosen_label, "mp3_speaker")
        ignore_dups = self.var_ignore_dups.get()

        max_tracks = 0
        limit_txt = self.entry_limit.get().strip()
        if limit_txt.isdigit():
            max_tracks = int(limit_txt)

        self.is_downloading = True
        self.stop_event.clear()
        self.btn_download.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress_bar.set(0)
        self.lbl_progress_status.configure(text="Initializing download queue...")
        self.lbl_hud_speed.configure(text="SPEED: --")
        self.lbl_hud_eta.configure(text="ETA: --")
        self.lbl_progress_meta.configure(text="0%")

        params = {
            "url": url,
            "dest_dir": dest_dir,
            "download_type": download_type,
            "ignore_dups": ignore_dups,
            "max_tracks": max_tracks,
            "format_label": chosen_label
        }

        self.download_thread = threading.Thread(target=self.run_download_worker, args=(params,), daemon=True)
        self.download_thread.start()

    def stop_download(self):
        if self.is_downloading:
            self.stop_event.set()
            self.append_log("[USER] Download cancellation requested.")
            self.lbl_progress_status.configure(text="Stopping...")

    def run_download_worker(self, params):
        url = params["url"]
        dest_dir = params["dest_dir"]
        download_type = params["download_type"]
        ignore_dups = params["ignore_dups"]
        max_tracks = params["max_tracks"]
        format_label = params.get("format_label", "")

        os.makedirs(dest_dir, exist_ok=True)

        is_video = download_type.startswith("video_")
        is_speaker = (download_type == "mp3_speaker")
        video_quality = download_type.replace("video_", "") if is_video else "1080"
        bitrate = "320" if download_type == "mp3_320" else ("192" if download_type == "mp3_192" else "128")

        self.append_log(f"[QUEUE] Target path: {dest_dir}")
        self.append_log(f"[QUEUE] Format profile: {download_type}")

        # Fetch playlist / video info
        ydl_opts = {'quiet': True, 'extract_flat': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.append_log(f"[ERR] Failed to extract URL info: {e}")
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
                    self.append_log(f"[SKIP] Existing: {title}")
                    continue
                if k in seen_keys:
                    self.append_log(f"[SKIP] Duplicate in batch: {title}")
                    continue
            seen_keys.add(k)
            queue_items.append({'id': vid, 'title': title, 'duration': dur, 'key': k})
            if max_tracks > 0 and len(queue_items) >= max_tracks:
                break

        total_queue = len(queue_items)
        self.append_log(f"[QUEUE] {total_queue} items queued for processing.")

        if total_queue == 0:
            self.append_log("[OK] All items are already downloaded and verified.")
            self.after(0, self.finish_download)
            return

        current_idx = 0
        def progress_hook(d):
            if self.stop_event.is_set():
                raise yt_dlp.utils.DownloadCancelled("Download cancelled by user.")
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                speed = d.get('speed') or 0
                speed_str = f"{speed / (1024*1024):.1f} MB/s" if speed else ""
                eta = d.get('eta') or 0
                eta_str = f"{eta}s" if eta else ""
                if total > 0:
                    sub_pct = (downloaded / total) * 100
                    base_pct = ((current_idx - 1) / total_queue) * 100
                    total_pct = min(99.9, base_pct + (sub_pct / total_queue))
                    self.after(0, lambda: self.update_progress_ui(total_pct, speed_str, eta_str))

        start_num = max_idx + 1
        downloaded_count = 0

        for i, item in enumerate(queue_items):
            if self.stop_event.is_set():
                self.append_log("[STOP] Process interrupted by user.")
                break

            current_idx = i + 1
            track_num = start_num + i
            cleaned = clean_filename(item['title'], track_num)
            ext_target = "mp4" if is_video else ("m4a" if download_type == "m4a" else "mp3")
            filename_base = f"{track_num:03d} - {cleaned}"
            full_target_path = os.path.join(dest_dir, f"{filename_base}.{ext_target}")

            # Register in Download Manager
            self.after(0, lambda name=filename_base, fmt=format_label: self.add_manager_item(name, name, "⏳ Downloading...", fmt))

            self.after(0, lambda n=current_idx, t=total_queue, name=item['title']: self.lbl_progress_status.configure(
                text=f"[{n}/{t}] Processing: {name[:55]}"
            ))
            self.append_log(f"[GET] [{current_idx}/{total_queue}] {item['title']}")

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
                self.append_log(f"[OK] Saved: {filename_base}")
                # Mark Done in Download Manager
                self.after(0, lambda name=filename_base, p=full_target_path: self.add_manager_item(name, name, "✓ Saved", format_label, p))
            except Exception as e:
                if self.stop_event.is_set():
                    self.after(0, lambda name=filename_base: self.add_manager_item(name, name, "✕ Stopped", format_label))
                    break
                self.append_log(f"[ERR] Download error ({item['title']}): {e}")
                self.after(0, lambda name=filename_base: self.add_manager_item(name, name, "✕ Failed", format_label))

        self.append_log(f"[DONE] Completed. Downloaded {downloaded_count} items.")
        self.after(0, self.finish_download)

    def update_progress_ui(self, pct, speed, eta):
        self.progress_bar.set(pct / 100.0)
        self.lbl_progress_meta.configure(text=f"{round(pct)}%")
        if speed:
            self.lbl_hud_speed.configure(text=f"SPEED: {speed}")
        if eta:
            self.lbl_hud_eta.configure(text=f"ETA: {eta}")

    def finish_download(self):
        self.is_downloading = False
        self.btn_download.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_progress_status.configure(text="Ready to download")
        self.progress_bar.set(1.0)
        self.lbl_progress_meta.configure(text="100%")
        self.lbl_hud_speed.configure(text="SPEED: --")
        self.lbl_hud_eta.configure(text="ETA: --")

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
