@echo off
title Universal Downloader - Mobile Phone Simulator
cd /d "%~dp0"

if exist "..\venv_android\Scripts\python.exe" (
    "..\venv_android\Scripts\python.exe" main.py
) else (
    python main.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo If Python failed to launch, install the dependencies by running:
    echo pip install -r requirements.txt
    echo.
    pause
)
