import os
import sys
import re
import json
import time
import shutil
import threading
import unicodedata
import subprocess

# Configure mobile simulation viewport if running on desktop
from kivy.config import Config
Config.set('graphics', 'width', '412')
Config.set('graphics', 'height', '860')
Config.set('graphics', 'resizable', '1')
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

import kivy
from kivy.app import App
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.progressbar import ProgressBar
from kivy.uix.behaviors import ButtonBehavior

# Import modular download engine
sys.path.insert(0, os.path.dirname(__file__))
import downloader_engine as engine

# Register Custom Font
FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "fonts", "Sebino-Soft-Regular.ttf")
if os.path.exists(FONT_PATH):
    LabelBase.register(name="Sebino", fn_regular=FONT_PATH)
    FONT_FAMILY = "Sebino"
else:
    FONT_FAMILY = "Roboto"

# Check Android Environment & PyJNIus
try:
    from jnius import autoclass
    from android.permissions import request_permissions, Permission
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Intent = autoclass('android.content.Intent')
    Uri = autoclass('android.net.Uri')
    IS_ANDROID = True
except Exception:
    IS_ANDROID = False

# Luxury Gold Theme Palette (Zero Red)
COLOR_BG = [0.055, 0.055, 0.075, 1.0]        # Deep Obsidian #0E0E13
COLOR_SURFACE = [0.10, 0.10, 0.13, 1.0]      # Card Surface #1A1A21
COLOR_SURFACE_ALT = [0.13, 0.13, 0.17, 1.0]  # Secondary Card #21212B
COLOR_BORDER = [0.18, 0.18, 0.23, 1.0]       # Subtle Border #2E2E3B
COLOR_GOLD = [0.83, 0.69, 0.22, 1.0]         # Primary Gold #D4AF37
COLOR_GOLD_LIGHT = [0.90, 0.76, 0.35, 1.0]   # Gold Hover #E5C158
COLOR_GOLD_DARK = [0.65, 0.52, 0.14, 1.0]    # Gold Accent Border
COLOR_TEXT_WHITE = [0.96, 0.96, 0.98, 1.0]   # Main Text
COLOR_TEXT_MUTED = [0.60, 0.60, 0.67, 1.0]   # Muted Text
COLOR_GREEN = [0.20, 0.78, 0.45, 1.0]        # Success Badge #33C773


# Reusable Styled Components
class CardBox(BoxLayout):
    """Luxury card container with rounded corners and subtle border."""
    def __init__(self, bg_color=COLOR_SURFACE, border_color=COLOR_BORDER, radius=12, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.border_color = border_color
        self.radius = radius
        with self.canvas.before:
            self.col_bg = Color(*self.bg_color)
            self.rect_bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self.col_border = Color(*self.border_color)
            self.rect_border = Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], self.radius), width=1.1)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

    def _update_canvas(self, *args):
        self.rect_bg.pos = self.pos
        self.rect_bg.size = self.size
        self.rect_border.rounded_rectangle = (self.pos[0], self.pos[1], self.size[0], self.size[1], self.radius)


