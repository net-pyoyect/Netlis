<p align="center">
  <img src="assets/netlis_logo_transparent.png" alt="Netlis Logo" width="128" />
</p>

<h1 align="center">Netlis Browser</h1>

Navegador web privado, ligero y personalizable para Linux y Windows, con **Tor integrado**, **puentes obfs4**, **bloqueo de rastreadores/anuncios por sitio**, **protección local anti-phishing y magic-bytes en descargas**, **extensiones WebExtension MV3 + Userscripts**, y **modo híbrido opcional con Firefox/Gecko C++**.

## Características principales

- **Tor integrado + Kill-Switch:** enruta tráfico y DNS (`SOCKS5h`) por la red Tor, con rotación de identidad/país en 1 clic, puentes anticensura `obfs4` y modo **Turbo** directo.
- **Escudos estilo Brave por sitio:** contador y lista en tiempo real de los anuncios/rastreadores bloqueados en la página actual (`🛡`).
- **Seguridad local sin telemetría:** bloqueo de más de 148,000 dominios de malware/phishing (`URLhaus` + `Phishing Army`) actualizados vía Tor y verificados con `SHA-256`, además de inspección de *magic bytes* (`ELF`/`MZ`/`#!`) en descargas.
- **Extensiones y Plugins:** soporte nativo C++ para WebExtensions (`manifest.json`, `.zip`, `.xpi`, `.crx`) y Userscripts `==UserScript==` (`@match`, `@exclude`, `GM_*`).
- **Personalización:** tema oscuro minimalista o **Nébula Glass**, wallpaper personalizado y selector rápido de buscador (`DuckDuckGo` por defecto).

## Instalación rápida

### Instalación automática en Linux (todas las distros)

Detecta automáticamente **Debian, Ubuntu, Kali, Linux Mint, Pop!_OS, Arch, Manjaro, Fedora, openSUSE, Void y Alpine**:

```bash
git clone https://github.com/net-pyoyect/Netlis.git netlis && cd netlis && chmod +x install.sh && ./install.sh
```

- **Actualizar en 1 comando (Linux):** `./update.sh --launch`
- **Diagnosticar y reparar errores (Linux):** `./doctor.sh` (o `./doctor.sh --fix`)

### Comandos manuales por distribución

**Debian / Ubuntu / Linux Mint / Pop!_OS / Kali Linux:**
```bash
sudo apt update; sudo apt install -y python3 python3-venv python3-pip git tor obfs4proxy libxcb-cursor0 libnss3 libegl1
git clone https://github.com/net-pyoyect/Netlis.git netlis && cd netlis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
chmod +x launch.sh install_desktop.sh && ./install_desktop.sh && ./launch.sh
```

**Arch Linux / Manjaro / EndeavourOS / Quantum Linux:**
```bash
sudo pacman -Sy --needed python git tor nss libxcb xcb-util-cursor
git clone https://github.com/net-pyoyect/Netlis.git netlis && cd netlis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
chmod +x launch.sh install_desktop.sh && ./install_desktop.sh && ./launch.sh
```

**Fedora / Nobara / RHEL:**
```bash
sudo dnf install -y python3 python3-pip git tor nss xcb-util-cursor
git clone https://github.com/net-pyoyect/Netlis.git netlis && cd netlis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
chmod +x launch.sh install_desktop.sh && ./install_desktop.sh && ./launch.sh
```

**openSUSE:**
```bash
sudo zypper install -y python3 python3-pip git tor mozilla-nss libxcb-cursor0
git clone https://github.com/net-pyoyect/Netlis.git netlis && cd netlis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
chmod +x launch.sh install_desktop.sh && ./install_desktop.sh && ./launch.sh
```

### Windows 10 / 11

**Requisitos previos (una sola vez):**
1. Instalar **Git para Windows** (`git-scm.com`).
2. Instalar **Python 3.10+** (`python.org`) marcando la casilla **"Add Python to PATH"**.

**Instalar y abrir en 1 comando (en CMD o PowerShell):**
```cmd
git clone https://github.com/net-pyoyect/Netlis.git netlis && cd netlis && install.bat && launch.bat
```

- `install.bat` crea automáticamente `.venv`, instala `PyQt6` + `PyQt6-WebEngine` y crea el acceso directo **Netlis** en el Escritorio.
- **Actualizar en 1 comando (Windows):** `update.bat --launch`
- **Diagnosticar y reparar errores (Windows):** `python doctor.py`

> **Nota (Tor):** En Linux puedes instalar `tor` del sistema (`sudo pacman -S tor` / `sudo apt install tor`) o colocarlo en `.tor/`. En Windows, coloca el Tor Expert Bundle en `.tor\tor\tor.exe` o añade `tor.exe` al `PATH`.

## Pruebas automatizadas

```bash
.venv/bin/python3 tests/test_suite.py -v
```

## Cómo lanzar nuevas actualizaciones (para mantenedores)

1. El repositorio ya está configurado en `version.json` (`"repo": "net-pyoyect/Netlis"`).
2. Cuando tengas cambios listos, ejecuta `release.py`:

```bash
.venv/bin/python3 release.py --bump patch --notes "Descripción de mejoras" --push
```

Esto ejecuta primero toda la suite de pruebas, incrementa la versión en `version.json`, crea el commit y la etiqueta `vX.Y.Z` y la publica en GitHub. Los usuarios podrán actualizar en 1 clic desde **Centro de Seguridad → Mantenimiento → Buscar y aplicar actualización de Netlis**.

## Licencia

Copyright (c) 2026 net-pyoyect. Todos los derechos reservados. Consulta el archivo [LICENSE](LICENSE) para más detalles.
