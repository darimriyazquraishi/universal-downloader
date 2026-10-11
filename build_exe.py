import os
import sys
import shutil
import subprocess

def build():
    # Kill any existing instance so files are not locked
    try:
        subprocess.run(["taskkill", "/f", "/im", "YouTube_Downloader.exe"], capture_output=True)
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

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name=YouTube_Downloader",
        "--add-binary=ffmpeg.exe;.",
        "--collect-all=customtkinter",
        "--collect-all=yt_dlp",
        "--hidden-import=darkdetect",
        "--hidden-import=imageio_ffmpeg",
        "--clean",
        "--noconfirm",
        "gui_app.py"
    ]

    print("Running command:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=app_dir)
    if proc.returncode != 0:
        print("[ERROR] PyInstaller failed.")
        sys.exit(proc.returncode)

    built_exe = os.path.join(dist_dir, "YouTube_Downloader.exe")

    if os.path.exists(built_exe):
        workspace_exe = os.path.join(os.path.dirname(app_dir), "YouTube_Downloader.exe")
        try:
            subprocess.run(["taskkill", "/f", "/im", "YouTube_Downloader.exe"], capture_output=True)
            shutil.copy2(built_exe, workspace_exe)
        except Exception:
            pass

        size_mb = os.path.getsize(built_exe) / (1024 * 1024)
        print("\n=======================================================")
        print(" SUCCESS: Native Desktop Windows EXE Created!")
        print(f" Location: {built_exe}")
        if os.path.exists(workspace_exe):
            print(f" Root App: {workspace_exe}")
        print(f" Size: {size_mb:.1f} MB")
        print(" Bundled: CustomTkinter GUI + yt-dlp + FFmpeg")
        print("=======================================================\n")
    else:
        print(f"[ERROR] Could not find built exe at: {built_exe}")
        sys.exit(1)

if __name__ == '__main__':
    build()
