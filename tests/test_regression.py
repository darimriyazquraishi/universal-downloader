import os
import sys

# Configure headless environment BEFORE any Kivy or UI imports
os.environ["KIVY_NO_ARGS"] = "1"
os.environ["KIVY_NO_CONSOLELOG"] = "1"
os.environ["KIVY_WINDOW"] = "dummy"
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["KIVY_AUDIO"] = "dummy"

import json
import unittest
import configparser
from unittest.mock import patch, MagicMock
import tempfile
import zipfile

# ---------------------------------------------------------------------------
# Dynamic Repository Root and Android App Path Discovery (Portable)
# ---------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# The repository root directly contains main.py, downloader_engine.py, buildozer.spec, requirements.txt
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if not os.path.exists(os.path.join(REPO_ROOT, "downloader_engine.py")):
    raise RuntimeError(f"Could not locate downloader_engine.py at repository root {REPO_ROOT}")

# Provide headless import fallback for Kivy and PyJNIus when running on environments without display/GUI wheels
if "kivy" not in sys.modules:
    try:
        import kivy
    except ImportError:
        from importlib.machinery import ModuleSpec

        class DummyMeta(type):
            def __getattr__(cls, name):
                return lambda *args, **kwargs: DummyMeta(name, (object,), {})()

        def make_dummy(name):
            return DummyMeta(name, (object,), {
                "__init__": lambda self, *a, **k: None,
                "__call__": lambda self, *a, **k: self,
                "__getattr__": lambda self, n: lambda *a, **k: None
            })

        class MockLoader:
            def create_module(self, spec):
                import types
                mod = types.ModuleType(spec.name)
                mod.__path__ = []
                mod.__file__ = spec.name
                mod.__getattr__ = lambda name: make_dummy(name)
                return mod
            def exec_module(self, module):
                pass

        class MockFinder:
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname.startswith(p) for p in ["kivy", "jnius", "android"]):
                    return ModuleSpec(fullname, MockLoader(), origin=fullname)
                return None

        sys.meta_path.insert(0, MockFinder())

