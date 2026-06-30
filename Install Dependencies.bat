@echo off
setlocal
cd /d "%~dp0"
set PYTHON_EXE=
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo Python was not found. Please install Python 3.12 or newer first.
  pause
  exit /b 1
)
"%PYTHON_EXE%" -m pip install -r requirements.txt
pause
