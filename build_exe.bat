@echo off
setlocal
cd /d "%~dp0"
echo === Generando Netlis.exe para Windows ===

if not exist ".venv\Scripts\python.exe" (
    call install.bat
)

".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller pillow
".venv\Scripts\python.exe" -c "from PIL import Image; img = Image.open('assets/netlis_logo_transparent.png').convert('RGBA'); img.save('assets/netlis.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed ^
  --name Netlis ^
  --icon assets/netlis.ico ^
  --add-data "assets;assets" ^
  --collect-all PyQt6.QtWebEngineWidgets ^
  --collect-all PyQt6.QtWebEngineCore ^
  browser.py

echo.
echo === Listo: dist\Netlis\Netlis.exe ===
pause
