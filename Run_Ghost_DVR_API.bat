@echo off
setlocal

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

:restart
python -m ghost_dvr.app --api
if errorlevel 75 if not errorlevel 76 (
  echo.
  echo Ghost DVR updated. Restarting API...
  goto restart
)

if errorlevel 1 (
  echo.
  echo Ghost DVR API exited with an error.
  pause
)
