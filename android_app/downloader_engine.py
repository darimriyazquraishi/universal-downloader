import os
import sys
import re
import json
import time
import shutil
import threading
import unicodedata
import urllib.parse
import yt_dlp

# Safeguard Kivy ProcessingStream buffer attribute so yt-dlp never encounters 'str' object has no attribute 'write'
try:
    from kivy.logger import ProcessingStream
    class _BufferProxy:
        def __init__(self, ps):
            self.ps = ps
        def write(self, b):
            try:
                if isinstance(b, bytes):
                    b = b.decode('utf-8', 'replace')
                return self.ps.write(b)
            except Exception:
                return 0
        def flush(self):
            try:
                return self.ps.flush()
            except Exception:
                pass

    ProcessingStream._line_accumulator = ''
    def _safe_write(self, s):
        try:
            if isinstance(s, bytes):
                s = s.decode('utf-8', 'replace')
            s = getattr(self, '_line_accumulator', '') + s
            lines = s.split('\n')
            for line in lines[:-1]:
                self.func('%s: %s' % (self.channel, line))
            self._line_accumulator = lines[-1]
        except Exception:
            pass

    ProcessingStream.write = _safe_write
    ProcessingStream.buffer = property(lambda self: _BufferProxy(self))
except Exception:
    pass

try:
    from jnius import autoclass
    Environment = autoclass('android.os.Environment')
    IS_ANDROID = True
except Exception:
    IS_ANDROID = False

def get_public_download_dir():
    """Retrieve public device Download directory."""
    if IS_ANDROID:
        try:
            pub_download = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).getAbsolutePath()
            if os.path.isdir(pub_download):
                return pub_download
        except Exception:
            pass
        for candidate in ["/storage/emulated/0/Download", "/sdcard/Download"]:
            if os.path.isdir(candidate):
                return candidate
        return "/storage/emulated/0/Download"
    else:
        user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(user_downloads):
            return os.path.normpath(os.path.join(user_downloads, "Media Downloads"))
        return os.path.normpath(os.path.join(os.path.dirname(__file__), "downloads"))

def get_default_download_dir():
    """Determine default storage directory for Android vs Desktop simulator."""
    if IS_ANDROID:
        # Priority 1: Public device Download folder (visible to user, gallery, and all video players)
        pub = get_public_download_dir()
        try:
            os.makedirs(pub, exist_ok=True)
            test_file = os.path.join(pub, ".write_test")
            with open(test_file, "w") as f:
                f.write("1")
            if os.path.exists(test_file):
                os.remove(test_file)
            return pub
        except Exception:
            pass

        # Fallback to app external files dir only if public storage cannot be written directly
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            ext_dir = activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            if ext_dir:
                path = ext_dir.getAbsolutePath()
                os.makedirs(path, exist_ok=True)
                return path
        except Exception:
            pass

        return pub
    else:
        user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(user_downloads):
            return os.path.normpath(os.path.join(user_downloads, "Media Downloads"))
        return os.path.normpath(os.path.join(os.path.dirname(__file__), "downloads"))

def ensure_valid_download_dir(dir_path=None):
    """Ensure directory exists and is writable, returning a safe, verified path."""
    if dir_path:
        # Automatic upgrade: if old settings had the locked Android/data path, migrate to public Downloads!
        if IS_ANDROID and "Android/data" in dir_path:
            pub = get_public_download_dir()
            try:
                os.makedirs(pub, exist_ok=True)
                test_file = os.path.join(pub, ".write_test")
                with open(test_file, "w") as f:
                    f.write("1")
                if os.path.exists(test_file):
                    os.remove(test_file)
                return pub
            except Exception:
                pass

        # Clean any legacy unpermitted subfolder path on Android
        if IS_ANDROID and dir_path.endswith("Media Downloads"):
            parent = os.path.dirname(dir_path)
            if os.path.isdir(parent):
                dir_path = parent

        try:
            os.makedirs(dir_path, exist_ok=True)
            test_file = os.path.join(dir_path, ".write_test")
            with open(test_file, "w") as f:
                f.write("1")
            if os.path.exists(test_file):
                os.remove(test_file)
            return dir_path
        except Exception:
            pass

    return get_default_download_dir()

