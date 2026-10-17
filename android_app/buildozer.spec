[app]

# (str) Title of your application
title = Universal Downloader

# (str) Package name
package.name = universaldownloader

# (str) Package domain (needed for android/ios packaging)
package.domain = com.universalmedia

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,ttf,json,xml

# (list) List of inclusions using pattern matching
source.include_patterns = assets/*,assets/fonts/*

# (list) List of directory to exclude (let empty to not exclude anything)
source.exclude_dirs = tests, bin, .buildozer, build, dist, static, .github, android_app, venv_android

# (list) List of exclusions using pattern matching
source.exclude_patterns = *.spec, *.exe, *.bat, gui_app.py, server.py, build_exe.py, requirements-desktop.txt, *.keystore, *.jks, *.p12, *.key

# (str) Icon of the application
icon.filename = %(source.dir)s/assets/icon.png

# (str) Presplash of the application
presplash.filename = %(source.dir)s/assets/icon.png

# (str) Application versioning
version = 2.0.0

# (int) Numeric version code
android.numeric_version = 20000

# (list) Application requirements
requirements = python3,kivy,openssl,yt-dlp,requests,certifi,mutagen,urllib3,charset-normalizer

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (list) Permissions (least-privilege: zero invasive media permissions)
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# (str) Format of artifact to build (apk, aab)
android.release_artifact = apk

# (bool) Automatically accept SDK license agreements
android.accept_sdk_license = True

# (int) Target Android API, aligned with Google Play requirements (API 35: Android 15)
android.api = 35

# (int) Minimum API your APK / AAB will support (Android 5.0 Lollipop)
android.minapi = 21

# (int) Android SDK version to use
android.sdk = 35

# (str) Android NDK version to use
android.ndk = 25b

# (int) Android NDK API to use
android.ndk_api = 21

# (bool) Use --private data storage (True) or --dir public storage (False)
android.private_storage = True

# (list) Android application meta-data to set (key=value format)
# Share intent filter for capturing shared links from social apps
android.manifest.intent_filters = assets/intent_filter.xml

# (bool) Copy library instead of making a libpymodules.so
android.copy_libs = 1

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug with command output)
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
