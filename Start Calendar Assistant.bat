@echo off
setlocal
title Calendar Assistant
cd /d "%~dp0"
set APP_URL=http://127.0.0.1:7871
set PYTHON_EXE=

if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"

if not defined PYTHON_EXE (
  echo Python was not found.
  echo.
  echo Please install Python 3.12 or newer from https://www.python.org/downloads/
  echo Then run this launcher again.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing $env:APP_URL -TimeoutSec 1 | Out-Null; Start-Process $env:APP_URL; exit 0 } catch { exit 1 }"
if not errorlevel 1 exit /b 0

echo Starting Calendar Assistant...
echo.
echo Keep this window open while using the app.
echo Close this window when you are done.
echo.
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 3; Start-Process $env:APP_URL"
"%PYTHON_EXE%" app.py
echo.
echo Calendar Assistant stopped.
pause
