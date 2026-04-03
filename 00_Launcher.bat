@echo off
setlocal
cd /d "%~dp0"

rem FFmpeg PATH fallback (winget + classic path)
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links;C:\ffmpeg\bin"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    ".venv\Scripts\python.exe" launcher_gui.py
    goto :end
  )
)

echo [INFO] .venv eksik veya bozuk. Yeni ortam olusturuluyor...
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" (
  set "PY_BOOT=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
) else if exist "C:\Python312\python.exe" (
  set "PY_BOOT=C:\Python312\python.exe"
) else (
  set "PY_BOOT=python"
)

%PY_BOOT% -m venv .venv
if errorlevel 1 (
  echo [ERROR] Sanal ortam olusturulamadi.
  goto :end
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Paket kurulumu basarisiz.
  goto :end
)

".venv\Scripts\python.exe" launcher_gui.py
:end
pause
