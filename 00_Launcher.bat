@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem FFmpeg PATH fallback (winget + classic path)
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links;C:\ffmpeg\bin"

if exist ".venv\Scripts\python.exe" (
  set "VENV_BROKEN="
  if exist ".venv\pyvenv.cfg" (
    for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"executable = " ".venv\pyvenv.cfg"') do (
      set "VENV_BASE_EXE=%%B"
    )
    if defined VENV_BASE_EXE (
      set "VENV_BASE_EXE=!VENV_BASE_EXE:~1!"
      if not exist "!VENV_BASE_EXE!" set "VENV_BROKEN=1"
    )
  )

  if defined VENV_BROKEN (
    echo [INFO] .venv taban Python yolu bulunamadi. .venv yeniden kurulacak...
  ) else (
    ".venv\Scripts\python.exe" -c "import sys, tkinter, customtkinter; print(sys.executable)" >nul 2>&1
    if not errorlevel 1 (
      ".venv\Scripts\python.exe" launcher_gui.py
      goto :end
    )
    echo [INFO] Mevcut .venv bozuk gorunuyor. Yeniden kurulacak...
  )
)

echo [INFO] .venv eksik veya bozuk. Yeni ortam olusturuluyor...
call :resolve_python
if not defined PY_BOOT_EXE (
  echo [ERROR] Calisir bir Python bulunamadi.
  echo [INFO] Beklenen yerler: Python 3.12/3.13/3.14 veya py launcher.
  echo [INFO] Once resmi Python kur: https://www.python.org/downloads/windows/
  goto :end
)

echo [INFO] Bootstrap Python: %PY_BOOT_EXE% %PY_BOOT_ARGS%
if exist ".venv" (
  rmdir /s /q ".venv"
)

"%PY_BOOT_EXE%" %PY_BOOT_ARGS% -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Bootstrap Python calistirilamadi.
  goto :end
)
"%PY_BOOT_EXE%" %PY_BOOT_ARGS% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Bulunan Python'da tkinter yok. GUI calismaz.
  echo [INFO] Lutfen resmi Python 3.12+ kur (python.org) ve tekrar dene.
  goto :end
)

"%PY_BOOT_EXE%" %PY_BOOT_ARGS% -m venv .venv
if errorlevel 1 (
  echo [ERROR] Sanal ortam olusturulamadi.
  echo [INFO] Cozum: Python 3.12+ kurup tekrar 00_Launcher.bat calistir.
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

:resolve_python
set "PY_BOOT_EXE="
set "PY_BOOT_ARGS="
for %%P in (
  "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python314\python.exe"
  "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe"
  "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
  "C:\Python314\python.exe"
  "C:\Python313\python.exe"
  "C:\Python312\python.exe"
) do (
  if exist %%~P (
    set "PY_BOOT_EXE=%%~P"
    goto :resolve_done
  )
)

where py >nul 2>&1
if not errorlevel 1 (
  set "PY_BOOT_EXE=py"
  set "PY_BOOT_ARGS=-3"
  py -3 -c "import sys" >nul 2>&1
  if errorlevel 1 (
    set "PY_BOOT_EXE="
    set "PY_BOOT_ARGS="
  ) else (
    goto :resolve_done
  )
)

where python >nul 2>&1
if not errorlevel 1 (
  set "PY_BOOT_EXE=python"
  python -c "import sys" >nul 2>&1
  if errorlevel 1 (
    set "PY_BOOT_EXE="
  ) else (
    goto :resolve_done
  )
)

:resolve_done
exit /b 0
