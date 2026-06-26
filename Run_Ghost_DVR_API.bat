@echo off
setlocal

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

python -m ghost_dvr.app --api

if errorlevel 1 (
  echo.
  echo Ghost DVR API exited with an error.
  pause
)