class GoldButton(ButtonBehavior, BoxLayout):
    """Modern gold touch button with tactile feedback."""
    def __init__(self, text="", icon="", is_outline=False, height_dp=48, **kwargs):
        kwargs['size_hint_y'] = None
        kwargs['height'] = height_dp
        super().__init__(**kwargs)
        self.text = text
        self.is_outline = is_outline
        self.orientation = "horizontal"
        self.padding = [12, 6]

        self.normal_bg = [0, 0, 0, 0] if is_outline else COLOR_GOLD
        self.pressed_bg = [0.83, 0.69, 0.22, 0.2] if is_outline else COLOR_GOLD_LIGHT
        self.border_col = COLOR_GOLD if is_outline else [0, 0, 0, 0]

        with self.canvas.before:
            self.canvas_bg = Color(*self.normal_bg)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
            self.canvas_border = Color(*self.border_col)
            self.line_border = Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], 10), width=1.2)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

        self.lbl = Label(
            text=self.text,
            font_name=FONT_FAMILY,
            font_size="15sp",
            bold=True,
            color=COLOR_GOLD if is_outline else [0.08, 0.08, 0.09, 1.0],
            halign="center",
            valign="middle"
        )
        self.lbl.bind(size=self.lbl.setter('text_size'))
        self.add_widget(self.lbl)

    def _update_canvas(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
        self.line_border.rounded_rectangle = (self.pos[0], self.pos[1], self.size[0], self.size[1], 10)

    def on_press(self):
        self.canvas_bg.rgba = self.pressed_bg

    def on_release(self):
        self.canvas_bg.rgba = self.normal_bg

    def set_text(self, text):
        self.text = text
        self.lbl.text = text


class NavButton(ButtonBehavior, BoxLayout):
    """Bottom navigation bar button."""
    def __init__(self, title="", icon_char="", target_screen="", app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.target_screen = target_screen
        self.app_ref = app_ref
        self.padding = [2, 4]
        self.spacing = 2
        self.is_active = False

        self.lbl_icon = Label(
            text=icon_char,
            font_name=FONT_FAMILY,
            font_size="18sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=0.6
        )
        self.lbl_text = Label(
            text=title,
            font_name=FONT_FAMILY,
            font_size="11sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=0.4
        )
        self.add_widget(self.lbl_icon)
        self.add_widget(self.lbl_text)

    def set_active(self, active):
        self.is_active = active
        c = COLOR_GOLD if active else COLOR_TEXT_MUTED
        self.lbl_icon.color = c
        self.lbl_text.color = c

    def on_release(self):
        if self.app_ref:
            self.app_ref.switch_screen(self.target_screen)


# ==========================================================
# SCREEN 1: HOME / DOWNLOADER
# ==========================================================
class HomeScreen(Screen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.active_analysis = None
        self.selected_format = "video_best"
        self.is_downloading = False
        self.stop_event = threading.Event()

        root = BoxLayout(orientation="vertical", padding=[16, 12, 16, 75], spacing=12)

        # Header
        hdr = BoxLayout(orientation="vertical", size_hint_y=None, height=52, spacing=2)
        lbl_brand = Label(
            text="UNIVERSAL DOWNLOADER",
            font_name=FONT_FAMILY,
            font_size="17sp",
            bold=True,
            color=COLOR_GOLD,
            halign="left"
        )
        lbl_brand.bind(size=lbl_brand.setter('text_size'))
        lbl_sub = Label(
            text="YouTube · Instagram · TikTok · X · Facebook · Reddit",
            font_name=FONT_FAMILY,
            font_size="11sp",
            color=COLOR_TEXT_MUTED,
            halign="left"
        )
        lbl_sub.bind(size=lbl_sub.setter('text_size'))
        hdr.add_widget(lbl_brand)
        hdr.add_widget(lbl_sub)
        root.add_widget(hdr)

        # Scrollable Content
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=14)
        content.bind(minimum_height=content.setter('height'))

        # Input Card
        card_input = CardBox(orientation="vertical", padding=12, spacing=10, size_hint_y=None, height=140)
        lbl_in_title = Label(
            text="MEDIA LINK",
            font_name=FONT_FAMILY,
            font_size="12sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=18,
            halign="left"
        )
        lbl_in_title.bind(size=lbl_in_title.setter('text_size'))
        card_input.add_widget(lbl_in_title)

        self.input_url = TextInput(
            hint_text="Paste video, reel, post, or playlist link...",
            font_name=FONT_FAMILY,
            font_size="13sp",
            multiline=False,
            size_hint_y=None,
            height=42,
            background_color=COLOR_SURFACE_ALT,
            foreground_color=COLOR_TEXT_WHITE,
            cursor_color=COLOR_GOLD,
            padding=[10, 10]
        )
        self.input_url.bind(text=self.on_url_text_change)
        card_input.add_widget(self.input_url)

        # Quick Actions Row
        actions_row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=38)
        self.btn_paste = GoldButton(text="PASTE", is_outline=True, height_dp=38, size_hint_x=0.45)
        self.btn_paste.bind(on_release=self.action_paste)
        self.btn_inspect = GoldButton(text="INSPECT", is_outline=True, height_dp=38, size_hint_x=0.55)
        self.btn_inspect.bind(on_release=self.action_inspect)
        actions_row.add_widget(self.btn_paste)
        actions_row.add_widget(self.btn_inspect)
        card_input.add_widget(actions_row)
        content.add_widget(card_input)

        # Inspection Results Card (Dynamic)
        self.card_inspect = CardBox(orientation="vertical", padding=12, spacing=8, size_hint_y=None, height=130)
        self.badge_platform = Label(
            text="▶ WAITING FOR LINK",
            font_name=FONT_FAMILY,
            font_size="11sp",
            bold=True,
            color=COLOR_GOLD,
            size_hint_y=None,
            height=20,
            halign="left"
        )
        self.badge_platform.bind(size=self.badge_platform.setter('text_size'))
        self.lbl_inspect_title = Label(
            text="No media inspected yet",
            font_name=FONT_FAMILY,
            font_size="14sp",
            bold=True,
            color=COLOR_TEXT_WHITE,
            size_hint_y=None,
            height=36,
            halign="left"
        )
        self.lbl_inspect_title.bind(size=self.lbl_inspect_title.setter('text_size'))

        # Metrics row
        row_chips = BoxLayout(orientation="horizontal", spacing=6, size_hint_y=None, height=28)
        self.chip_items = Label(text="-- items", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED)
        self.chip_dur = Label(text="-- duration", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED)
        self.chip_size = Label(text="-- size", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED)
        row_chips.add_widget(self.chip_items)
        row_chips.add_widget(self.chip_dur)
        row_chips.add_widget(self.chip_size)

        self.card_inspect.add_widget(self.badge_platform)
        self.card_inspect.add_widget(self.lbl_inspect_title)
        self.card_inspect.add_widget(row_chips)
        content.add_widget(self.card_inspect)

        # Format Selector Card
        card_format = CardBox(orientation="vertical", padding=12, spacing=8, size_hint_y=None, height=135)
        lbl_fmt_head = Label(
            text="SELECT OUTPUT PROFILE",
            font_name=FONT_FAMILY,
            font_size="12sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=18,
            halign="left"
        )
        lbl_fmt_head.bind(size=lbl_fmt_head.setter('text_size'))
        card_format.add_widget(lbl_fmt_head)

        # Format Chips Grid
        grid_fmt = GridLayout(cols=3, spacing=6, size_hint_y=None, height=80)
        self.fmt_buttons = {}
        formats = [
            ("video_best", "MP4 Best"),
            ("video_720", "MP4 720p"),
            ("mp3_320", "MP3 320k"),
            ("mp3_192", "MP3 192k"),
            ("mp3_128", "Car/USB 128k"),
            ("m4a", "AAC M4A"),
        ]
        for key, name in formats:
            btn = GoldButton(text=name, is_outline=(key != self.selected_format), height_dp=36)
            btn.bind(on_release=lambda instance, k=key: self.select_format(k))
            self.fmt_buttons[key] = btn
            grid_fmt.add_widget(btn)

        card_format.add_widget(grid_fmt)
        content.add_widget(card_format)

        # Download HUD / Progress Card
        self.card_progress = CardBox(orientation="vertical", padding=12, spacing=8, size_hint_y=None, height=105)
        self.lbl_progress_status = Label(
            text="Ready to download",
            font_name=FONT_FAMILY,
            font_size="12sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=20,
            halign="left"
        )
        self.lbl_progress_status.bind(size=self.lbl_progress_status.setter('text_size'))

        self.bar_progress = ProgressBar(max=100, value=0, size_hint_y=None, height=14)
        
        row_hud = BoxLayout(orientation="horizontal", size_hint_y=None, height=20)
        self.lbl_pct = Label(text="0%", font_name=FONT_FAMILY, font_size="11sp", bold=True, color=COLOR_GOLD, size_hint_x=0.3, halign="left")
        self.lbl_pct.bind(size=self.lbl_pct.setter('text_size'))
        self.lbl_speed = Label(text="SPEED: --", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_x=0.4)
        self.lbl_eta = Label(text="ETA: --", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_x=0.3, halign="right")
        self.lbl_eta.bind(size=self.lbl_eta.setter('text_size'))
        row_hud.add_widget(self.lbl_pct)
        row_hud.add_widget(self.lbl_speed)
        row_hud.add_widget(self.lbl_eta)

        self.card_progress.add_widget(self.lbl_progress_status)
        self.card_progress.add_widget(self.bar_progress)
        self.card_progress.add_widget(row_hud)
        content.add_widget(self.card_progress)

        # Primary Download Action Button
        self.btn_download = GoldButton(text="START DOWNLOAD", is_outline=False, height_dp=52)
        self.btn_download.bind(on_release=self.action_start_download)
        content.add_widget(self.btn_download)

        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)

    def select_format(self, key):
        self.selected_format = key
        for k, btn in self.fmt_buttons.items():
            is_active = (k == key)
            btn.is_outline = not is_active
            btn.normal_bg = COLOR_GOLD if is_active else [0, 0, 0, 0]
            btn.canvas_bg.rgba = btn.normal_bg
            btn.lbl.color = [0.08, 0.08, 0.09, 1.0] if is_active else COLOR_GOLD

    def on_url_text_change(self, instance, text):
        pass

    def action_paste(self, *args):
        try:
            from kivy.core.clipboard import Clipboard
            txt = Clipboard.paste()
            if txt and txt.strip().startswith(('http://', 'https://')):
                self.input_url.text = txt.strip()
                self.action_inspect()
        except Exception:
            pass

    def action_inspect(self, *args):
        url = self.input_url.text.strip()
        if not url:
            return
        self.btn_inspect.set_text("CHECKING...")
        self.badge_platform.text = "▶ INSPECTING LINK..."

        def worker():
            try:
                res = engine.inspect_url(url)
                Clock.schedule_once(lambda dt: self.on_inspect_success(res), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.on_inspect_error(str(e)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def on_inspect_success(self, res):
        self.active_analysis = res
        self.btn_inspect.set_text("INSPECT")
        self.badge_platform.text = f"▶ VERIFIED {res['platform'].upper()}"
        self.lbl_inspect_title.text = res['title']
        self.chip_items.text = f"{res['track_count']} item(s)"
        self.chip_dur.text = res['duration_str']
        self.chip_size.text = f"~{res['size_estimate']}"

    def on_inspect_error(self, err):
        self.btn_inspect.set_text("INSPECT")
        self.badge_platform.text = "✕ INSPECTION FAILED"
        self.lbl_inspect_title.text = err[:80]

    def action_start_download(self, *args):
        url = self.input_url.text.strip()
        if not url:
            self.lbl_progress_status.text = "Please paste a link first."
            return

        cfg = engine.load_settings()
        dest_dir = cfg.get("download_dir", engine.get_default_download_dir())
        os.makedirs(dest_dir, exist_ok=True)

        self.is_downloading = True
        self.stop_event.clear()
        self.btn_download.set_text("DOWNLOADING...")
        self.bar_progress.value = 0
        self.lbl_pct.text = "0%"
        self.lbl_progress_status.text = "Preparing media stream..."

        # Download worker thread
        def worker():
            platform = engine.detect_platform(url)
            is_video = self.selected_format.startswith("video_")
            is_speaker = (self.selected_format == "mp3_128")
            bitrate = "320" if self.selected_format == "mp3_320" else ("192" if self.selected_format == "mp3_192" else "128")

            # Resolve item title
            title = self.active_analysis['title'] if self.active_analysis else f"{platform} Clip"
            filename_base = engine.clean_filename(title, 1)
            ext_target = "mp4" if is_video else ("m4a" if self.selected_format == "m4a" else "mp3")
            full_path = os.path.join(dest_dir, f"{filename_base}.{ext_target}")

            # Notify Download Manager
            Clock.schedule_once(lambda dt: self.app_ref.manager_screen.add_item(filename_base, "⏳ Downloading...", full_path, self.selected_format), 0)

            def progress_hook(d):
                if self.stop_event.is_set():
                    raise yt_dlp.utils.DownloadCancelled("Stopped by user")
                if d['status'] == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    downloaded = d.get('downloaded_bytes') or 0
                    speed = d.get('speed') or 0
                    speed_str = f"{speed / (1024*1024):.1f} MB/s" if speed else ""
                    eta = d.get('eta') or 0
                    eta_str = f"{eta}s" if eta else ""
                    if total > 0:
                        pct = (downloaded / total) * 100
                        Clock.schedule_once(lambda dt: self.update_progress_ui(pct, speed_str, eta_str), 0)

            if is_video:
                fmt_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'format': fmt_str,
                    'merge_output_format': 'mp4',
                    'outtmpl': os.path.join(dest_dir, f"{filename_base}.%(ext)s"),
                    'progress_hooks': [progress_hook],
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                    }
                }
            else:
                postprocessors = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3' if self.selected_format != 'm4a' else 'm4a', 'preferredquality': bitrate}]
                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(dest_dir, f"{filename_base}.%(ext)s"),
                    'progress_hooks': [progress_hook],
                    'postprocessors': postprocessors,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                    }
                }

            try:
                import yt_dlp
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                Clock.schedule_once(lambda dt: self.on_download_complete(filename_base, full_path), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.on_download_failed(filename_base, str(e)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def update_progress_ui(self, pct, speed, eta):
        self.bar_progress.value = pct
        self.lbl_pct.text = f"{int(pct)}%"
        if speed:
            self.lbl_speed.text = f"SPEED: {speed}"
        if eta:
            self.lbl_eta.text = f"ETA: {eta}"

    def on_download_complete(self, name, full_path):
        self.is_downloading = False
        self.btn_download.set_text("START DOWNLOAD")
        self.bar_progress.value = 100
        self.lbl_pct.text = "100%"
        self.lbl_progress_status.text = f"Saved: {name[:35]}"
        self.lbl_speed.text = "SPEED: --"
        self.lbl_eta.text = "ETA: --"
        self.app_ref.manager_screen.mark_completed(name, full_path)

    def on_download_failed(self, name, err):
        self.is_downloading = False
        self.btn_download.set_text("START DOWNLOAD")
        self.lbl_progress_status.text = f"Error: {err[:50]}"
        self.app_ref.manager_screen.mark_failed(name)


# ==========================================================
# SCREEN 2: DOWNLOAD MANAGER
# ==========================================================
class ManagerScreen(Screen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.items_data = {}

        root = BoxLayout(orientation="vertical", padding=[16, 12, 16, 75], spacing=12)

        # Header
        hdr = BoxLayout(orientation="horizontal", size_hint_y=None, height=40)
        lbl_brand = Label(
            text="DOWNLOAD MANAGER",
            font_name=FONT_FAMILY,
            font_size="17sp",
            bold=True,
            color=COLOR_GOLD,
            halign="left"
        )
        lbl_brand.bind(size=lbl_brand.setter('text_size'))
        hdr.add_widget(lbl_brand)
        root.add_widget(hdr)

        # Scrollable items list
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.list_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))

        self.lbl_empty = Label(
            text="No active downloads or history yet.\nDownloaded clips will appear here.",
            font_name=FONT_FAMILY,
            font_size="13sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=100,
            halign="center"
        )
        self.lbl_empty.bind(size=self.lbl_empty.setter('text_size'))
        self.list_layout.add_widget(self.lbl_empty)

        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        # Bottom clear history button
        btn_clear = GoldButton(text="CLEAR HISTORY", is_outline=True, height_dp=42)
        btn_clear.bind(on_release=self.clear_all)
        root.add_widget(btn_clear)

        self.add_widget(root)

    def add_item(self, name, status, path, fmt):
        if self.lbl_empty in self.list_layout.children:
            self.list_layout.remove_widget(self.lbl_empty)

        card = CardBox(orientation="vertical", padding=10, spacing=6, size_hint_y=None, height=85)
        
        row_top = BoxLayout(orientation="horizontal", size_hint_y=None, height=22)
        lbl_title = Label(
            text=name[:40],
            font_name=FONT_FAMILY,
            font_size="13sp",
            bold=True,
            color=COLOR_TEXT_WHITE,
            halign="left"
        )
        lbl_title.bind(size=lbl_title.setter('text_size'))
        
        lbl_status = Label(
            text=status,
            font_name=FONT_FAMILY,
            font_size="11sp",
            bold=True,
            color=COLOR_GOLD,
            size_hint_x=0.35,
            halign="right"
        )
        lbl_status.bind(size=lbl_status.setter('text_size'))
        row_top.add_widget(lbl_title)
        row_top.add_widget(lbl_status)
        card.add_widget(row_top)

        row_actions = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=32)
        btn_open = GoldButton(text="OPEN FILE", is_outline=True, height_dp=32, size_hint_x=0.5)
        btn_open.bind(on_release=lambda x: self.open_file(path))
        btn_folder = GoldButton(text="FOLDER", is_outline=True, height_dp=32, size_hint_x=0.5)
        btn_folder.bind(on_release=lambda x: self.open_folder(path))
        row_actions.add_widget(btn_open)
        row_actions.add_widget(btn_folder)
        card.add_widget(row_actions)

        self.items_data[name] = {"card": card, "status_lbl": lbl_status, "path": path}
        self.list_layout.add_widget(card)

    def mark_completed(self, name, full_path):
        if name in self.items_data:
            self.items_data[name]["status_lbl"].text = "✓ Saved"
            self.items_data[name]["status_lbl"].color = COLOR_GREEN
            self.items_data[name]["path"] = full_path

    def mark_failed(self, name):
        if name in self.items_data:
            self.items_data[name]["status_lbl"].text = "✕ Failed"
            self.items_data[name]["status_lbl"].color = [0.8, 0.4, 0.4, 1.0]

    def open_file(self, path):
        if not path or not os.path.exists(path):
            return
        if IS_ANDROID:
            try:
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                currentActivity = PythonActivity.mActivity
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                File = autoclass('java.io.File')
                file_obj = File(path)
                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(Uri.fromFile(file_obj), "video/*" if path.endswith('.mp4') else "audio/*")
                currentActivity.startActivity(intent)
            except Exception:
                pass
        else:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])

    def open_folder(self, path):
        folder = os.path.dirname(path) if path else engine.get_default_download_dir()
        if not os.path.exists(folder):
            return
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder])
        else:
            subprocess.run(["xdg-open", folder])

    def clear_all(self, *args):
        self.list_layout.clear_widgets()
        self.items_data.clear()
        self.list_layout.add_widget(self.lbl_empty)


