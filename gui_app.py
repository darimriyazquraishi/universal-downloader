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
        self.geometry("1100x780")
        self.minsize(960, 700)

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
        """
        ArtCraft + Impeccable Design System:
        - Deep industrial black palette (#0B0B0C)
        - Hairline 1px borders (#1C1C1F, #26262B)
        - Monospace technical HUD tags
        - Sharp, precise geometry (no puffy bubble cards or card-in-card nesting)
        - High contrast crisp typography & signature inverted monochrome CTA
        """
        self.configure(fg_color="#0B0B0C")
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Main Workbench
        self.grid_columnconfigure(0, weight=1)

        # Style Tokens
        self.tokens = {
            "bg": "#0B0B0C",
            "sidebar": "#0E0E10",
            "surface": "#121214",
            "surface_elevated": "#18181B",
            "border": "#1F1F24",
            "border_strong": "#2E2E35",
            "text_primary": "#F4F4F5",
            "text_secondary": "#A1A1AA",
            "text_muted": "#71717A",
            "cta_bg": "#FFFFFF",
            "cta_fg": "#000000",
            "cta_hover": "#E4E4E7",
            "emerald": "#10B981",
            "rose": "#F43F5E",
            "amber": "#F59E0B",
            "cyan": "#06B6D4"
        }

        # ---------------- 1. TOP HEADER (Hairline Border) ----------------
        top_bar = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color=self.tokens["bg"], border_width=1, border_color=self.tokens["border"])
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)
        top_bar.grid_propagate(False)

        # Brand Mark
        brand_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=16, pady=8, sticky="w")

        lbl_logo = ctk.CTkLabel(brand_frame, text="[↓]", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=self.tokens["cta_bg"])
        lbl_logo.pack(side="left", padx=(0, 8))

        lbl_title = ctk.CTkLabel(brand_frame, text="YOUTUBE DOWNLOADER", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color=self.tokens["text_primary"])
        lbl_title.pack(side="left")

        lbl_tag = ctk.CTkLabel(brand_frame, text=" · NATIVE ENGINE", font=ctk.CTkFont(family="Consolas", size=10), text_color=self.tokens["text_muted"])
        lbl_tag.pack(side="left", padx=6)

        # Status HUD (Right)
        status_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        status_frame.grid(row=0, column=2, padx=16, pady=8, sticky="e")

        self.lbl_header_status = ctk.CTkLabel(
            status_frame, text="● ENGINE READY",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=self.tokens["emerald"]
        )
        self.lbl_header_status.pack(side="right")

        # ---------------- 2. WORKBENCH ----------------
        workbench = ctk.CTkFrame(self, corner_radius=0, fg_color=self.tokens["bg"])
        workbench.grid(row=1, column=0, sticky="nsew")
        workbench.grid_rowconfigure(0, weight=1)
        workbench.grid_columnconfigure(0, weight=0) # Sidebar
        workbench.grid_columnconfigure(1, weight=1) # Main Viewport

        # ---------------- LEFT SIDEBAR (Explorer & Telemetry) ----------------
        sidebar = ctk.CTkFrame(workbench, width=220, corner_radius=0, fg_color=self.tokens["sidebar"], border_width=1, border_color=self.tokens["border"])
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # Header Label
        ctk.CTkLabel(
            sidebar, text="01 / DESTINATIONS",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.btn_dest_songs = ctk.CTkButton(
            sidebar, text="♫  songs", anchor="w", height=32, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["border_strong"],
            text_color=self.tokens["text_primary"],
            command=lambda: self.set_destination(DEFAULT_SONGS)
        )
        self.btn_dest_songs.pack(fill="x", padx=10, pady=2)

        self.btn_dest_videos = ctk.CTkButton(
            sidebar, text="▣  videos", anchor="w", height=32, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="transparent", hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_secondary"],
            command=lambda: self.set_destination(DEFAULT_VIDEOS)
        )
        self.btn_dest_videos.pack(fill="x", padx=10, pady=2)

        self.btn_dest_root = ctk.CTkButton(
            sidebar, text="⌂  root folder", anchor="w", height=32, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="transparent", hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_secondary"],
            command=lambda: self.set_destination(DEFAULT_ROOT)
        )
        self.btn_dest_root.pack(fill="x", padx=10, pady=2)

        ctk.CTkButton(
            sidebar, text="+  custom path...", anchor="w", height=30, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="transparent", hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_muted"],
            border_width=1, border_color=self.tokens["border"],
            command=self.browse_folder
        ).pack(fill="x", padx=10, pady=(10, 4))

        # Bottom System Telemetry (Docked, flat, no nested cards)
        telemetry = ctk.CTkFrame(sidebar, corner_radius=0, fg_color="transparent", border_width=1, border_color=self.tokens["border"])
        telemetry.pack(side="bottom", fill="x", padx=10, pady=16)

        ctk.CTkLabel(
            telemetry, text="SYSTEM STATUS",
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(anchor="w", padx=10, pady=(10, 4))

        self.lbl_free_space = ctk.CTkLabel(telemetry, text="FREE: --", font=ctk.CTkFont(family="Consolas", size=10), text_color=self.tokens["text_primary"], anchor="w")
        self.lbl_free_space.pack(fill="x", padx=10, pady=1)

        self.lbl_drive = ctk.CTkLabel(telemetry, text="DRIVE: --", font=ctk.CTkFont(family="Consolas", size=10), text_color=self.tokens["text_muted"], anchor="w")
        self.lbl_drive.pack(fill="x", padx=10, pady=1)

        self.lbl_ffmpeg_status = ctk.CTkLabel(telemetry, text="ENCODER: Ready", font=ctk.CTkFont(family="Consolas", size=10), text_color=self.tokens["emerald"], anchor="w")
        self.lbl_ffmpeg_status.pack(fill="x", padx=10, pady=(1, 10))

        # ---------------- MAIN CONTENT VIEWPORT ----------------
        main_viewport = ctk.CTkFrame(workbench, corner_radius=0, fg_color=self.tokens["bg"])
        main_viewport.grid(row=0, column=1, sticky="nsew")
        main_viewport.grid_columnconfigure(0, weight=1)
        main_viewport.grid_rowconfigure(0, weight=0) # Controls section
        main_viewport.grid_rowconfigure(1, weight=1) # Activity & Terminal section

        # --- UPPER CONTROLS SECTION ---
        controls_panel = ctk.CTkFrame(main_viewport, corner_radius=0, fg_color=self.tokens["bg"])
        controls_panel.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 12))
        controls_panel.grid_columnconfigure(0, weight=1)

        # 1. URL Input Block
        ctk.CTkLabel(
            controls_panel, text="02 / SOURCE LINK",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(anchor="w", pady=(0, 6))

        url_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        url_row.pack(fill="x", pady=(0, 10))

        self.entry_url = ctk.CTkEntry(
            url_row, placeholder_text="Paste YouTube video or playlist URL...",
            height=38, corner_radius=3,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"], text_color=self.tokens["text_primary"],
            placeholder_text_color="#52525B", font=ctk.CTkFont(size=12)
        )
        self.entry_url.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_url.bind("<Return>", lambda _event: self.trigger_analyze())

        ctk.CTkButton(
            url_row, text="PASTE", width=64, height=38, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["border_strong"],
            text_color=self.tokens["text_primary"], command=self.paste_from_clipboard
        ).pack(side="left", padx=(0, 6))

        self.btn_analyze = ctk.CTkButton(
            url_row, text="INSPECT", width=86, height=38, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["border_strong"],
            border_width=1, border_color=self.tokens["border_strong"],
            text_color=self.tokens["text_primary"], command=self.trigger_analyze
        )
        self.btn_analyze.pack(side="left")

        # Telemetry Banner (Revealed only when link is inspected)
        self.frame_analysis = ctk.CTkFrame(
            controls_panel, corner_radius=3, fg_color=self.tokens["surface"],
            border_width=1, border_color=self.tokens["border_strong"]
        )
        self.lbl_an_title = ctk.CTkLabel(
            self.frame_analysis, text="", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tokens["text_primary"], anchor="w", justify="left", wraplength=720
        )
        self.lbl_an_title.pack(fill="x", padx=12, pady=(8, 2))
        self.lbl_an_meta = ctk.CTkLabel(
            self.frame_analysis, text="", font=ctk.CTkFont(family="Consolas", size=11),
            text_color=self.tokens["cyan"], anchor="w", justify="left", wraplength=720
        )
        self.lbl_an_meta.pack(fill="x", padx=12, pady=(0, 8))
        self.frame_analysis.pack_forget()

        # 2. Output Specification Block
        ctk.CTkLabel(
            controls_panel, text="03 / OUTPUT SPECIFICATION",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(anchor="w", pady=(4, 6))

        self.format_options_map = {
            "MP3 · Old Speaker / USB (128 kbps CBR, 44.1kHz, ID3v2.3)": "mp3_speaker",
            "MP3 · Maximum Quality (320 kbps)": "mp3_320",
            "MP3 · High Quality (192 kbps)": "mp3_192",
            "M4A · Original AAC Audio Stream": "m4a",
            "MP4 Video · 1080p Full HD": "video_1080",
            "MP4 Video · 720p HD": "video_720",
            "MP4 Video · Best Available Quality": "video_best",
            "MP4 Video · 480p": "video_480"
        }

        self.combo_format = ctk.CTkComboBox(
            controls_panel, values=list(self.format_options_map.keys()),
            height=38, corner_radius=3,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"],
            button_color=self.tokens["surface_elevated"], button_hover_color=self.tokens["border_strong"],
            dropdown_fg_color=self.tokens["surface"], dropdown_hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_primary"], font=ctk.CTkFont(size=12),
            dropdown_font=ctk.CTkFont(size=11), command=self.on_format_changed
        )
        self.combo_format.pack(fill="x", pady=(0, 4))
        self.combo_format.set("MP3 · Old Speaker / USB (128 kbps CBR, 44.1kHz, ID3v2.3)")

        self.lbl_format_hint = ctk.CTkLabel(
            controls_panel, text="[SPEC] 128k Constant Bitrate · 44.1kHz Stereo · Stripped Artwork · FAT32 Clean Filenames",
            font=ctk.CTkFont(family="Consolas", size=10), text_color=self.tokens["text_muted"], anchor="w"
        )
        self.lbl_format_hint.pack(fill="x", pady=(0, 10))

        # 3. Parameters Row (Destination & Limits)
        params_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        params_row.pack(fill="x", pady=(0, 10))
        params_row.grid_columnconfigure(0, weight=3)
        params_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(params_row, text="SAVE PATH", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=self.tokens["text_muted"]).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(params_row, text="ITEM LIMIT", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=self.tokens["text_muted"]).grid(row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 4))

        dest_inner = ctk.CTkFrame(params_row, fg_color="transparent")
        dest_inner.grid(row=1, column=0, sticky="ew", padx=(0, 10))

        self.entry_dest = ctk.CTkEntry(
            dest_inner, height=34, corner_radius=3,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"], text_color=self.tokens["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.entry_dest.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_dest.insert(0, DEFAULT_SONGS)
        self.entry_dest.bind("<FocusOut>", lambda _event: (self.update_storage_info(), self.update_sidebar_selection()))

        ctk.CTkButton(
            dest_inner, text="BROWSE", width=72, height=34, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["border_strong"],
            text_color=self.tokens["text_primary"], command=self.browse_folder
        ).pack(side="left")

        self.entry_limit = ctk.CTkEntry(
            params_row, placeholder_text="All items", height=34, corner_radius=3,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"], text_color=self.tokens["text_primary"],
            placeholder_text_color="#52525B", font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.entry_limit.grid(row=1, column=1, sticky="ew", padx=(10, 0))

        # Checkbox: Skip duplicates
        self.var_ignore_dups = ctk.BooleanVar(value=True)
        self.chk_dups = ctk.CTkCheckBox(
            controls_panel, text="Skip files already present in destination folder",
            variable=self.var_ignore_dups, corner_radius=2,
            font=ctk.CTkFont(size=11), text_color=self.tokens["text_secondary"],
            fg_color=self.tokens["cta_bg"], hover_color=self.tokens["cta_hover"],
            checkmark_color=self.tokens["cta_fg"], border_color=self.tokens["border_strong"]
        )
        self.chk_dups.pack(anchor="w", pady=(0, 14))

        # 4. Action Row (ArtCraft Signature Invert CTA Button)
        action_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 4))

        self.btn_download = ctk.CTkButton(
            action_row, text="START DOWNLOAD", height=42, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color=self.tokens["cta_bg"], hover_color=self.tokens["cta_hover"],
            text_color=self.tokens["cta_fg"], command=self.start_download
        )
        self.btn_download.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            action_row, text="STOP", width=84, height=42, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#271418", hover_color="#3B1C22",
            border_width=1, border_color="#4C1D24",
            text_color=self.tokens["rose"], state="disabled", command=self.stop_download
        )
        self.btn_stop.pack(side="left")

        # --- LOWER ACTIVITY & TELEMETRY SECTION (Hairline Separator) ---
        term_frame = ctk.CTkFrame(main_viewport, corner_radius=0, fg_color=self.tokens["bg"], border_width=1, border_color=self.tokens["border"])
        term_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        term_frame.grid_columnconfigure(0, weight=1)
        term_frame.grid_rowconfigure(2, weight=1)

        # Progress Status Line
        prog_header = ctk.CTkFrame(term_frame, fg_color=self.tokens["surface"], height=32, corner_radius=0)
        prog_header.grid(row=0, column=0, sticky="ew")
        prog_header.grid_columnconfigure(0, weight=1)

        self.lbl_progress_status = ctk.CTkLabel(
            prog_header, text="Ready to download",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=self.tokens["text_primary"]
        )
        self.lbl_progress_status.grid(row=0, column=0, sticky="w", padx=12, pady=6)

        self.lbl_progress_meta = ctk.CTkLabel(
            prog_header, text="0%",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=self.tokens["emerald"]
        )
        self.lbl_progress_meta.grid(row=0, column=1, sticky="e", padx=12, pady=6)

        # Clean 3px progress bar
        self.progress_bar = ctk.CTkProgressBar(
            term_frame, height=3, corner_radius=0,
            progress_color=self.tokens["emerald"], fg_color=self.tokens["border"]
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
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            console_toolbar, text="[CLEAR]", width=48, height=20, corner_radius=2,
            font=ctk.CTkFont(family="Consolas", size=9),
            fg_color="transparent", hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_muted"], command=self.clear_logs
        ).grid(row=0, column=1, sticky="e")

        self.txt_terminal = ctk.CTkTextbox(
            term_body, corner_radius=0, fg_color="#070708", text_color="#D4D4D8",
            border_width=1, border_color=self.tokens["border"],
            font=ctk.CTkFont(family="Consolas", size=10),
            activate_scrollbars=True
        )
        self.txt_terminal.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.append_log("[SYS] YouTube Downloader initialized.")
        self.append_log("[SYS] Paste a YouTube link above, choose format, and click START DOWNLOAD.")

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
        self.update_storage_info()
        self.update_sidebar_selection()
        self.append_log(f"[DIR] Destination: {path}")

    def update_sidebar_selection(self):
        curr = os.path.normpath(self.entry_dest.get().strip()).lower()
        songs_norm = os.path.normpath(DEFAULT_SONGS).lower()
        videos_norm = os.path.normpath(DEFAULT_VIDEOS).lower()
        root_norm = os.path.normpath(DEFAULT_ROOT).lower()

        self.btn_dest_songs.configure(fg_color=self.tokens["surface_elevated"] if curr == songs_norm else "transparent")
        self.btn_dest_videos.configure(fg_color=self.tokens["surface_elevated"] if curr == videos_norm else "transparent")
        self.btn_dest_root.configure(fg_color=self.tokens["surface_elevated"] if curr == root_norm else "transparent")

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
            self.lbl_free_space.configure(text=f"FREE: {free_gb:.1f} GB")
            self.lbl_drive.configure(text=f"DRIVE: {drive}")
        except Exception:
            pass

        if FFMPEG_EXE and os.path.exists(FFMPEG_EXE):
            self.lbl_ffmpeg_status.configure(text="ENCODER: FFmpeg Ready", text_color=self.tokens["emerald"])
        else:
            self.lbl_ffmpeg_status.configure(text="ENCODER: Not Found", text_color=self.tokens["rose"])

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
        self.lbl_header_status.configure(text="● ANALYZING", text_color=self.tokens["cyan"])
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
        self.lbl_header_status.configure(text="● READY", text_color=self.tokens["emerald"])
        self.frame_analysis.pack(fill="x", pady=(0, 10))
        self.update_analysis_meta(res)
        self.append_log(f"[OK] Link verified: '{res['title']}' ({res['track_count']} items, {res['duration_str']})")

    def update_analysis_meta(self, res):
        chosen_format = self.format_options_map.get(self.combo_format.get(), "mp3_speaker")
        dur = res["total_duration"]

        if chosen_format.startswith("video_"):
            if chosen_format in ("video_720", "video_480"):
                mb = (320000 * dur) / (1024 * 1024)
            else:
                mb = (580000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            label = f"{res['track_count']} Items  ·  {res['duration_str']}  ·  Estimated Size: {est_str} (MP4)"
        elif chosen_format == "mp3_320":
            mb = (40000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            label = f"{res['track_count']} Items  ·  {res['duration_str']}  ·  Estimated Size: {est_str} (320k MP3)"
        elif chosen_format == "mp3_192":
            mb = (24000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            label = f"{res['track_count']} Items  ·  {res['duration_str']}  ·  Estimated Size: {est_str} (192k MP3)"
        else:
            mb = (16000 * dur) / (1024 * 1024)
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            label = f"{res['track_count']} Items  ·  {res['duration_str']}  ·  Estimated Size: {est_str} (128k CBR MP3)"

        self.lbl_an_title.configure(text=res['title'])
        self.lbl_an_meta.configure(text=label)

    def on_analysis_error(self, err):
        self.btn_analyze.configure(state="normal", text="INSPECT")
        self.lbl_header_status.configure(text="● ERROR", text_color=self.tokens["rose"])
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
        self.lbl_header_status.configure(text="● DOWNLOADING", text_color=self.tokens["amber"])
        self.progress_bar.set(0)
        self.lbl_progress_status.configure(text="Initializing download queue...")
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
            self.append_log("[USER] Download cancellation requested.")
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
                self.append_log("[STOP] Process interrupted by user.")
                break

            current_idx = i + 1
            track_num = start_num + i
            cleaned = clean_filename(item['title'], track_num)
            filename_base = f"{track_num:03d} - {cleaned}"

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
            except Exception as e:
                if self.stop_event.is_set():
                    break
                self.append_log(f"[ERR] Download error ({item['title']}): {e}")

        self.append_log(f"[DONE] Completed. Downloaded {downloaded_count} items.")
        self.after(0, self.finish_download)

    def update_progress_ui(self, pct, speed, eta):
        self.progress_bar.set(pct / 100.0)
        meta_str = f"{round(pct)}%"
        if speed:
            meta_str = f"{speed}  ·  {meta_str}"
        if eta:
            meta_str = f"{meta_str}  ·  {eta}"
        self.lbl_progress_meta.configure(text=meta_str)

    def finish_download(self):
        self.is_downloading = False
        self.btn_download.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_header_status.configure(text="● ENGINE READY", text_color=self.tokens["emerald"])
        self.lbl_progress_status.configure(text="Ready to download")
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
