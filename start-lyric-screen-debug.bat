@echo off
setlocal

cd /d "%~dp0"

echo Starting lyLyrics screen in debug mode...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-lyric-screen.ps1"

echo.
echo If the app did not open, copy the message above.
pause
