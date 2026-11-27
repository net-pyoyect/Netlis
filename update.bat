@echo off
setlocal
cd /d "%~dp0"
echo === Actualizando Netlis Browser en Windows ===

if exist ".git" (
    echo [*] Descargando ultimos cambios desde GitHub...
    git pull --ff-only origin main || git pull --rebase --autostash origin main
)

if not exist ".venv\Scripts\python.exe" (
    call install.bat
    exit /b %errorlevel%
)

echo [*] Actualizando dependencias Python...
".venv\Scripts\pip.exe" install -q -r requirements.txt

echo.
echo === Netlis actualizado correctamente ===
if "%~1"=="--launch" (
    call launch.bat
) else (
    echo Abrelo con: launch.bat
)
