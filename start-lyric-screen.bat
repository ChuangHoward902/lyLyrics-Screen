@echo off
setlocal

cd /d "%~dp0"
start "" wscript.exe //nologo "%~dp0start-lyric-screen.vbs"
exit /b
