@echo off
title YouTube Downloader
cd /d "%~dp0"
echo =======================================================
echo             YouTube Downloader
echo =======================================================
echo.
echo Launching server at http://127.0.0.1:5000 ...
start "" "http://127.0.0.1:5000"
python server.py 5000
pause
