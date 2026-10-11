import os
import sys
import re
import json
import time
import shutil
import threading
import unicodedata
import subprocess

# Configure smartphone simulation viewport on desktop
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
from kivy.graphics import Color, RoundedRectangle, Line, Rectangle, Ellipse
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

# Luxury Gold Theme Palette (Artcraft / Watermelon / Seal Inspired)
COLOR_BG = [0.045, 0.045, 0.060, 1.0]        # Deep Obsidian #0B0B0F
COLOR_CARD = [0.085, 0.085, 0.115, 1.0]      # Elevated Surface #16161D
COLOR_CARD_ALT = [0.12, 0.12, 0.16, 1.0]     # Sub-card Surface #1F1F29
COLOR_BORDER = [0.20, 0.20, 0.26, 0.9]       # Subtle Border #333342
COLOR_BORDER_GOLD = [0.83, 0.69, 0.22, 0.45] # Glowing Gold Border
COLOR_GOLD = [0.85, 0.70, 0.24, 1.0]         # Primary Gold #D9B33D
COLOR_GOLD_HOVER = [0.93, 0.79, 0.35, 1.0]   # Gold Hover #EDC959
COLOR_GOLD_SUBTLE = [0.85, 0.70, 0.24, 0.12] # Gold Glow Fill
COLOR_TEXT_WHITE = [0.96, 0.96, 0.98, 1.0]   # Main Title Text
COLOR_TEXT_MUTED = [0.55, 0.55, 0.63, 1.0]   # Secondary Text
COLOR_GREEN = [0.22, 0.82, 0.48, 1.0]        # Success Badge #38D17A


# -------------------------------------------------------------
# Clean Geometric Vector Icon (Zero missing Unicode glyphs)
# -------------------------------------------------------------
class VectorIcon(Widget):
    """Draws razor-sharp canvas vector icons to guarantee 0 missing glyphs."""
    def __init__(self, icon_type="download", is_active=False, size_px=22, **kwargs):
        super().__init__(**kwargs)
        self.icon_type = icon_type
        self.is_active = is_active
        self.size_hint = (None, None)
        self.size = (size_px, size_px)
        self.bind(pos=self.redraw, size=self.redraw)

    def set_active(self, active):
        self.is_active = active
        self.redraw()

    def redraw(self, *args):
        self.canvas.clear()
        cx = self.x + self.width / 2.0
        cy = self.y + self.height / 2.0
        c = COLOR_GOLD if self.is_active else COLOR_TEXT_MUTED

        with self.canvas:
            Color(*c)
            if self.icon_type == "download":
                # Down arrow inside circular arc
                Line(circle=(cx, cy, 10), width=1.3)
                Line(points=[cx, cy + 4, cx, cy - 3], width=1.6)
                Line(points=[cx - 4, cy, cx, cy - 4, cx + 4, cy], width=1.6)
            elif self.icon_type == "manager":
                # Clean list stacks
                Line(points=[cx - 7, cy + 4, cx + 7, cy + 4], width=1.5)
                Line(points=[cx - 7, cy, cx + 7, cy], width=1.5)
                Line(points=[cx - 7, cy - 4, cx + 7, cy - 4], width=1.5)
                Ellipse(pos=(cx - 10, cy + 3), size=(2.5, 2.5))
                Ellipse(pos=(cx - 10, cy - 1), size=(2.5, 2.5))
                Ellipse(pos=(cx - 10, cy - 5), size=(2.5, 2.5))
            elif self.icon_type == "settings":
                # Precision cog/sliders
                Line(circle=(cx, cy, 9), width=1.3)
                Ellipse(pos=(cx - 2.5, cy - 2.5), size=(5, 5))
                Line(points=[cx, cy + 5, cx, cy + 9], width=1.5)
                Line(points=[cx, cy - 5, cx, cy - 9], width=1.5)
                Line(points=[cx - 5, cy, cx - 9, cy], width=1.5)
                Line(points=[cx + 5, cy, cx + 9, cy], width=1.5)
            elif self.icon_type == "paste":
                # Clipboard icon
                Line(rounded_rectangle=(cx - 6, cy - 7, 12, 14, 2), width=1.3)
                Line(points=[cx - 3, cy + 7, cx + 3, cy + 7], width=1.8)
            elif self.icon_type == "play":
                # Play triangle
                Line(points=[cx - 4, cy - 5, cx - 4, cy + 5, cx + 5, cy, cx - 4, cy - 5], width=1.4)


