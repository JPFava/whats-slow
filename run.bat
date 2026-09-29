@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title What is slowing this PC

set "BASEPY="
where py >nul 2>&1 && py -3 -c "import sys" >nul 2>&1 && set "BASEPY=py -3"
if not defined BASEPY (
  where python >nul 2>&1 && python -c "import sys" >nul 2>&1 && set "BASEPY=python"
)
if not defined BASEPY (
  echo.
  echo Python was not found.
  echo.
  echo 1. Install it from https://www.python.org/downloads/
  echo 2. On the first installer screen, check "Add python.exe to PATH".
  echo 3. If Python is already installed, turn OFF the app execution aliases
  echo    for python.exe and python3.exe:
  echo    Settings, Apps, Advanced app settings, App execution aliases.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Setting up a private Python environment in this folder...
  %BASEPY% -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto FAIL

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto FAIL

echo.
echo Watching the PC. The window will look paused for several seconds.
echo That pause is the measurement. Nothing will be closed.
echo.
".venv\Scripts\python.exe" -m whats_slow --open %*
echo.
echo A copy is also in the reports folder. Open the newest HTML file if the browser did not.
echo.
pause
exit /b 0

:FAIL
echo.
echo Setup failed. From this folder you can try:
echo     %BASEPY% -m pip install -r requirements.txt
echo     %BASEPY% -m whats_slow
echo.
pause
exit /b 1
