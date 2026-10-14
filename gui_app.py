import os
import sys
import re
import time
import json
import shutil
import threading
import unicodedata
import queue
import urllib.parse
import yt_dlp
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox

# Resolve base directory (PyInstaller bundled vs source)
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))

# Find FFmpeg binary dynamically
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

# Application icon paths
ICON_PNG = os.path.join(BASE_DIR, "assets", "icon_gold.png")
ICON_ICO = os.path.join(BASE_DIR, "assets", "app_icon.ico")
if not os.path.exists(ICON_PNG):
    alt_png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon_gold.png")
    if os.path.exists(alt_png):
        ICON_PNG = alt_png
if not os.path.exists(ICON_ICO):
    alt_ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "app_icon.ico")
    if os.path.exists(alt_ico):
        ICON_ICO = alt_ico

# Dynamic download directory and user settings
def get_default_download_dir():
    """Dynamically determine default download directory based on OS user Downloads folder."""
    user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.exists(user_downloads):
        return os.path.normpath(os.path.join(user_downloads, "Media Downloads"))
    return os.path.normpath(os.path.join(EXE_DIR, "downloads"))

def get_config_file():
    """Path to the user configuration file stored in %APPDATA% or ~/.universal_downloader."""
    appdata = os.getenv("APPDATA")
    if appdata and os.path.exists(appdata):
        cfg_dir = os.path.join(appdata, "UniversalDownloader")
    else:
        cfg_dir = os.path.join(os.path.expanduser("~"), ".universal_downloader")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "settings.json")

def load_saved_destination():
    """Load previously selected destination or fall back to dynamic default."""
    try:
        cfg_file = get_config_file()
        if os.path.exists(cfg_file):
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                saved = data.get("download_dir")
                if saved and os.path.exists(saved):
                    return os.path.normpath(saved)
    except Exception:
        pass
    return get_default_download_dir()

def save_destination(dest_path):
    """Save the user's chosen destination path for future sessions."""
    try:
        cfg_file = get_config_file()
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump({"download_dir": os.path.normpath(dest_path)}, f, indent=2)
    except Exception:
        pass

# Platform detection helper
def detect_platform(url):
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube"
    elif "instagram.com" in u:
        return "Instagram"
    elif "tiktok.com" in u:
        return "TikTok"
    elif "facebook.com" in u or "fb.watch" in u or "fb.com" in u:
        return "Facebook"
    elif "x.com" in u or "twitter.com" in u:
        return "X / Twitter"
    elif "reddit.com" in u or "redd.it" in u:
        return "Reddit"
    elif "pinterest.com" in u or "pin.it" in u:
        return "Pinterest"
    elif "vimeo.com" in u:
        return "Vimeo"
    elif "soundcloud.com" in u:
        return "SoundCloud"
    elif "twitch.tv" in u:
        return "Twitch"
    return "Universal Web"

def parse_url_structure(url):
    """Detect if a URL contains a single video, a playlist, or a video within a YouTube Mix/Radio."""
    u = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(u.query)
    is_yt = 'youtube.com' in u.netloc or 'youtu.be' in u.netloc
    
    vid = None
    if is_yt:
        if 'youtu.be' in u.netloc:
            vid = u.path.strip('/')
        else:
            vid = qs.get('v', [None])[0]
            
    plist = qs.get('list', [None])[0]
    is_mix = bool(plist and plist.startswith(('RD', 'UL', 'TL', 'PU', 'LL')))
    has_both = bool(vid and plist)
    clean_vid_url = f"https://www.youtube.com/watch?v={vid}" if vid else None
    
    return {
        "is_youtube": is_yt,
        "video_id": vid,
        "playlist_id": plist,
        "is_mix": is_mix,
        "has_both": has_both,
        "clean_video_url": clean_vid_url
    }

def clean_url(url, remove_playlist=False):
    """Clean URL by removing tracking params, timestamps, and optionally playlist/mix IDs."""
    try:
        u = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(u.query)
        
        # Strip tracking & session params
        for param in ['si', 'pp', 'feature', 't', 'fbclid', 'igshid', 'utm_source', 'utm_medium', 'utm_campaign']:
            qs.pop(param, None)
            
        is_yt = 'youtube.com' in u.netloc or 'youtu.be' in u.netloc
        if is_yt:
            vid = qs.get('v', [None])[0]
            plist = qs.get('list', [None])[0]
            is_mix = bool(plist and plist.startswith(('RD', 'UL', 'TL', 'PU', 'LL')))
            
            if vid and (remove_playlist or is_mix):
                return f"https://www.youtube.com/watch?v={vid}"
                
        new_query = urllib.parse.urlencode(qs, doseq=True)
        return urllib.parse.urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
    except Exception:
        return url

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
    t_clean = re.sub(r'\b(full video|lyric video|lyrics|lyrical|full song|official audio song|official audio|audio song|song|audio|hd|official|video|timeless classics|remastered|4k|reel|tiktok|post)\b', '', t_clean, flags=re.IGNORECASE)
    parts = re.split(r'[-|:]', t_clean)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    candidate = re.sub(r'[^a-zA-Z0-9]', '', parts[0].lower())
    if len(candidate) < 3 and len(parts) > 1:
        candidate = re.sub(r'[^a-zA-Z0-9]', '', (parts[0] + parts[1]).lower())
    return candidate