# ==========================================================
# SCREEN 3: SETTINGS
# ==========================================================
class SettingsScreen(Screen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.cfg = engine.load_settings()

        root = BoxLayout(orientation="vertical", padding=[16, 12, 16, 75], spacing=12)

        # Header
        hdr = BoxLayout(orientation="horizontal", size_hint_y=None, height=40)
        lbl_brand = Label(
            text="SETTINGS",
            font_name=FONT_FAMILY,
            font_size="17sp",
            bold=True,
            color=COLOR_GOLD,
            halign="left"
        )
        lbl_brand.bind(size=lbl_brand.setter('text_size'))
        hdr.add_widget(lbl_brand)
        root.add_widget(hdr)

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=14)
        content.bind(minimum_height=content.setter('height'))

        # Destination Storage Card
        card_dest = CardBox(orientation="vertical", padding=12, spacing=10, size_hint_y=None, height=140)
        lbl_d = Label(
            text="DOWNLOAD DESTINATION FOLDER",
            font_name=FONT_FAMILY,
            font_size="12sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=18,
            halign="left"
        )
        lbl_d.bind(size=lbl_d.setter('text_size'))
        card_dest.add_widget(lbl_d)

        self.input_dest = TextInput(
            text=self.cfg.get("download_dir", engine.get_default_download_dir()),
            font_name=FONT_FAMILY,
            font_size="12sp",
            multiline=False,
            size_hint_y=None,
            height=40,
            background_color=COLOR_SURFACE_ALT,
            foreground_color=COLOR_TEXT_WHITE,
            cursor_color=COLOR_GOLD,
            padding=[8, 8]
        )
        card_dest.add_widget(self.input_dest)

        row_dest_act = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=36)
        btn_save_dest = GoldButton(text="SAVE FOLDER", is_outline=False, height_dp=36, size_hint_x=0.5)
        btn_save_dest.bind(on_release=self.save_folder)
        btn_reset_dest = GoldButton(text="RESET DEFAULT", is_outline=True, height_dp=36, size_hint_x=0.5)
        btn_reset_dest.bind(on_release=self.reset_folder)
        row_dest_act.add_widget(btn_save_dest)
        row_dest_act.add_widget(btn_reset_dest)
        card_dest.add_widget(row_dest_act)
        content.add_widget(card_dest)

        # Batch & Duplicate Preferences
        card_dups = CardBox(orientation="vertical", padding=12, spacing=10, size_hint_y=None, height=135)
        lbl_dup_title = Label(
            text="DOWNLOAD PREFERENCES",
            font_name=FONT_FAMILY,
            font_size="12sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=18,
            halign="left"
        )
        lbl_dup_title.bind(size=lbl_dup_title.setter('text_size'))
        card_dups.add_widget(lbl_dup_title)

        row_dup = BoxLayout(orientation="horizontal", size_hint_y=None, height=36)
        self.lbl_dup_status = Label(
            text="Skip Duplicate Downloads: ON",
            font_name=FONT_FAMILY,
            font_size="13sp",
            color=COLOR_TEXT_WHITE,
            size_hint_x=0.7,
            halign="left"
        )
        self.lbl_dup_status.bind(size=self.lbl_dup_status.setter('text_size'))
        btn_toggle_dup = GoldButton(text="TOGGLE", is_outline=True, height_dp=34, size_hint_x=0.3)
        btn_toggle_dup.bind(on_release=self.toggle_dup)
        row_dup.add_widget(self.lbl_dup_status)
        row_dup.add_widget(btn_toggle_dup)
        card_dups.add_widget(row_dup)

        # Max limit row
        row_limit = BoxLayout(orientation="horizontal", size_hint_y=None, height=36)
        lbl_limit = Label(
            text="Playlist Max Items (0 for all):",
            font_name=FONT_FAMILY,
            font_size="12sp",
            color=COLOR_TEXT_MUTED,
            size_hint_x=0.7,
            halign="left"
        )
        lbl_limit.bind(size=lbl_limit.setter('text_size'))
        self.input_limit = TextInput(
            text=str(self.cfg.get("max_tracks", 0)),
            font_name=FONT_FAMILY,
            font_size="12sp",
            multiline=False,
            size_hint_x=0.3,
            background_color=COLOR_SURFACE_ALT,
            foreground_color=COLOR_TEXT_WHITE,
            cursor_color=COLOR_GOLD
        )
        self.input_limit.bind(text=self.save_limit)
        row_limit.add_widget(lbl_limit)
        row_limit.add_widget(self.input_limit)
        card_dups.add_widget(row_limit)
        content.add_widget(card_dups)

        # Engine Info Card
        card_info = CardBox(orientation="vertical", padding=12, spacing=6, size_hint_y=None, height=130)
        lbl_info_head = Label(
            text="ENGINE SPECIFICATIONS",
            font_name=FONT_FAMILY,
            font_size="12sp",
            bold=True,
            color=COLOR_GOLD,
            size_hint_y=None,
            height=18,
            halign="left"
        )
        lbl_info_head.bind(size=lbl_info_head.setter('text_size'))
        lbl_info1 = Label(text="Core Engine: yt-dlp + FFmpeg", font_name=FONT_FAMILY, font_size="12sp", color=COLOR_TEXT_WHITE, size_hint_y=None, height=18, halign="left")
        lbl_info1.bind(size=lbl_info1.setter('text_size'))
        lbl_info2 = Label(text="Platforms: YouTube, Instagram, TikTok, X, FB, Reddit", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_y=None, height=18, halign="left")
        lbl_info2.bind(size=lbl_info2.setter('text_size'))
        lbl_info3 = Label(text="Architecture: Android Kivy/KivyMD Native Application", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_y=None, height=18, halign="left")
        lbl_info3.bind(size=lbl_info3.setter('text_size'))
        card_info.add_widget(lbl_info_head)
        card_info.add_widget(lbl_info1)
        card_info.add_widget(lbl_info2)
        card_info.add_widget(lbl_info3)
        content.add_widget(card_info)

        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)

    def save_folder(self, *args):
        p = self.input_dest.text.strip()
        if p:
            self.cfg["download_dir"] = p
            engine.save_settings(self.cfg)

    def reset_folder(self, *args):
        d = engine.get_default_download_dir()
        self.input_dest.text = d
        self.cfg["download_dir"] = d
        engine.save_settings(self.cfg)

    def toggle_dup(self, *args):
        cur = self.cfg.get("ignore_dups", True)
        new_val = not cur
        self.cfg["ignore_dups"] = new_val
        self.lbl_dup_status.text = f"Skip Duplicate Downloads: {'ON' if new_val else 'OFF'}"
        engine.save_settings(self.cfg)

    def save_limit(self, instance, val):
        if val.isdigit():
            self.cfg["max_tracks"] = int(val)
            engine.save_settings(self.cfg)


