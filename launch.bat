@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" browser.py %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" browser.py %*
) else (
    python browser.py %*
)
