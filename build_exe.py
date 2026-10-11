import os
import sys
import shutil
import subprocess

def build():
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
    final_dest = r"e:\deleteme\YouTube_Downloader.exe"

    if os.path.exists(built_exe):
        # Kill any running instance of YouTube_Downloader.exe if currently open
        try:
            subprocess.run(["taskkill", "/f", "/im", "YouTube_Downloader.exe"], capture_output=True)
        except Exception:
            pass

        shutil.copy2(built_exe, final_dest)
        size_mb = os.path.getsize(final_dest) / (1024 * 1024)
        print(f"\n=======================================================")
        print(f" SUCCESS: Native Desktop Windows EXE Created!")
        print(f" Location: {final_dest}")
        print(f" Size: {size_mb:.1f} MB")
        print(f" Bundled: Native Dark GUI + yt-dlp + FFmpeg 7.1")
        print(f" Zero Browser Involvement: Pure Native Desktop Window")
        print(f"=======================================================\n")
    else:
        print(f"[ERROR] Could not find built exe at: {built_exe}")
        sys.exit(1)

if __name__ == '__main__':
    build()
