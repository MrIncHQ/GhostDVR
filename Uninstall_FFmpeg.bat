@echo off
setlocal

winget uninstall --id Gyan.FFmpeg -e --source winget

echo.
echo If FFmpeg uninstalled successfully, close and reopen any Ghost DVR windows.
pause
