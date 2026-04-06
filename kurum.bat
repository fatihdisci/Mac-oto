@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo [INFO] Mac-oto kurulum basladi...
echo [INFO] Proje klasoru: %cd%

call :resolve_python
if not defined PY_BOOT_EXE (
  echo [ERROR] Calisir bir Python bulunamadi.
  echo [INFO] Lutfen Python 3.12+ kur: https://www.python.org/downloads/windows/
  goto :end
)

echo [INFO] Bootstrap Python: %PY_BOOT_EXE% %PY_BOOT_ARGS%

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
    echo [WARN] .venv taban Python yolu bulunamadi. .venv yeniden kurulacak...
    rmdir /s /q ".venv"
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Yeni .venv olusturuluyor...
  "%PY_BOOT_EXE%" %PY_BOOT_ARGS% -c "import tkinter" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Bulunan Python'da tkinter yok. GUI calismaz.
    echo [INFO] Resmi Python 3.12+ kurup tekrar dene.
    goto :end
  )
  "%PY_BOOT_EXE%" %PY_BOOT_ARGS% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] .venv olusturulamadi.
    goto :end
  )
)

echo [INFO] Pip guncelleniyor...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] pip guncellenemedi.
  goto :end
)

echo [INFO] Paketler kuruluyor (requirements.txt)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Paket kurulumu basarisiz.
  goto :end
)

echo [INFO] Kurulum dogrulamasi...
".venv\Scripts\python.exe" -c "import tkinter,customtkinter,pygame,pymunk; print('OK')"
if errorlevel 1 (
  echo [ERROR] Kurulum dogrulamasi basarisiz.
  goto :end
)

echo.
echo [SUCCESS] Kurulum tamamlandi.
echo [INFO] Simdi 00_Launcher.bat dosyasini cift tiklayip GUI'yi acabilirsin.

:end
pause
exit /b 0

:resolve_python
set "PY_BOOT_EXE="
set "PY_BOOT_ARGS="

for %%P in (
  "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
  "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"
  "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe"
  "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python314\python.exe"
  "C:\Python312\python.exe"
  "C:\Python310\python.exe"
  "C:\Python313\python.exe"
  "C:\Python314\python.exe"
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
