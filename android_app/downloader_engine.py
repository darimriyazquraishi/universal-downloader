import os
import sys
import re
import json
import time
import shutil
import threading
import unicodedata
import yt_dlp

try:
    from jnius import autoclass
    Environment = autoclass('android.os.Environment')
    IS_ANDROID = True
except Exception:
    IS_ANDROID = False

def get_default_download_dir():
    """Determine default storage directory for Android vs Desktop simulator."""
    if IS_ANDROID:
        try:
            download_dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).getAbsolutePath()
            return os.path.join(download_dir, "Media Downloads")
        except Exception:
            return "/storage/emulated/0/Download/Media Downloads"
    else:
        user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(user_downloads):
            return os.path.normpath(os.path.join(user_downloads, "Media Downloads"))
        return os.path.normpath(os.path.join(os.path.dirname(__file__), "downloads"))

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
        "default_format": "video_best"
    }
    try:
        p = get_config_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
    except Exception:
        pass
    return default_cfg

def save_settings(cfg):
    try:
        p = get_config_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

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

def inspect_url(url):
    """Deep inspect media URL for tracks, metadata, and rough size estimate."""
    platform = detect_platform(url)
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
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
                    item_url = url
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
            "track_count": len(valid),
            "duration_str": dur_str,
            "total_duration": total_dur,
            "size_estimate": size_est,
            "items": valid
        }
