@echo off
setlocal
cd /d "%~dp0"
echo === Instalador de Netlis Browser para Windows ===

set "PY_CMD="
where py >nul 2>&1 && set "PY_CMD=py -3"
if "%PY_CMD%"=="" (
    where python >nul 2>&1 && set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
    echo [ERROR] No se encontro Python 3.10+.
    echo Instala Python desde https://www.python.org/downloads/ y marca "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creando entorno virtual .venv...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual .venv.
        pause
        exit /b 1
    )
)

echo [*] Actualizando pip e instalando PyQt6 y PyQt6-WebEngine...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo [*] Creando acceso directo en el Escritorio...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Netlis.lnk'); $s.TargetPath = '%~dp0launch.bat'; $s.WorkingDirectory = '%~dp0'; $s.Save()" >nul 2>&1

echo.
echo === Netlis instalado correctamente en Windows ===
echo Puedes abrirlo con doble clic en Netlis (Escritorio) o ejecutando: launch.bat
