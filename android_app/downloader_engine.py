import os
import sys
import re
import json
import time
import shutil
import logging
import threading
import unicodedata
import urllib.parse
import yt_dlp

logger = logging.getLogger(__name__)

# Configure secure Mozilla CA bundle via certifi for robust TLS certificate validation
try:
    import certifi
    ca_bundle = certifi.where()
    if ca_bundle and os.path.exists(ca_bundle):
        os.environ.setdefault('SSL_CERT_FILE', ca_bundle)
        os.environ.setdefault('REQUESTS_CA_BUNDLE', ca_bundle)
except Exception:
    pass

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

def is_content_uri(path_or_uri):
    """Check if target string is any Android content:// URI."""
    if not path_or_uri:
        return False
    return str(path_or_uri).strip().startswith("content://")

def is_mediastore_uri(path_or_uri):
    """Check if target string is an Android MediaStore collection or item URI."""
    if not is_content_uri(path_or_uri):
        return False
    return str(path_or_uri).strip().startswith("content://media/")

def is_document_uri(path_or_uri):
    """
    Check if target string is an individual SAF document URI.
    Matches standalone document URIs ('.../document/...') as well as document
    URIs nested/generated inside a tree ('.../tree/.../document/...').
    """
    if not is_content_uri(path_or_uri):
        return False
    return "/document/" in str(path_or_uri)

def is_tree_uri(path_or_uri):
    """
    Check if target string is specifically an Android SAF Tree root URI
    (directory from ACTION_OPEN_DOCUMENT_TREE) used for folder selection.
    
    A document generated inside a tree contains '/document/' and must NOT
    be misclassified as a folder-selection tree URI.
    """
    if not is_content_uri(path_or_uri):
        return False
    s = str(path_or_uri)
    return ("/tree/" in s) and ("/document/" not in s)

def is_saf_uri(path_or_uri):
    """Check if target string is specifically a Storage Access Framework URI (tree root or document)."""
    return is_tree_uri(path_or_uri) or is_document_uri(path_or_uri)

def extract_parent_tree_uri(path_or_uri):
    """
    Extract the parent SAF tree URI from a document URI generated inside a tree.
    Returns the tree URI string if path_or_uri is a nested document URI or tree URI,
    or None if no tree root can be resolved.
    """
    if not is_content_uri(path_or_uri):
        return None
    s = str(path_or_uri).strip()
    if is_tree_uri(s):
        return s
    if is_document_uri(s) and "/tree/" in s:
        # Format: content://authority/tree/<tree_id>/document/<doc_id>
        return s.split("/document/")[0]
    return None

def _write_staging_to_uri(resolver, target_uri, staging_filepath):
    """
    Safely stream data from local staging_filepath into an Android ContentResolver target_uri.
    First attempts native ParcelFileDescriptor streaming via openFileDescriptor('w'),
    which executes directly via OS-level kernel file descriptor (maximum performance, zero JNI overhead).
    Falls back to Java OutputStream if ParcelFileDescriptor is unavailable.
    """
    pfd = None
    try:
        String = autoclass('java.lang.String')
        pfd = resolver.openFileDescriptor(target_uri, String("w"))
    except Exception as e:
        logger.debug(f"openFileDescriptor failed for {target_uri}: {e}")
        pfd = None

    if pfd is not None:
        try:
            fd = pfd.getFd()
            with open(staging_filepath, "rb") as in_f:
                with open(fd, "wb", closefd=False) as out_f:
                    shutil.copyfileobj(in_f, out_f, length=131072)
                    out_f.flush()
                    try:
                        os.fsync(fd)
                    except OSError:
                        pass
            return
        finally:
            try:
                pfd.close()
            except Exception:
                pass

    # Fallback to openOutputStream
    out_stream = None
    try:
        out_stream = resolver.openOutputStream(target_uri)
        if not out_stream:
            raise IOError(f"Failed to open output stream for URI {target_uri}")
        with open(staging_filepath, "rb") as in_f:
            while True:
                chunk = in_f.read(65536)
                if not chunk:
                    break
                try:
                    from jnius import jarray
                    out_stream.write(jarray('B')(chunk), 0, len(chunk))
                except Exception:
                    out_stream.write(bytearray(chunk))
        out_stream.flush()
    finally:
        if out_stream:
            try:
                out_stream.close()
            except Exception:
                pass

