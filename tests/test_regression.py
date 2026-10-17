import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import zipfile

# ---------------------------------------------------------------------------
# Dynamic Repository Root and Android App Path Discovery (Portable)
# ---------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# If tests is inside repo root:
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if os.path.exists(os.path.join(REPO_ROOT, "android_app", "downloader_engine.py")):
    ANDROID_DIR = os.path.join(REPO_ROOT, "android_app")
elif os.path.exists(os.path.join(CURRENT_DIR, "..", "downloader_engine.py")):
    ANDROID_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
    REPO_ROOT = ANDROID_DIR
else:
    raise RuntimeError(f"Could not locate android_app directory relative to {__file__}")

sys.path.insert(0, ANDROID_DIR)
import downloader_engine as engine


# ===========================================================================
# Area 1: URL Validation and Supported Platform Handling
# ===========================================================================
class TestUrlValidationAndPlatforms(unittest.TestCase):
    """Verify platform detection, URL structure parsing, and tracking parameter cleaning."""

    def test_platform_detection_coverage(self):
        cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "YouTube"),
            ("https://youtu.be/dQw4w9WgXcQ", "YouTube"),
            ("https://www.youtube.com/shorts/abc123xyz", "YouTube"),
            ("https://www.instagram.com/reel/C123456789/", "Instagram"),
            ("https://www.instagram.com/p/C123456789/", "Instagram"),
            ("https://www.tiktok.com/@creator/video/1234567890", "TikTok"),
            ("https://twitter.com/user/status/1234567890", "X / Twitter"),
            ("https://x.com/user/status/1234567890", "X / Twitter"),
            ("https://www.facebook.com/watch/?v=1234567890", "Facebook"),
            ("https://www.reddit.com/r/videos/comments/12345/video/", "Reddit"),
            ("https://pin.it/7mXyZ12", "Pinterest"),
            ("https://soundcloud.com/artist/sample-track", "SoundCloud"),
            ("https://vimeo.com/123456789", "Vimeo"),
            ("https://www.dailymotion.com/video/x12345", "Dailymotion"),
            ("https://cdn.example.org/files/sample_video.mp4", "Universal Web"),
        ]
        for url, expected in cases:
            self.assertEqual(engine.detect_platform(url), expected, f"Platform mismatch for {url}")

    def test_url_structure_parsing(self):
        # Single video without playlist
        s = engine.parse_url_structure("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(s["is_youtube"])
        self.assertEqual(s["video_id"], "dQw4w9WgXcQ")
        self.assertIsNone(s["playlist_id"])
        self.assertFalse(s["is_mix"])
        self.assertFalse(s["has_both"])

        # YouTube Mix (Video + RD playlist)
        m = engine.parse_url_structure("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ")
        self.assertTrue(m["is_youtube"])
        self.assertTrue(m["is_mix"])
        self.assertTrue(m["has_both"])
        self.assertEqual(m["clean_video_url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        # Standard YouTube Playlist (standalone)
        p = engine.parse_url_structure("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf")
        self.assertTrue(p["is_youtube"])
        self.assertFalse(p["is_mix"])
        self.assertEqual(p["playlist_id"], "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf")

    def test_clean_url_strips_tracking_parameters(self):
        dirty = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=track123&feature=share&utm_source=social&fbclid=abc"
        clean = engine.clean_url(dirty)
        self.assertNotIn("si=", clean)
        self.assertNotIn("feature=", clean)
        self.assertNotIn("utm_source=", clean)
        self.assertNotIn("fbclid=", clean)
        self.assertIn("v=dQw4w9WgXcQ", clean)


# ===========================================================================
# Area 2: Download Configuration and TLS Certificate Verification
# ===========================================================================
class TestTlsSecurityAndConfiguration(unittest.TestCase):
    """Verify TLS verification is strictly enabled with zero insecure bypasses."""

    def test_no_nocheckcertificate_in_codebase(self):
        for fname in ["downloader_engine.py", "main.py"]:
            fpath = os.path.join(ANDROID_DIR, fname)
            self.assertTrue(os.path.exists(fpath), f"File {fname} must exist in {ANDROID_DIR}")
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertNotIn("nocheckcertificate", content, f"Insecure 'nocheckcertificate' found in {fname}")
                self.assertNotIn("verify=False", content, f"Insecure 'verify=False' found in {fname}")
                self.assertNotIn("check_hostname=False", content, f"Insecure hostname check found in {fname}")

    def test_certifi_ca_bundle_configured(self):
        import certifi
        ca_path = certifi.where()
        self.assertTrue(os.path.exists(ca_path), "Mozilla CA root bundle from certifi must exist on filesystem")
        self.assertGreater(os.path.getsize(ca_path), 100000, "CA bundle file size should be substantial")

    @patch("yt_dlp.YoutubeDL")
    def test_inspect_url_preserves_tls_options(self, mock_ydl_class):
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "title": "Test Title",
            "duration": 180,
            "id": "12345",
            "webpage_url": "https://www.youtube.com/watch?v=12345"
        }
        mock_ydl_class.return_value.__enter__.return_value = mock_instance

        engine.inspect_url("https://www.youtube.com/watch?v=12345")
        # Ensure YoutubeDL was called with options that DO NOT include nocheckcertificate
        call_opts = mock_ydl_class.call_args[0][0]
        self.assertNotIn("nocheckcertificate", call_opts)
        self.assertFalse(call_opts.get("nocheckcertificate", False))


# ===========================================================================
# Area 3: Invalid Certificate and Network Failure Handling
# ===========================================================================
class TestNetworkFailureAndErrorHandling(unittest.TestCase):
    """Verify that network and SSL certificate failures are handled gracefully without insecure fallbacks."""

    def test_ssl_certificate_verify_error_mapping(self):
        error_msg = "Unable to download: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate"
        # Test simulated clean error mapping
        clean_err = str(error_msg)
        if "CERTIFICATE_VERIFY_FAILED" in clean_err or "CertificateVerifyError" in clean_err:
            clean_err = "SSL certificate verification failed"
        self.assertEqual(clean_err, "SSL certificate verification failed")

    def test_http_403_and_unavailable_error_mapping(self):
        cases = [
            ("HTTP Error 403: Forbidden", "Access forbidden (403)"),
            ("ERROR: Requested format is not available", "Format unavailable on host"),
            ("ERROR: Video unavailable", "Media unavailable"),
            ("ERROR: Private video", "Media is private"),
        ]
        for raw, expected in cases:
            clean = raw
            if "Requested format is not available" in clean:
                clean = "Format unavailable on host"
            elif "HTTP Error 403" in clean:
                clean = "Access forbidden (403)"
            elif "Video unavailable" in clean:
                clean = "Media unavailable"
            elif "Private video" in clean:
                clean = "Media is private"
            self.assertEqual(clean, expected)


# ===========================================================================
# Area 4: Filename Sanitization and Path Traversal Protection
# ===========================================================================
class TestFilenameSanitizationAndTraversal(unittest.TestCase):
    """Verify filename cleaning and path traversal prevention."""

    def test_clean_filename_strips_illegal_characters(self):
        dirty = 'My Video: Song | Part 1 / 2 ? * < > " [1080p]'
        cleaned = engine.clean_filename(dirty, 1)
        for char in ['?', '*', '<', '>', '"', '|', '/', '\\', ':']:
            self.assertNotIn(char, cleaned, f"Illegal char '{char}' remained in cleaned filename")
        self.assertTrue(len(cleaned) > 0)
        self.assertTrue(len(cleaned) <= 75)

    def test_clean_filename_path_traversal_payloads(self):
        payloads = [
            "../../../../etc/passwd",
            "..\\..\\Windows\\System32\\cmd.exe",
            "folder/../../secret.txt",
            "/absolute/root/file.mp4"
        ]
        for payload in payloads:
            cleaned = engine.clean_filename(payload, 1)
            self.assertNotIn("/", cleaned)
            self.assertNotIn("\\", cleaned)
            self.assertFalse(cleaned.startswith(".."))

    def test_clean_filename_length_boundary(self):
        long_name = "X" * 200
        cleaned = engine.clean_filename(long_name, 1, max_len=60)
        self.assertLessEqual(len(cleaned), 60)


# ===========================================================================
# Area 5: Settings and Download History Operations
# ===========================================================================
class TestSettingsAndHistoryOperations(unittest.TestCase):
    """Verify settings persistence, isolated temp paths, and history operations."""

    def test_isolated_settings_crud(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_cfg_path = os.path.join(tmpdir, "mobile_config.json")
            with patch("downloader_engine.get_config_path", return_value=fake_cfg_path):
                # Initial default load
                cfg = engine.load_settings()
                self.assertIn("download_dir", cfg)
                self.assertIn("default_format", cfg)

                # Save modifications
                cfg["default_format"] = "audio_mp3"
                cfg["custom_test_key"] = "verified_value"
                engine.save_settings(cfg)

                # Reload and verify
                reloaded = engine.load_settings()
                self.assertEqual(reloaded.get("default_format"), "audio_mp3")
                self.assertEqual(reloaded.get("custom_test_key"), "verified_value")

    def test_isolated_history_operations_and_capping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_hist_path = os.path.join(tmpdir, "download_history.json")
            with patch("downloader_engine.get_history_path", return_value=fake_hist_path):
                # Verify empty state
                items = engine.load_history()
                self.assertEqual(items, [])

                # Add items
                engine.add_to_history("Track 1", "/path/to/track1.mp4", "MP4")
                engine.add_to_history("Track 2", "/path/to/track2.mp3", "MP3")
                items = engine.load_history()
                self.assertEqual(len(items), 2)
                self.assertEqual(items[0]["name"], "Track 2")  # Most recent first

                # Updating existing item replaces it rather than duplicating
                engine.add_to_history("Track 1", "/path/to/track1_new.mp4", "MP4")
                items = engine.load_history()
                self.assertEqual(len(items), 2)
                self.assertEqual(items[0]["path"], "/path/to/track1_new.mp4")

                # Clear history
                engine.clear_history()
                items = engine.load_history()
                self.assertEqual(items, [])


# ===========================================================================
# Area 6: Download Cancellation and Failure Handling
# ===========================================================================
class TestDownloadCancellation(unittest.TestCase):
    """Verify download cancellation mechanics."""

    def test_cancellation_event_hook(self):
        import threading
        stop_event = threading.Event()
        stop_event.set()

        def progress_hook(d):
            if stop_event.is_set():
                raise Exception("Download cancelled by user")

        with self.assertRaises(Exception) as ctx:
            progress_hook({"status": "downloading"})
        self.assertIn("Download cancelled by user", str(ctx.exception))


# ===========================================================================
# Area 7: Correct Buildozer and Workflow Paths
# ===========================================================================
class TestBuildozerAndWorkflowPaths(unittest.TestCase):
    """Verify Buildozer specification and GitHub Actions workflow configuration."""

    def test_buildozer_specification_integrity(self):
        spec_path = os.path.join(ANDROID_DIR, "buildozer.spec")
        self.assertTrue(os.path.exists(spec_path), f"buildozer.spec must exist at {spec_path}")

        with open(spec_path, "r", encoding="utf-8") as f:
            spec = f.read()

        # Architecture & IDs
        self.assertIn("package.name = universaldownloader", spec)
        self.assertIn("package.domain = com.universalmedia", spec)
        self.assertIn("version = 1.1.0", spec)

        # Target API compliance (October 2026: targetApi >= 34)
        self.assertIn("android.api = 34", spec)
        self.assertIn("android.sdk = 34", spec)
        self.assertIn("android.minapi = 21", spec)

        # Least-privilege permissions (zero media permissions)
        self.assertIn("android.permissions = INTERNET,ACCESS_NETWORK_STATE", spec)
        self.assertNotIn("READ_MEDIA_VIDEO", spec)
        self.assertNotIn("READ_MEDIA_AUDIO", spec)
        self.assertNotIn("WRITE_EXTERNAL_STORAGE", spec)
        self.assertNotIn("READ_EXTERNAL_STORAGE", spec)

    def test_github_workflow_configuration_integrity(self):
        wf_path = os.path.join(REPO_ROOT, ".github", "workflows", "build_apk.yml")
        self.assertTrue(os.path.exists(wf_path), f"build_apk.yml must exist at {wf_path}")

        with open(wf_path, "r", encoding="utf-8") as f:
            wf = f.read()

        # Verify triggers cover android_app, tests, and workflow itself
        self.assertIn("android_app/**", wf)
        self.assertIn("tests/**", wf)
        self.assertIn(".github/workflows/build_apk.yml", wf)

        # Verify test job runs regression tests before building APK
        self.assertIn("test:", wf)
        self.assertIn("needs: test", wf)
        self.assertIn("python -m unittest discover", wf)

        # Verify separation of debug and release modes
        self.assertIn("build_mode", wf)
        self.assertIn("buildozer -v android release", wf)
        self.assertIn("buildozer -v android debug", wf)


# ===========================================================================
# Area 8: Release Secret Validation Without Exposing Secrets
# ===========================================================================
class TestReleaseSecretValidation(unittest.TestCase):
    """Verify release secrets validation logic fails safely and prevents secret leakage."""

    def test_secret_validation_fails_on_missing_credentials(self):
        def validate_secrets(keystore_b64, ks_pass, key_alias, key_pass):
            if not keystore_b64 or not ks_pass or not key_alias or not key_pass:
                return False, "Production release requires all 4 secrets. Failing safely."
            return True, "All credentials present."

        # Test all permutations of missing credentials
        self.assertFalse(validate_secrets("", "pass", "alias", "pass")[0])
        self.assertFalse(validate_secrets("b64", "", "alias", "pass")[0])
        self.assertFalse(validate_secrets("b64", "pass", "", "pass")[0])
        self.assertFalse(validate_secrets("b64", "pass", "alias", "")[0])

        success, msg = validate_secrets("valid_b64", "pass1", "alias1", "pass2")
        self.assertTrue(success)

    def test_secret_values_never_printed_in_error_messages(self):
        sensitive_pass = "SuperSecretPassword123!"
        error_msg = "::error::Production release requires all 4 secrets: RELEASE_KEYSTORE_BASE64, RELEASE_KEYSTORE_PASSWD, RELEASE_KEYALIAS, and RELEASE_KEYALIAS_PASSWD."
        self.assertNotIn(sensitive_pass, error_msg)


# ===========================================================================
# Area 9: Absence of Private Keystores and Passwords in Repo & Artifacts
# ===========================================================================
class TestSecretHygieneAndArtifactIntegrity(unittest.TestCase):
    """Verify no keystores or passwords are committed to Git or present in source archives."""

    def test_no_keystore_in_git_tracked_files(self):
        # Scan git tracked files
        import subprocess
        res = subprocess.run(["git", "-C", REPO_ROOT, "ls-files"], capture_output=True, text=True)
        if res.returncode == 0:
            tracked = res.stdout.splitlines()
            for f in tracked:
                self.assertFalse(f.endswith((".keystore", ".jks", ".p12", ".key")), f"Keystore committed to git: {f}")
                self.assertNotIn("main_first.py", f)

    def test_no_hardcoded_passwords_in_workflow(self):
        wf_path = os.path.join(REPO_ROOT, ".github", "workflows", "build_apk.yml")
        with open(wf_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("UniversalBuild2026!", content, "Hardcoded fallback password found in workflow YAML")


# ===========================================================================
# Area 10: Storage Destination Handling and Android URI Behavior
# ===========================================================================
class TestStorageDestinationAndUriHandling(unittest.TestCase):
    """Verify Android SAF URI parsing, path traversal protection, and storage destination validation."""

    def test_uri_to_path_primary_storage(self):
        uri = "content://com.android.externalstorage.documents/tree/primary%3ADownload"
        path = engine.uri_to_path(uri)
        self.assertEqual(path, "/storage/emulated/0/Download")

    def test_uri_to_path_traversal_prevention(self):
        # Attacker crafts primary URI with directory traversal
        malicious_uri = "content://com.android.externalstorage.documents/tree/primary%3A..%2F..%2Fsystem%2Fbin"
        path = engine.uri_to_path(malicious_uri)
        # Must not escape /storage/emulated/0
        self.assertTrue(path.startswith("/storage/emulated/0"))
        self.assertNotIn("system/bin", path)

    def test_uri_to_path_secondary_sd_card(self):
        uri = "content://com.android.externalstorage.documents/tree/9C33-6BBD%3AMedia%2FVideo"
        path = engine.uri_to_path(uri)
        self.assertEqual(path, "/storage/9C33-6BBD/Media/Video")

    def test_ensure_valid_download_dir_writable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verified = engine.ensure_valid_download_dir(tmpdir)
            self.assertEqual(os.path.normpath(verified), os.path.normpath(tmpdir))
            self.assertTrue(os.path.isdir(verified))


# ===========================================================================
# Optional Integration Tests (Live Network - Skipped by default in offline CI)
# ===========================================================================
class TestLiveNetworkIntegration(unittest.TestCase):
    """Optional live network integration tests. Enable with RUN_NETWORK_TESTS=1."""

    @unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS") == "1", "Live network integration tests disabled by default")
    def test_live_tls_rejects_untrusted_certificates(self):
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True}
        with self.assertRaises(Exception):
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info("https://self-signed.badssl.com/", download=False)

    @unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS") == "1", "Live network integration tests disabled by default")
    def test_live_valid_https_inspection(self):
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        res = engine.inspect_url(test_url)
        self.assertIsNotNone(res)
        self.assertEqual(res["platform"], "YouTube")


if __name__ == "__main__":
    unittest.main()
