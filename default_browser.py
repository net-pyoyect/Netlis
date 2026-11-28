"""Linux and Windows browser registration, performed only on explicit action."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

DESKTOP_ID = 'netlis.desktop'
ASSOCIATIONS = ('x-scheme-handler/http', 'x-scheme-handler/https', 'text/html', 'application/xhtml+xml')


def run_command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=12, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'El sistema rechazó el cambio.').strip()[:300])
    return result.stdout.strip()


def available():
    return sys.platform == 'win32' or sys.platform.startswith('linux') and bool(shutil.which('xdg-settings')) and bool(shutil.which('xdg-mime'))


def default_status():
    if sys.platform == "win32":
        return windows_default_status()
    if not available():
        return None, 'Esta integración está disponible en escritorios Linux con xdg-utils.'
    try:
        browser = run_command(['xdg-settings', 'get', 'default-web-browser'])
        handlers = [run_command(['xdg-mime', 'query', 'default', kind]) for kind in ASSOCIATIONS]
        active = browser == DESKTOP_ID and all(value == DESKTOP_ID for value in handlers)
        return active, ('Netlis es tu navegador predeterminado.' if active else 'Netlis no es el navegador predeterminado para todos los enlaces y archivos web.')
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return None, f'No se pudo consultar el navegador predeterminado: {exc}'


def desktop_argument(value):
    # Desktop Entry Exec quoting, not shell quoting. Percent is a field-code escape.
    value = str(value).replace('%', '%%')
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, '\\' + character)
    return '"' + value.replace('\\', '\\\\') + '"'


def register_desktop(project):
    project = Path(project).resolve()
    if not (project / 'launch.sh').is_file():
        raise RuntimeError('No se encontró el lanzador de Netlis.')
    data_home = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    if not data_home.is_absolute():
        data_home = Path.home() / '.local/share'
    applications = data_home / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    desktop = applications / DESKTOP_ID
    content = '\n'.join([
        '[Desktop Entry]', 'Version=1.0', 'Type=Application', 'Name=Netlis',
        'GenericName=Navegador web',
        f'Exec=/bin/bash {desktop_argument(project / "launch.sh")} %U',
        'Icon=' + str(project / 'assets/netlis_logo_transparent.png').replace('\\', '\\\\'),
        'Terminal=false', 'Categories=Network;WebBrowser;',
        'MimeType=' + ';'.join(ASSOCIATIONS) + ';',
        'StartupNotify=true', 'StartupWMClass=netlis', '',
    ])
    temporary = desktop.with_suffix('.desktop.tmp')
    temporary.write_text(content, encoding='utf-8')
    temporary.replace(desktop)
    return desktop


def set_default_browser(project=None):
    if sys.platform == "win32":
        return set_windows_default(project or Path(__file__).parent)
    if not available():
        return False, 'Instala xdg-utils para poder establecer Netlis como navegador predeterminado en Linux.'
    try:
        desktop = register_desktop(project or Path(__file__).parent)
        if shutil.which('update-desktop-database'):
            run_command(['update-desktop-database', str(desktop.parent)])
        run_command(['xdg-settings', 'set', 'default-web-browser', DESKTOP_ID])
        for kind in ASSOCIATIONS:
            run_command(['xdg-mime', 'default', DESKTOP_ID, kind])
        active, message = default_status()
        return active is True, message
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return False, f'No se pudo completar el cambio: {exc}'


WINDOWS_PROG_ID = 'Netlis.HTML'
WINDOWS_CAPABILITIES = r'Software\Clients\StartMenuInternet\Netlis\Capabilities'


def windows_launch_command(project):
    project = Path(project)
    if getattr(sys, 'frozen', False):
        args = [sys.executable]
    else:
        script = project / 'browser.py'
        if not script.is_file():
            raise RuntimeError('No se encontró browser.py.')
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        args = [str(pythonw if pythonw.is_file() else Path(sys.executable)), str(script)]
    return subprocess.list2cmdline(args)


def write_windows_value(path, name, value):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def register_windows(project):
    project = Path(project)
    command = windows_launch_command(project)
    icon_path = project / 'assets/netlis.ico'
    icon = f'"{icon_path}",0' if icon_path.is_file() else f'"{sys.executable}",0'
    classes = 'Software\\Classes\\' + WINDOWS_PROG_ID
    client = r'Software\Clients\StartMenuInternet\Netlis'
    values = [
        (classes, '', 'Netlis HTML Document'),
        (classes, 'URL Protocol', ''),
        (classes + r'\DefaultIcon', '', icon),
        (classes + r'\shell\open\command', '', command + ' "%1"'),
        (client, '', 'Netlis'),
        (client + r'\DefaultIcon', '', icon),
        (client + r'\shell\open\command', '', command),
        (WINDOWS_CAPABILITIES, 'ApplicationName', 'Netlis'),
        (WINDOWS_CAPABILITIES, 'ApplicationDescription', 'Navegador web Netlis'),
        (WINDOWS_CAPABILITIES, 'ApplicationIcon', icon),
        (r'Software\RegisteredApplications', 'Netlis', WINDOWS_CAPABILITIES),
    ]
    for scheme in ('http', 'https'):
        values.append((WINDOWS_CAPABILITIES + r'\URLAssociations', scheme, WINDOWS_PROG_ID))
    for extension in ('.htm', '.html', '.xhtml'):
        values.append((WINDOWS_CAPABILITIES + r'\FileAssociations', extension, WINDOWS_PROG_ID))
        values.append(('Software\\Classes\\' + extension + r'\OpenWithProgids', WINDOWS_PROG_ID, ''))
    for path, name, value in values:
        write_windows_value(path, name, value)


def windows_default_status():
    import winreg
    paths = ['Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\' + scheme + r'\UserChoice' for scheme in ('http', 'https')]
    paths += ['Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\' + ext + r'\UserChoice' for ext in ('.htm', '.html', '.xhtml')]
    try:
        for path in paths:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                    value, _ = winreg.QueryValueEx(key, 'ProgId')
                if value != WINDOWS_PROG_ID:
                    return False, 'Selecciona Netlis en Aplicaciones predeterminadas de Windows para abrir enlaces y archivos web.'
            except FileNotFoundError:
                return False, 'Selecciona Netlis en Aplicaciones predeterminadas de Windows.'
        return True, 'Netlis es tu navegador predeterminado.'
    except OSError as exc:
        return None, f'No se pudo consultar la configuración de Windows: {exc}'


def set_windows_default(project):
    try:
        register_windows(project)
        # Windows owns the protected UserChoice keys; let the user choose in Settings.
        version = sys.getwindowsversion()
        uri = 'ms-settings:defaultapps?registeredAppUser=Netlis' if version.build >= 22621 else 'ms-settings:defaultapps'
        os.startfile(uri)
        return False, 'En Windows, busca Netlis y elige Establecer como predeterminado. El estado se actualizará al volver.'
    except (OSError, RuntimeError) as exc:
        return False, f'No se pudo abrir la configuración de Windows: {exc}'