def save_to_mediastore_downloads(staging_filepath, display_name, mime_type="video/mp4"):
    """
    Publish completed media file to Android MediaStore Downloads collection.
    Complies 100% with Android 10+ (API 29 to 36) Scoped Storage without requiring
    broad storage permissions (WRITE_EXTERNAL_STORAGE / MANAGE_EXTERNAL_STORAGE).
    Returns the created content:// URI or raises an Exception.
    """
    if not os.path.exists(staging_filepath):
        raise FileNotFoundError(f"Staged download not found at {staging_filepath}")

    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    activity = PythonActivity.mActivity
    resolver = activity.getContentResolver()
    ContentValues = autoclass('android.content.ContentValues')
    String = autoclass('java.lang.String')
    Integer = autoclass('java.lang.Integer')
    Long = autoclass('java.lang.Long')
    Uri = autoclass('android.net.Uri')

    # MediaStore column names as literal string constants to avoid PyJNIus inner-interface reflection failures
    COLUMN_DISPLAY_NAME = "_display_name"
    COLUMN_MIME_TYPE = "mime_type"
    COLUMN_RELATIVE_PATH = "relative_path"
    COLUMN_IS_PENDING = "is_pending"
    COLUMN_SIZE = "_size"

    sdk_int = 30
    try:
        BuildVersion = autoclass('android.os.Build$VERSION')
        sdk_int = int(BuildVersion.SDK_INT)
    except Exception:
        pass

    values = ContentValues()
    values.put(String(COLUMN_DISPLAY_NAME), String(display_name))
    values.put(String(COLUMN_MIME_TYPE), String(mime_type or "application/octet-stream"))
    try:
        values.put(String(COLUMN_SIZE), Long(os.path.getsize(staging_filepath)))
    except Exception:
        pass

    if sdk_int >= 29:
        # Android Scoped Storage requires trailing slash for RELATIVE_PATH
        rel_path = "Download/"
        try:
            Environment = autoclass('android.os.Environment')
            if hasattr(Environment, 'DIRECTORY_DOWNLOADS'):
                d = Environment.DIRECTORY_DOWNLOADS
                d_str = str(d.toString() if hasattr(d, 'toString') else d).strip('/')
                rel_path = f"{d_str}/"
        except Exception:
            rel_path = "Download/"
        values.put(String(COLUMN_RELATIVE_PATH), String(rel_path))
        values.put(String(COLUMN_IS_PENDING), Integer(1))

    # Resolve MediaStore.Downloads.EXTERNAL_CONTENT_URI (API 29+) or MediaStore.Files
    downloads_uri = None
    if sdk_int >= 29:
        try:
            MediaStoreDownloads = autoclass('android.provider.MediaStore$Downloads')
            downloads_uri = MediaStoreDownloads.EXTERNAL_CONTENT_URI
        except Exception:
            try:
                downloads_uri = Uri.parse("content://media/external/downloads")
            except Exception:
                pass

    if not downloads_uri:
        try:
            MediaStoreFiles = autoclass('android.provider.MediaStore$Files')
            downloads_uri = MediaStoreFiles.getContentUri(String("external"))
        except Exception:
            downloads_uri = Uri.parse("content://media/external/downloads")

    item_uri = resolver.insert(downloads_uri, values)
    if not item_uri:
        # Retry with unique timestamped filename if duplicate entry constraint occurred
        base, ext = os.path.splitext(display_name)
        unique_name = f"{base}_{int(time.time())}{ext}"
        values.put(String(COLUMN_DISPLAY_NAME), String(unique_name))
        item_uri = resolver.insert(downloads_uri, values)

    if not item_uri:
        # Fallback to MediaStore.Files collection if Downloads collection returned null
        try:
            MediaStoreFiles = autoclass('android.provider.MediaStore$Files')
            files_uri = MediaStoreFiles.getContentUri(String("external"))
            item_uri = resolver.insert(files_uri, values)
        except Exception:
            pass

    if not item_uri:
        raise IOError(f"Failed to create MediaStore entry for '{display_name}' (resolver.insert returned null)")

    try:
        _write_staging_to_uri(resolver, item_uri, staging_filepath)

        # Mark item as no longer pending so external player apps, download manager, and gallery see it
        if sdk_int >= 29:
            try:
                clear_values = ContentValues()
                clear_values.put(String(COLUMN_IS_PENDING), Integer(0))
                resolver.update(item_uri, clear_values, None, None)
            except Exception as update_err:
                logger.warning(f"Failed to clear IS_PENDING for {item_uri}: {update_err}")

        try:
            os.remove(staging_filepath)
        except Exception:
            pass
        return str(item_uri.toString())
    except Exception as e:
        try:
            resolver.delete(item_uri, None, None)
        except Exception:
            pass
        raise IOError(f"Failed to stream data to MediaStore item: {e}")

