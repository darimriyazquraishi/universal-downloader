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
from kivy.metrics import dp, sp
from kivy.core.text import LabelBase
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Line, Rectangle, Ellipse
from kivy.animation import Animation
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition, FadeTransition, CardTransition
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.progressbar import ProgressBar
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image

# Icon Paths
ICON_GOLD_PATH = os.path.join(os.path.dirname(__file__), "assets", "icon_gold.png")
ICON_APP_PATH = os.path.join(os.path.dirname(__file__), "assets", "icon.png")

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


# Vector Icon for crisp navigation rendering
class VectorIcon(Widget):
    """Draws razor-sharp canvas vector icons to guarantee zero missing glyphs."""
    def __init__(self, icon_type="download", is_active=False, size_px=22, **kwargs):
        super().__init__(**kwargs)
        self.icon_type = icon_type
        self.is_active = is_active
        self.size_hint = (None, None)
        self.size = (dp(size_px), dp(size_px))
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
                Line(circle=(cx, cy, dp(10)), width=dp(1.4))
                Line(points=[cx, cy + dp(4), cx, cy - dp(3)], width=dp(1.8))
                Line(points=[cx - dp(4), cy, cx, cy - dp(4), cx + dp(4), cy], width=dp(1.8))
            elif self.icon_type == "manager":
                Line(points=[cx - dp(7), cy + dp(4), cx + dp(7), cy + dp(4)], width=dp(1.6))
                Line(points=[cx - dp(7), cy, cx + dp(7), cy], width=dp(1.6))
                Line(points=[cx - dp(7), cy - dp(4), cx + dp(7), cy - dp(4)], width=dp(1.6))
                Ellipse(pos=(cx - dp(10), cy + dp(3)), size=(dp(3), dp(3)))
                Ellipse(pos=(cx - dp(10), cy - dp(1)), size=(dp(3), dp(3)))
                Ellipse(pos=(cx - dp(10), cy - dp(5)), size=(dp(3), dp(3)))
            elif self.icon_type == "settings":
                Line(circle=(cx, cy, dp(9)), width=dp(1.4))
                Ellipse(pos=(cx - dp(2.5), cy - dp(2.5)), size=(dp(5), dp(5)))
                Line(points=[cx, cy + dp(5), cx, cy + dp(9)], width=dp(1.6))
                Line(points=[cx, cy - dp(5), cx, cy - dp(9)], width=dp(1.6))
                Line(points=[cx - dp(5), cy, cx - dp(9), cy], width=dp(1.6))
                Line(points=[cx + dp(5), cy, cx + dp(9), cy], width=dp(1.6))


# Reusable Styled Components
class CardBox(BoxLayout):
    """Luxury card container with rounded corners and subtle border."""
    def __init__(self, bg_color=COLOR_SURFACE, border_color=COLOR_BORDER, radius=12, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.border_color = border_color
        self.radius = dp(radius)
        with self.canvas.before:
            self.col_bg = Color(*self.bg_color)
            self.rect_bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self.col_border = Color(*self.border_color)
            self.rect_border = Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], self.radius), width=dp(1.1))
        self.bind(pos=self._update_canvas, size=self._update_canvas)

    def _update_canvas(self, *args):
        self.rect_bg.pos = self.pos
        self.rect_bg.size = self.size
        self.rect_border.rounded_rectangle = (self.pos[0], self.pos[1], self.size[0], self.size[1], self.radius)