class CTkTooltip:
    """Displays a sleek dark obsidian & gold 1-line tooltip when hovering for 2s+ or on long-press.
    Strict singleton manager guarantees at most ONE tooltip exists across the entire application."""
    _current_window = None
    _current_owner = None

    @classmethod
    def dismiss_active(cls):
        """Immediately destroys any currently visible tooltip across the entire app."""
        if cls._current_window:
            try:
                cls._current_window.destroy()
            except Exception:
                pass
            cls._current_window = None
            cls._current_owner = None

    def __init__(self, widget, text, delay_ms=2000):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.timer_id = None
        self.press_timer_id = None

        self.widget.bind("<Enter>", self.on_enter, add="+")
        self.widget.bind("<Leave>", self.on_leave, add="+")
        self.widget.bind("<ButtonPress-1>", self.on_press, add="+")
        self.widget.bind("<ButtonRelease-1>", self.on_release, add="+")

    def on_enter(self, event=None):
        # Entering any button immediately dismisses any older tooltip from another button
        if CTkTooltip._current_owner is not self:
            CTkTooltip.dismiss_active()
        self.schedule_tooltip()

    def on_leave(self, event=None):
        self.cancel_timer()
        try:
            x, y = self.widget.winfo_pointerxy()
            containing = self.widget.winfo_containing(x, y)
            if containing and str(containing).startswith(str(self.widget)):
                return  # Pointer is still within this widget's internal canvas or text label
        except Exception:
            pass
        if CTkTooltip._current_owner is self:
            CTkTooltip.dismiss_active()

    def on_press(self, event=None):
        self.cancel_timer()
        CTkTooltip.dismiss_active()
        if self.press_timer_id:
            try:
                self.widget.after_cancel(self.press_timer_id)
            except Exception:
                pass
        self.press_timer_id = self.widget.after(1800, self.show_tooltip)

    def on_release(self, event=None):
        if self.press_timer_id:
            try:
                self.widget.after_cancel(self.press_timer_id)
            except Exception:
                pass
            self.press_timer_id = None

    def schedule_tooltip(self):
        self.cancel_timer()
        self.timer_id = self.widget.after(self.delay_ms, self.show_tooltip)

    def cancel_timer(self):
        if self.timer_id:
            try:
                self.widget.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None

    def show_tooltip(self):
        # Destroy any previously active tooltip before creating a new one
        CTkTooltip.dismiss_active()
        if not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + (self.widget.winfo_width() // 2)
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return

        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)

        frame = tk.Frame(tw, bg="#0E0E13", highlightbackground="#D4AF37", highlightthickness=1)
        frame.pack()

        lbl_icon = tk.Label(frame, text="◆ INFO", bg="#0E0E13", fg="#D4AF37", font=(FONT_FAMILY, 9, "bold"))
        lbl_icon.pack(side="left", padx=(10, 4), pady=6)

        lbl = tk.Label(frame, text=self.text, bg="#0E0E13", fg="#F4F4F5", font=(FONT_FAMILY, 10))
        lbl.pack(side="left", padx=(0, 12), pady=6)

        tw.update_idletasks()
        tip_w = tw.winfo_width()
        tip_h = tw.winfo_height()

        screen_w = tw.winfo_screenwidth()
        screen_h = tw.winfo_screenheight()
        pos_x = max(10, min(x - (tip_w // 2), screen_w - tip_w - 10))
        pos_y = y
        if pos_y + tip_h > screen_h - 20:
            pos_y = self.widget.winfo_rooty() - tip_h - 8

        tw.wm_geometry(f"+{pos_x}+{pos_y}")

        CTkTooltip._current_window = tw
        CTkTooltip._current_owner = self

    def hide_tooltip(self):
        if CTkTooltip._current_owner is self:
            CTkTooltip.dismiss_active()


class UniversalDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Appearance & Geometry
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.title("Universal Downloader · YouTube, Instagram, TikTok, Facebook, X")
        self.geometry("1160x820")
        self.minsize(1020, 720)

        # Set Window Titlebar and Taskbar Icon
        try:
            from PIL import Image, ImageTk
            if os.path.exists(ICON_PNG):
                ico_img = Image.open(ICON_PNG)
                self._app_icon_photo = ImageTk.PhotoImage(ico_img)
                self.wm_iconphoto(True, self._app_icon_photo)
            if os.path.exists(ICON_ICO):
                self.iconbitmap(ICON_ICO)
        except Exception:
            pass

        # State Variables
        self.stop_event = threading.Event()
        self.download_thread = None
        self.analysis_thread = None
        self.log_queue = queue.Queue()
        self.current_analysis = None
        self.single_cache = None
        self.playlist_cache = None
        self.is_downloading = False
        self.current_mode = "video" # Default to video for multi-platform clips

        # Download Manager items state
        self.manager_items = {} # title -> dict(card_widget, status_lbl, path)

        # Format mappings
        self.video_formats = {
            "MP4 Video · Best Available Quality": "video_best",
            "MP4 Video · 1080p Full HD": "video_1080",
            "MP4 Video · 720p HD": "video_720",
            "MP4 Video · 480p": "video_480"
        }
        self.audio_formats = {
            "MP3 · Maximum Quality (320 kbps)": "mp3_320",
            "MP3 · High Quality (192 kbps)": "mp3_192",
            "MP3 · Standard / USB (128 kbps CBR, 44.1kHz, ID3v2.3)": "mp3_speaker",
            "M4A · Original Audio Stream": "m4a"
        }
        self.all_formats = {**self.video_formats, **self.audio_formats}

        # Build UI Components
        self.create_layout()
        self.load_initial_downloads()
        self.poll_log_queue()

        # Global dismiss for active tooltips upon clicks or window repositioning
        self.bind_all("<Button-1>", lambda _e: CTkTooltip.dismiss_active(), add="+")
        self.bind("<Configure>", lambda _e: CTkTooltip.dismiss_active(), add="+")

        # Handle clean exit
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_layout(self):
        """
        Luxurious Gold + Sebino Soft Design System:
        - Primary typography: Sebino Soft Regular
        - Universal support: YouTube, Facebook, Instagram, TikTok, X (Twitter), Reddit, etc.
        - Color palette: Deep obsidian canvas (#09090B) with rich gold accents (#D4AF37, #E5C158)
        - Clean and minimal top header
        - Left sidebar: Dedicated Download Manager
        - Clean Save Location section without any hardcoded buttons or paths
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
            # Luxurious Gold Accent Palette (No red)
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

        # ---------------- 1. TOP HEADER ----------------
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

        try:
            from PIL import Image
            if os.path.exists(ICON_PNG):
                logo_pil = Image.open(ICON_PNG)
                self.logo_ctk_image = ctk.CTkImage(light_image=logo_pil, dark_image=logo_pil, size=(22, 22))
                lbl_logo = ctk.CTkLabel(brand_frame, text="", image=self.logo_ctk_image)
            else:
                lbl_logo = ctk.CTkLabel(brand_frame, text="⚡", font=ctk.CTkFont(size=15))
        except Exception:
            lbl_logo = ctk.CTkLabel(brand_frame, text="⚡", font=ctk.CTkFont(size=15))
        lbl_logo.pack(side="left", padx=(0, 8))

        lbl_title = ctk.CTkLabel(
            brand_frame, text="UNIVERSAL DOWNLOADER",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=self.tokens["text_primary"]
        )
        lbl_title.pack(side="left")

        lbl_tag = ctk.CTkLabel(
            brand_frame, text="· YOUTUBE, IG, TIKTOK, FB, X & 1000+ SITES",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=self.tokens["text_muted"]
        )
        lbl_tag.pack(side="left", padx=8)

        # Right side: Minimal version mark
        lbl_ver = ctk.CTkLabel(
            top_bar, text="v2.0.0",
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
            self.scroll_manager, text="No active downloads yet.\nPaste any video or audio link to start.",
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
        CTkTooltip(btn_open_folder, "Open the current downloads folder in Windows File Explorer.")

        btn_clear_dm = ctk.CTkButton(
            dm_footer, text="CLEAR LIST", height=26, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            fg_color="transparent", hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_muted"],
            command=self.clear_manager_list
        )
        btn_clear_dm.pack(fill="x", padx=8, pady=(0, 8))
        CTkTooltip(btn_clear_dm, "Clear completed items from the download manager list.")

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
            controls_panel, text="01 / SOURCE LINK (YOUTUBE, INSTAGRAM, TIKTOK, FACEBOOK, X & MORE)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(anchor="w", pady=(0, 6))

        url_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        url_row.pack(fill="x", pady=(0, 10))

        self.entry_url = ctk.CTkEntry(
            url_row, placeholder_text="Paste link from YouTube, Instagram, TikTok, Facebook, X, or any site...",
            height=40, corner_radius=4,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"], text_color=self.tokens["text_primary"],
            placeholder_text_color="#52525B", font=ctk.CTkFont(family=FONT_FAMILY, size=12)
        )
        self.entry_url.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_url.bind("<Return>", lambda _event: self.trigger_analyze())

        btn_paste = ctk.CTkButton(
            url_row, text="PASTE", width=70, height=40, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.tokens["gold_subtle"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border"],
            text_color=self.tokens["gold_bright"], command=self.paste_from_clipboard
        )
        btn_paste.pack(side="left", padx=(0, 6))
        CTkTooltip(btn_paste, "Paste link from clipboard and automatically inspect metadata.")

        self.btn_analyze = ctk.CTkButton(
            url_row, text="INSPECT", width=92, height=40, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.tokens["gold_subtle"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border_bright"],
            text_color=self.tokens["gold_bright"], command=self.trigger_analyze
        )
        self.btn_analyze.pack(side="left", padx=(0, 6))
        CTkTooltip(self.btn_analyze, "Inspect link metadata, duration, track count, and estimated file size.")

        btn_clear = ctk.CTkButton(
            url_row, text="CLEAR", width=64, height=40, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.tokens["gold_subtle"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border"],
            text_color=self.tokens["gold_bright"], command=self.clear_url_input
        )
        btn_clear.pack(side="left")
        CTkTooltip(btn_clear, "Clear the link input field and reset inspection card.")

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

        # Scope Selector (Visible when link has both a single video AND a playlist/mix)
        self.scope_row = ctk.CTkFrame(self.frame_analysis, fg_color="transparent")
        
        self.btn_scope_single = ctk.CTkButton(
            self.scope_row, text="THIS VIDEO ONLY", width=140, height=28, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=self.tokens["gold"], hover_color=self.tokens["gold_hover"],
            text_color=self.tokens["gold_text_dark"], command=lambda: self.switch_scope("single")
        )
        self.btn_scope_single.pack(side="left", padx=(0, 8))
        CTkTooltip(self.btn_scope_single, "Download only this single video, ignoring playlist or radio mix.")

        self.btn_scope_playlist = ctk.CTkButton(
            self.scope_row, text="FULL PLAYLIST", width=140, height=28, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["surface_hover"],
            border_width=1, border_color=self.tokens["border"],
            text_color=self.tokens["text_secondary"], command=lambda: self.switch_scope("playlist")
        )
        self.btn_scope_playlist.pack(side="left")
        CTkTooltip(self.btn_scope_playlist, "Download all media tracks in the full playlist or radio mix.")

        # Inspection Metric Chips Container (Gold accented)
        self.chips_row = ctk.CTkFrame(self.frame_analysis, fg_color="transparent")
        self.chips_row.pack(fill="x", padx=12, pady=(0, 10))

        self.chip_items = self.create_metric_pill(self.chips_row, "ITEMS", "0")
        self.chip_duration = self.create_metric_pill(self.chips_row, "DURATION", "0m")
        self.chip_size = self.create_metric_pill(self.chips_row, "EST. SIZE", "--")
        self.chip_spec = self.create_metric_pill(self.chips_row, "PROFILE", "1080p MP4")

        self.frame_analysis.pack_forget()

        # 2. Output Specification Block with Gold Segmented Switcher
        spec_header = ctk.CTkFrame(controls_panel, fg_color="transparent")
        spec_header.pack(fill="x", pady=(4, 6))

        ctk.CTkLabel(
            spec_header, text="02 / OUTPUT SPECIFICATION",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(side="left")

        # Gold Segmented Switcher ([ 🎬 VIDEO ] / [ ♫ AUDIO ])
        segmented_switcher = ctk.CTkFrame(
            spec_header, corner_radius=4,
            fg_color=self.tokens["surface"],
            border_width=1, border_color=self.tokens["border"]
        )
        segmented_switcher.pack(side="right")

        self.btn_mode_video = ctk.CTkButton(
            segmented_switcher, text="🎬 VIDEO", width=76, height=26, corner_radius=3,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=self.tokens["gold"], hover_color=self.tokens["gold_hover"],
            text_color=self.tokens["gold_text_dark"], command=lambda: self.switch_mode("video")
        )
        self.btn_mode_video.pack(side="left", padx=2, pady=2)
        CTkTooltip(self.btn_mode_video, "Switch output format selector to MP4 video profiles.")

        self.btn_mode_audio = ctk.CTkButton(
            segmented_switcher, text="♫ AUDIO", width=76, height=26, corner_radius=3,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color="transparent", hover_color=self.tokens["surface_hover"],
            text_color=self.tokens["text_secondary"], command=lambda: self.switch_mode("audio")
        )
        self.btn_mode_audio.pack(side="left", padx=2, pady=2)
        CTkTooltip(self.btn_mode_audio, "Switch output format selector to MP3 and AAC audio profiles.")

        # Format selector dropdown
        self.combo_format = ctk.CTkComboBox(
            controls_panel, values=list(self.video_formats.keys()),
            height=38, corner_radius=4,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"],
            button_color=self.tokens["surface_elevated"], button_hover_color=self.tokens["surface_hover"],
            dropdown_fg_color=self.tokens["surface"], dropdown_hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_primary"], font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=11), command=self.on_format_changed
        )
        self.combo_format.pack(fill="x", pady=(0, 4))
        self.combo_format.set("MP4 Video · Best Available Quality")

        self.lbl_format_hint = ctk.CTkLabel(
            controls_panel, text="[SPEC] Best Quality MP4 Video · Audio Muxed · Universal Codec Compatibility",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10), text_color=self.tokens["text_muted"], anchor="w"
        )
        self.lbl_format_hint.pack(fill="x", pady=(0, 10))

        # 3. Parameters Row: Save Path (dynamic default, persistent, no hardcoded pills)
        params_header = ctk.CTkFrame(controls_panel, fg_color="transparent")
        params_header.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            params_header, text="03 / SAVE LOCATION & LIMITS",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=self.tokens["text_muted"]
        ).pack(side="left")

        # Path input and limit row
        params_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        params_row.pack(fill="x", pady=(0, 10))
        params_row.grid_columnconfigure(0, weight=3)
        params_row.grid_columnconfigure(1, weight=1)

        dest_inner = ctk.CTkFrame(params_row, fg_color="transparent")
        dest_inner.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        initial_dest = load_saved_destination()
        self.entry_dest = ctk.CTkEntry(
            dest_inner, height=36, corner_radius=4,
            border_width=1, border_color=self.tokens["border"],
            fg_color=self.tokens["surface"], text_color=self.tokens["text_primary"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=11)
        )
        self.entry_dest.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_dest.insert(0, initial_dest)
        self.entry_dest.bind("<FocusOut>", lambda _event: save_destination(self.entry_dest.get().strip()))

        btn_browse = ctk.CTkButton(
            dest_inner, text="BROWSE", width=74, height=36, corner_radius=4,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=self.tokens["surface_elevated"], hover_color=self.tokens["surface_hover"],
            border_width=1, border_color=self.tokens["border"],
            text_color=self.tokens["text_primary"], command=self.browse_folder
        )
        btn_browse.pack(side="left")
        CTkTooltip(btn_browse, "Browse and choose a custom destination folder on your computer.")

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
        CTkTooltip(self.chk_dups, "Skip downloading any files that already exist in your destination folder.")

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
        CTkTooltip(self.btn_download, "Begin downloading the selected media files.")

        self.btn_stop = ctk.CTkButton(
            action_row, text="STOP", width=90, height=44, corner_radius=5,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.tokens["gold_subtle"], hover_color=self.tokens["gold_dark"],
            border_width=1, border_color=self.tokens["gold_border"],
            text_color=self.tokens["gold_bright"], state="disabled", command=self.stop_download
        )
        self.btn_stop.pack(side="left")
        CTkTooltip(self.btn_stop, "Cancel and halt the ongoing download task.")

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

        btn_clear_logs = ctk.CTkButton(
            console_toolbar, text="[CLEAR]", width=48, height=20, corner_radius=2,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            fg_color="transparent", hover_color=self.tokens["surface_elevated"],
            text_color=self.tokens["text_muted"], command=self.clear_logs
        )
        btn_clear_logs.grid(row=0, column=1, sticky="e")
        CTkTooltip(btn_clear_logs, "Clear the activity terminal log.")

        self.txt_terminal = ctk.CTkTextbox(
            term_body, corner_radius=0, fg_color="#060608", text_color="#D4D4D8",
            border_width=1, border_color=self.tokens["border"],
            font=ctk.CTkFont(family="Consolas", size=10),
            activate_scrollbars=True
        )
        self.txt_terminal.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.append_log("[SYS] Universal Media Downloader initialized.")
        self.append_log("[SYS] Native support: YouTube, Facebook, Instagram, TikTok, X (Twitter), Reddit & 1000+ sites.")

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
                data["status_lbl"].configure(text=self.tokens["text_muted"])
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

        fmt_short = format_label.split("·")[0].strip() if "·" in format_label else (format_label[:14] if format_label else "Media")
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
        p = self.entry_dest.get().strip() or get_default_download_dir()
        try:
            os.makedirs(p, exist_ok=True)
            os.startfile(p)
        except Exception:
            messagebox.showinfo("Notice", f"Unable to open destination folder:\n{p}")

    def locate_file(self, filepath):
        if filepath and os.path.exists(filepath):
            try:
                subprocess_dir = os.path.dirname(filepath)
                os.startfile(subprocess_dir)
            except Exception:
                self.open_current_destination()
        else:
            self.open_current_destination()

    def load_initial_downloads(self):
        """Populate the download manager with existing recent downloads from destination folder."""
        dest = self.entry_dest.get().strip() or get_default_download_dir()
        try:
            if os.path.exists(dest):
                files = [f for f in os.listdir(dest) if f.lower().endswith(('.mp3', '.m4a', '.mp4', '.mkv', '.webm'))]
                # Sort by modification time descending
                files.sort(key=lambda f: os.path.getmtime(os.path.join(dest, f)), reverse=True)
                for f in files[:15]:
                    full_p = os.path.join(dest, f)
                    f_lower = f.lower()
                    if f_lower.endswith(('.mp4', '.mkv', '.webm', '.mov')):
                        if '[best]' in f_lower: fmt_tag = "MP4 · Best"
                        elif '[1080p]' in f_lower: fmt_tag = "MP4 · 1080p"
                        elif '[720p]' in f_lower: fmt_tag = "MP4 · 720p"
                        elif '[480p]' in f_lower: fmt_tag = "MP4 · 480p"
                        else: fmt_tag = "MP4 Video"
                    else:
                        if '[320k]' in f_lower: fmt_tag = "MP3 · 320k"
                        elif '[192k]' in f_lower: fmt_tag = "MP3 · 192k"
                        elif '[128k]' in f_lower: fmt_tag = "MP3 · 128k"
                        elif f_lower.endswith('.m4a'): fmt_tag = "AAC M4A"
                        else: fmt_tag = "MP3 Audio"
                    self.add_manager_item(f, f, "✓ Saved", fmt_tag, full_p)
        except Exception:
            pass

    # ---------------- UI Event Handlers ----------------

    def switch_mode(self, mode):
        """Toggle between Video and Audio mode via Gold segmented pills."""
        self.current_mode = mode
        if mode == "video":
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
            self.combo_format.set("MP4 Video · Best Available Quality")
            self.on_format_changed("MP4 Video · Best Available Quality")
        else:
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
            self.combo_format.set("MP3 · Maximum Quality (320 kbps)")
            self.on_format_changed("MP3 · Maximum Quality (320 kbps)")

    def paste_from_clipboard(self):
        try:
            txt = self.clipboard_get().strip()
            if txt:
                self.entry_url.delete(0, "end")
                self.entry_url.insert(0, txt)
                if txt.startswith("http://") or txt.startswith("https://"):
                    self.trigger_analyze()
        except Exception:
            pass

    def clean_url_input(self):
        url = self.entry_url.get().strip()
        if url:
            cleaned = clean_url(url, remove_playlist=True)
            self.entry_url.delete(0, "end")
            self.entry_url.insert(0, cleaned)
            self.append_log("[SYS] URL sanitized: stripped tracking parameters & mix radio playlist.")
            self.trigger_analyze()

    def clear_url_input(self):
        self.entry_url.delete(0, "end")
        self.current_analysis = None
        self.single_cache = None
        self.playlist_cache = None
        self.frame_analysis.pack_forget()
        self.append_log("[SYS] URL input and inspection card cleared.")

    def switch_scope(self, scope):
        if not self.current_analysis or not self.current_analysis.get("has_both"):
            return
        url = self.current_analysis.get("original_url") or self.entry_url.get().strip()
        if scope == "single":
            self.current_analysis["active_scope"] = "single"
            self.btn_scope_single.configure(
                fg_color=self.tokens["gold"],
                hover_color=self.tokens["gold_hover"],
                text_color=self.tokens["gold_text_dark"]
            )
            self.btn_scope_playlist.configure(
                fg_color=self.tokens["surface_elevated"],
                hover_color=self.tokens["surface_hover"],
                text_color=self.tokens["text_secondary"]
            )
            if self.single_cache:
                self.current_analysis = self.single_cache
                self.update_analysis_meta(self.single_cache)
        else:
            self.current_analysis["active_scope"] = "playlist"
            self.btn_scope_single.configure(
                fg_color=self.tokens["surface_elevated"],
                hover_color=self.tokens["surface_hover"],
                text_color=self.tokens["text_secondary"]
            )
            self.btn_scope_playlist.configure(
                fg_color=self.tokens["gold"],
                hover_color=self.tokens["gold_hover"],
                text_color=self.tokens["gold_text_dark"]
            )
            if self.playlist_cache:
                self.current_analysis = self.playlist_cache
                self.update_analysis_meta(self.playlist_cache)
            else:
                self.lbl_an_title.configure(text="Fetching full playlist metadata...")
                def worker():
                    try:
                        res = self.fetch_analysis(url, scope="playlist")
                        self.playlist_cache = res
                        self.after(0, lambda: self.on_playlist_loaded(res))
                    except Exception as e:
                        self.after(0, lambda: self.append_log(f"[ERR] Failed to load playlist: {e}"))
                threading.Thread(target=worker, daemon=True).start()

    def on_playlist_loaded(self, res):
        if self.current_analysis and self.current_analysis.get("active_scope") == "playlist":
            self.current_analysis = res
            self.update_analysis_meta(res)
            self.append_log(f"[OK] Full playlist loaded: '{res['title']}' ({res['track_count']} item(s), {res['duration_str']})")

    def on_format_changed(self, choice):
        selected_code = self.all_formats.get(choice, "video_best")

        if selected_code.startswith("video_"):
            self.lbl_format_hint.configure(
                text=f"[SPEC] {selected_code.replace('video_', '').upper()} MP4 Video · Audio Muxed · Universal Codec Compatibility"
            )
        else:
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
        norm_path = os.path.normpath(path)
        self.entry_dest.delete(0, "end")
        self.entry_dest.insert(0, norm_path)
        save_destination(norm_path)
        self.append_log(f"[DIR] Destination set: {norm_path}")

    def browse_folder(self):
        curr = self.entry_dest.get().strip() or get_default_download_dir()
        selected = filedialog.askdirectory(initialdir=curr, title="Select Download Folder")
        if selected:
            self.set_destination(selected)

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

    # ---------------- Link Analysis (Universal) ----------------

    def trigger_analyze(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Notice", "Please paste a video or audio link first.")
            return

        platform_name = detect_platform(url)
        self.btn_analyze.configure(state="disabled", text="CHECKING")
        self.append_log(f"[GET] Inspecting {platform_name} link: {url}")

        def worker():
            try:
                res = self.fetch_analysis(url, scope="single")
                self.after(0, lambda: self.on_analysis_success(res))
            except Exception as e:
                self.after(0, lambda: self.on_analysis_error(str(e)))

        self.analysis_thread = threading.Thread(target=worker, daemon=True)
        self.analysis_thread.start()

    def fetch_analysis(self, url, scope=None):
        platform = detect_platform(url)
        parsed = parse_url_structure(url)

        target_url = url
        active_scope = "single"
        if parsed["has_both"]:
            if scope == "playlist":
                active_scope = "playlist"
                target_url = url
            else:
                active_scope = "single"
                target_url = parsed["clean_video_url"]
        elif scope == "single" and parsed["clean_video_url"]:
            active_scope = "single"
            target_url = parsed["clean_video_url"]

        ydl_opts = {
            'quiet': True,
            'extract_flat': (active_scope == "playlist"),
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            is_playlist = 'entries' in info and bool(info.get('entries'))
            entries = [e for e in info.get('entries', []) if e] if is_playlist else [info]

            valid = []
            total_dur = 0
            for e in entries:
                if not e:
                    continue
                t = e.get('title') or info.get('title') or f"{platform} Media"
                dur = e.get('duration') or 0
                item_url = e.get('webpage_url') or e.get('url') or e.get('original_url')
                if not item_url:
                    if ('youtube' in url.lower() or 'youtu.be' in url.lower()) and e.get('id'):
                        item_url = f"https://www.youtube.com/watch?v={e['id']}"
                    else:
                        item_url = target_url
                valid.append({
                    'id': e.get('id') or str(len(valid) + 1),
                    'title': t,
                    'duration': dur,
                    'url': item_url,
                    'platform': platform
                })
                total_dur += dur

            total_hours = total_dur / 3600
            if total_hours >= 1:
                dur_str = f"{int(total_hours)}h {int((total_dur%3600)/60)}m"
            elif total_dur >= 60:
                dur_str = f"{int(total_dur/60)}m {int(total_dur%60)}s"
            elif total_dur > 0:
                dur_str = f"{int(total_dur)}s"
            else:
                dur_str = "Clip"

            media_title = info.get('title') or (valid[0]['title'] if valid else f"{platform} Media")

            return {
                "title": media_title,
                "platform": platform,
                "is_playlist": is_playlist,
                "has_both": parsed["has_both"],
                "is_mix": parsed["is_mix"],
                "active_scope": active_scope,
                "clean_video_url": parsed["clean_video_url"],
                "playlist_id": parsed["playlist_id"],
                "original_url": url,
                "track_count": len(valid),
                "duration_str": dur_str,
                "total_duration": total_dur,
                "items": valid
            }

    def on_analysis_success(self, res):
        self.current_analysis = res
        self.single_cache = res
        self.btn_analyze.configure(state="normal", text="INSPECT")
        self.frame_analysis.pack(fill="x", pady=(0, 10))

        # Setup Scope Buttons
        if res.get("has_both"):
            self.scope_row.pack(fill="x", padx=12, pady=(0, 8))
            self.btn_scope_single.configure(
                fg_color=self.tokens["gold"],
                text_color=self.tokens["gold_text_dark"]
            )
            self.btn_scope_playlist.configure(
                fg_color=self.tokens["surface_elevated"],
                text_color=self.tokens["text_secondary"]
            )
        else:
            self.scope_row.pack_forget()

        self.update_analysis_meta(res)
        tag_extra = " (YouTube Mix Auto-Protected: Single Video)" if res.get("is_mix") else ""
        self.append_log(f"[OK] {res['platform']} link verified{tag_extra}: '{res['title']}' ({res['track_count']} item(s), {res['duration_str']})")

    def update_analysis_meta(self, res):
        chosen_format = self.all_formats.get(self.combo_format.get(), "video_best")
        dur = res["total_duration"]
        platform = res.get("platform", "Media")

        if chosen_format.startswith("video_"):
            if chosen_format in ("video_720", "video_480"):
                mb = max(5.0, (320000 * max(10, dur)) / (1024 * 1024))
            else:
                mb = max(10.0, (580000 * max(10, dur)) / (1024 * 1024))
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = f"{chosen_format.replace('video_', '').upper()} MP4"
        elif chosen_format == "mp3_320":
            mb = max(2.0, (40000 * max(10, dur)) / (1024 * 1024))
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = "320k MP3"
        elif chosen_format == "mp3_192":
            mb = max(1.5, (24000 * max(10, dur)) / (1024 * 1024))
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = "192k MP3"
        elif chosen_format == "m4a":
            mb = max(1.0, (16000 * max(10, dur)) / (1024 * 1024))
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = "AAC M4A"
        else:
            mb = max(1.0, (16000 * max(10, dur)) / (1024 * 1024))
            est_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"
            profile_str = "128k CBR MP3"

        self.lbl_an_badge.configure(text=f"▶ VERIFIED {platform.upper()}")
        self.lbl_an_title.configure(text=res['title'])
        self.chip_items.configure(text=f"{res['track_count']} item(s)")
        self.chip_duration.configure(text=res['duration_str'])
        self.chip_size.configure(text=est_str)
        self.chip_spec.configure(text=profile_str)

    def on_analysis_error(self, err):
        self.btn_analyze.configure(state="normal", text="INSPECT")
        self.append_log(f"[ERR] Inspection failed: {err}")

    # ---------------- Universal Download Engine ----------------

    def start_download(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Notice", "Please paste a media link before downloading.")
            return

        dest_dir = self.entry_dest.get().strip()
        if not dest_dir:
            dest_dir = get_default_download_dir()
        save_destination(dest_dir)

        chosen_label = self.combo_format.get()
        download_type = self.all_formats.get(chosen_label, "video_best")
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
        self.lbl_progress_status.configure(text="Initializing universal download engine...")
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
        video_quality = download_type.replace("video_", "") if is_video else "best"
        bitrate = "320" if download_type == "mp3_320" else ("192" if download_type == "mp3_192" else "128")

        if is_video:
            if video_quality == 'best':
                q_tag = "Best"
                q_tier = "best"
            elif video_quality == '1080':
                q_tag = "1080p"
                q_tier = "1080"
            elif video_quality == '720':
                q_tag = "720p"
                q_tier = "720"
            elif video_quality == '480':
                q_tag = "480p"
                q_tier = "480"
            else:
                q_tag = video_quality.upper()
                q_tier = video_quality.lower()
        else:
            if download_type == "mp3_320":
                q_tag = "320k"
                q_tier = "320"
            elif download_type == "mp3_192":
                q_tag = "192k"
                q_tier = "192"
            elif download_type == "mp3_speaker":
                q_tag = "128k"
                q_tier = "128"
            elif download_type == "m4a":
                q_tag = "m4a"
                q_tier = "m4a"
            else:
                q_tag = "128k"
                q_tier = "128"

        platform = detect_platform(url)
        self.append_log(f"[QUEUE] Platform detected: {platform}")
        self.append_log(f"[QUEUE] Target directory: {dest_dir}")
        self.append_log(f"[QUEUE] Format profile: {download_type} ({q_tag})")

        # Smart target URL resolution: Single video vs Playlist
        parsed = parse_url_structure(url)
        target_download_url = url
        if hasattr(self, 'current_analysis') and self.current_analysis and self.current_analysis.get("has_both"):
            if self.current_analysis.get("active_scope") == "single":
                target_download_url = self.current_analysis.get("clean_video_url") or url
        elif parsed.get("is_mix") and parsed.get("clean_video_url"):
            # Auto-guard against dynamic radio mixes when user didn't explicitly inspect & switch to playlist
            target_download_url = parsed["clean_video_url"]

        # Extract info
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            }
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_download_url, download=False)
        except Exception as e:
            self.append_log(f"[ERR] Failed to extract URL info: {e}")
            self.after(0, self.finish_download)
            return

        is_playlist = 'entries' in info and bool(info.get('entries'))
        entries = [e for e in info.get('entries', []) if e] if is_playlist else [info]

        # Scan existing files for duplicate check with quality awareness
        if is_video:
            existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(('.mp4', '.mkv', '.webm', '.mov', '.avi'))]
        else:
            existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(('.mp3', '.m4a', '.opus', '.aac', '.flac'))]

        existing_records_by_key = {}
        max_idx = 0
        for f in existing_files:
            m = re.match(r'^(\d+)\s*-\s*(.+)\.[a-z0-9]+$', f, re.IGNORECASE)
            if m:
                num = int(m.group(1))
                if num > max_idx:
                    max_idx = num
                raw_title = m.group(2)
            else:
                raw_title = os.path.splitext(f)[0]

            k = get_core_title_key(raw_title)

            # Check for explicit quality tag in filename: e.g. [1080p], [720p], [Best], [320k]
            m_tag = re.search(r'\[(best|2160p?|4k|1440p?|1080p?|720p?|480p?|360p?|320k|192k|128k|m4a)\]', f, re.IGNORECASE)
            detected_tag = None
            if m_tag:
                raw_tag = m_tag.group(1).lower()
                if raw_tag in ('best', '2160', '2160p', '4k', '1440', '1440p'):
                    detected_tag = 'best'
                elif '1080' in raw_tag:
                    detected_tag = '1080'
                elif '720' in raw_tag:
                    detected_tag = '720'
                elif '480' in raw_tag:
                    detected_tag = '480'
                elif '320' in raw_tag:
                    detected_tag = '320'
                elif '192' in raw_tag:
                    detected_tag = '192'
                elif '128' in raw_tag:
                    detected_tag = '128'
                elif 'm4a' in raw_tag:
                    detected_tag = 'm4a'

            if k not in existing_records_by_key:
                existing_records_by_key[k] = []
            existing_records_by_key[k].append({
                'filename': f,
                'filepath': os.path.join(dest_dir, f),
                'tag': detected_tag,
                'is_video': is_video
            })

        queue_items = []
        seen_keys = set()
        for idx, e in enumerate(entries, 1):
            if not e:
                continue
            t = e.get('title') or info.get('title') or f"{platform}_Track_{idx}"
            vid = e.get('id') or str(idx)
            dur = e.get('duration') or 0
            item_url = e.get('webpage_url') or e.get('url') or e.get('original_url')
            if not item_url:
                if ('youtube' in url.lower() or 'youtu.be' in url.lower()) and e.get('id'):
                    item_url = f"https://www.youtube.com/watch?v={e['id']}"
                else:
                    item_url = target_download_url

            k = get_core_title_key(t)
            is_dup = False
            dup_reason = ""

            if ignore_dups and k in existing_records_by_key:
                for rec in existing_records_by_key[k]:
                    # If this existing file didn't have a tag in its name, probe it on-demand
                    if rec['tag'] is None and is_video and os.path.exists(rec['filepath']):
                        try:
                            probe_res = subprocess.run([FFMPEG_EXE, '-i', rec['filepath']], capture_output=True, text=True, timeout=1)
                            m_res = re.search(r'(\d{3,4})x(\d{3,4})', probe_res.stderr)
                            if m_res:
                                w_val, h_val = int(m_res.group(1)), int(m_res.group(2))
                                tier = min(w_val, h_val)
                                if tier > 1080: rec['tag'] = 'best'
                                elif tier >= 900: rec['tag'] = '1080'
                                elif tier >= 600: rec['tag'] = '720'
                                elif tier >= 400: rec['tag'] = '480'
                                else: rec['tag'] = '360'
                        except Exception:
                            pass

                    # Compare requested quality profile
                    if is_video:
                        if rec['tag'] == q_tier:
                            is_dup = True
                            dup_reason = f"Existing ({q_tag}): {rec['filename']}"
                            break
                        elif q_tier == 'best' and rec['tag'] in ('best', '2160', '4k'):
                            is_dup = True
                            dup_reason = f"Existing (Best): {rec['filename']}"
                            break
                    else:
                        if rec['tag'] == q_tier:
                            is_dup = True
                            dup_reason = f"Existing ({q_tag}): {rec['filename']}"
                            break
                        elif rec['tag'] is None:
                            if (download_type == 'm4a' and rec['filename'].lower().endswith('.m4a')) or \
                               (download_type.startswith('mp3') and rec['filename'].lower().endswith('.mp3')):
                                is_dup = True
                                dup_reason = f"Existing Audio: {rec['filename']}"
                                break

            if is_dup:
                self.append_log(f"[SKIP] {dup_reason}")
                continue

            if k in seen_keys:
                self.append_log(f"[SKIP] Duplicate in batch: {t}")
                continue

            seen_keys.add(k)
            queue_items.append({'id': vid, 'title': t, 'duration': dur, 'url': item_url, 'key': k})
            if max_tracks > 0 and len(queue_items) >= max_tracks:
                break

        total_queue = len(queue_items)
        self.append_log(f"[QUEUE] {total_queue} item(s) queued for download.")

        if total_queue == 0:
            self.append_log(f"[OK] All requested items already exist in destination ({format_label}).")
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
                self.append_log("[STOP] Download process interrupted by user.")
                break

            current_idx = i + 1
            track_num = start_num + i
            cleaned = clean_filename(item['title'], track_num)
            ext_target = "mp4" if is_video else ("m4a" if download_type == "m4a" else "mp3")
            track_prefix = f"{track_num:03d} - " if total_queue > 1 else ""

            if is_video:
                # Video files always carry their resolution profile tag for clean distinction
                clean_title = re.sub(r'\s*\[(best|2160p?|4k|1440p?|1080p?|720p?|480p?|360p?|320k|192k|128k|m4a)\]$', '', cleaned, flags=re.IGNORECASE)
                filename_base = f"{track_prefix}{clean_title} [{q_tag}]"
            else:
                # For audio: if an existing untagged file exists with different bitrate, tag it to avoid collision
                plain_path = os.path.join(dest_dir, f"{track_prefix}{cleaned}.{ext_target}")
                if os.path.exists(plain_path):
                    clean_title = re.sub(r'\s*\[(320k|192k|128k|m4a)\]$', '', cleaned, flags=re.IGNORECASE)
                    filename_base = f"{track_prefix}{clean_title} [{q_tag}]"
                else:
                    filename_base = f"{track_prefix}{cleaned}"

            full_target_path = os.path.join(dest_dir, f"{filename_base}.{ext_target}")

            # Register in Download Manager
            self.after(0, lambda name=filename_base, fmt=format_label: self.add_manager_item(name, name, "⏳ Downloading...", fmt))

            self.after(0, lambda n=current_idx, t=total_queue, name=item['title']: self.lbl_progress_status.configure(
                text=f"[{n}/{t}] Processing: {name[:55]}"
            ))
            self.append_log(f"[GET] [{current_idx}/{total_queue}] {item['title']}")

            if is_video:
                if video_quality == 'best':
                    fmt_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
                elif video_quality == '720':
                    fmt_str = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best'
                elif video_quality == '480':
                    fmt_str = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best'
                else:
                    fmt_str = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'

                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'ffmpeg_location': FFMPEG_EXE,
                    'format': fmt_str,
                    'merge_output_format': 'mp4',
                    'outtmpl': os.path.join(dest_dir, f"{filename_base}.%(ext)s"),
                    'overwrites': True,
                    'progress_hooks': [progress_hook],
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                    }
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
                    'overwrites': True,
                    'progress_hooks': [progress_hook],
                    'postprocessors': postprocessors,
                    'postprocessor_args': postprocessor_args,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                    }
                }

            try:
                target_download_url = item.get('url') or url
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([target_download_url])
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

        self.append_log(f"[DONE] Completed. Downloaded {downloaded_count} item(s).")
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


# Compatibility alias
YouTubeDownloaderApp = UniversalDownloaderApp

if __name__ == '__main__':
    app = UniversalDownloaderApp()
    app.mainloop()