def get_staging_download_dir():
    """Retrieve an always-writable staging directory for progressive downloading & muxing."""
    if IS_ANDROID:
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            cache_dir = activity.getExternalCacheDir()
            if cache_dir:
                p = cache_dir.getAbsolutePath()
                os.makedirs(p, exist_ok=True)
                return p
        except Exception:
            pass
        try:
            files_dir = activity.getFilesDir()
            if files_dir:
                p = os.path.join(files_dir.getAbsolutePath(), "staging")
                os.makedirs(p, exist_ok=True)
                return p
        except Exception:
            pass
    return get_default_download_dir()

def save_file_to_destination(staging_filepath, destination_dir_or_uri, display_name, mime_type="video/mp4"):
    """
    Export completed download from staging path into the final destination.
    Handles Storage Access Framework (SAF) tree URIs, MediaStore Downloads,
    and standard filesystem paths.

    Security and Integrity Rule:
    Never silently redirect a failed custom destination to another folder.
    Preserve completed staged downloads and raise errors when the selected
    destination is unavailable.
    """
    if not os.path.exists(staging_filepath):
        raise FileNotFoundError(f"Staged download not found at {staging_filepath}")

    # Case 1: Android Storage Access Framework content:// tree URI (custom user-selected directory)
    if IS_ANDROID and is_tree_uri(destination_dir_or_uri):
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()
            Uri = autoclass('android.net.Uri')
            DocumentsContract = autoclass('android.provider.DocumentsContract')
            String = autoclass('java.lang.String')

            tree_uri = Uri.parse(str(destination_dir_or_uri))
            doc_id = DocumentsContract.getTreeDocumentId(tree_uri)
            parent_doc_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, doc_id)

            new_doc_uri = DocumentsContract.createDocument(resolver, parent_doc_uri, String(mime_type), String(display_name))
            if not new_doc_uri:
                raise IOError(f"DocumentsContract failed to create document for '{display_name}'")

            _write_staging_to_uri(resolver, new_doc_uri, staging_filepath)

            try:
                os.remove(staging_filepath)
            except Exception:
                pass
            return str(new_doc_uri.toString())
        except Exception as e:
            # Preserve staging file and raise error to user: DO NOT SILENTLY REDIRECT!
            raise IOError(f"Failed to save to selected custom folder: {e}")

    # Case 2: On Android, invalid content URI destinations (e.g. document URIs) cannot serve as destination folders
    if IS_ANDROID and is_content_uri(destination_dir_or_uri) and not is_tree_uri(destination_dir_or_uri) and not is_mediastore_uri(destination_dir_or_uri):
        raise IOError(f"Invalid custom destination URI '{destination_dir_or_uri}'. Must be a valid SAF folder tree URI.")

    # Case 3: On Android, shared / default downloads publish via MediaStore Downloads
    if IS_ANDROID and (not destination_dir_or_uri or is_mediastore_uri(destination_dir_or_uri) or destination_dir_or_uri == get_default_download_dir()):
        try:
            mediastore_uri = save_to_mediastore_downloads(staging_filepath, display_name, mime_type)
            if mediastore_uri:
                return mediastore_uri
            raise IOError(f"save_to_mediastore_downloads returned empty URI for '{display_name}'")
        except Exception as e:
            # Preserve staging file and report clear error: DO NOT SWALLOW OR SILENTLY REDIRECT!
            raise IOError(f"Failed to save to Android MediaStore Downloads: {e}")

    # Case 4: Standard filesystem destination (desktop simulator or Android app-specific storage)
    if is_content_uri(destination_dir_or_uri):
        raise IOError(f"Unsupported destination content URI: {destination_dir_or_uri}")

    dest_dir = destination_dir_or_uri or get_default_download_dir()
    dest_dir = ensure_valid_download_dir(dest_dir)
    if not os.path.isdir(dest_dir):
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            raise IOError(f"Destination folder '{dest_dir}' is unavailable and could not be created: {e}")

    target_path = os.path.join(dest_dir, display_name)

    # Handle overwrite or existing files
    if os.path.exists(target_path):
        base, ext = os.path.splitext(display_name)
        target_path = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext}")

    try:
        shutil.move(staging_filepath, target_path)
    except Exception as move_err:
        try:
            shutil.copy2(staging_filepath, target_path)
            try:
                os.remove(staging_filepath)
            except Exception:
                pass
        except Exception as copy_err:
            # Preserve staging file and raise error to user: DO NOT SILENTLY DROP OR REDIRECT!
            raise IOError(f"Failed to save file to destination '{target_path}': {copy_err}")

    if IS_ANDROID and os.path.exists(target_path):
        try:
            MediaScannerConnection = autoclass('android.media.MediaScannerConnection')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity
            MediaScannerConnection.scanFile(context, [target_path], None, None)
        except Exception:
            pass

    return target_path

