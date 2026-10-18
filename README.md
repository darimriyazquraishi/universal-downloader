# 📱 Universal Downloader for Android (v2.1.1)
High-performance, luxury-styled mobile media downloader for Android devices built with **Python**, **Kivy**, and **yt-dlp**.

---

## 🌟 Key Highlights
- **Target Android API 36 (Android 16)**: Built with modern SDK 36 and NDK 28c toolchain supporting genuine 16 KB ELF segment alignment conforming to Google Play submission requirements.
- **Universal Platform Support**: YouTube, Instagram Reels/Posts, TikTok, X (Twitter), Facebook, Reddit, Pinterest, SoundCloud, and Vimeo.
- **Strict TLS Security**: Complete TLS certificate validation using Mozilla CA bundles (via `certifi`). Insecure certificate bypasses are strictly disabled.
- **Scoped Storage & MediaStore**: Compliant Scoped Storage utilizing Android MediaStore and Storage Access Framework (SAF) without broad storage permissions (`MANAGE_EXTERNAL_STORAGE`).
- **High-Refresh Display Fluidity**: Unlocked frame loop rendering (`maxfps: 0`) delivering butter-smooth 90Hz / 120Hz / 144Hz animation on modern AMOLED displays.
- **Hardware-Accelerated 2D Rendering**: Nested rounded-rectangle vertex caching eliminating CPU bezier re-tessellation during fast scrolling.
- **Least-Privilege Permissions**: Clean Scoped Storage architecture declaring only `INTERNET` and `ACCESS_NETWORK_STATE` permissions. Zero invasive media library permissions (`READ_MEDIA_VIDEO`, `READ_MEDIA_AUDIO`).
- **App-Only Download Manager**: Tracks and manages only downloaded media with one-tap system player and file explorer integration.
- **Social Share Intent**: Select "Share" from YouTube, Instagram, or TikTok and pick Universal Downloader to inspect and download immediately.
- **Production Release Packaging**: Configured for clean `buildozer android release` builds with rigorous cryptographic signature verification.

---

## 📂 Project Structure
```text
UniversalDownloader_Android/
├── assets/
│   ├── fonts/
│   │   └── Sebino-Soft-Regular.ttf      # Custom font
│   ├── icon.png                         # App logo icon
│   ├── icon_gold.png                    # Brand vector logo
│   └── intent_filter.xml                # Android social media share menu hook
├── .github/
│   └── workflows/
│       └── build_apk.yml                # CI/CD automated cloud APK builder
├── tests/
│   └── test_regression.py               # Automated unit & integration regression tests
├── main.py                              # Mobile UI, gesture engine, 120 FPS render loop
├── downloader_engine.py                 # Media extraction, format logic & Scoped Storage
├── buildozer.spec                       # Buildozer release build specification
├── requirements.txt                     # Python dependencies
├── run_mobile_simulator.bat             # One-click Windows mobile viewport launcher
├── .gitignore                           # Excludes build outputs, keys, and cache
└── README.md                            # Documentation and build setup
```

---

## 💻 Running the Desktop Simulator
You can run and test the complete mobile interface on Windows, macOS, or Linux:

1. **Install Python 3.10 or 3.11**.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Launch the simulator**:
   ```bash
   python main.py
   # Or on Windows, double-click run_mobile_simulator.bat
   ```

---

## 🧪 Running Automated Tests
Run the test suite to verify security, URL parsing, TLS rejection, and format operations:
```bash
python -m unittest tests/test_regression.py
```

---

## 🔨 Building the Android APK

### Option A: Cloud Build with GitHub Actions (Recommended)
1. Push this project to your GitHub repository.
2. In your repository on GitHub, navigate to **Settings > Secrets and variables > Actions**.
3. Configure mandatory release signing secrets for production releases:
   - `RELEASE_KEYSTORE_BASE64`: Base64-encoded string of your `.keystore` file (`base64 -w 0 my-release-key.keystore`).
   - `RELEASE_KEYSTORE_PASSWD`: Keystore password.
   - `RELEASE_KEYALIAS`: Key alias.
   - `RELEASE_KEYALIAS_PASSWD`: Key alias password.
   - `RELEASE_CERT_SHA256`: Independent trusted SHA-256 certificate fingerprint (64 hex characters) matching the actual signing identity.
   *(All 5 secrets are mandatory for production releases. If omitted, the workflow builds a secure debug APK).*
4. Run the **Build Android APK** workflow in GitHub Actions.

### Option B: Local Build with Buildozer (Linux / WSL2 / macOS)
1. Generate your private release keystore (keep this file private and never commit it):
   ```bash
   keytool -genkeypair -v -keystore release.keystore -alias mykey -keyalg RSA -keysize 2048 -validity 10000 -storetype PKCS12
   ```
2. Export your signing environment variables:
   ```bash
   export P4A_RELEASE_KEYSTORE=release.keystore
   export P4A_RELEASE_KEYSTORE_PASSWD="YourPassword"
   export P4A_RELEASE_KEYALIAS="mykey"
   export P4A_RELEASE_KEYALIAS_PASSWD="YourPassword"
   ```
3. Build the signed release APK:
   ```bash
   buildozer -v android release
   ```
4. The generated APK will be placed in the `./bin/` folder.