class GoldButton(ButtonBehavior, BoxLayout):
    """Modern gold touch button with tactile feedback."""
    def __init__(self, text="", is_outline=False, height_dp=48, tooltip="", **kwargs):
        kwargs['size_hint_y'] = None
        kwargs['height'] = dp(height_dp)
        super().__init__(**kwargs)
        self.text = text
        self.is_outline = is_outline
        self.orientation = "horizontal"
        self.padding = [dp(8), dp(4)]

        self.normal_bg = [0, 0, 0, 0] if is_outline else COLOR_GOLD
        self.pressed_bg = [0.83, 0.69, 0.22, 0.2] if is_outline else COLOR_GOLD_LIGHT
        self.border_col = COLOR_GOLD if is_outline else [0, 0, 0, 0]

        with self.canvas.before:
            self.canvas_bg = Color(*self.normal_bg)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
            self.canvas_border = Color(*self.border_col)
            self.line_border = Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], dp(10)), width=dp(1.2))
        self.bind(pos=self._update_canvas, size=self._update_canvas)

        self.lbl = Label(
            text=self.text,
            font_name=FONT_FAMILY,
            font_size="13sp",
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
        self.line_border.rounded_rectangle = (self.pos[0], self.pos[1], self.size[0], self.size[1], dp(10))

    def on_press(self):
        Animation.stop_all(self.canvas_bg)
        Animation(rgba=self.pressed_bg, duration=0.06).start(self.canvas_bg)

    def on_release(self):
        Animation.stop_all(self.canvas_bg)
        Animation(rgba=self.normal_bg, duration=0.18, t='out_quad').start(self.canvas_bg)

    def set_outline(self, is_outline):
        self.is_outline = is_outline
        self.normal_bg = [0, 0, 0, 0] if is_outline else COLOR_GOLD
        self.border_col = COLOR_GOLD if is_outline else [0, 0, 0, 0]
        Animation.stop_all(self.canvas_bg)
        Animation.stop_all(self.canvas_border)
        Animation(rgba=self.normal_bg, duration=0.15).start(self.canvas_bg)
        Animation(rgba=self.border_col, duration=0.15).start(self.canvas_border)
        self.lbl.color = COLOR_GOLD if is_outline else [0.08, 0.08, 0.09, 1.0]

    def set_text(self, text):
        self.text = text
        self.lbl.text = text


class NavButton(ButtonBehavior, BoxLayout):
    """Bottom navigation bar button."""
    def __init__(self, title="", icon_type="download", target_screen="", tooltip="", app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.target_screen = target_screen
        self.app_ref = app_ref
        self.padding = [dp(2), dp(4)]
        self.spacing = dp(2)
        self.is_active = False

        self.box_icon = AnchorLayout(size_hint_y=0.6, anchor_x="center", anchor_y="center")
        with self.box_icon.canvas.before:
            self.pill_col = Color(0.83, 0.69, 0.22, 0.0)
            self.pill_rect = RoundedRectangle(pos=self.box_icon.pos, size=(dp(54), dp(28)), radius=[dp(14)])
        self.box_icon.bind(pos=self._update_pill, size=self._update_pill)

        self.v_icon = VectorIcon(icon_type=icon_type, is_active=False, size_px=20)
        self.box_icon.add_widget(self.v_icon)
        self.add_widget(self.box_icon)

        self.lbl_text = Label(
            text=title,
            font_name=FONT_FAMILY,
            font_size="11sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=0.4
        )
        self.add_widget(self.lbl_text)

    def _update_pill(self, *args):
        pw, ph = dp(54), dp(28)
        self.pill_rect.pos = (self.box_icon.x + (self.box_icon.width - pw) / 2, self.box_icon.y + (self.box_icon.height - ph) / 2)
        self.pill_rect.size = (pw, ph)

    def set_active(self, active):
        self.is_active = active
        self.v_icon.set_active(active)
        Animation.stop_all(self.pill_col)
        Animation.stop_all(self.v_icon)
        if active:
            Animation(rgba=[0.83, 0.69, 0.22, 0.18], duration=0.22, t='out_quad').start(self.pill_col)
            self.lbl_text.color = COLOR_GOLD
            anim_bounce = Animation(size=(dp(23), dp(23)), duration=0.09, t='out_quad') + Animation(size=(dp(20), dp(20)), duration=0.12, t='in_out_quad')
            anim_bounce.start(self.v_icon)
        else:
            Animation(rgba=[0, 0, 0, 0], duration=0.16).start(self.pill_col)
            self.lbl_text.color = COLOR_TEXT_MUTED

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
        self.single_cache = None
        self.playlist_cache = None
        self.selected_format = "video_best"
        self.is_downloading = False
        self.stop_event = threading.Event()

        root = BoxLayout(orientation="vertical", padding=[dp(16), dp(44), dp(16), dp(78)], spacing=dp(12))

        # Header with Logo Icon (Safe from notch / status bar)
        hdr = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(50), spacing=dp(10))
        if os.path.exists(ICON_GOLD_PATH):
            hdr_icon = Image(source=ICON_GOLD_PATH, size_hint=(None, None), size=(dp(38), dp(38)))
            hdr.add_widget(hdr_icon)

        hdr_text = BoxLayout(orientation="vertical", spacing=dp(2))
        lbl_brand = Label(
            text="UNIVERSAL DOWNLOADER",
            font_name=FONT_FAMILY,
            font_size="16.5sp",
            bold=True,
            color=COLOR_GOLD,
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle"
        )
        lbl_brand.bind(size=lbl_brand.setter('text_size'))
        lbl_sub = Label(
            text="YouTube · Instagram · TikTok · X · Facebook · Reddit",
            font_name=FONT_FAMILY,
            font_size="10.5sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=dp(18),
            halign="left",
            valign="middle"
        )
        lbl_sub.bind(size=lbl_sub.setter('text_size'))
        hdr_text.add_widget(lbl_brand)
        hdr_text.add_widget(lbl_sub)
        hdr.add_widget(hdr_text)
        root.add_widget(hdr)

        # Scrollable Content
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12))
        content.bind(minimum_height=content.setter('height'))

        # Input Card
        card_input = CardBox(orientation="vertical", padding=dp(12), spacing=dp(10), size_hint_y=None)
        card_input.bind(minimum_height=card_input.setter('height'))
        lbl_in_title = Label(
            text="MEDIA LINK",
            font_name=FONT_FAMILY,
            font_size="11.5sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle"
        )
        lbl_in_title.bind(size=lbl_in_title.setter('text_size'))
        card_input.add_widget(lbl_in_title)

        self.input_url = TextInput(
            hint_text="Paste video, reel, post, or playlist link...",
            font_name=FONT_FAMILY,
            font_size="13sp",
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            background_color=COLOR_SURFACE_ALT,
            foreground_color=COLOR_TEXT_WHITE,
            cursor_color=COLOR_GOLD,
            padding=[dp(10), dp(10)]
        )
        self.input_url.bind(text=self.on_url_text_change)
        card_input.add_widget(self.input_url)

        # Quick Actions Toolbar (PASTE | INSPECT | CLEAR)
        actions_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(38))
        self.btn_paste = GoldButton(text="PASTE", is_outline=True, height_dp=38, size_hint_x=0.34, tooltip="Paste link from clipboard and automatically inspect it.")
        self.btn_paste.bind(on_release=self.action_paste)

        self.btn_inspect = GoldButton(text="INSPECT", is_outline=False, height_dp=38, size_hint_x=0.42, tooltip="Inspect link metadata, duration, track count, and size.")
        self.btn_inspect.bind(on_release=self.action_inspect)

        self.btn_clear = GoldButton(text="CLEAR", is_outline=True, height_dp=38, size_hint_x=0.24, tooltip="Clear URL input box and reset inspection results.")
        self.btn_clear.bind(on_release=self.action_clear_input)

        actions_row.add_widget(self.btn_paste)
        actions_row.add_widget(self.btn_inspect)
        actions_row.add_widget(self.btn_clear)
        card_input.add_widget(actions_row)
        content.add_widget(card_input)

        # Inspection Results Card (Dynamic)
        self.card_inspect = CardBox(orientation="vertical", padding=dp(12), spacing=dp(8), size_hint_y=None)
        self.card_inspect.bind(minimum_height=self.card_inspect.setter('height'))
        
        self.badge_platform = Label(
            text="WAITING FOR LINK",
            font_name="Roboto",
            font_size="11sp",
            bold=True,
            color=COLOR_GOLD,
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle"
        )
        self.badge_platform.bind(size=self.badge_platform.setter('text_size'))
        self.card_inspect.add_widget(self.badge_platform)

        self.lbl_inspect_title = Label(
            text="No media inspected yet",
            font_name=FONT_FAMILY,
            font_size="13.5sp",
            bold=True,
            color=COLOR_TEXT_WHITE,
            size_hint_y=None,
            height=dp(36),
            halign="left",
            valign="middle"
        )
        self.lbl_inspect_title.bind(size=self.lbl_inspect_title.setter('text_size'))
        self.card_inspect.add_widget(self.lbl_inspect_title)

        # Scope Selector (Visible when link has both a single video AND a playlist/mix)
        self.row_scope = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=0, opacity=0.0)
        self.row_scope.disabled = True
        self.btn_scope_single = GoldButton(text="THIS VIDEO ONLY", is_outline=False, height_dp=36, size_hint_x=0.5, tooltip="Download only this single video, ignoring playlist/mix tracks.")
        self.btn_scope_single.bind(on_release=lambda *_: self.switch_scope("single"))
        self.btn_scope_playlist = GoldButton(text="FULL PLAYLIST", is_outline=True, height_dp=36, size_hint_x=0.5, tooltip="Download all media tracks in the full playlist or radio mix.")
        self.btn_scope_playlist.bind(on_release=lambda *_: self.switch_scope("playlist"))
        self.row_scope.add_widget(self.btn_scope_single)
        self.row_scope.add_widget(self.btn_scope_playlist)
        self.card_inspect.add_widget(self.row_scope)

        # Metrics row
        row_chips = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(26))
        self.chip_items = Label(text="-- items", font_name=FONT_FAMILY, font_size="11.5sp", color=COLOR_TEXT_MUTED)
        self.chip_dur = Label(text="-- duration", font_name=FONT_FAMILY, font_size="11.5sp", color=COLOR_TEXT_MUTED)
        self.chip_size = Label(text="-- size", font_name=FONT_FAMILY, font_size="11.5sp", color=COLOR_TEXT_MUTED)
        row_chips.add_widget(self.chip_items)
        row_chips.add_widget(self.chip_dur)
        row_chips.add_widget(self.chip_size)
        self.card_inspect.add_widget(row_chips)
        content.add_widget(self.card_inspect)

        # Luxury Output Format Specification Card
        card_format = CardBox(orientation="vertical", padding=dp(12), spacing=dp(8), size_hint_y=None)
        card_format.bind(minimum_height=card_format.setter('height'))

        row_fmt_head = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(8))
        lbl_fmt_head = Label(
            text="OUTPUT PROFILE",
            font_name=FONT_FAMILY,
            font_size="11.5sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_x=None,
            width=dp(130),
            halign="left",
            valign="middle"
        )
        lbl_fmt_head.bind(size=lbl_fmt_head.setter('text_size'))
        row_fmt_head.add_widget(lbl_fmt_head)
        row_fmt_head.add_widget(Widget())

        # Gold Segmented Switcher (VIDEO / AUDIO)
        box_switcher = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint=(None, None), size=(dp(160), dp(32)))
        self.btn_mode_video = GoldButton(text="VIDEO", is_outline=False, height_dp=32, size_hint=(None, None), size=(dp(77), dp(32)), tooltip="Switch to MP4 Video quality profiles.")
        self.btn_mode_video.lbl.font_size = "11.5sp"
        self.btn_mode_video.bind(on_release=lambda *_: self.switch_mode("video"))

        self.btn_mode_audio = GoldButton(text="AUDIO", is_outline=True, height_dp=32, size_hint=(None, None), size=(dp(77), dp(32)), tooltip="Switch to MP3 & M4A Audio profiles.")
        self.btn_mode_audio.lbl.font_size = "11.5sp"
        self.btn_mode_audio.bind(on_release=lambda *_: self.switch_mode("audio"))

        box_switcher.add_widget(self.btn_mode_video)
        box_switcher.add_widget(self.btn_mode_audio)
        row_fmt_head.add_widget(box_switcher)
        card_format.add_widget(row_fmt_head)

        # Video Formats Grid (2 cols x 2 rows, height dp(94))
        self.grid_fmt_video = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(94))
        self.grid_fmt_audio = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(94))

        self.fmt_buttons = {}
        video_formats = [
            ("video_best", "MP4 Best", "Highest available MP4 video (up to 4K / 1080p)."),
            ("video_1080", "MP4 1080p", "Crisp 1080p Full HD video stream."),
            ("video_720", "MP4 720p", "720p HD MP4 video for fast download."),
            ("video_480", "MP4 480p", "480p SD MP4 video for data saving."),
        ]
        for key, name, tip in video_formats:
            btn = GoldButton(text=name, is_outline=(key != self.selected_format), height_dp=43, tooltip=tip)
            btn.lbl.font_size = "13sp"
            btn.bind(on_release=lambda instance, k=key: self.select_format(k))
            self.fmt_buttons[key] = btn
            self.grid_fmt_video.add_widget(btn)

        audio_formats = [
            ("mp3_320", "MP3 320k", "Maximum fidelity 320 kbps CBR MP3 audio stream."),
            ("mp3_192", "MP3 192k", "Standard high-quality 192 kbps MP3 audio."),
            ("mp3_128", "USB 128k", "128 kbps MP3 with clean metadata for car USB & players."),
            ("m4a", "AAC M4A", "Untouched original AAC audio stream without transcoding."),
        ]
        for key, name, tip in audio_formats:
            btn = GoldButton(text=name, is_outline=(key != self.selected_format), height_dp=43, tooltip=tip)
            btn.lbl.font_size = "13sp"
            btn.bind(on_release=lambda instance, k=key: self.select_format(k))
            self.fmt_buttons[key] = btn
            self.grid_fmt_audio.add_widget(btn)

        self.format_slots_box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(94))
        self.format_slots_box.add_widget(self.grid_fmt_video)
        card_format.add_widget(self.format_slots_box)

        content.add_widget(card_format)

        # Download HUD / Progress Card
        self.card_progress = CardBox(orientation="vertical", padding=dp(12), spacing=dp(8), size_hint_y=None)
        self.card_progress.bind(minimum_height=self.card_progress.setter('height'))
        
        self.lbl_progress_status = Label(
            text="Ready to download",
            font_name=FONT_FAMILY,
            font_size="12sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle"
        )
        self.lbl_progress_status.bind(size=self.lbl_progress_status.setter('text_size'))

        self.bar_progress = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(12))
        
        row_hud = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22))
        self.lbl_pct = Label(text="0%", font_name=FONT_FAMILY, font_size="11.5sp", bold=True, color=COLOR_GOLD, size_hint_x=0.3, halign="left", valign="middle")
        self.lbl_pct.bind(size=self.lbl_pct.setter('text_size'))
        self.lbl_speed = Label(text="SPEED: --", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_x=0.4, valign="middle")
        self.lbl_eta = Label(text="ETA: --", font_name=FONT_FAMILY, font_size="11sp", color=COLOR_TEXT_MUTED, size_hint_x=0.3, halign="right", valign="middle")
        self.lbl_eta.bind(size=self.lbl_eta.setter('text_size'))
        row_hud.add_widget(self.lbl_pct)
        row_hud.add_widget(self.lbl_speed)
        row_hud.add_widget(self.lbl_eta)

        self.card_progress.add_widget(self.lbl_progress_status)
        self.card_progress.add_widget(self.bar_progress)
        self.card_progress.add_widget(row_hud)
        content.add_widget(self.card_progress)

        # Primary Download Action Button
        self.btn_download = GoldButton(text="START DOWNLOAD", is_outline=False, height_dp=52, tooltip="Start downloading the inspected media to your device storage.")
        self.btn_download.lbl.font_size = "14.5sp"
        self.btn_download.bind(on_release=self.action_start_download)
        content.add_widget(self.btn_download)

        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)

    def switch_mode(self, mode):
        self.current_mode = mode
        if mode == "video":
            self.btn_mode_video.set_outline(False)
            self.btn_mode_audio.set_outline(True)
            self.format_slots_box.clear_widgets()
            self.format_slots_box.add_widget(self.grid_fmt_video)
            if not self.selected_format.startswith("video_"):
                self.select_format("video_best")
            else:
                self.select_format(self.selected_format)
        else:
            self.btn_mode_video.set_outline(True)
            self.btn_mode_audio.set_outline(False)
            self.format_slots_box.clear_widgets()
            self.format_slots_box.add_widget(self.grid_fmt_audio)
            if self.selected_format.startswith("video_"):
                self.select_format("mp3_320")
            else:
                self.select_format(self.selected_format)

    def select_format(self, key):
        self.selected_format = key
        for k, btn in self.fmt_buttons.items():
            is_active = (k == key)
            btn.set_outline(not is_active)

    def on_url_text_change(self, instance, text):
        t = text.strip()
        if t.startswith(('http://', 'https://')):
            parsed = engine.parse_url_structure(t)
            plat = engine.detect_platform(t)
            if parsed.get("is_mix"):
                self.badge_platform.text = f"{plat.upper()} MIX (DEFAULT: SINGLE VIDEO)"
            elif parsed.get("has_both"):
                self.badge_platform.text = f"{plat.upper()} (VIDEO + PLAYLIST DETECTED)"
            else:
                self.badge_platform.text = f"{plat.upper()} LINK DETECTED"

    def action_clean_url(self, *args):
        url = self.input_url.text.strip()
        if url:
            cleaned = engine.clean_url(url, remove_playlist=True)
            self.input_url.text = cleaned
            self.action_inspect()

    def action_clear_input(self, *args):
        self.input_url.text = ""
        self.active_analysis = None
        self.single_cache = None
        self.playlist_cache = None
        self.badge_platform.text = "WAITING FOR LINK"
        self.lbl_inspect_title.text = "No media inspected yet"
        self.chip_items.text = "-- items"
        self.chip_dur.text = "-- duration"
        self.chip_size.text = "-- size"
        Animation.stop_all(self.row_scope)
        self.row_scope.disabled = True
        Animation(height=0, opacity=0.0, duration=0.20, t='out_quad').start(self.row_scope)

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
        self.badge_platform.text = "INSPECTING LINK..."

        def worker():
            try:
                # By default inspects the single video if it's a mix/combo link
                res = engine.inspect_url(url, scope="single")
                Clock.schedule_once(lambda dt: self.on_inspect_success(res), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.on_inspect_error(str(e)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def on_inspect_success(self, res):
        self.active_analysis = res
        self.single_cache = res
        self.btn_inspect.set_text("INSPECT")
        
        # Configure badge
        badge_txt = f"VERIFIED {res['platform'].upper()}"
        if res.get("is_mix"):
            badge_txt = "VERIFIED YOUTUBE (MIX DETECTED)"
        elif res.get("has_both"):
            badge_txt = "VERIFIED YOUTUBE (VIDEO + PLAYLIST)"
        self.badge_platform.text = badge_txt

        self.lbl_inspect_title.text = res['title']
        self.chip_items.text = f"{res['track_count']} item(s)"
        self.chip_dur.text = res['duration_str']
        self.chip_size.text = f"~{res['size_estimate']}"

        # Setup Scope Buttons with fluid expansion animation
        if res.get("has_both"):
            Animation.stop_all(self.row_scope)
            self.row_scope.disabled = False
            Animation(height=dp(36), opacity=1.0, duration=0.25, t='out_cubic').start(self.row_scope)
            self.btn_scope_single.set_outline(False) # Selected
            self.btn_scope_playlist.set_outline(True)
        else:
            Animation.stop_all(self.row_scope)
            self.row_scope.disabled = True
            Animation(height=0, opacity=0.0, duration=0.20, t='out_quad').start(self.row_scope)

    def on_inspect_error(self, err):
        self.btn_inspect.set_text("INSPECT")
        self.badge_platform.text = "INSPECTION FAILED"
        self.lbl_inspect_title.text = err[:80]
        Animation.stop_all(self.row_scope)
        self.row_scope.disabled = True
        Animation(height=0, opacity=0.0, duration=0.20, t='out_quad').start(self.row_scope)

    def switch_scope(self, scope):
        if not self.active_analysis or not self.active_analysis.get("has_both"):
            return
        url = self.active_analysis.get("original_url") or self.input_url.text.strip()
        
        if scope == "single":
            self.active_analysis["active_scope"] = "single"
            self.btn_scope_single.set_outline(False)
            self.btn_scope_playlist.set_outline(True)
            if self.single_cache:
                self.lbl_inspect_title.text = self.single_cache["title"]
                self.chip_items.text = f"{self.single_cache['track_count']} item(s)"
                self.chip_dur.text = self.single_cache["duration_str"]
                self.chip_size.text = f"~{self.single_cache['size_estimate']}"
        else:
            self.active_analysis["active_scope"] = "playlist"
            self.btn_scope_single.set_outline(True)
            self.btn_scope_playlist.set_outline(False)
            if self.playlist_cache:
                self.lbl_inspect_title.text = self.playlist_cache["title"]
                self.chip_items.text = f"{self.playlist_cache['track_count']} item(s)"
                self.chip_dur.text = self.playlist_cache["duration_str"]
                self.chip_size.text = f"~{self.playlist_cache['size_estimate']}"
            else:
                self.lbl_inspect_title.text = "Fetching full playlist details..."
                def worker():
                    try:
                        p_res = engine.inspect_url(url, scope="playlist")
                        self.playlist_cache = p_res
                        Clock.schedule_once(lambda dt: self.on_playlist_loaded(p_res), 0)
                    except Exception as e:
                        pass
                threading.Thread(target=worker, daemon=True).start()

    def on_playlist_loaded(self, res):
        if self.active_analysis and self.active_analysis.get("active_scope") == "playlist":
            self.lbl_inspect_title.text = res['title']
            self.chip_items.text = f"{res['track_count']} item(s)"
            self.chip_dur.text = res['duration_str']
            self.chip_size.text = f"~{res['size_estimate']}"

    def action_start_download(self, *args):
        url = self.input_url.text.strip()
        if not url:
            self.lbl_progress_status.text = "Please paste a link first."
            return

        cfg = engine.load_settings()
        dest_dir = cfg.get("download_dir", engine.get_default_download_dir())
        os.makedirs(dest_dir, exist_ok=True)

        # Smart target URL resolution: Single video vs Playlist
        parsed = engine.parse_url_structure(url)
        target_download_url = url
        if self.active_analysis and self.active_analysis.get("has_both"):
            if self.active_analysis.get("active_scope") == "single":
                target_download_url = self.active_analysis.get("clean_video_url") or url
        elif parsed.get("is_mix") and parsed.get("clean_video_url"):
            # Auto-guard against dynamic radio mixes when user didn't explicitly inspect & switch to playlist
            target_download_url = parsed["clean_video_url"]

        self.is_downloading = True
        self.stop_event.clear()
        self.btn_download.set_text("DOWNLOADING...")
        self.bar_progress.value = 0
        self.lbl_pct.text = "0%"
        self.lbl_progress_status.text = "Preparing media stream..."

        def worker():
            platform = engine.detect_platform(target_download_url)
            is_video = self.selected_format.startswith("video_")
            bitrate = "320" if self.selected_format == "mp3_320" else ("192" if self.selected_format == "mp3_192" else "128")

            title = self.active_analysis['title'] if self.active_analysis else f"{platform} Clip"
            cleaned = engine.clean_filename(title, 1)
            ext_target = "mp4" if is_video else ("m4a" if self.selected_format == "m4a" else "mp3")

            if is_video:
                if self.selected_format == "video_1080":
                    q_tag = "1080p"
                elif self.selected_format == "video_720":
                    q_tag = "720p"
                elif self.selected_format == "video_480":
                    q_tag = "480p"
                else:
                    q_tag = "Best"
                clean_title = re.sub(r'\s*\[(best|1080p?|720p?|480p?|320k|192k|128k|m4a)\]$', '', cleaned, flags=re.IGNORECASE)
                filename_base = f"{clean_title} [{q_tag}]"
            else:
                q_tag = "320k" if self.selected_format == "mp3_320" else ("192k" if self.selected_format == "mp3_192" else ("m4a" if self.selected_format == "m4a" else "128k"))
                plain_path = os.path.join(dest_dir, f"{cleaned}.{ext_target}")
                if os.path.exists(plain_path):
                    clean_title = re.sub(r'\s*\[(320k|192k|128k|m4a)\]$', '', cleaned, flags=re.IGNORECASE)
                    filename_base = f"{clean_title} [{q_tag}]"
                else:
                    filename_base = cleaned

            full_path = os.path.join(dest_dir, f"{filename_base}.{ext_target}")

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
                if self.selected_format == "video_720":
                    fmt_str = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best'
                elif self.selected_format == "video_480":
                    fmt_str = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best'
                elif self.selected_format == "video_1080":
                    fmt_str = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
                else:
                    fmt_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
                opts = {
                    'quiet': True,
                    'no_warnings': True,
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
                postprocessors = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3' if self.selected_format != 'm4a' else 'm4a', 'preferredquality': bitrate}]
                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(dest_dir, f"{filename_base}.%(ext)s"),
                    'overwrites': True,
                    'progress_hooks': [progress_hook],
                    'postprocessors': postprocessors,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                    }
                }

            try:
                import yt_dlp
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([target_download_url])
                Clock.schedule_once(lambda dt: self.on_download_complete(filename_base, full_path), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.on_download_failed(filename_base, str(e)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def update_progress_ui(self, pct, speed, eta):
        Animation.stop_all(self.bar_progress)
        Animation(value=pct, duration=0.15, t='out_quad').start(self.bar_progress)
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

        root = BoxLayout(orientation="vertical", padding=[dp(16), dp(44), dp(16), dp(78)], spacing=dp(12))

        # Header
        hdr = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40))
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

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.list_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))

        self.lbl_empty = Label(
            text="No active downloads or history yet.\nDownloaded clips will appear here.",
            font_name=FONT_FAMILY,
            font_size="13sp",
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=dp(100),
            halign="center"
        )
        self.lbl_empty.bind(size=self.lbl_empty.setter('text_size'))
        self.list_layout.add_widget(self.lbl_empty)

        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        btn_clear = GoldButton(text="CLEAR HISTORY", is_outline=True, height_dp=42, tooltip="Clears the download history list from display.")
        btn_clear.bind(on_release=self.clear_all)
        root.add_widget(btn_clear)

        self.add_widget(root)

    def add_item(self, name, status, path, fmt):
        if self.lbl_empty in self.list_layout.children:
            self.list_layout.remove_widget(self.lbl_empty)

        card = CardBox(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, height=dp(88))
        
        row_top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24))
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

        row_actions = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(34))
        btn_open = GoldButton(text="OPEN FILE", is_outline=True, height_dp=34, size_hint_x=0.5, tooltip="Opens this media file in your default player.")
        btn_open.bind(on_release=lambda x: self.open_file(path))
        btn_folder = GoldButton(text="FOLDER", is_outline=True, height_dp=34, size_hint_x=0.5, tooltip="Opens the folder containing this file in file manager.")
        btn_folder.bind(on_release=lambda x: self.open_folder(path))
        row_actions.add_widget(btn_open)
        row_actions.add_widget(btn_folder)
        card.add_widget(row_actions)

        self.items_data[name] = {"card": card, "status_lbl": lbl_status, "path": path}
        card.opacity = 0
        self.list_layout.add_widget(card)
        Animation(opacity=1.0, duration=0.25, t='out_quad').start(card)

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

        root = BoxLayout(orientation="vertical", padding=[dp(16), dp(44), dp(16), dp(78)], spacing=dp(12))

        # Header
        hdr = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40))
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
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12))
        content.bind(minimum_height=content.setter('height'))

        # Destination Storage Card
        card_dest = CardBox(orientation="vertical", padding=dp(12), spacing=dp(10), size_hint_y=None)
        card_dest.bind(minimum_height=card_dest.setter('height'))
        lbl_d = Label(
            text="DOWNLOAD DESTINATION FOLDER",
            font_name=FONT_FAMILY,
            font_size="11.5sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle"
        )
        lbl_d.bind(size=lbl_d.setter('text_size'))
        card_dest.add_widget(lbl_d)

        self.input_dest = TextInput(
            text=self.cfg.get("download_dir", engine.get_default_download_dir()),
            font_name=FONT_FAMILY,
            font_size="12sp",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
            background_color=COLOR_SURFACE_ALT,
            foreground_color=COLOR_TEXT_WHITE,
            cursor_color=COLOR_GOLD,
            padding=[dp(8), dp(8)]
        )
        card_dest.add_widget(self.input_dest)

        row_dest_act = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(38))
        btn_save_dest = GoldButton(text="SAVE FOLDER", is_outline=False, height_dp=38, size_hint_x=0.5, tooltip="Saves custom destination path to app settings.")
        btn_save_dest.bind(on_release=self.save_folder)
        btn_reset_dest = GoldButton(text="RESET DEFAULT", is_outline=True, height_dp=38, size_hint_x=0.5, tooltip="Restores default storage path to device Downloads folder.")
        btn_reset_dest.bind(on_release=self.reset_folder)
        row_dest_act.add_widget(btn_save_dest)
        row_dest_act.add_widget(btn_reset_dest)
        card_dest.add_widget(row_dest_act)
        content.add_widget(card_dest)

        # Batch & Duplicate Preferences
        card_dups = CardBox(orientation="vertical", padding=dp(12), spacing=dp(10), size_hint_y=None)
        card_dups.bind(minimum_height=card_dups.setter('height'))
        lbl_dup_title = Label(
            text="DOWNLOAD PREFERENCES",
            font_name=FONT_FAMILY,
            font_size="11.5sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle"
        )
        lbl_dup_title.bind(size=lbl_dup_title.setter('text_size'))
        card_dups.add_widget(lbl_dup_title)

        row_dup = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(38))
        self.lbl_dup_status = Label(
            text="Skip Duplicate Downloads: ON",
            font_name=FONT_FAMILY,
            font_size="13sp",
            color=COLOR_TEXT_WHITE,
            size_hint_x=0.7,
            halign="left",
            valign="middle"
        )
        self.lbl_dup_status.bind(size=self.lbl_dup_status.setter('text_size'))
        btn_toggle_dup = GoldButton(text="TOGGLE", is_outline=True, height_dp=34, size_hint_x=0.3, tooltip="Toggles automatic skipping of duplicate downloads.")
        btn_toggle_dup.bind(on_release=self.toggle_dup)
        row_dup.add_widget(self.lbl_dup_status)
        row_dup.add_widget(btn_toggle_dup)
        card_dups.add_widget(row_dup)

        row_limit = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(38))
        lbl_limit = Label(
            text="Playlist Max Items (0 for all):",
            font_name=FONT_FAMILY,
            font_size="12sp",
            color=COLOR_TEXT_MUTED,
            size_hint_x=0.7,
            halign="left",
            valign="middle"
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

        # Transition Style Card
        card_trans = CardBox(orientation="vertical", padding=dp(12), spacing=dp(8), size_hint_y=None)
        card_trans.bind(minimum_height=card_trans.setter('height'))
        lbl_trans_head = Label(
            text="SCREEN TRANSITION STYLE",
            font_name=FONT_FAMILY,
            font_size="11.5sp",
            bold=True,
            color=COLOR_TEXT_MUTED,
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle"
        )
        lbl_trans_head.bind(size=lbl_trans_head.setter('text_size'))
        card_trans.add_widget(lbl_trans_head)

        row_trans = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(38))
        cur_style = self.cfg.get("transition_style", "slide")
        self.btn_t_slide = GoldButton(text="DIRECTIONAL SLIDE", is_outline=(cur_style != "slide"), height_dp=34, size_hint_x=0.5, tooltip="Smooth directional sliding based on tab order.")
        self.btn_t_fade = GoldButton(text="SILK CROSSFADE", is_outline=(cur_style != "fade"), height_dp=34, size_hint_x=0.5, tooltip="Silky smooth alpha crossfade between screens.")
        self.btn_t_slide.bind(on_release=lambda *_: self.set_transition_style("slide"))
        self.btn_t_fade.bind(on_release=lambda *_: self.set_transition_style("fade"))
        row_trans.add_widget(self.btn_t_slide)
        row_trans.add_widget(self.btn_t_fade)
        card_trans.add_widget(row_trans)
        content.add_widget(card_trans)

        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)

    def set_transition_style(self, style):
        self.cfg["transition_style"] = style
        engine.save_settings(self.cfg)
        self.btn_t_slide.set_outline(style != "slide")
        self.btn_t_fade.set_outline(style != "fade")

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
    icon = ICON_APP_PATH

    def build(self):
        Window.clearcolor = COLOR_BG
        self.title = "Universal Downloader Mobile"
        self.icon = ICON_APP_PATH

        if IS_ANDROID:
            try:
                perms = [
                    Permission.INTERNET,
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE
                ]
                for p_name in ['READ_MEDIA_VIDEO', 'READ_MEDIA_AUDIO']:
                    if hasattr(Permission, p_name):
                        perms.append(getattr(Permission, p_name))
                request_permissions(perms)
            except Exception:
                pass

        self.master_layout = FloatLayout()

        self.sm = ScreenManager(transition=SlideTransition(duration=0.2), size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
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
            height=dp(64),
            pos_hint={'x': 0, 'y': 0},
            padding=[dp(16), dp(4)],
            spacing=dp(10),
            bg_color=[0.08, 0.08, 0.11, 0.98],
            border_color=COLOR_BORDER,
            radius=0
        )

        self.nav_home = NavButton(title="Downloader", icon_type="download", target_screen="home", app_ref=self, tooltip="Go to primary media link downloader screen.")
        self.nav_mgr = NavButton(title="Manager", icon_type="manager", target_screen="manager", app_ref=self, tooltip="View and manage downloaded media files on your device.")
        self.nav_set = NavButton(title="Settings", icon_type="settings", target_screen="settings", app_ref=self, tooltip="Configure download folder, duplicate filtering, and preferences.")

        self.nav_bar.add_widget(self.nav_home)
        self.nav_bar.add_widget(self.nav_mgr)
        self.nav_bar.add_widget(self.nav_set)
        self.nav_home.set_active(True)
        self.master_layout.add_widget(self.sm)
        self.master_layout.add_widget(self.nav_bar)

        # Global window touch handlers for seamless horizontal swipe tab switching
        Window.bind(on_touch_down=self._on_window_touch_down)
        Window.bind(on_touch_move=self._on_window_touch_move)
        Window.bind(on_touch_up=self._on_window_touch_up)

        Clock.schedule_once(self.check_android_share_intent, 0.5)

        return self.master_layout

    def _on_window_touch_down(self, win, touch):
        # Ignore touches on or below the bottom navigation bar (height dp(64) + padding)
        if touch.y <= dp(68):
            return False

        # Only ignore touches inside the media URL input box when actively on the Home screen
        if getattr(self.sm, 'current', '') == "home" and hasattr(self, 'home_screen') and hasattr(self.home_screen, 'input_url'):
            try:
                if self.home_screen.input_url.collide_point(touch.x, touch.y):
                    return False
            except Exception:
                pass

        touch.ud['tab_swipe_origin'] = (touch.x, touch.y)
        touch.ud['tab_swipe_locked'] = False
        return False

    def _on_window_touch_move(self, win, touch):
        origin = touch.ud.get('tab_swipe_origin')
        if not origin:
            return False

        dx = touch.x - origin[0]
        dy = touch.y - origin[1]

        # When horizontal gesture begins, ungrab buttons so they don't fire accidental taps
        if abs(dx) > dp(25) and abs(dx) > 1.3 * abs(dy):
            for item in list(touch.grab_list):
                try:
                    touch.ungrab(item)
                    if hasattr(item, 'state'):
                        item.state = 'normal'
                except Exception:
                    pass
        return False

    def _on_window_touch_up(self, win, touch):
        origin = touch.ud.get('tab_swipe_origin')
        if not origin or touch.ud.get('tab_swipe_locked', False):
            return False

        # Avoid interrupting an ongoing transition
        if hasattr(self.sm, 'transition') and hasattr(self.sm.transition, 'is_active') and self.sm.transition.is_active:
            return False

        # Enforce minimum cooldown between consecutive tab swipes
        now = time.time()
        if now - getattr(self, '_last_swipe_time', 0) < 0.35:
            return False

        dx = touch.x - origin[0]
        dy = touch.y - origin[1]
        threshold = dp(35)

        # Require predominantly horizontal swipe
        if abs(dx) >= threshold and abs(dx) > 1.25 * abs(dy):
            touch.ud['tab_swipe_locked'] = True
            self._last_swipe_time = now

            # Ensure all buttons ungrabbed
            for item in list(touch.grab_list):
                try:
                    touch.ungrab(item)
                    if hasattr(item, 'state'):
                        item.state = 'normal'
                except Exception:
                    pass

            order = ["home", "manager", "settings"]
            curr = self.sm.current
            if curr not in order:
                return False
            idx = order.index(curr)

            if dx < 0 and idx < len(order) - 1:
                # Swipe LEFT -> advance EXACTLY 1 screen (Downloader -> Manager -> Settings)
                next_screen = order[idx + 1]
                self.switch_screen(next_screen, direction="left")
            elif dx > 0 and idx > 0:
                # Swipe RIGHT -> go back EXACTLY 1 screen (Settings -> Manager -> Downloader)
                prev_screen = order[idx - 1]
                self.switch_screen(prev_screen, direction="right")
            return False

        return False

    def switch_screen(self, screen_name, direction=None):
        curr_screen = self.sm.current
        if curr_screen == screen_name:
            return

        order = {"home": 0, "manager": 1, "settings": 2}
        curr_idx = order.get(curr_screen, 0)
        new_idx = order.get(screen_name, 0)

        # Retrieve transition mode from settings
        cfg_style = "slide"
        if hasattr(self, 'settings_screen') and hasattr(self.settings_screen, 'cfg'):
            cfg_style = self.settings_screen.cfg.get("transition_style", "slide")

        if cfg_style == "fade" and direction is None:
            if not isinstance(self.sm.transition, FadeTransition):
                self.sm.transition = FadeTransition(duration=0.20)
        else:
            # Default or gesture swipe: Smooth Direction-Aware Slide (left if going forward, right if going back)
            if not isinstance(self.sm.transition, SlideTransition):
                self.sm.transition = SlideTransition(duration=0.25)
            if direction:
                self.sm.transition.direction = direction
            else:
                self.sm.transition.direction = "left" if new_idx > curr_idx else "right"

        self.sm.current = screen_name
        self.nav_home.set_active(screen_name == "home")
        self.nav_mgr.set_active(screen_name == "manager")
        self.nav_set.set_active(screen_name == "settings")

    def check_android_share_intent(self, dt):
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