def uri_to_display_name(uri_or_path):
    """Generate human-readable representation of directory path or SAF/MediaStore content URI."""
    if not uri_or_path:
        return "Default: Downloads"
    s = str(uri_or_path)
    if is_content_uri(s):
        import urllib.parse
        decoded = urllib.parse.unquote(s)
        if "primary:" in decoded:
            rel = decoded.split("primary:")[-1].strip("/")
            return f"Selected Folder: {rel}" if rel else "Selected Folder: Internal Storage"
        elif "/tree/" in decoded:
            part = decoded.split("/tree/")[-1]
            return f"Selected Folder: {part}"
        elif "downloads" in decoded.lower():
            return "Downloads (MediaStore)"
        elif "video" in decoded.lower():
            return "Videos (MediaStore)"
        elif "audio" in decoded.lower():
            return "Audio (MediaStore)"
        return "Selected Folder (SAF/MediaStore)"
    return s

def ensure_valid_download_dir(dir_path=None):
    """Ensure directory exists and is writable, returning a safe, verified path or content URI."""
    if dir_path:
        # If already a valid Storage Access Framework or MediaStore URI, preserve it directly
        if is_content_uri(dir_path):
            return str(dir_path)

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

def uri_to_path(uri_obj):
    """
    Convert file:// URI or local filesystem representation to a normalized POSIX path.
    Note: Android content:// URIs (SAF and MediaStore) cannot and must not be converted
    to direct filesystem paths under Scoped Storage; this function explicitly rejects them.
    """
    if not uri_obj:
        return None
    try:
        uri_str = uri_obj.toString() if hasattr(uri_obj, 'toString') else str(uri_obj)
        if not uri_str:
            return None
        # Reject all content:// URIs - they cannot be converted to filesystem paths
        if is_content_uri(uri_str):
            return None
        if uri_str.startswith("file://"):
            raw_path = uri_str[7:]
            return os.path.normpath(raw_path).replace("\\", "/")
        if os.path.isabs(uri_str):
            return os.path.normpath(uri_str).replace("\\", "/")
    except Exception:
        pass
    return None


def get_history_path():
    """Path to app-specific download history JSON file."""
    if IS_ANDROID:
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            files_dir = activity.getFilesDir().getAbsolutePath()
            return os.path.join(files_dir, "download_history.json")
        except Exception:
            pass
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    cfg_dir = os.path.join(appdata, ".universal_downloader_mobile")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "download_history.json")

def load_history():
    """Load items downloaded strictly through this app."""
    p = get_history_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    # First launch: initialize clean empty history
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as out_f:
            json.dump([], out_f, indent=2)
    except Exception:
        pass
    return []

def add_to_history(name, path, fmt_tag="MP4"):
    """Record an item downloaded by this app."""
    try:
        items = load_history()
        items = [it for it in items if it.get("name") != name]
        items.insert(0, {
            "name": name,
            "path": path,
            "format": fmt_tag,
            "time": time.time()
        })
        items = items[:100]
        p = get_history_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
    except Exception:
        pass

def clear_history():
    """Clear app download history."""
    try:
        p = get_history_path()
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass


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

