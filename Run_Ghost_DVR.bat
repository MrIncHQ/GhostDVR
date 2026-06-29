@echo off
setlocal

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

:restart
python -m ghost_dvr.app --ui
if errorlevel 75 if not errorlevel 76 (
  echo.
  echo Ghost DVR updated. Restarting...
  goto restart
)

if errorlevel 1 (
  echo.
  echo Ghost DVR exited with an error.
  pause
)
