@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" launcher_gui.py
) else (
  python launcher_gui.py
)
pause