def resolve_mukaplay_url(url):
    """
    Resolve Muka / MukaPlay dynamic share links to their underlying canonical media URL.
    Extracts embedded YouTube video ID or direct media stream from the MukaPlay share page.
    Returns (resolved_url, page_title).
    """
    if not url:
        return url, None
    u = str(url).strip()
    if not any(domain in u.lower() for domain in ["mukaplay.com", "muka-box.com", "muka.com"]):
        return u, None

    try:
        import ssl
        import urllib.request
        ctx = ssl.create_default_context()
        try:
            import certifi
            ca_bundle = certifi.where()
            if os.path.exists(ca_bundle):
                ctx.load_verify_locations(ca_bundle)
        except Exception:
            pass

        req = urllib.request.Request(u, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            html = resp.read().decode('utf-8', 'replace')

        # Extract og:title if present
        og_title = None
        m_title = re.search(r'<meta\s+property=[\"\']og:title[\"\']\s+content=[\"\']([^\"\']+)[\"\']', html)
        if m_title:
            og_title = m_title.group(1).strip()

        # 1. JSON ytData in __INITIAL_STATE__
        m = re.search(r'\"ytData\"\s*:\s*\{([^}]+)\}', html)
        if m:
            block = '{' + m.group(1) + '}'
            try:
                data = json.loads(block)
                if data.get('i'):
                    return f"https://www.youtube.com/watch?v={data['i']}", (data.get('tl') or og_title)
            except Exception:
                pass
            m_id = re.search(r'\"i\"\s*:\s*\"([a-zA-Z0-9_-]{11})\"', block)
            if m_id:
                return f"https://www.youtube.com/watch?v={m_id.group(1)}", og_title

        # 2. General __INITIAL_STATE__ parse for videoId or youtube ID
        m_yt_id = re.search(r'\"(?:videoId|ytId|youtubeId|video_id)\"\s*:\s*\"([a-zA-Z0-9_-]{11})\"', html)
        if m_yt_id:
            return f"https://www.youtube.com/watch?v={m_yt_id.group(1)}", og_title

        # 3. YouTube thumbnail / poster
        m_yt = re.search(r'i\.ytimg\.com/vi/([a-zA-Z0-9_-]{11})/', html)
        if m_yt:
            return f"https://www.youtube.com/watch?v={m_yt.group(1)}", og_title

        # 4. og:video or direct media tag
        m_vid = re.search(r'<meta\s+property=[\"\']og:video(?::url)?[\"\']\s+content=[\"\']([^\"\']+)[\"\']', html)
        if m_vid:
            return m_vid.group(1), og_title

        # 5. Direct audio / video source tags
        m_src = re.search(r'<(?:video|audio|source)[^>]+src=[\"\'](https?://[^\"\']+)[\"\']', html)
        if m_src:
            return m_src.group(1), og_title

    except Exception:
        pass

    return u, None

def parse_url_structure(url):
    """Detect if a URL contains a single video, a playlist, or a video within a YouTube Mix/Radio."""
    if not url:
        return {
            "is_youtube": False,
            "video_id": None,
            "playlist_id": None,
            "is_mix": False,
            "has_both": False,
            "clean_video_url": None
        }

    canonical_url = url
    if any(domain in str(url).lower() for domain in ["mukaplay.com", "muka-box.com", "muka.com"]):
        resolved, _ = resolve_mukaplay_url(url)
        if resolved:
            canonical_url = resolved

    u = urllib.parse.urlparse(str(canonical_url))
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
    if not url:
        return ""
    try:
        u = urllib.parse.urlparse(str(url))
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
    if "mukaplay.com" in u or "muka-box.com" in u or "muka.com" in u:
        return "MukaPlay"
    elif "youtube.com" in u or "youtu.be" in u:
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
    elif "dailymotion.com" in u or "dai.ly" in u:
        return "Dailymotion"
    elif "twitch.tv" in u:
        return "Twitch"
    return "Universal Web"

def clean_filename(title, idx, max_len=75):
    """Sanitize title for Android FAT32 / SD Card / internal storage compatibility."""
    title = str(title or f"Track_{idx:03d}")
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

    target_url = url
    muka_title = None
    if platform == "MukaPlay":
        resolved_url, muka_title = resolve_mukaplay_url(url)
        if resolved_url:
            target_url = resolved_url

    parsed = parse_url_structure(target_url)
    
    # Auto-resolve scope if user has both video and playlist
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

        media_title = info.get('title') or muka_title or (valid[0]['title'] if valid else f"{platform} Media")

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
            "target_url": target_url,
            "track_count": len(valid),
            "duration_str": dur_str,
            "total_duration": total_dur,
            "size_estimate": size_est,
            "items": valid
        }