# -------------------------------------------------------------
# Reusable Modern Mobile Components
# -------------------------------------------------------------
class ModernCard(BoxLayout):
    """Refined Material-3 card with soft border & ambient background."""
    def __init__(self, bg_color=COLOR_CARD, border_color=COLOR_BORDER, radius=14, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.border_color = border_color
        self.radius = radius
        with self.canvas.before:
            self.col_bg = Color(*self.bg_color)
            self.rect_bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self.col_border = Color(*self.border_color)
            self.rect_border = Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], self.radius), width=1.1)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.rect_bg.pos = self.pos
        self.rect_bg.size = self.size
        self.rect_border.rounded_rectangle = (self.pos[0], self.pos[1], self.size[0], self.size[1], self.radius)


class PillButton(ButtonBehavior, BoxLayout):
    """Touch-friendly pill button with dynamic outline/fill states."""
    def __init__(self, text="", is_primary=False, height_dp=44, radius=12, **kwargs):
        kwargs['size_hint_y'] = None
        kwargs['height'] = height_dp
        super().__init__(**kwargs)
        self.text_val = text
        self.is_primary = is_primary
        self.radius = radius
        self.orientation = "horizontal"
        self.padding = [14, 4]

        self.normal_bg = COLOR_GOLD if is_primary else [0, 0, 0, 0]
        self.border_col = [0, 0, 0, 0] if is_primary else COLOR_BORDER_GOLD
        self.text_col = [0.06, 0.06, 0.08, 1.0] if is_primary else COLOR_GOLD

        with self.canvas.before:
            self.canvas_bg = Color(*self.normal_bg)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self.canvas_border = Color(*self.border_col)
            self.line_border = Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], self.radius), width=1.1)
        self.bind(pos=self._update, size=self._update)

        self.lbl = Label(
            text=self.text_val,
            font_name=FONT_FAMILY,
            font_size="14sp",
            bold=True,
            color=self.text_col,
            halign="center",
            valign="middle"
        )
        self.lbl.bind(size=self.lbl.setter('text_size'))
        self.add_widget(self.lbl)

    def _update(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
        self.line_border.rounded_rectangle = (self.pos[0], self.pos[1], self.size[0], self.size[1], self.radius)

    def set_primary(self, is_primary):
        self.is_primary = is_primary
        self.normal_bg = COLOR_GOLD if is_primary else [0, 0, 0, 0]
        self.border_col = [0, 0, 0, 0] if is_primary else COLOR_BORDER_GOLD
        self.text_col = [0.06, 0.06, 0.08, 1.0] if is_primary else COLOR_GOLD
        self.canvas_bg.rgba = self.normal_bg
        self.canvas_border.rgba = self.border_col
        self.lbl.color = self.text_col

    def set_text(self, text):
        self.text_val = text
        self.lbl.text = text


class StatChip(BoxLayout):
    """Small pill badge displaying metadata stats."""
    def __init__(self, label="", val="", **kwargs):
        kwargs['size_hint'] = (None, None)
        kwargs['size'] = (105, 30)
        super().__init__(**kwargs)
        self.padding = [6, 2]
        with self.canvas.before:
            Color(0.12, 0.12, 0.16, 0.9)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
            Color(0.25, 0.25, 0.32, 0.8)
            self.line = Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], 8), width=1.0)
        self.bind(pos=self._update, size=self._update)

        self.lbl = Label(
            text=f"{label} {val}".strip(),
            font_name=FONT_FAMILY,
            font_size="11sp",
            color=COLOR_TEXT_WHITE,
            halign="center",
            valign="middle"
        )
        self.lbl.bind(size=self.lbl.setter('text_size'))
        self.add_widget(self.lbl)

    def _update(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
        self.line.rounded_rectangle = (self.pos[0], self.pos[1], self.size[0], self.size[1], 8)

    def update_text(self, txt):
        self.lbl.text = txt


class NavTab(ButtonBehavior, BoxLayout):
    """Floating Navigation bar touch tab."""
    def __init__(self, title="", icon_name="download", target_screen="", app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.target_screen = target_screen
        self.app_ref = app_ref
        self.padding = [4, 6]
        self.spacing = 3

        # Vector Icon container
        self.box_icon = AnchorLayout(size_hint_y=0.6, anchor_x="center", anchor_y="center")
        self.v_icon = VectorIcon(icon_type=icon_name, is_active=False)
        self.box_icon.add_widget(self.v_icon)
        self.add_widget(self.box_icon)

        # Tab Title
        self.lbl_title = Label(
            text=title,
            font_name=FONT_FAMILY,
            font_size="11sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=0.4,
            halign="center"
        )
        self.add_widget(self.lbl_title)

    def set_active(self, active):
        self.v_icon.set_active(active)
        self.lbl_title.color = COLOR_GOLD if active else COLOR_TEXT_MUTED

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
        self.current_mode = "video" # 'video' or 'audio'
        self.selected_format = "video_best"
        self.is_downloading = False
        self.stop_event = threading.Event()

        root = BoxLayout(orientation="vertical", padding=[16, 10, 16, 80], spacing=12)

        # 1. Elegant Top App Bar
        app_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=48, spacing=10)
        
        # Gold emblem box
        emblem = Widget(size_hint=(None, None), size=(34, 34))
        with emblem.canvas:
            Color(*COLOR_GOLD)
            RoundedRectangle(pos=emblem.pos, size=emblem.size, radius=[8])
            Color(0.08, 0.08, 0.1, 1.0)
            Line(circle=(emblem.x + 17, emblem.y + 17, 7), width=1.8)
        emblem.bind(pos=lambda *_: setattr(emblem.canvas.children[2], 'pos', emblem.pos) or setattr(emblem.canvas.children[5], 'circle', (emblem.x + 17, emblem.y + 17, 7)))
        app_bar.add_widget(emblem)

        # Brand Text
        brand_box = BoxLayout(orientation="vertical", spacing=0)
        lbl_brand = Label(
            text="UNIVERSAL",
            font_name=FONT_FAMILY,
            font_size="16sp",
            bold=True,
            color=COLOR_TEXT_WHITE,
            halign="left"
        )
        lbl_brand.bind(size=lbl_brand.setter('text_size'))
        lbl_brand_sub = Label(
            text="MEDIA DOWNLOADER",
            font_name=FONT_FAMILY,
            font_size="10sp",
            bold=True,
            color=COLOR_GOLD,
            halign="left"
        )
        lbl_brand_sub.bind(size=lbl_brand_sub.setter('text_size'))
        brand_box.add_widget(lbl_brand)
        brand_box.add_widget(lbl_brand_sub)
        app_bar.add_widget(brand_box)

        # Quick Manager counter button on header
        btn_quick_mgr = PillButton(text="QUEUE ≡", is_primary=False, height_dp=34, size_hint_x=0.3)
        btn_quick_mgr.bind(on_release=lambda *_: self.app_ref.switch_screen("manager"))
        app_bar.add_widget(btn_quick_mgr)
        root.add_widget(app_bar)

        # 2. Supported Platforms Ribbon
        ribbon = Label(
            text="YouTube · Instagram · TikTok · X · Facebook · Reddit · Vimeo",
            font_name=FONT_FAMILY,
            font_size="10.5sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=16,
            halign="left"
        )
        ribbon.bind(size=ribbon.setter('text_size'))
        root.add_widget(ribbon)

        # 3. Scrollable Main Content
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=12)
        content.bind(minimum_height=content.setter('height'))

        # Modern Search / URL Input Card
        card_search = ModernCard(orientation="vertical", padding=12, spacing=10, size_hint_y=None, height=122)
        
        row_input = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
        self.input_url = TextInput(
            hint_text="Paste video, reel, or playlist link...",
            font_name=FONT_FAMILY,
            font_size="13sp",
            multiline=False,
            size_hint_x=0.74,
            background_color=COLOR_CARD_ALT,
            foreground_color=COLOR_TEXT_WHITE,
            cursor_color=COLOR_GOLD,
            padding=[12, 11]
        )
        self.input_url.bind(text=self.on_url_typed)

        # Inline Paste Button
        btn_paste = PillButton(text="PASTE", is_primary=False, height_dp=44, size_hint_x=0.26)
        btn_paste.bind(on_release=self.action_paste)
        row_input.add_widget(self.input_url)
        row_input.add_widget(btn_paste)
        card_search.add_widget(row_input)

        # Secondary action row
        row_sec = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=36)
        self.btn_inspect = PillButton(text="CHECK & INSPECT LINK", is_primary=False, height_dp=36, size_hint_x=0.75)
        self.btn_inspect.bind(on_release=self.action_inspect)
        self.btn_clear = PillButton(text="CLEAR", is_primary=False, height_dp=36, size_hint_x=0.25)
        self.btn_clear.bind(on_release=self.action_clear)
        row_sec.add_widget(self.btn_inspect)
        row_sec.add_widget(self.btn_clear)
        card_search.add_widget(row_sec)
        content.add_widget(card_search)

        # 4. Hero Media Inspection Card (Seal Style)
        self.card_inspect = ModernCard(orientation="vertical", padding=12, spacing=8, size_hint_y=None, height=128)
        
        row_badge = BoxLayout(orientation="horizontal", size_hint_y=None, height=22)
        self.badge_platform = Label(
            text="✦ READY TO INSPECT",
            font_name=FONT_FAMILY,
            font_size="11sp",
            bold=True,
            color=COLOR_GOLD,
            halign="left"
        )
        self.badge_platform.bind(size=self.badge_platform.setter('text_size'))
        row_badge.add_widget(self.badge_platform)
        self.card_inspect.add_widget(row_badge)

        self.lbl_title = Label(
            text="Paste any media link above to inspect quality, track count, and duration.",
            font_name=FONT_FAMILY,
            font_size="13sp",
            color=COLOR_TEXT_WHITE,
            size_hint_y=None,
            height=38,
            halign="left"
        )
        self.lbl_title.bind(size=self.lbl_title.setter('text_size'))
        self.card_inspect.add_widget(self.lbl_title)

        # Stats Chips Row
        self.row_stats = BoxLayout(orientation="horizontal", spacing=6, size_hint_y=None, height=30)
        self.chip_items = StatChip(label="Items:", val="--")
        self.chip_dur = StatChip(label="Length:", val="--")
        self.chip_size = StatChip(label="Est:", val="--")
        self.row_stats.add_widget(self.chip_items)
        self.row_stats.add_widget(self.chip_dur)
        self.row_stats.add_widget(self.chip_size)
        self.card_inspect.add_widget(self.row_stats)
        content.add_widget(self.card_inspect)

        # 5. Output Profile Selector (Segmented Switch + Quality Pills)
        card_format = ModernCard(orientation="vertical", padding=12, spacing=10, size_hint_y=None, height=138)
        
        # Segmented Video / Audio Switch
        row_mode = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=36)
        self.btn_mode_video = PillButton(text="🎬 VIDEO (MP4)", is_primary=True, height_dp=36, size_hint_x=0.5)
        self.btn_mode_video.bind(on_release=lambda *_: self.switch_mode("video"))
        self.btn_mode_audio = PillButton(text="🎵 AUDIO (MP3/M4A)", is_primary=False, height_dp=36, size_hint_x=0.5)
        self.btn_mode_audio.bind(on_release=lambda *_: self.switch_mode("audio"))
        row_mode.add_widget(self.btn_mode_video)
        row_mode.add_widget(self.btn_mode_audio)
        card_format.add_widget(row_mode)

        # Sub-pills Row
        self.row_qualities = BoxLayout(orientation="horizontal", spacing=6, size_hint_y=None, height=36)
        self.quality_buttons = {}
        self.build_quality_buttons("video")
        card_format.add_widget(self.row_qualities)
        content.add_widget(card_format)

        # 6. Live Progress & Status HUD
        self.card_hud = ModernCard(orientation="vertical", padding=12, spacing=6, size_hint_y=None, height=88)
        
        row_hud_top = BoxLayout(orientation="horizontal", size_hint_y=None, height=18)
        self.lbl_hud_status = Label(
            text="Engine Standby",
            font_name=FONT_FAMILY,
            font_size="11.5sp",
            color=COLOR_TEXT_MUTED,
            halign="left"
        )
        self.lbl_hud_status.bind(size=self.lbl_hud_status.setter('text_size'))
        self.lbl_hud_pct = Label(
            text="0%",
            font_name=FONT_FAMILY,
            font_size="12sp",
            bold=True,
            color=COLOR_GOLD,
            size_hint_x=0.25,
            halign="right"
        )
        self.lbl_hud_pct.bind(size=self.lbl_hud_pct.setter('text_size'))
        row_hud_top.add_widget(self.lbl_hud_status)
        row_hud_top.add_widget(self.lbl_hud_pct)
        self.card_hud.add_widget(row_hud_top)

        self.bar_hud = ProgressBar(max=100, value=0, size_hint_y=None, height=12)
        self.card_hud.add_widget(self.bar_hud)

        row_hud_bottom = BoxLayout(orientation="horizontal", size_hint_y=None, height=16)
        self.lbl_speed = Label(text="SPEED: --", font_name=FONT_FAMILY, font_size="10.5sp", color=COLOR_TEXT_MUTED, halign="left")
        self.lbl_speed.bind(size=self.lbl_speed.setter('text_size'))
        self.lbl_eta = Label(text="ETA: --", font_name=FONT_FAMILY, font_size="10.5sp", color=COLOR_TEXT_MUTED, halign="right")
        self.lbl_eta.bind(size=self.lbl_eta.setter('text_size'))
        row_hud_bottom.add_widget(self.lbl_speed)
        row_hud_bottom.add_widget(self.lbl_eta)
        self.card_hud.add_widget(row_hud_bottom)
        content.add_widget(self.card_hud)

        # 7. Hero CTA Download Button
        self.btn_download = PillButton(text="DOWNLOAD NOW", is_primary=True, height_dp=54, radius=14)
        self.btn_download.lbl.font_size = "16sp"
        self.btn_download.bind(on_release=self.action_start_download)
        content.add_widget(self.btn_download)

        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)

    def build_quality_buttons(self, mode):
        self.row_qualities.clear_widgets()
        self.quality_buttons.clear()
        if mode == "video":
            options = [
                ("video_best", "Best (1080p+)"),
                ("video_720", "720p HD"),
                ("video_480", "480p SD")
            ]
            if not self.selected_format.startswith("video_"):
                self.selected_format = "video_best"
        else:
            options = [
                ("mp3_320", "320k HQ"),
                ("mp3_192", "192k"),
                ("mp3_128", "128k Car"),
                ("m4a", "AAC M4A")
            ]
            if self.selected_format.startswith("video_"):
                self.selected_format = "mp3_320"

        for key, title in options:
            is_active = (key == self.selected_format)
            btn = PillButton(text=title, is_primary=is_active, height_dp=34, radius=8)
            btn.lbl.font_size = "12sp"
            btn.bind(on_release=lambda instance, k=key: self.select_quality(k))
            self.quality_buttons[key] = btn
            self.row_qualities.add_widget(btn)

    def switch_mode(self, mode):
        self.current_mode = mode
        self.btn_mode_video.set_primary(mode == "video")
        self.btn_mode_audio.set_primary(mode == "audio")
        self.build_quality_buttons(mode)

    def select_quality(self, key):
        self.selected_format = key
        for k, btn in self.quality_buttons.items():
            btn.set_primary(k == key)

    def on_url_typed(self, instance, text):
        pass

    def action_clear(self, *args):
        self.input_url.text = ""
        self.active_analysis = None
        self.badge_platform.text = "✦ READY TO INSPECT"
        self.lbl_title.text = "Paste any media link above to inspect quality, track count, and duration."
        self.chip_items.update_text("Items: --")
        self.chip_dur.update_text("Length: --")
        self.chip_size.update_text("Est: --")

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
        self.btn_inspect.set_text("ANALYZING...")
        self.badge_platform.text = "✦ CONNECTING TO PLATFORM..."

        def worker():
            try:
                res = engine.inspect_url(url)
                Clock.schedule_once(lambda dt: self.on_inspect_success(res), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.on_inspect_error(str(e)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def on_inspect_success(self, res):
        self.active_analysis = res
        self.btn_inspect.set_text("CHECK & INSPECT LINK")
        self.badge_platform.text = f"✦ VERIFIED {res['platform'].upper()}"
        self.lbl_title.text = res['title']
        self.chip_items.update_text(f"{res['track_count']} item(s)")
        self.chip_dur.update_text(res['duration_str'])
        self.chip_size.update_text(f"~{res['size_estimate']}")

    def on_inspect_error(self, err):
        self.btn_inspect.set_text("CHECK & INSPECT LINK")
        self.badge_platform.text = "✕ INSPECTION ERROR"
        self.lbl_title.text = err[:90]

    def action_start_download(self, *args):
        url = self.input_url.text.strip()
        if not url:
            self.lbl_hud_status.text = "Please enter or paste a media link."
            return

        cfg = engine.load_settings()
        dest_dir = cfg.get("download_dir", engine.get_default_download_dir())
        os.makedirs(dest_dir, exist_ok=True)

        self.is_downloading = True
        self.stop_event.clear()
        self.btn_download.set_text("DOWNLOADING MEDIA...")
        self.bar_hud.value = 0
        self.lbl_hud_pct.text = "0%"
        self.lbl_hud_status.text = "Extracting video streams..."

        def worker():
            platform = engine.detect_platform(url)
            is_video = self.selected_format.startswith("video_")
            bitrate = "320" if self.selected_format == "mp3_320" else ("192" if self.selected_format == "mp3_192" else "128")

            title = self.active_analysis['title'] if self.active_analysis else f"{platform}_Media"
            filename_base = engine.clean_filename(title, 1)
            ext_target = "mp4" if is_video else ("m4a" if self.selected_format == "m4a" else "mp3")
            full_path = os.path.join(dest_dir, f"{filename_base}.{ext_target}")

            Clock.schedule_once(lambda dt: self.app_ref.manager_screen.add_item(filename_base, "⏳ Downloading...", full_path, self.selected_format), 0)

            def progress_hook(d):
                if self.stop_event.is_set():
                    raise yt_dlp.utils.DownloadCancelled("Cancelled")
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
        self.bar_hud.value = pct
        self.lbl_hud_pct.text = f"{int(pct)}%"
        if speed:
            self.lbl_speed.text = f"SPEED: {speed}"
        if eta:
            self.lbl_eta.text = f"ETA: {eta}"

    def on_download_complete(self, name, full_path):
        self.is_downloading = False
        self.btn_download.set_text("DOWNLOAD NOW")
        self.bar_hud.value = 100
        self.lbl_hud_pct.text = "100%"
        self.lbl_hud_status.text = f"✓ Saved: {name[:30]}"
        self.lbl_speed.text = "SPEED: --"
        self.lbl_eta.text = "ETA: --"
        self.app_ref.manager_screen.mark_completed(name, full_path)

    def on_download_failed(self, name, err):
        self.is_downloading = False
        self.btn_download.set_text("DOWNLOAD NOW")
        self.lbl_hud_status.text = f"✕ Error: {err[:45]}"
        self.app_ref.manager_screen.mark_failed(name)


# ==========================================================
# SCREEN 2: DOWNLOAD MANAGER
# ==========================================================
class ManagerScreen(Screen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.items_data = {}

        root = BoxLayout(orientation="vertical", padding=[16, 12, 16, 80], spacing=12)

        # Header
        hdr = BoxLayout(orientation="horizontal", size_hint_y=None, height=44)
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
            text="No active downloads or history.\nClips and tracks saved will appear here.",
            font_name=FONT_FAMILY,
            font_size="13sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=120,
            halign="center"
        )
        self.lbl_empty.bind(size=self.lbl_empty.setter('text_size'))
        self.list_layout.add_widget(self.lbl_empty)

        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        # Clear history button
        btn_clear = PillButton(text="CLEAR HISTORY", is_primary=False, height_dp=42)
        btn_clear.bind(on_release=self.clear_all)
        root.add_widget(btn_clear)

        self.add_widget(root)

    def add_item(self, name, status, path, fmt):
        if self.lbl_empty in self.list_layout.children:
            self.list_layout.remove_widget(self.lbl_empty)

        card = ModernCard(orientation="vertical", padding=10, spacing=8, size_hint_y=None, height=88)
        
        row_top = BoxLayout(orientation="horizontal", size_hint_y=None, height=22)
        lbl_title = Label(
            text=name[:36],
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
        btn_open = PillButton(text="PLAY FILE", is_primary=True, height_dp=32, radius=8, size_hint_x=0.5)
        btn_open.lbl.font_size = "12sp"
        btn_open.bind(on_release=lambda x: self.open_file(path))
        btn_folder = PillButton(text="FOLDER", is_primary=False, height_dp=32, radius=8, size_hint_x=0.5)
        btn_folder.lbl.font_size = "12sp"
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

        root = BoxLayout(orientation="vertical", padding=[16, 12, 16, 80], spacing=12)

        # Header
        hdr = BoxLayout(orientation="horizontal", size_hint_y=None, height=44)
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
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=12)
        content.bind(minimum_height=content.setter('height'))

        # Destination Storage Card
        card_dest = ModernCard(orientation="vertical", padding=12, spacing=10, size_hint_y=None, height=138)
        lbl_d = Label(
            text="STORAGE DESTINATION",
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
            height=38,
            background_color=COLOR_CARD_ALT,
            foreground_color=COLOR_TEXT_WHITE,
            cursor_color=COLOR_GOLD,
            padding=[8, 8]
        )
        card_dest.add_widget(self.input_dest)

        row_dest_act = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=36)
        btn_save_dest = PillButton(text="SAVE FOLDER", is_primary=True, height_dp=36, size_hint_x=0.5)
        btn_save_dest.bind(on_release=self.save_folder)
        btn_reset_dest = PillButton(text="RESET DEFAULT", is_primary=False, height_dp=36, size_hint_x=0.5)
        btn_reset_dest.bind(on_release=self.reset_folder)
        row_dest_act.add_widget(btn_save_dest)
        row_dest_act.add_widget(btn_reset_dest)
        card_dest.add_widget(row_dest_act)
        content.add_widget(card_dest)

        # Batch & Duplicate Preferences
        card_dups = ModernCard(orientation="vertical", padding=12, spacing=10, size_hint_y=None, height=128)
        lbl_dup_title = Label(
            text="DOWNLOAD RULES",
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

        row_dup = BoxLayout(orientation="horizontal", size_hint_y=None, height=34)
        self.lbl_dup_status = Label(
            text="Skip Duplicate Downloads: ON",
            font_name=FONT_FAMILY,
            font_size="13sp",
            color=COLOR_TEXT_WHITE,
            size_hint_x=0.7,
            halign="left"
        )
        self.lbl_dup_status.bind(size=self.lbl_dup_status.setter('text_size'))
        btn_toggle_dup = PillButton(text="TOGGLE", is_primary=False, height_dp=34, size_hint_x=0.3)
        btn_toggle_dup.bind(on_release=self.toggle_dup)
        row_dup.add_widget(self.lbl_dup_status)
        row_dup.add_widget(btn_toggle_dup)
        card_dups.add_widget(row_dup)

        # Max limit row
        row_limit = BoxLayout(orientation="horizontal", size_hint_y=None, height=34)
        lbl_limit = Label(
            text="Playlist Max Limit (0 for all):",
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
            background_color=COLOR_CARD_ALT,
            foreground_color=COLOR_TEXT_WHITE,
            cursor_color=COLOR_GOLD
        )
        self.input_limit.bind(text=self.save_limit)
        row_limit.add_widget(lbl_limit)
        row_limit.add_widget(self.input_limit)
        card_dups.add_widget(row_limit)
        content.add_widget(card_dups)

        # Engine Info Card
        card_info = ModernCard(orientation="vertical", padding=12, spacing=6, size_hint_y=None, height=135)
        lbl_info_head = Label(
            text="SYSTEM & ENGINE",
            font_name=FONT_FAMILY,
            font_size="12sp",
            bold=True,
            color=COLOR_GOLD,
            size_hint_y=None,
            height=18,
            halign="left"
        )
        lbl_info_head.bind(size=lbl_info_head.setter('text_size'))
        lbl_info1 = Label(text="Engine: yt-dlp + FFmpeg (Direct Stream)", font_name=FONT_FAMILY, font_size="12sp", color=COLOR_TEXT_WHITE, size_hint_y=None, height=18, halign="left")
        lbl_info1.bind(size=lbl_info1.setter('text_size'))
        lbl_info2 = Label(text="Supported: YouTube, Instagram, TikTok, X, FB, Reddit", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_y=None, height=18, halign="left")
        lbl_info2.bind(size=lbl_info2.setter('text_size'))
        lbl_info3 = Label(text="Design System: Material 3 + Artcraft Gold Aesthetic", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_y=None, height=18, halign="left")
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
# MAIN APPLICATION ROOT
# ==========================================================
class UniversalDownloaderMobileApp(App):
    def build(self):
        Window.clearcolor = COLOR_BG
        self.title = "Universal Downloader Mobile"

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
        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.home_screen = HomeScreen(self, name="home")
        self.manager_screen = ManagerScreen(self, name="manager")
        self.settings_screen = SettingsScreen(self, name="settings")

        self.sm.add_widget(self.home_screen)
        self.sm.add_widget(self.manager_screen)
        self.sm.add_widget(self.settings_screen)

        # Elevated Floating Bottom Navigation Bar
        self.nav_bar = ModernCard(
            orientation="horizontal",
            size_hint=(1, None),
            height=66,
            padding=[20, 2],
            spacing=16,
            bg_color=[0.07, 0.07, 0.09, 0.98],
            border_color=COLOR_BORDER_GOLD,
            radius=16
        )

        self.nav_home = NavTab(title="Downloader", icon_name="download", target_screen="home", app_ref=self)
        self.nav_mgr = NavTab(title="Manager", icon_name="manager", target_screen="manager", app_ref=self)
        self.nav_set = NavTab(title="Settings", icon_name="settings", target_screen="settings", app_ref=self)

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
