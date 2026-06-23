@echo off
setlocal

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

python -m ghost_dvr.app --ui

if errorlevel 1 (
  echo.
  echo Ghost DVR exited with an error.
  pause
)
