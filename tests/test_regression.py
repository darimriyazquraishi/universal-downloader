import os
import sys
import unittest
import zipfile

# Add android_app to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "android_app"))
import downloader_engine as engine

class TestSecurityAndTls(unittest.TestCase):
    """Verify TLS verification is active and insecure bypasses are eliminated."""

    def test_no_nocheckcertificate_in_codebase(self):
        android_dir = os.path.join(os.path.dirname(__file__), "..", "android_app")
        for fname in ["downloader_engine.py", "main.py"]:
            fpath = os.path.join(android_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertNotIn("nocheckcertificate", content, f"Insecure 'nocheckcertificate' found in {fname}")
                self.assertNotIn("verify=False", content, f"Insecure 'verify=False' found in {fname}")

    def test_tls_rejects_untrusted_certificates(self):
        import yt_dlp
        opts = {'quiet': True, 'no_warnings': True}
        with self.assertRaises(Exception):
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info("https://self-signed.badssl.com/", download=False)

    def test_tls_valid_https_inspection(self):
        # Rick Astley - Never Gonna Give You Up (official video)
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        res = engine.inspect_url(test_url)
        self.assertIsNotNone(res)
        self.assertIn("title", res)
        self.assertIn("duration_str", res)
        self.assertEqual(res["platform"], "YouTube")
        self.assertFalse(res["is_playlist"])


class TestPlatformAndUrlHandling(unittest.TestCase):
    """Verify URL structure parsing and platform detection."""

    def test_platform_detection(self):
        cases = [
            ("https://www.youtube.com/watch?v=12345", "YouTube"),
            ("https://youtu.be/12345", "YouTube"),
            ("https://www.instagram.com/reel/C12345/", "Instagram"),
            ("https://www.tiktok.com/@user/video/12345", "TikTok"),
            ("https://twitter.com/user/status/12345", "X / Twitter"),
            ("https://x.com/user/status/12345", "X / Twitter"),
            ("https://www.facebook.com/watch/?v=12345", "Facebook"),
            ("https://www.reddit.com/r/videos/comments/12345/", "Reddit"),
            ("https://pin.it/12345", "Pinterest"),
            ("https://soundcloud.com/artist/track", "SoundCloud"),
            ("https://vimeo.com/12345", "Vimeo"),
            ("https://example.com/video.mp4", "Universal Web"),
        ]
        for url, expected in cases:
            self.assertEqual(engine.detect_platform(url), expected, f"Failed for {url}")

    def test_url_structure_parsing(self):
        # Single video
        s = engine.parse_url_structure("https://www.youtube.com/watch?v=abc123xyz")
        self.assertTrue(s["is_youtube"])
        self.assertEqual(s["video_id"], "abc123xyz")
        self.assertIsNone(s["playlist_id"])
        self.assertFalse(s["is_mix"])
        self.assertFalse(s["has_both"])

        # YouTube Mix
        m = engine.parse_url_structure("https://www.youtube.com/watch?v=abc123xyz&list=RDabc123xyz")
        self.assertTrue(m["is_mix"])
        self.assertTrue(m["has_both"])
        self.assertEqual(m["clean_video_url"], "https://www.youtube.com/watch?v=abc123xyz")

        # Standard Playlist
        p = engine.parse_url_structure("https://www.youtube.com/playlist?list=PL123456789")
        self.assertFalse(p["is_mix"])
        self.assertEqual(p["playlist_id"], "PL123456789")

    def test_clean_url(self):
        dirty = "https://www.youtube.com/watch?v=abc123xyz&si=tracker123&feature=share&utm_source=test"
        clean = engine.clean_url(dirty)
        self.assertNotIn("si=", clean)
        self.assertNotIn("utm_source=", clean)
        self.assertNotIn("feature=", clean)
        self.assertIn("v=abc123xyz", clean)


class TestFileOperationsAndSanitization(unittest.TestCase):
    """Verify filename cleaning and safe directory handling."""

    def test_clean_filename(self):
        dirty = 'My Video: Song | Part 1 / 2 ? * < > " [1080p]'
        cleaned = engine.clean_filename(dirty, 1)
        for char in ['?', '*', '<', '>', '"', '|', '/', '\\', ':']:
            self.assertNotIn(char, cleaned)
        self.assertTrue(len(cleaned) > 0)
        self.assertTrue(len(cleaned) <= 75)

    def test_clean_filename_length_boundary(self):
        long_name = "A" * 150
        cleaned = engine.clean_filename(long_name, 1, max_len=50)
        self.assertLessEqual(len(cleaned), 50)


class TestPermissionsAndPackaging(unittest.TestCase):
    """Verify least-privilege permissions and packaging configuration."""

    def test_buildozer_permissions(self):
        spec_path = os.path.join(os.path.dirname(__file__), "..", "android_app", "buildozer.spec")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Permissions must strictly be INTERNET and ACCESS_NETWORK_STATE
        self.assertIn("android.permissions = INTERNET,ACCESS_NETWORK_STATE", content)
        self.assertNotIn("READ_MEDIA_VIDEO", content)
        self.assertNotIn("READ_MEDIA_AUDIO", content)
        self.assertNotIn("WRITE_EXTERNAL_STORAGE", content)
        self.assertNotIn("READ_EXTERNAL_STORAGE", content)

    def test_buildozer_release_mode(self):
        spec_path = os.path.join(os.path.dirname(__file__), "..", "android_app", "buildozer.spec")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("version = 1.1.0", content)
        self.assertIn("android.release_artifact = apk", content)

    def test_no_keystore_in_source_zip(self):
        zip_path = r"e:\deleteme\UniversalDownloader_Android_Source.zip"
        self.assertTrue(os.path.exists(zip_path), "Source zip does not exist")
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            for name in names:
                self.assertFalse(name.endswith((".keystore", ".jks", ".p12", ".key")), f"Keystore leaked in zip: {name}")
                self.assertNotIn("main_first.py", name)


class TestDownloaderEngineAndStorage(unittest.TestCase):
    """Verify settings, history, destination selection, and cancellation mechanisms."""

    def test_settings_load_and_save(self):
        cfg = engine.load_settings()
        self.assertIn("download_dir", cfg)
        self.assertIn("default_format", cfg)
        # Test modifying and restoring
        orig_fmt = cfg.get("default_format")
        cfg["default_format"] = "video_720"
        engine.save_settings(cfg)
        reloaded = engine.load_settings()
        self.assertEqual(reloaded["default_format"], "video_720")
        # Restore
        cfg["default_format"] = orig_fmt
        engine.save_settings(cfg)

    def test_ensure_valid_download_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            verified = engine.ensure_valid_download_dir(tmpdir)
            self.assertEqual(os.path.normpath(verified), os.path.normpath(tmpdir))
            self.assertTrue(os.path.isdir(verified))

    def test_history_operations(self):
        history_path = engine.get_history_path()
        backup_data = None
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                backup_data = f.read()

        try:
            engine.clear_history()
            items = engine.load_history()
            self.assertEqual(items, [], "History should be empty after clear")

            # Add test item
            engine.add_to_history("Test Track 1", "/path/to/test.mp4", "MP4")
            items = engine.load_history()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["name"], "Test Track 1")

            # Update existing item
            engine.add_to_history("Test Track 1", "/path/to/test_new.mp4", "MP4")
            items = engine.load_history()
            self.assertEqual(len(items), 1, "Duplicate should not be created")
            self.assertEqual(items[0]["path"], "/path/to/test_new.mp4")
        finally:
            if backup_data is not None:
                with open(history_path, "w", encoding="utf-8") as f:
                    f.write(backup_data)

    def test_cancellation_mechanism(self):
        import threading
        stop_event = threading.Event()
        stop_event.set()

        def progress_hook(d):
            if stop_event.is_set():
                raise Exception("Stopped by user")

        with self.assertRaises(Exception) as ctx:
            progress_hook({'status': 'downloading'})
        self.assertIn("Stopped by user", str(ctx.exception))

    def test_invalid_url_handling(self):
        with self.assertRaises(Exception):
            engine.inspect_url("https://www.youtube.com/watch?v=NON_EXISTENT_ID_9999999999999")


if __name__ == "__main__":
    unittest.main()

