import os
import sys
import shutil
import subprocess

def build():
    # Kill any existing instance so files are not locked
    for exe_name in ["Universal_Downloader.exe", "UniversalDownloader.exe", "YouTube_Downloader.exe"]:
        try:
            subprocess.run(["taskkill", "/f", "/im", exe_name], capture_output=True)
        except Exception:
            pass

    app_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(app_dir, "dist")
    build_dir = os.path.join(app_dir, "build")
    ffmpeg_src = os.path.join(app_dir, "ffmpeg.exe")

    if not os.path.exists(ffmpeg_src):
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        shutil.copy2(ffmpeg_bin, ffmpeg_src)
        print(f"Copied FFmpeg from {ffmpeg_bin} to {ffmpeg_src}")

    ico_file = os.path.join(app_dir, "assets", "app_icon.ico")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name=Universal_Downloader",
        f"--icon={ico_file}",
        "--add-binary=ffmpeg.exe;.",
        "--add-data=assets;assets",
        "--collect-all=customtkinter",
        "--collect-all=yt_dlp",
        "--collect-all=curl_cffi",
        "--hidden-import=darkdetect",
        "--hidden-import=imageio_ffmpeg",
        "--hidden-import=curl_cffi",
        "--clean",
        "--noconfirm",
        "gui_app.py"
    ]

    print("Running command:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=app_dir)
    if proc.returncode != 0:
        print("[ERROR] PyInstaller failed.")
        sys.exit(proc.returncode)

    built_exe = os.path.join(dist_dir, "Universal_Downloader.exe")

    if os.path.exists(built_exe):
        workspace_dir = os.path.dirname(app_dir)
        workspace_exe = os.path.join(workspace_dir, "Universal_Downloader.exe")
        workspace_exe_alt = os.path.join(workspace_dir, "UniversalDownloader.exe")
        workspace_exe_compat = os.path.join(workspace_dir, "YouTube_Downloader.exe")
        try:
            for exe_name in ["Universal_Downloader.exe", "UniversalDownloader.exe", "YouTube_Downloader.exe"]:
                subprocess.run(["taskkill", "/f", "/im", exe_name], capture_output=True)
            shutil.copy2(built_exe, workspace_exe)
            shutil.copy2(built_exe, workspace_exe_alt)
            # Remove legacy YouTube_Downloader.exe if requested or replace with new binary
            if os.path.exists(workspace_exe_compat):
                try:
                    os.remove(workspace_exe_compat)
                except Exception:
                    pass
        except Exception as e:
            print(f"[WARN] Copy warning: {e}")

        size_mb = os.path.getsize(built_exe) / (1024 * 1024)
        print("\n=======================================================")
        print(" SUCCESS: Universal Downloader Native Windows EXE Created!")
        print(f" Location: {built_exe}")
        print(f" Primary App: {workspace_exe}")
        print(f" Alt App: {workspace_exe_alt}")
        print(f" Size: {size_mb:.1f} MB")
        print(" Bundled: CustomTkinter GUI + yt-dlp + FFmpeg")
        print("=======================================================\n")
    else:
        print(f"[ERROR] Could not find built exe at: {built_exe}")
        sys.exit(1)

if __name__ == '__main__':
    build()