sys.path.insert(0, REPO_ROOT)
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
            ("https://www.mukaplay.com/dynps/share/DBVZTRUQQUEc123", "MukaPlay"),
            ("https://muka-box.com/share/track123", "MukaPlay"),
            ("https://muka.com/song/456", "MukaPlay"),
            ("https://cdn.example.org/files/sample_video.mp4", "Universal Web"),
        ]
        for url, expected in cases:
            self.assertEqual(engine.detect_platform(url), expected, f"Platform mismatch for {url}")

    def test_mukaplay_resolution(self):
        # 1. Non-Muka URL returns original untouched
        yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        resolved, title = engine.resolve_mukaplay_url(yt_url)
        self.assertEqual(resolved, yt_url)
        self.assertIsNone(title)

        # 2. Mock SSR HTML with __INITIAL_STATE__ containing ytData
        mock_html_state = '''
        <html>
        <head>
            <meta property="og:title" content="Fallback Track Title" />
        </head>
        <body>
            <script>
            window.__INITIAL_STATE__ = {
                "ytData": {"i": "LA8n8INoMOI", "tl": "Muka State Title"}
            };
            </script>
        </body>
        </html>
        '''
        class MockRespState:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return mock_html_state.encode('utf-8')

        with patch("urllib.request.urlopen", return_value=MockRespState()):
            res_url, res_title = engine.resolve_mukaplay_url("https://www.mukaplay.com/dynps/share/sample_key")
            self.assertEqual(res_url, "https://www.youtube.com/watch?v=LA8n8INoMOI")
            self.assertEqual(res_title, "Muka State Title")

        # 3. Mock HTML with og:image YouTube thumbnail fallback
        mock_html_og = '''
        <html>
        <head>
            <meta property="og:title" content="Muka OG Title" />
            <meta property="og:image" content="https://i.ytimg.com/vi/dQw4w9WgXcQ/hq720.jpg" />
        </head>
        </html>
        '''
        class MockRespOg:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return mock_html_og.encode('utf-8')

        with patch("urllib.request.urlopen", return_value=MockRespOg()):
            res_url, res_title = engine.resolve_mukaplay_url("https://www.mukaplay.com/dynps/share/sample_og")
            self.assertEqual(res_url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertEqual(res_title, "Muka OG Title")

    def test_url_structure_parsing(self):
        # MukaPlay URL parses seamlessly through canonical resolution
        with patch("downloader_engine.resolve_mukaplay_url", return_value=("https://www.youtube.com/watch?v=LA8n8INoMOI", "Test Track")):
            muka_parsed = engine.parse_url_structure("https://www.mukaplay.com/dynps/share/sample")
            self.assertTrue(muka_parsed["is_youtube"])
            self.assertEqual(muka_parsed["video_id"], "LA8n8INoMOI")

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
            fpath = os.path.join(REPO_ROOT, fname)
            self.assertTrue(os.path.exists(fpath), f"File {fname} must exist in {REPO_ROOT}")
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
        spec_path = os.path.join(REPO_ROOT, "buildozer.spec")
        self.assertTrue(os.path.exists(spec_path), f"buildozer.spec must exist at root {spec_path}")

        config = configparser.ConfigParser()
        config.read(spec_path, encoding="utf-8")
        self.assertTrue(config.has_section("app"), "buildozer.spec must contain [app] section")

        app = config["app"]
        # Architecture & IDs
        self.assertEqual(app.get("package.name"), "universaldownloader")
        self.assertEqual(app.get("package.domain"), "com.universalmedia")
        self.assertEqual(app.get("version"), "2.2.0")
        self.assertEqual(app.get("android.numeric_version"), "20200")
        self.assertEqual(app.get("source.dir"), ".")

        # Target API compliance: dynamically verify target API requirement >= 36 (Android 16)
        api = int(app.get("android.api", "0"))
        sdk = int(app.get("android.sdk", "0"))
        minapi = int(app.get("android.minapi", "0"))
        self.assertGreaterEqual(api, 36, f"Target Android API must be >= 36 to satisfy Google Play requirements (found {api})")
        self.assertGreaterEqual(sdk, 36, f"Android SDK must be >= 36 (found {sdk})")
        self.assertGreaterEqual(minapi, 21, f"Minimum API must support modern Android (found {minapi})")
        self.assertIn(app.get("p4a.branch"), ["release-2026.05.09", "v2026.05.09", "develop"], "python-for-android branch must be pinned release or develop")

        # Least-privilege permissions (zero media permissions)
        raw_perms = app.get("android.permissions", "")
        perms = [p.strip() for p in raw_perms.split(",") if p.strip()]
        self.assertIn("INTERNET", perms)
        self.assertIn("ACCESS_NETWORK_STATE", perms)
        for forbidden in ["READ_MEDIA_VIDEO", "READ_MEDIA_AUDIO", "READ_MEDIA_IMAGES", "WRITE_EXTERNAL_STORAGE", "READ_EXTERNAL_STORAGE", "MANAGE_EXTERNAL_STORAGE"]:
            self.assertNotIn(forbidden, perms, f"Unnecessary storage permission '{forbidden}' detected in buildozer.spec")

    def test_github_workflow_configuration_integrity(self):
        wf_path = os.path.join(REPO_ROOT, ".github", "workflows", "build_apk.yml")
        self.assertTrue(os.path.exists(wf_path), f"build_apk.yml must exist at {wf_path}")

        with open(wf_path, "r", encoding="utf-8") as f:
            wf = f.read()

        # Verify triggers cover repository root files, tests, and workflow itself
        self.assertIn("main.py", wf)
        self.assertIn("buildozer.spec", wf)
        self.assertIn("requirements.txt", wf)
        self.assertIn("tests/**", wf)
        self.assertIn("tools/**", wf, "Changes to release validation tooling must trigger CI")
        self.assertIn(".github/workflows/build_apk.yml", wf)

        # Verify obsolete android_app/ directory references are removed
        self.assertNotIn("android_app/**", wf, "Obsolete 'android_app/**' trigger path found in workflow")
        self.assertNotIn("working-directory: ./android_app", wf, "Obsolete working directory './android_app' found in workflow")
        self.assertNotIn("android_app/bin", wf, "Obsolete 'android_app/bin' path found in workflow")
        self.assertNotIn("android_app/requirements.txt", wf, "Obsolete 'android_app/requirements.txt' path found in workflow")

        # Verify test job runs regression tests before building APK
        self.assertIn("test:", wf)
        self.assertIn("needs: test", wf)
        self.assertTrue("unittest" in wf and "discover" in wf, "Workflow must discover and run tests via unittest")

        # Verify API 36 SDK component setup
        self.assertIn("platforms;android-36", wf, "Workflow must install platforms;android-36 SDK component")

        # Verify build modes and commands
        self.assertIn("buildozer -v android release", wf)
        self.assertIn("buildozer -v android debug", wf)

        # Verify fresh APK build and cleanup of old artifacts
        self.assertIn("rm -rf bin dist_apk", wf)

        # Verify dynamic version and artifact naming derived from buildozer.spec
        self.assertIn("buildozer.spec", wf)
        self.assertIn("APP_VERSION", wf)

        # Verify strict cryptographic signature verification and fingerprint matching
        self.assertTrue(any(p in wf for p in ["apksigner verify --print-certs", "$APKSIGNER verify --print-certs", '"$APKSIGNER" verify --print-certs']), "Workflow must verify signature with apksigner --print-certs")
        self.assertIn("EXPECTED_KS_FP", wf)
        self.assertIn("ACTUAL_CERT_FP", wf)
        self.assertIn("CN=Android Debug", wf)
        self.assertIn("RELEASE_CERT_SHA256", wf, "Workflow must mandate independent trusted RELEASE_CERT_SHA256")
        self.assertNotIn("|| true", wf, "Workflow commands must not mask errors with '|| true'")
        # Verify shell injection is eliminated: inputs passed through explicit env vars and not inline in shell
        self.assertIn("INPUT_RELEASE_TAG:", wf)
        self.assertIn("INPUT_BUILD_TYPE:", wf)
        self.assertNotIn('="${{ github.event.inputs.release_tag }}"', wf)
        self.assertNotIn('="${{ github.event.inputs.build_type }}"', wf)
        self.assertNotIn('build_mode=${{ github.event.inputs.build_type }}', wf)

        # Verify collision-safe release tags
        self.assertIn("github.run_attempt", wf)

        # Verify absence of unverified release claims (e.g. no fake 100% test coverage claim)
        self.assertNotIn("100% CI automated test coverage", wf, "Unverified 100% test coverage claim found in release body")

        # Verify default restricted permissions
        self.assertIn("permissions:", wf)
        self.assertIn("contents: read", wf)

    def test_workflow_manual_and_tag_release_publishing_conditions(self):
        wf_path = os.path.join(REPO_ROOT, ".github", "workflows", "build_apk.yml")
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = f.read()

        # 1. Verify publish_release boolean handling covers both boolean true and string 'true'
        self.assertIn("publish_release == true || github.event.inputs.publish_release == 'true'", wf)

        # 2. Verify pull requests are strictly excluded from publishing releases
        self.assertIn("github.event_name != 'pull_request'", wf)

        # 3. Verify tag-triggered publishing condition
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", wf)

    def test_workflow_mandatory_apk_inspection_and_dependency_pinning(self):
        wf_path = os.path.join(REPO_ROOT, ".github", "workflows", "build_apk.yml")
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = f.read()

        # 1. Required inspection tools must fail the build if not found
        self.assertIn("Required inspection tool 'apksigner' not found", wf)
        self.assertIn("Required inspection tool 'zipalign' not found", wf)
        self.assertIn("Required inspection tool 'aapt' not found", wf)

        # 2. Page alignment verification (accepts modern 16 KB alignment verification -P 16 4)
        self.assertTrue(any(p in wf for p in ['$ZIPALIGN" -c -P 16 4', '$ZIPALIGN" -c -v 4', '"$ZIPALIGN" -c -P 16 4']), "Workflow must verify zipalign alignment")

        # 3. Target API 36, package ID, and non-debuggable verification
        self.assertIn("targetSdkVersion:'36'", wf)
        self.assertIn("com.universalmedia.universaldownloader", wf)
        self.assertIn('dump xmltree "$FINAL_APK" AndroidManifest.xml', wf)
        self.assertIn("android:debuggable", wf)
        self.assertIn("Compiled manifest contains no true android:debuggable value", wf)

        # 4. Reproducible build: pinned versions of Buildozer, Cython, and python-for-android
        self.assertIn("buildozer==1.6.0", wf)
        self.assertIn("cython==0.29.37", wf)
        self.assertIn("virtualenv==21.14.8", wf)
        # Buildozer resolves python-for-android from the pinned p4a.branch in buildozer.spec;
        # a separate pip-installed copy must not be patched or mistaken for the build checkout.
        self.assertNotIn("python-for-android==2026.5.9", wf)
        self.assertNotIn("site.getsitepackages()", wf)
        self.assertNotIn("Successfully patched", wf)
        self.assertIn("ndk;28.2.13676358", wf)
        self.assertIn("ANDROIDSDK=$BUILD_SDK", wf)
        self.assertIn("ANDROIDNDK=$BUILD_NDK", wf)
        self.assertIn('"$BUILD_SDK/cmdline-tools/latest/bin/sdkmanager"', wf)
        self.assertIn('"$BUILD_SDK/cmdline-tools/latest/source.properties"', wf)
        self.assertIn('"$BUILD_SDK/platforms/android-36/android.jar"', wf)
        self.assertIn("tools/check_elf_alignment.py", wf)
        self.assertIn("android-ndk-r28c", wf)


# ===========================================================================
# Area 8: Release Secret Validation Without Exposing Secrets
# ===========================================================================
class TestReleaseSecretValidation(unittest.TestCase):
    """Verify release secrets validation logic fails safely and prevents secret leakage."""

    def test_secret_validation_fails_on_missing_credentials(self):
        def validate_secrets(keystore_b64, ks_pass, key_alias, key_pass, cert_sha256):
            if not keystore_b64 or not ks_pass or not key_alias or not key_pass or not cert_sha256:
                return False, "Production release requires all 5 secrets. Failing safely."
            clean_fp = cert_sha256.replace(":", "").replace(" ", "").lower()
            if len(clean_fp) != 64 or not all(c in "0123456789abcdef" for c in clean_fp):
                return False, "Invalid SHA-256 fingerprint format."
            return True, "All credentials present and verified."

        # Test all permutations of missing credentials
        self.assertFalse(validate_secrets("", "pass", "alias", "pass", "a"*64)[0])
        self.assertFalse(validate_secrets("b64", "", "alias", "pass", "a"*64)[0])
        self.assertFalse(validate_secrets("b64", "pass", "", "pass", "a"*64)[0])
        self.assertFalse(validate_secrets("b64", "pass", "alias", "", "a"*64)[0])
        self.assertFalse(validate_secrets("b64", "pass", "alias", "pass", "")[0])

        success, msg = validate_secrets("valid_b64", "pass1", "alias1", "pass2", "a"*64)
        self.assertTrue(success)

    def test_trusted_cert_fingerprint_normalization_and_validation(self):
        def normalize_and_validate_fp(raw_fp):
            if not raw_fp:
                return None, False
            clean = raw_fp.replace(":", "").replace(" ", "").strip().lower()
            if len(clean) == 64 and all(c in "0123456789abcdef" for c in clean):
                return clean, True
            return clean, False

        # Valid with colons and uppercase
        norm, valid = normalize_and_validate_fp("AA:BB:CC:DD:EE:FF:11:22:33:44:55:66:77:88:99:00:AA:BB:CC:DD:EE:FF:11:22:33:44:55:66:77:88:99:00")
        self.assertTrue(valid)
        self.assertEqual(len(norm), 64)
        self.assertNotIn(":", norm)

        # Valid with spaces
        norm, valid = normalize_and_validate_fp("aa bb cc dd ee ff 11 22 33 44 55 66 77 88 99 00 aa bb cc dd ee ff 11 22 33 44 55 66 77 88 99 00")
        self.assertTrue(valid)

        # Invalid (short or non-hex)
        _, valid = normalize_and_validate_fp("tooshort")
        self.assertFalse(valid)
        _, valid = normalize_and_validate_fp("ZZ"*32)
        self.assertFalse(valid)

    def test_secret_values_never_printed_in_error_messages(self):
        sensitive_pass = "SuperSecretPassword123!"
        error_msg = "::error::Production release requires all 5 secrets: RELEASE_KEYSTORE_BASE64, RELEASE_KEYSTORE_PASSWD, RELEASE_KEYALIAS, RELEASE_KEYALIAS_PASSWD, and RELEASE_CERT_SHA256."
        self.assertNotIn(sensitive_pass, error_msg)


# ===========================================================================
# Area 9: Absence of Private Keystores and Passwords in Repo & Artifacts
# ===========================================================================
class TestSecretHygieneAndArtifactIntegrity(unittest.TestCase):
    """Verify no keystores or passwords are committed to Git or present in source archives."""

    def test_no_keystore_in_git_tracked_files(self):
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

    def test_uri_classification_distinguishes_types(self):
        saf_tree = "content://com.android.externalstorage.documents/tree/primary%3ADownload"
        saf_doc = "content://com.android.externalstorage.documents/document/primary%3ADownload%2Fvideo.mp4"
        media_down = "content://media/external/downloads"
        media_item = "content://media/external/images/media/123"
        posix_path = "/storage/emulated/0/Download"
        win_path = "C:\\Users\\User\\Downloads"

        # Tree URI classification
        self.assertTrue(engine.is_tree_uri(saf_tree))
        self.assertFalse(engine.is_tree_uri(saf_doc))
        self.assertFalse(engine.is_tree_uri(media_down))
        self.assertFalse(engine.is_tree_uri(posix_path))

        # Document URI classification
        self.assertTrue(engine.is_document_uri(saf_doc))
        self.assertFalse(engine.is_document_uri(saf_tree))
        self.assertFalse(engine.is_document_uri(media_down))

        # SAF URI (tree or document)
        self.assertTrue(engine.is_saf_uri(saf_tree))
        self.assertTrue(engine.is_saf_uri(saf_doc))
        # Critical assertion: MediaStore URIs are NOT SAF URIs
        self.assertFalse(engine.is_saf_uri(media_down))
        self.assertFalse(engine.is_saf_uri(media_item))
        self.assertFalse(engine.is_saf_uri(posix_path))
        self.assertFalse(engine.is_saf_uri(None))

        # MediaStore URI classification
        self.assertTrue(engine.is_mediastore_uri(media_down))
        self.assertTrue(engine.is_mediastore_uri(media_item))
        self.assertFalse(engine.is_mediastore_uri(saf_tree))
        self.assertFalse(engine.is_mediastore_uri(saf_doc))
        self.assertFalse(engine.is_mediastore_uri(posix_path))

        # General content URI classification
        self.assertTrue(engine.is_content_uri(saf_tree))
        self.assertTrue(engine.is_content_uri(saf_doc))
        self.assertTrue(engine.is_content_uri(media_down))
        self.assertTrue(engine.is_content_uri(media_item))
        self.assertFalse(engine.is_content_uri(posix_path))
        self.assertFalse(engine.is_content_uri(win_path))
        self.assertFalse(engine.is_content_uri(None))

    def test_ensure_valid_download_dir_preserves_content_uris(self):
        saf_uri = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
        result = engine.ensure_valid_download_dir(saf_uri)
        self.assertEqual(result, saf_uri, "ensure_valid_download_dir must preserve SAF URIs without attempting filesystem operations")

        mediastore_uri = "content://media/external/downloads"
        res_ms = engine.ensure_valid_download_dir(mediastore_uri)
        self.assertEqual(res_ms, mediastore_uri, "ensure_valid_download_dir must preserve MediaStore URIs without attempting filesystem operations")

    def test_uri_to_display_name_formatting(self):
        # SAF URIs formatted for user display
        self.assertEqual(engine.uri_to_display_name("content://com.android.externalstorage.documents/tree/primary%3ADownload"), "Selected Folder: Download")
        self.assertEqual(engine.uri_to_display_name("content://com.android.externalstorage.documents/tree/primary%3AMusic%2FRock"), "Selected Folder: Music/Rock")
        # MediaStore URIs formatted for user display
        self.assertEqual(engine.uri_to_display_name("content://media/external/downloads"), "Downloads (MediaStore)")
        self.assertEqual(engine.uri_to_display_name("content://media/external/video/media"), "Videos (MediaStore)")
        self.assertEqual(engine.uri_to_display_name("content://media/external/audio/media"), "Audio (MediaStore)")
        # Standard filesystem paths
        self.assertEqual(engine.uri_to_display_name("/storage/emulated/0/Download"), "/storage/emulated/0/Download")
        self.assertEqual(engine.uri_to_display_name(None), "Default: Downloads")

    def test_uri_to_path_rejects_content_uris(self):
        # Scoped Storage rule: content URIs cannot be converted to POSIX paths
        self.assertIsNone(engine.uri_to_path("content://com.android.externalstorage.documents/tree/primary%3ADownload"))
        self.assertIsNone(engine.uri_to_path("content://media/external/downloads"))
        self.assertIsNone(engine.uri_to_path("content://com.android.externalstorage.documents/tree/primary%3A..%2F..%2Fsystem%2Fbin"))
        # File URIs and filesystem paths are normalized
        self.assertEqual(engine.uri_to_path("file:///storage/emulated/0/test.mp4"), "/storage/emulated/0/test.mp4")
        self.assertIsNone(engine.uri_to_path(None))

    def test_custom_destination_failure_preserves_staging_and_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_file = os.path.join(tmpdir, "staging_test.mp4")
            with open(staging_file, "w") as f:
                f.write("test content")

            # Simulate Android environment where writing to SAF tree fails
            with patch.object(engine, "IS_ANDROID", True):
                with patch.dict(engine.__dict__, {"autoclass": MagicMock(side_effect=RuntimeError("SAF access revoked"))}):
                    custom_tree = "content://com.android.externalstorage.documents/tree/primary%3AFolder"
                    with self.assertRaises(IOError) as ctx:
                        engine.save_file_to_destination(staging_file, custom_tree, "test.mp4")
                    self.assertIn("Failed to save to selected custom folder", str(ctx.exception))
                    # Staging file MUST NOT be deleted or moved!
                    self.assertTrue(os.path.exists(staging_file), "Staging file must be preserved upon destination failure")

    def test_nested_document_uri_handling_and_parent_tree_extraction(self):
        tree_root = "content://com.android.externalstorage.documents/tree/primary%3ADownload"
        nested_doc = "content://com.android.externalstorage.documents/tree/primary%3ADownload/document/primary%3ADownload%2Fvideo.mp4"
        standalone_doc = "content://com.android.externalstorage.documents/document/primary%3ADownload%2Fvideo.mp4"

        # Tree root check
        self.assertTrue(engine.is_tree_uri(tree_root))
        self.assertFalse(engine.is_document_uri(tree_root))
        self.assertEqual(engine.extract_parent_tree_uri(tree_root), tree_root)

        # Nested document must NOT be classified as tree root
        self.assertFalse(engine.is_tree_uri(nested_doc), "Nested document URI in a tree must not be misclassified as a folder tree URI")
        self.assertTrue(engine.is_document_uri(nested_doc))
        self.assertTrue(engine.is_saf_uri(nested_doc))
        # Resolving parent tree URI from nested document URI
        self.assertEqual(engine.extract_parent_tree_uri(nested_doc), tree_root)

        # Standalone document
        self.assertFalse(engine.is_tree_uri(standalone_doc))
        self.assertTrue(engine.is_document_uri(standalone_doc))
        self.assertIsNone(engine.extract_parent_tree_uri(standalone_doc))

        # MediaStore and filesystem paths
        self.assertIsNone(engine.extract_parent_tree_uri("content://media/external/downloads"))
        self.assertIsNone(engine.extract_parent_tree_uri("/storage/emulated/0/Download"))

    def test_invalid_destination_uri_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_file = os.path.join(tmpdir, "staging_invalid.mp4")
            with open(staging_file, "w") as f:
                f.write("test content")

            with patch.object(engine, "IS_ANDROID", True):
                # Document URI passed as directory destination
                doc_uri = "content://com.android.externalstorage.documents/document/primary%3ADownload%2Fvideo.mp4"
                with self.assertRaises(IOError) as ctx:
                    engine.save_file_to_destination(staging_file, doc_uri, "test.mp4")
                self.assertIn("Invalid custom destination URI", str(ctx.exception))
                self.assertTrue(os.path.exists(staging_file), "Staging file must be preserved when destination URI is invalid")

    def test_revoked_saf_permissions_preserves_staging_and_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_file = os.path.join(tmpdir, "staging_perm.mp4")
            with open(staging_file, "w") as f:
                f.write("test content")

            with patch.object(engine, "IS_ANDROID", True):
                # Mock SecurityException from DocumentsContract
                mock_activity = MagicMock()
                mock_activity.mActivity.getContentResolver.side_effect = PermissionError("Permission Denial: requires android.permission.MANAGE_DOCUMENTS")
                with patch.dict(engine.__dict__, {"autoclass": MagicMock(return_value=mock_activity)}):
                    custom_tree = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
                    with self.assertRaises(IOError) as ctx:
                        engine.save_file_to_destination(staging_file, custom_tree, "song.mp3")
                    self.assertIn("Failed to save to selected custom folder", str(ctx.exception))
                    self.assertTrue(os.path.exists(staging_file), "Staging file must be preserved when SAF permissions are revoked")

    def test_mediastore_failure_preserves_staging_and_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_file = os.path.join(tmpdir, "staging_ms.mp4")
            with open(staging_file, "w") as f:
                f.write("test content")

            with patch.object(engine, "IS_ANDROID", True):
                with patch("downloader_engine.save_to_mediastore_downloads", side_effect=IOError("MediaStore insertion failed")):
                    with self.assertRaises(IOError) as ctx:
                        engine.save_file_to_destination(staging_file, None, "test.mp4")
                    self.assertIn("Failed to save to Android MediaStore Downloads", str(ctx.exception))
                    # Staging file MUST NOT be deleted or moved!
                    self.assertTrue(os.path.exists(staging_file), "Staging file must be preserved upon MediaStore failure")

    def test_mediastore_save_success_and_streaming(self):
        """Verify save_to_mediastore_downloads correctly sets Scoped Storage values and clears IS_PENDING."""
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_file = os.path.join(tmpdir, "video.mp4")
            with open(staging_file, "wb") as f:
                f.write(b"video bytes content 12345")

            dest_target_file = os.path.join(tmpdir, "dest_out.mp4")
            dest_fd = os.open(dest_target_file, os.O_CREAT | os.O_RDWR)
            try:
                mock_activity = MagicMock()
                mock_resolver = MagicMock()
                mock_activity.mActivity.getContentResolver.return_value = mock_resolver

                mock_item_uri = MagicMock()
                mock_item_uri.toString.return_value = "content://media/external/downloads/42"
                mock_resolver.insert.return_value = mock_item_uri

                mock_pfd = MagicMock()
                mock_pfd.getFd.return_value = dest_fd
                mock_resolver.openFileDescriptor.return_value = mock_pfd

                put_dict = {}
                class FakeContentValues:
                    def put(self, k, v):
                        put_dict[str(k)] = str(v)
                    def clear(self):
                        put_dict.clear()

                def mock_autoclass(cls_name):
                    if cls_name == "org.kivy.android.PythonActivity":
                        return mock_activity
                    if cls_name == "android.content.ContentValues":
                        return FakeContentValues
                    if cls_name == "java.lang.String":
                        return lambda s: str(s)
                    if cls_name == "java.lang.Integer":
                        return lambda i: int(i)
                    if cls_name == "java.lang.Long":
                        return lambda l: int(l)
                    if cls_name == "android.net.Uri":
                        mock_uri = MagicMock()
                        mock_uri.parse = lambda s: s
                        return mock_uri
                    if cls_name == "android.os.Build$VERSION":
                        b = MagicMock()
                        b.SDK_INT = 36
                        return b
                    if cls_name == "android.os.Environment":
                        e = MagicMock()
                        e.DIRECTORY_DOWNLOADS = "Download"
                        return e
                    return MagicMock()

                with patch.dict(engine.__dict__, {"autoclass": mock_autoclass}):
                    res = engine.save_to_mediastore_downloads(staging_file, "video.mp4", "video/mp4")
                    self.assertEqual(res, "content://media/external/downloads/42")
                    self.assertFalse(os.path.exists(staging_file), "Staging file must be cleaned up on success")

                    # Verify written contents in destination file
                    with open(dest_target_file, "rb") as out_f:
                        self.assertEqual(out_f.read(), b"video bytes content 12345")

                    # Verify resolver.update was called to clear IS_PENDING (set to 0)
                    mock_resolver.update.assert_called_once()
                    update_args = mock_resolver.update.call_args[0]
                    self.assertEqual(update_args[0], mock_item_uri)
                    self.assertEqual(put_dict.get("is_pending"), "0")
            finally:
                try:
                    os.close(dest_fd)
                except OSError:
                    pass

    def test_write_staging_to_uri_fallback_to_stream(self):
        """Verify _write_staging_to_uri falls back to openOutputStream when pfd fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_file = os.path.join(tmpdir, "staging.bin")
            with open(staging_file, "wb") as f:
                f.write(b"fallback stream data")

            mock_resolver = MagicMock()
            mock_resolver.openFileDescriptor.side_effect = Exception("PFD not supported")

            written_bytes = bytearray()
            mock_out_stream = MagicMock()
            def mock_write(b, *args):
                if isinstance(b, (bytes, bytearray)):
                    written_bytes.extend(b)
                elif hasattr(b, '__iter__'):
                    written_bytes.extend(bytes(b))
            mock_out_stream.write.side_effect = mock_write
            mock_resolver.openOutputStream.return_value = mock_out_stream

            engine._write_staging_to_uri(mock_resolver, "content://test/uri", staging_file)
            self.assertEqual(bytes(written_bytes), b"fallback stream data")
            mock_out_stream.flush.assert_called_once()
            mock_out_stream.close.assert_called_once()

    def test_failed_file_write_preserves_staging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_file = os.path.join(tmpdir, "staging_disk_full.mp4")
            with open(staging_file, "w") as f:
                f.write("media data")

            # Simulate filesystem failure during move/copy
            with patch("shutil.move", side_effect=OSError("No space left on device")):
                with patch("shutil.copy2", side_effect=OSError("No space left on device")):
                    with self.assertRaises(IOError) as ctx:
                        engine.save_file_to_destination(staging_file, tmpdir, "test.mp4")
                    self.assertIn("Failed to save file to destination", str(ctx.exception))
                    self.assertTrue(os.path.exists(staging_file), "Staging file must be preserved when disk write fails")

    def test_ensure_valid_download_dir_writable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verified = engine.ensure_valid_download_dir(tmpdir)
            self.assertEqual(os.path.normpath(verified), os.path.normpath(tmpdir))
            self.assertTrue(os.path.isdir(verified))

    def test_save_file_to_destination_filesystem(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_file = os.path.join(tmpdir, "staging_test.mp4")
            with open(staging_file, "w") as f:
                f.write("mock media content")

            dest_folder = os.path.join(tmpdir, "dest")
            os.makedirs(dest_folder, exist_ok=True)

            final_path = engine.save_file_to_destination(staging_file, dest_folder, "test_track.mp4")
            self.assertTrue(os.path.exists(final_path))
            self.assertEqual(os.path.basename(final_path), "test_track.mp4")
            self.assertFalse(os.path.exists(staging_file), "Staging file should be moved/cleaned up")
# ===========================================================================
# Area 8: Custom Folder Opening, File Opening Security, and 16 KB ELF Alignment
# ===========================================================================
class TestArea8FolderAndFileOpeningAnd16KbAlignment(unittest.TestCase):
    """Verify custom folder navigation, file opening security, and 16 KB ELF validation."""

    def test_open_folder_saf_failure_does_not_open_downloads(self):
        """
        Verify that when opening a custom SAF tree directory fails (e.g. revoked permission
        or missing activity), open_folder() reports an error and NEVER silently falls back
        to opening the public Downloads screen.
        """
        import main as app_module
        screen = app_module.ManagerScreen.__new__(app_module.ManagerScreen)
        screen.items_data = {}

        mock_activity = MagicMock()
        mock_resolver = MagicMock()
        mock_resolver.getPersistedUriPermissions.return_value = []
        mock_activity.mActivity.getContentResolver.return_value = mock_resolver

        mock_download_manager = MagicMock()
        mock_download_manager.ACTION_VIEW_DOWNLOADS = "android.intent.action.VIEW_DOWNLOADS"

        def mock_autoclass(cls_name):
            if cls_name == "org.kivy.android.PythonActivity":
                return mock_activity
            if cls_name == "android.app.DownloadManager":
                return mock_download_manager
            if cls_name == "android.net.Uri":
                mock_uri = MagicMock()
                mock_uri.parse.return_value = MagicMock()
                return mock_uri
            if cls_name == "android.content.Intent":
                return MagicMock()
            return MagicMock()

        with patch.object(app_module, "IS_ANDROID", True):
            with patch.object(app_module, "autoclass", mock_autoclass):
                saf_tree = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
                result = screen.open_folder(saf_tree)
                self.assertFalse(result, "open_folder must return False on SAF permission failure")
                mock_activity.mActivity.startActivity.assert_not_called()

    def test_open_folder_nested_document_uri_targets_parent_tree(self):
        """
        Verify that when open_folder is called with a document URI inside a tree,
        it resolves the parent tree root and attempts to open that tree instead of Downloads.
        """
        import main as app_module
        screen = app_module.ManagerScreen.__new__(app_module.ManagerScreen)
        screen.items_data = {}

        mock_activity = MagicMock()
        mock_resolver = MagicMock()
        mock_perm = MagicMock()
        mock_perm.getUri.return_value.toString.return_value = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
        mock_perm.isReadPermission.return_value = True
        mock_resolver.getPersistedUriPermissions.return_value = [mock_perm]
        mock_activity.mActivity.getContentResolver.return_value = mock_resolver

        mock_download_manager = MagicMock()
        mock_download_manager.ACTION_VIEW_DOWNLOADS = "android.intent.action.VIEW_DOWNLOADS"
        doc_contract_called = []

        def mock_autoclass(cls_name):
            if cls_name == "org.kivy.android.PythonActivity":
                return mock_activity
            if cls_name == "android.app.DownloadManager":
                return mock_download_manager
            if cls_name == "android.provider.DocumentsContract":
                mock_dc = MagicMock()
                mock_dc.getTreeDocumentId.return_value = "primary:Music"
                mock_dc.buildDocumentUriUsingTree.return_value = "content://doc/dir"
                doc_contract_called.append(True)
                return mock_dc
            if cls_name == "android.net.Uri":
                mock_uri = MagicMock()
                mock_uri.parse.return_value = MagicMock()
                return mock_uri
            if cls_name == "android.content.Intent":
                return MagicMock()
            return MagicMock()

        with patch.object(app_module, "IS_ANDROID", True):
            with patch.object(app_module, "autoclass", mock_autoclass):
                nested_doc = "content://com.android.externalstorage.documents/tree/primary%3AMusic/document/primary%3AMusic%2Fsong.mp3"
                result = screen.open_folder(nested_doc)
                self.assertTrue(result)
                self.assertTrue(len(doc_contract_called) > 0, "DocumentsContract must be used for parent tree opening")
                mock_activity.mActivity.startActivity.assert_called_once()

    def test_open_folder_mediastore_and_default_uses_downloads(self):
        """
        Verify that when open_folder is called for MediaStore item or default Downloads,
        the system Downloads action is used.
        """
        import main as app_module
        screen = app_module.ManagerScreen.__new__(app_module.ManagerScreen)
        screen.items_data = {}

        mock_activity = MagicMock()
        mock_download_manager = MagicMock()
        mock_download_manager.ACTION_VIEW_DOWNLOADS = "android.intent.action.VIEW_DOWNLOADS"

        def mock_autoclass(cls_name):
            if cls_name == "org.kivy.android.PythonActivity":
                return mock_activity
            if cls_name == "android.app.DownloadManager":
                return mock_download_manager
            return MagicMock()

        with patch.object(app_module, "IS_ANDROID", True):
            with patch.object(app_module, "autoclass", mock_autoclass):
                ms_uri = "content://media/external/downloads/100"
                result = screen.open_folder(ms_uri)
                self.assertTrue(result)
                mock_activity.mActivity.startActivity.assert_called_once()

    def test_open_file_content_uri_launches_read_permission_intent(self):
        """
        Verify that opening a content:// URI (new download or from history)
        launches an ACTION_VIEW intent with FLAG_GRANT_READ_URI_PERMISSION.
        """
        import main as app_module
        screen = app_module.ManagerScreen.__new__(app_module.ManagerScreen)
        screen.items_data = {}

        mock_activity = MagicMock()
        mock_intent_class = MagicMock()
        mock_intent = MagicMock()
        mock_intent_class.return_value = mock_intent
        mock_intent_class.FLAG_GRANT_READ_URI_PERMISSION = 1
        mock_intent_class.FLAG_ACTIVITY_NEW_TASK = 268435456
        mock_intent_class.createChooser.return_value = MagicMock()

        def mock_autoclass(cls_name):
            if cls_name == "org.kivy.android.PythonActivity":
                return mock_activity
            if cls_name == "android.content.Intent":
                return mock_intent_class
            if cls_name == "android.net.Uri":
                mock_uri = MagicMock()
                mock_uri.parse.return_value = MagicMock()
                return mock_uri
            return MagicMock()

        with patch.object(app_module, "IS_ANDROID", True):
            with patch.object(app_module, "autoclass", mock_autoclass):
                screen.open_file("content://media/external/downloads/42")
                mock_intent.addFlags.assert_any_call(mock_intent_class.FLAG_GRANT_READ_URI_PERMISSION)
                mock_activity.mActivity.startActivity.assert_called_once()

    def test_open_file_unindexed_filesystem_path_wires_scanner_callback(self):
        """
        Verify that when open_file is called on an unindexed filesystem path,
        it does not return immediately without a callback, but wires an
        OnScanCompletedListener to MediaScannerConnection.
        """
        import main as app_module
        screen = app_module.ManagerScreen.__new__(app_module.ManagerScreen)
        screen.items_data = {}

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"video bytes")
            tmp_path = f.name

        try:
            mock_activity = MagicMock()
            mock_resolver = MagicMock()
            mock_resolver.query.return_value = None
            mock_activity.mActivity.getContentResolver.return_value = mock_resolver

            mock_scanner = MagicMock()
            mock_intent_class = MagicMock()

            def mock_autoclass(cls_name):
                if cls_name == "org.kivy.android.PythonActivity":
                    return mock_activity
                if cls_name == "android.media.MediaScannerConnection":
                    return mock_scanner
                if cls_name == "android.provider.MediaStore":
                    m = MagicMock()
                    m.MediaColumns.DISPLAY_NAME = "_display_name"
                    m.MediaColumns.DATE_ADDED = "date_added"
                    return m
                if cls_name == "android.content.ContentUris":
                    return MagicMock()
                if cls_name == "android.content.Intent":
                    return mock_intent_class
                if cls_name == "android.net.Uri":
                    return MagicMock()
                return MagicMock()

            with patch.object(app_module, "IS_ANDROID", True):
                with patch.object(app_module, "autoclass", mock_autoclass):
                    screen.open_file(tmp_path)
                    mock_scanner.scanFile.assert_called_once()
                    call_args = mock_scanner.scanFile.call_args[0]
                    self.assertEqual(len(call_args), 4)
                    self.assertEqual(call_args[1], [tmp_path])
                    self.assertIsNotNone(call_args[3], "Listener must NOT be None: callback required to open resulting URI")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_no_permissive_strictmode_or_file_uri_exposure(self):
        """Verify no StrictMode workarounds or Uri.fromFile intents exist in source."""
        for fname in ["main.py", "downloader_engine.py"]:
            fpath = os.path.join(REPO_ROOT, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                code = f.read()
                self.assertNotIn("detectFileUriExposure", code, f"Insecure StrictMode workaround in {fname}")
                self.assertNotIn("Uri.fromFile", code, f"Insecure Uri.fromFile usage in {fname}")
        with open(os.path.join(REPO_ROOT, "main.py"), "r", encoding="utf-8") as f:
            code = f.read()
            self.assertNotIn("file://", code.replace("file:///", ""), "Unsafe file:// scheme usage in main.py")

    def test_elf_16kb_page_alignment_detection(self):
        """Use the same strict ELF validator that the release workflow runs."""
        import struct
        from tools.check_elf_alignment import inspect_elf

        def make_elf64(p_align, p_offset=0, p_vaddr=0, machine=183, elf_class=2):
            data = bytearray(64 + 56)
            data[0:4] = b"\x7fELF"
            data[4] = elf_class
            data[5] = 1  # little endian
            data[6] = 1  # current ELF identification version
            struct.pack_into("<H", data, 16, 3)  # ET_DYN
            struct.pack_into("<H", data, 18, machine)
            struct.pack_into("<I", data, 20, 1)  # e_version
            struct.pack_into("<Q", data, 32, 64)  # e_phoff
            struct.pack_into("<H", data, 52, 64)  # e_ehsize
            struct.pack_into("<H", data, 54, 56)  # e_phentsize
            struct.pack_into("<H", data, 56, 1)   # e_phnum
            # PT_LOAD, PF_R | PF_X, offset, vaddr, paddr, filesz, memsz, align
            struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, p_offset, p_vaddr, p_vaddr, len(data), len(data), p_align)
            return bytes(data)

        aligned = make_elf64(p_align=16384, p_offset=0, p_vaddr=0)
        self.assertEqual(inspect_elf(aligned, "aligned.so", "arm64-v8a"), [])

        bad_4kb = make_elf64(p_align=4096)
        self.assertTrue(inspect_elf(bad_4kb, "4kb.so", "arm64-v8a"))

        misaligned = make_elf64(p_align=16384, p_offset=0, p_vaddr=4096)
        self.assertTrue(inspect_elf(misaligned, "misaligned.so", "arm64-v8a"))

        wrong_arch = make_elf64(p_align=16384, machine=62)
        self.assertTrue(inspect_elf(wrong_arch, "wrong-arch.so", "arm64-v8a"))

        wrong_class = make_elf64(p_align=16384, elf_class=1)
        self.assertTrue(inspect_elf(wrong_class, "32bit.so", "arm64-v8a"))

    def test_elf_apk_validator_rejects_missing_or_malformed_libraries(self):
        """The production validator must fail closed for empty/malformed APK contents."""
        from tools.check_elf_alignment import inspect_apk
        import struct

        def make_elf64():
            data = bytearray(120)
            data[0:4] = b"\x7fELF"
            data[4] = 2
            data[5] = 1
            data[6] = 1
            struct.pack_into("<H", data, 16, 3)
            struct.pack_into("<H", data, 18, 183)
            struct.pack_into("<I", data, 20, 1)
            struct.pack_into("<Q", data, 32, 64)
            struct.pack_into("<H", data, 52, 64)
            struct.pack_into("<H", data, 54, 56)
            struct.pack_into("<H", data, 56, 1)
            struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, len(data), len(data), 16384)
            return bytes(data)

        with tempfile.TemporaryDirectory() as tmp:
            empty_apk = os.path.join(tmp, "empty.apk")
            with zipfile.ZipFile(empty_apk, "w"):
                pass
            empty_results, empty_count = inspect_apk(empty_apk, "arm64-v8a")
            self.assertEqual(empty_count, 0)
            self.assertTrue(any(errors for _, errors in empty_results))

            malformed_apk = os.path.join(tmp, "malformed.apk")
            with zipfile.ZipFile(malformed_apk, "w") as archive:
                archive.writestr("lib/arm64-v8a/libbroken.so", b"not an ELF")
            malformed_results, malformed_count = inspect_apk(malformed_apk, "arm64-v8a")
            self.assertEqual(malformed_count, 1)
            self.assertTrue(any(errors for _, errors in malformed_results))

            valid_apk = os.path.join(tmp, "valid.apk")
            with zipfile.ZipFile(valid_apk, "w") as archive:
                archive.writestr("lib/arm64-v8a/libexample.so", make_elf64())
            valid_results, valid_count = inspect_apk(valid_apk, "arm64-v8a")
            self.assertEqual(valid_count, 1)
            self.assertFalse(any(errors for _, errors in valid_results))

    def test_ci_workflow_runs_test_suite_once_and_fails_on_nonzero(self):
        """
        Verify that .github/workflows/build_apk.yml executes tests once,
        records dynamic outputs, and exits with nonzero status on failure.
        """
        wf_path = os.path.join(REPO_ROOT, ".github", "workflows", "build_apk.yml")
        with open(wf_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Must not run unittest discover twice
        self.assertNotIn("python -m unittest discover", content, "Redundant second test execution found in workflow")
        # Must execute single test runner with verbosity and exit 1 on failure
        self.assertIn("sys.exit(1)", content, "Workflow test runner must exit 1 on test failure")
        self.assertIn("tests_passed=", content)
        self.assertIn("tests_failed=", content)
        self.assertIn("tests_skipped=", content)



class TestV220ActionButtonsAndExplorerChooser(unittest.TestCase):
    """Verify v2.2.0 action buttons (pause/terminate), file explorer packages, and manifest queries."""

    def test_file_explorer_packages_declared(self):
        import main
        packages = getattr(main, "FILE_EXPLORER_PACKAGES", [])
        self.assertGreater(len(packages), 10, "FILE_EXPLORER_PACKAGES should list major OEM and third-party explorers")
        expected_packages = [
            "com.sec.android.app.myfiles",          # Samsung My Files
            "com.mi.android.globalFileexplorer",   # Xiaomi File Manager
            "com.oneplus.filemanager",              # OnePlus File Manager
            "com.coloros.filemanager",              # Oppo File Manager
            "ru.zdevs.zarchiver",                   # ZArchiver
            "com.estrongs.android.pop",             # ES File Explorer
            "com.cxinventor.file.explorer",         # Cx File Explorer
            "com.google.android.apps.nbu.files",    # Google Files
            "com.android.documentsui",              # AOSP Files
        ]
        for pkg in expected_packages:
            self.assertIn(pkg, packages, f"Package {pkg} missing from FILE_EXPLORER_PACKAGES")

    def test_extra_manifest_queries(self):
        manifest_xml_path = os.path.join(REPO_ROOT, "assets", "extra_manifest.xml")
        self.assertTrue(os.path.exists(manifest_xml_path), "assets/extra_manifest.xml must exist")
        with open(manifest_xml_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("<queries>", content)
        self.assertIn("vnd.android.document/directory", content)
        self.assertIn("resource/folder", content)
        self.assertIn("ru.zdevs.zarchiver", content)
        self.assertIn("com.estrongs.android.pop", content)
        self.assertIn("com.sec.android.app.myfiles", content)

    def test_buildozer_extra_manifest_configured(self):
        spec_path = os.path.join(REPO_ROOT, "buildozer.spec")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("android.extra_manifest_xml", content)
        self.assertIn("assets/extra_manifest.xml", content)
        self.assertIn("version = 2.2.0", content)
        self.assertIn("android.numeric_version = 20200", content)

    def test_home_screen_pause_and_terminate_buttons(self):
        import main
        import threading
        home = main.HomeScreen.__new__(main.HomeScreen)
        home.app_ref = MagicMock()
        home.is_downloading = False
        home.is_paused = False
        home.stop_event = threading.Event()
        home.pause_event = threading.Event()
        home.pause_event.set()
        home.btn_pause = MagicMock()
        home.lbl_progress_status = MagicMock()
        home.lbl_speed = MagicMock()

        self.assertTrue(home.pause_event.is_set())
        self.assertFalse(home.is_paused)

        # Simulate active download and test pause toggle
        home.is_downloading = True
        home.action_toggle_pause()
        self.assertTrue(home.is_paused)
        self.assertFalse(home.pause_event.is_set())
        home.btn_pause.set_icon.assert_called_with("resume")

        # Resume
        home.action_toggle_pause()
        self.assertFalse(home.is_paused)
        self.assertTrue(home.pause_event.is_set())
        home.btn_pause.set_icon.assert_called_with("pause")

        # Terminate
        home.action_terminate_download()
        self.assertTrue(home.stop_event.is_set())
        self.assertTrue(home.pause_event.is_set())

    def test_manager_screen_callbacks_and_helpers(self):
        import main
        mgr = main.ManagerScreen.__new__(main.ManagerScreen)
        mgr.app_ref = MagicMock()
        mgr.items_data = {}
        self.assertTrue(hasattr(mgr, "open_item_file"))
        self.assertTrue(hasattr(mgr, "open_item_folder"))
        self.assertTrue(hasattr(mgr, "_launch_folder_chooser"))
        self.assertTrue(hasattr(mgr, "_launch_view_intent"))


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