# ==========================================================
# MAIN APPLICATION CLASS
# ==========================================================
class UniversalDownloaderMobileApp(App):
    def build(self):
        Window.clearcolor = COLOR_BG
        self.title = "Universal Downloader Mobile"

        # Request Android Runtime Permissions if on device
        if IS_ANDROID:
            try:
                request_permissions([
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.INTERNET
                ])
            except Exception:
                pass

        # Master Root Layout
        self.master_layout = AnchorLayout(anchor_x="center", anchor_y="bottom")

        # Screen Manager
        self.sm = ScreenManager(transition=SlideTransition(duration=0.2))
        self.home_screen = HomeScreen(self, name="home")
        self.manager_screen = ManagerScreen(self, name="manager")
        self.settings_screen = SettingsScreen(self, name="settings")

        self.sm.add_widget(self.home_screen)
        self.sm.add_widget(self.manager_screen)
        self.sm.add_widget(self.settings_screen)

        # Fixed Bottom Navigation Bar
        self.nav_bar = CardBox(
            orientation="horizontal",
            size_hint=(1, None),
            height=65,
            padding=[16, 4],
            spacing=10,
            bg_color=[0.08, 0.08, 0.11, 0.98],
            border_color=COLOR_BORDER,
            radius=0
        )

        self.nav_home = NavButton(title="Downloader", icon_char="▼", target_screen="home", app_ref=self)
        self.nav_mgr = NavButton(title="Manager", icon_char="≡", target_screen="manager", app_ref=self)
        self.nav_set = NavButton(title="Settings", icon_char="⚙", target_screen="settings", app_ref=self)

        self.nav_bar.add_widget(self.nav_home)
        self.nav_bar.add_widget(self.nav_mgr)
        self.nav_bar.add_widget(self.nav_set)
        self.nav_home.set_active(True)

        self.master_layout.add_widget(self.sm)
        self.master_layout.add_widget(self.nav_bar)

        # Handle incoming Android Share Intent
        Clock.schedule_once(self.check_android_share_intent, 0.5)

        return self.master_layout

    def switch_screen(self, screen_name):
        self.sm.current = screen_name
        self.nav_home.set_active(screen_name == "home")
        self.nav_mgr.set_active(screen_name == "manager")
        self.nav_set.set_active(screen_name == "settings")

    def check_android_share_intent(self, dt):
        """Intercept Android Share Intent when a user clicks Share in YouTube/Instagram/TikTok."""
        if not IS_ANDROID:
            return
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            currentActivity = PythonActivity.mActivity
            intent = currentActivity.getIntent()
            action = intent.getAction()
            type_str = intent.getType()
            if Intent.ACTION_SEND == action and type_str and "text/plain" in type_str:
                shared_text = intent.getStringExtra(Intent.EXTRA_TEXT)
                if shared_text:
                    urls = re.findall(r'https?://\S+', shared_text)
                    if urls:
                        extracted = urls[0]
                        self.home_screen.input_url.text = extracted
                        self.switch_screen("home")
                        self.home_screen.action_inspect()
        except Exception:
            pass


if __name__ == "__main__":
    UniversalDownloaderMobileApp().run()