def get_storage_presets():
    """Return available storage location presets for UI selection."""
    presets = []
    if IS_ANDROID:
        try:
            p_dl = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).getAbsolutePath()
            presets.append({"id": "downloads", "title": "Downloads", "path": p_dl, "desc": "Phone Downloads (Public)"})
        except Exception:
            presets.append({"id": "downloads", "title": "Downloads", "path": "/storage/emulated/0/Download", "desc": "Phone Downloads (Public)"})

        try:
            p_mov = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES).getAbsolutePath()
            presets.append({"id": "movies", "title": "Movies", "path": p_mov, "desc": "Movies Folder (Public)"})
        except Exception:
            presets.append({"id": "movies", "title": "Movies", "path": "/storage/emulated/0/Movies", "desc": "Movies Folder (Public)"})

        try:
            p_mus = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC).getAbsolutePath()
            presets.append({"id": "music", "title": "Music", "path": p_mus, "desc": "Music Folder (Public)"})
        except Exception:
            presets.append({"id": "music", "title": "Music", "path": "/storage/emulated/0/Music", "desc": "Music Folder (Public)"})

        try:
            p_doc = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS).getAbsolutePath()
            presets.append({"id": "documents", "title": "Documents", "path": p_doc, "desc": "Documents Folder (Public)"})
        except Exception:
            presets.append({"id": "documents", "title": "Documents", "path": "/storage/emulated/0/Documents", "desc": "Documents Folder (Public)"})
    else:
        user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        presets.append({"id": "downloads", "title": "Downloads", "path": os.path.normpath(os.path.join(user_downloads, "Media Downloads")), "desc": "User Downloads"})
        user_videos = os.path.join(os.path.expanduser("~"), "Videos")
        if os.path.exists(user_videos):
            presets.append({"id": "movies", "title": "Videos", "path": os.path.normpath(os.path.join(user_videos, "Media Downloads")), "desc": "User Videos"})
        user_music = os.path.join(os.path.expanduser("~"), "Music")
        if os.path.exists(user_music):
            presets.append({"id": "music", "title": "Music", "path": os.path.normpath(os.path.join(user_music, "Media Downloads")), "desc": "User Music"})
        user_docs = os.path.join(os.path.expanduser("~"), "Documents")
        if os.path.exists(user_docs):
            presets.append({"id": "documents", "title": "Documents", "path": os.path.normpath(os.path.join(user_docs, "Media Downloads")), "desc": "User Documents"})


    return presets


def get_config_path():
    """Path to settings JSON file."""
    if IS_ANDROID:
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            files_dir = activity.getFilesDir().getAbsolutePath()
            return os.path.join(files_dir, "settings.json")
        except Exception:
            pass
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    cfg_dir = os.path.join(appdata, ".universal_downloader_mobile")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "settings.json")

def load_settings():
    default_cfg = {
        "download_dir": get_default_download_dir(),
        "ignore_dups": True,
        "max_tracks": 0,
        "default_format": "video_best",
        "auto_clean_mixes": True
    }
    try:
        p = get_config_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
    except Exception:
        pass
    default_cfg["download_dir"] = ensure_valid_download_dir(default_cfg.get("download_dir"))
    return default_cfg

def save_settings(cfg):
    try:
        p = get_config_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

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
                # Return clean single video URL
                return f"https://www.youtube.com/watch?v={vid}"
                
        # Reconstruct clean URL
        new_query = urllib.parse.urlencode(qs, doseq=True)
        return urllib.parse.urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
    except Exception:
        return url

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

def clean_filename(title, idx, max_len=75):
    """Sanitize title for Android FAT32 / SD Card / internal storage compatibility."""
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

def inspect_url(url, scope=None):
    """Deep inspect media URL for tracks, metadata, and rough size estimate.
    Automatically handles single video vs playlist/mix selection.
    scope: None (auto-detect), 'single' (force video only), 'playlist' (force entire playlist)
    """
    platform = detect_platform(url)
    parsed = parse_url_structure(url)
    
    # Auto-resolve scope if user has both video and playlist
    target_url = url
    active_scope = "single"
    
    if parsed["has_both"]:
        # If user explicitly wants playlist, use original url
        if scope == "playlist":
            active_scope = "playlist"
            target_url = url
        else:
            # Default to single video for YouTube mixes (RDMM etc.) or when single requested
            active_scope = "single"
            target_url = parsed["clean_video_url"]
    elif scope == "single" and parsed["clean_video_url"]:
        active_scope = "single"
        target_url = parsed["clean_video_url"]

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extract_flat': (active_scope == "playlist"),
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        },
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
            dur_str = "Media Clip"

        media_title = info.get('title') or (valid[0]['title'] if valid else f"{platform} Media")

        # Rough size estimate for standard 1080p / MP4
        mb = max(8.0, (500000 * max(10, total_dur)) / (1024 * 1024))
        size_est = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"

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
            "size_estimate": size_est,
            "items": valid
        }
