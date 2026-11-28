from interface_style import MANAGEMENT_QSS, navigation_icon
"""Searchable native settings page for supported Netlis preferences."""
from dataclasses import replace
from pathlib import Path
import json
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QLineEdit,QFrame,QScrollArea,QCheckBox,QComboBox,QMessageBox)
from newtab import SEARCH_ENGINES
from theme_page import ThemesPanel

class DefaultBrowserWorker(QThread):
    result = pyqtSignal(object, str)
    def __init__(self, change=False, parent=None):
        super().__init__(parent); self.change=change
    def run(self):
        from default_browser import default_status, set_default_browser
        active,message=set_default_browser() if self.change else default_status()
        self.result.emit(active,message)


class SettingsPage(QWidget):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser=browser;self.cards=[];self.category='Inicio';self.buttons={}
        self.setObjectName('settingsPage')
        self.setStyleSheet('''
            QWidget#settingsPage { background: #19151f; }
            QWidget#sidebar { background: #211c29; }
            QLabel { color: #f0edf5; background: transparent; font-size: 14px; }
            QLabel#heading { font-size: 24px; font-weight: 600; }
            QLabel#cardTitle { font-size: 17px; font-weight: 600; }
            QLabel#muted { color: #bcb4c8; font-size: 13px; }
            QFrame#card, QFrame#hero { background: #2b2533; border: 1px solid #44394e; border-radius: 16px; }
            QPushButton { background: #3b3147; color: #f0edf5; border: 1px solid #79678f; border-radius: 15px; padding: 10px 16px; font-size: 13px; }
            QPushButton:hover { background: #50405e; }
            QPushButton:focus { border-color: #cfb6ff; }
            QPushButton#nav { text-align: left; background: transparent; border: none; padding: 12px 16px; }
            QPushButton#nav:checked { background: #bfa0ff; color: #21162e; font-weight: 600; }
            QPushButton#nav:hover:!checked { background: #362b43; }
            QLineEdit,QComboBox { background: #27212f; color: #eee8f5; border: 1px solid #82708f; border-radius: 14px; padding: 10px 14px; font-size: 14px; }
            QComboBox QAbstractItemView { background: #27212f; color: #eee8f5; selection-background-color: #58456d; }
            QCheckBox { color: #eee8f5; spacing: 12px; font-size: 14px; padding: 6px 0; }
            QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #92829e; border-radius: 5px; background: #27212f; }
            QCheckBox::indicator:checked { background: #bfa0ff; border-color: #d3baff; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 7px; }
            QScrollBar::handle:vertical { background: #665570; border-radius: 3px; min-height: 30px; }
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height: 0; }
        ''')
        self.setStyleSheet(self.styleSheet()+MANAGEMENT_QSS)
        check_icon=(Path(__file__).parent/"assets/settings-check.svg").as_posix()
        self.setStyleSheet(self.styleSheet()+f'QCheckBox::indicator:checked {{ image: url("{check_icon}"); }}')
        root=QHBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(280)
        nav=QVBoxLayout(sidebar);nav.setContentsMargins(28,64,12,24);nav.setSpacing(4)
        title=QLabel('Ajustes');title.setObjectName('heading');nav.addWidget(title);nav.addSpacing(16)
        for name in ['Cuenta','Inicio','Buscar','Privacidad y seguridad','Contraseñas','Apariencia','Descargas','Pestañas','Acerca de Netlis']:
            button=QPushButton('  '+name);button.setIcon(navigation_icon(name));button.setObjectName('nav');button.setCheckable(True);button.clicked.connect(lambda checked,n=name:self.select(n));nav.addWidget(button);self.buttons[name]=button
        nav.addStretch();root.addWidget(sidebar)
        main=QWidget();main.setMaximumWidth(700);right=QVBoxLayout(main);right.setContentsMargins(22,60,22,24);right.setSpacing(18)
        self.search=QLineEdit();self.search.setPlaceholderText('Buscar en ajustes');self.search.setClearButtonEnabled(True);right.addWidget(self.search)
        self.heading=QLabel();self.heading.setObjectName('heading');right.addWidget(self.heading)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);host=QWidget();self.content=QVBoxLayout(host);self.content.setContentsMargins(0,0,10,0);self.content.setSpacing(20);self.scroll.setWidget(host);right.addWidget(self.scroll,1);root.addWidget(main,1);root.addStretch()
        _,box=self.card('Inicio','Navegador predeterminado','Abre los enlaces web y los archivos HTML con Netlis.')
        default_row=QHBoxLayout()
        default_logo=QLabel();default_logo.setPixmap(QPixmap(str(Path(__file__).parent/'assets/settings-eagle.png')).scaled(76,70,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));default_row.addWidget(default_logo)
        default_text=QVBoxLayout();self.default_status_label=QLabel('Comprobando navegador predeterminado…');self.default_status_label.setWordWrap(True);default_text.addWidget(self.default_status_label)
        self.default_button=QPushButton('Convertir en predeterminado');self.default_button.setObjectName('primary');self.default_button.setEnabled(False);self.default_button.clicked.connect(lambda:self.check_default_browser(True));default_text.addWidget(self.default_button,0,Qt.AlignmentFlag.AlignLeft)
        default_row.addLayout(default_text,1);box.addLayout(default_row)
        self.default_worker=None
        QTimer.singleShot(0,self.check_default_browser)
        self.default_poll=QTimer(self);self.default_poll.setInterval(5000)
        self.default_poll.timeout.connect(lambda:self.check_default_browser() if self.isVisible() and self.category=="Inicio" else None)
        self.default_poll.start()
        card,box=self.card('Inicio','Bienvenido a Netlis','Configura tu navegador para sentirte en casa.')
        row=QHBoxLayout();eagle=QLabel();eagle.setAccessibleName('Águila de Netlis');pix=QPixmap(str(Path(__file__).parent/'assets/settings-eagle.png'));eagle.setPixmap(pix.scaled(110,95,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));row.addWidget(eagle)
        text=QLabel('Netlis\nUn espacio para navegar a tu manera.');text.setWordWrap(True);row.addWidget(text,1);box.addLayout(row)
        _,box=self.card('Inicio','Página de inicio','Elige qué aparece cuando abres una nueva pestaña.')
        self.check(box,'Mostrar el logotipo',browser.appearance.show_home_logo,lambda value:self.appearance('show_home_logo',value))
        self.check(box,'Mostrar el buscador',browser.appearance.show_home_search,lambda value:self.appearance('show_home_search',value))
        self.action(box,'Elegir fondo de pantalla',browser._show_appearance)
        _,box=self.card('Cuenta','Cuenta de Google','Abre tus servicios de Google en su perfil separado. Iniciar sesión no sincroniza la configuración de Netlis.')
        self.action(box,'Abrir cuenta',browser._open_google_vault)
        self.card('Cuenta','Datos locales','Netlis no ofrece sincronización de marcadores o contraseñas entre dispositivos. La bóveda se guarda en este equipo.')
        from browser import _make_search_engine_icon
        _,box=self.card('Buscar','Buscador predeterminado','Elige el buscador que se utiliza en la barra de direcciones y en la página de inicio.')
        self.engines=QComboBox(); self.engines.setFixedWidth(250)
        self.engine_buttons={}
        for key,(name,_) in SEARCH_ENGINES.items():
            self.engines.addItem(_make_search_engine_icon(key),name.split(' (')[0],key)
        self.engines.setCurrentIndex(self.engines.findData(browser.appearance.search_engine))
        box.addWidget(self.engines,0,Qt.AlignmentFlag.AlignLeft)
        self.check(box,'Mostrar términos de búsqueda en la barra de direcciones',browser.appearance.show_search_terms,lambda value:self.appearance('show_search_terms',value))
        _,box=self.card('Buscar','Buscadores disponibles','Usa un atajo en la barra de direcciones o elige otro buscador predeterminado.')
        group=QFrame();group.setObjectName('engineList')
        group.setStyleSheet('QFrame#engineList { border: 1px solid #85818b; border-radius: 14px; background: transparent; }')
        rows=QVBoxLayout(group);rows.setContentsMargins(0,6,0,6);rows.setSpacing(0)
        for index,(key,(name,_)) in enumerate(SEARCH_ENGINES.items()):
            if index:
                line=QFrame();line.setFixedHeight(1);line.setStyleSheet('background: #59565e; border: none;');rows.addWidget(line)
            row_widget=QWidget();row=QHBoxLayout(row_widget);row.setContentsMargins(18,14,16,14);row.setSpacing(14)
            icon=QLabel();icon.setPixmap(_make_search_engine_icon(key).pixmap(26,26));icon.setFixedWidth(28);row.addWidget(icon)
            labels=QVBoxLayout();labels.setSpacing(4);labels.addWidget(QLabel(name.split(' (')[0]))
            shortcut=QLabel('@'+key);shortcut.setObjectName('muted');labels.addWidget(shortcut);row.addLayout(labels,1)
            use=QPushButton('Elegir');use.setToolTip('Usar como buscador predeterminado');use.clicked.connect(lambda checked,k=key:self.choose_engine(k));row.addWidget(use);self.engine_buttons[key]=use
            rows.addWidget(row_widget)
        box.addWidget(group)
        self.engines.currentIndexChanged.connect(lambda:self.choose_engine(self.engines.currentData()))
        self.update_engine_buttons()
        _,box=self.card('Buscar','Atajos de búsqueda','Escribe el atajo seguido de tu consulta. Por ejemplo: @wikipedia sistema solar.')
        note=QLabel('La búsqueda se realiza al pulsar Intro.');note.setObjectName('muted');box.addWidget(note)
        _,box=self.card('Privacidad y seguridad','Netlis protege tu navegación','Consulta las protecciones que tienes activadas.')
        status_row=QHBoxLayout();status_text=QVBoxLayout()
        self.protection_state=QLabel();self.protection_state.setWordWrap(True);status_text.addWidget(self.protection_state)
        self.blocked_state=QLabel();self.blocked_state.setObjectName('muted');status_text.addWidget(self.blocked_state);status_row.addLayout(status_text,1)
        shield=QLabel();shield.setPixmap(QPixmap(str(Path(__file__).parent/'assets/privacy-eagle.png')).scaled(100,110,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));shield.setAccessibleName('Águila con escudo');status_row.addWidget(shield);box.addLayout(status_row)
        _,box=self.card('Privacidad y seguridad','Protección contra el rastreo','Los sitios pueden usar rastreadores para seguir tu actividad. Elige qué conexiones y datos bloquea Netlis.')
        controls=QFrame();controls.setStyleSheet('QFrame { border: 1px solid #77717f; border-radius: 12px; background: transparent; } QCheckBox { border: none; }')
        checks=QVBoxLayout(controls);checks.setContentsMargins(16,12,16,12);checks.setSpacing(8)
        for label,field in [('Bloquear rastreadores y anuncios','block_trackers'),('Bloquear cookies de terceros','block_third_party_cookies'),('Usar conexiones HTTPS','https_only'),('Quitar parámetros de seguimiento','strip_tracking_params'),('Detectar sitios de phishing y malware','phishing_and_malware_guard')]:
            self.check(checks,label,getattr(browser.settings,field),lambda value,f=field:self.privacy(f,value))
        box.addWidget(controls);self.action(box,'Configuración avanzada  ›',browser._show_advanced_privacy_center)
        _,box=self.card('Privacidad y seguridad','Navegación con Tor','Añade privacidad a las conexiones del navegador usando la red Tor.')
        banner=QFrame();banner.setObjectName('torBanner');banner.setStyleSheet('QFrame#torBanner { background: #40315f; border: none; border-radius: 14px; }')
        banner_row=QHBoxLayout(banner);banner_row.setContentsMargins(16,16,16,16);banner_row.setSpacing(12);tor_text=QVBoxLayout()
        self.tor_state=QLabel();self.tor_state.setObjectName('cardTitle');tor_text.addWidget(self.tor_state)
        detail=QLabel('Los sitios reciben una IP de salida de Tor.\nLa conexión puede ser más lenta.');detail.setWordWrap(True);tor_text.addWidget(detail)
        self.tor_button=QPushButton();self.tor_button.setObjectName('primary');self.tor_button.clicked.connect(self.toggle_tor);tor_text.addWidget(self.tor_button,0,Qt.AlignmentFlag.AlignLeft);banner_row.addLayout(tor_text,1)
        eagle=QLabel();eagle.setPixmap(QPixmap(str(Path(__file__).parent/'assets/privacy-eagle.png')).scaled(96,120,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));banner_row.addWidget(eagle);box.addWidget(banner)
        note=QLabel('Tor no es una VPN para todo el equipo. Iniciar sesión en una cuenta permite que ese servicio te identifique.');note.setObjectName('muted');note.setWordWrap(True);box.addWidget(note)
        self.action(box,'Configurar conexión y puentes  ›',browser._show_advanced_privacy_center)
        _,box=self.card('Privacidad y seguridad','Datos de navegación','Gestiona las cookies, la caché y los datos que conservan los sitios.')
        self.action(box,'Eliminar datos de navegación…  ›',self.wipe)
        self.check(box,'Borrar datos de navegación al cerrar Netlis',browser.settings.clear_on_exit,lambda value:self.privacy('clear_on_exit',value))
        _,box=self.card('Privacidad y seguridad','Historial','Consulta los sitios que has visitado y elimina entradas de tu historial.')
        self.action(box,'Administrar historial  ›',browser._show_history)
        self.privacy_timer=QTimer(self);self.privacy_timer.setInterval(1500);self.privacy_timer.timeout.connect(self.refresh_privacy_status);self.privacy_timer.start();self.refresh_privacy_status()
        _,box=self.card('Contraseñas','Contraseñas guardadas','Administra los datos de acceso de tu bóveda local.')
        self.action(box,'Abrir contraseñas',browser._show_password_vault)
        _,box=self.card('Apariencia','Colores del navegador','Personaliza las pestañas y la barra de navegación.')
        themes=ThemesPanel(browser.appearance.chrome_theme,browser._set_chrome_theme);themes.setMinimumHeight(650);box.addWidget(themes)
        _,box=self.card('Descargas','Archivos descargados','Consulta las descargas de esta sesión y abre la carpeta de destino.')
        self.action(box,'Ver descargas',browser._show_downloads)
        _,box=self.card('Pestañas','Contenedores','Separa los datos de los sitios entre pestañas. Se aplica a las pestañas nuevas.')
        self.check(box,'Usar contenedores aislados por pestaña',browser.settings.isolated_tab_containers,lambda value:self.privacy('isolated_tab_containers',value))
        _,box=self.card('Pestañas','Navegación privada','Abre una ventana privada independiente.')
        self.action(box,'Nueva ventana privada',browser.open_incognito_window)
        try: version=json.loads((Path(__file__).parent/'version.json').read_text()).get('version','')
        except (OSError,ValueError):version=''
        self.card('Acerca de Netlis','Netlis '+version,'Navegador basado en QtWebEngine. La privacidad depende de los ajustes, de las extensiones y de los sitios que visitas.')
        self.empty=QLabel('No se encontraron ajustes.');self.empty.setObjectName('muted');self.content.addWidget(self.empty);self.content.addStretch()
        self.search.textChanged.connect(self.filter);self.select('Inicio')

    def check_default_browser(self, change=False):
        if self.default_worker is not None and self.default_worker.isRunning():
            return
        self.default_button.setEnabled(False)
        self.default_status_label.setText('Aplicando cambio…' if change else 'Comprobando navegador predeterminado…')
        # Keep the worker alive even if its settings tab is closed mid-operation.
        worker=DefaultBrowserWorker(change)
        from PyQt6.QtWidgets import QApplication
        worker.setParent(QApplication.instance())
        QApplication.instance().aboutToQuit.connect(worker.wait)
        self.default_worker=worker
        worker.result.connect(self.default_browser_result)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self.default_browser_finished)
        worker.start()

    def default_browser_finished(self):
        self.default_worker=None

    def default_browser_result(self,active,message):
        from default_browser import available
        self.default_status_label.setText(message)
        self.default_button.setText('Ya es el predeterminado' if active else 'Convertir en predeterminado')
        self.default_button.setEnabled(active is not True and available())

    def refresh_privacy_status(self):
        settings=self.browser.settings
        self.protection_state.setText('Bloqueo de rastreadores activado' if settings.block_trackers else 'Bloqueo de rastreadores desactivado')
        count=getattr(getattr(self.browser,'interceptor',None),'blocked_count',0)
        self.blocked_state.setText(f'{count:,} solicitudes bloqueadas durante esta sesión')
        self.tor_state.setText('Modo Tor seleccionado' if settings.proxy_enabled else 'Estás usando conexión directa')
        self.tor_button.setText('Usar conexión directa' if settings.proxy_enabled else 'Activar Tor')

    def toggle_tor(self):
        self.browser._toggle_turbo_mode()
        self.refresh_privacy_status()

    def choose_engine(self,key):
        self.browser._set_quick_search_engine(key)
        self.engines.blockSignals(True);self.engines.setCurrentIndex(self.engines.findData(key));self.engines.blockSignals(False)
        self.update_engine_buttons()

    def update_engine_buttons(self):
        for key,button in self.engine_buttons.items():
            active=key==self.browser.appearance.search_engine
            button.setText('Predeterminado' if active else 'Elegir');button.setEnabled(not active)

    def card(self,category,title,description):
        card=QFrame();card.setObjectName('card');box=QVBoxLayout(card);box.setContentsMargins(22,20,22,20);box.setSpacing(14)
        label=QLabel(title);label.setObjectName('cardTitle');label.setWordWrap(True);box.addWidget(label)
        label=QLabel(description);label.setObjectName('muted');label.setWordWrap(True);box.addWidget(label)
        self.content.addWidget(card);self.cards.append((category,title+' '+description,card));return card,box
    def action(self,box,label,callback):
        button=QPushButton(label);button.clicked.connect(lambda:callback());box.addWidget(button,0,Qt.AlignmentFlag.AlignLeft)
    def check(self,box,label,value,callback):
        check=QCheckBox(label);check.setChecked(value);check.toggled.connect(callback);box.addWidget(check)
    def select(self,name):
        self.category=name;self.search.blockSignals(True);self.search.clear();self.search.blockSignals(False);self.filter();self.scroll.verticalScrollBar().setValue(0)
    def filter(self):
        query=self.search.text().strip().casefold();count=0
        self.heading.setText('Resultados de búsqueda' if query else self.category)
        for name,button in self.buttons.items():button.setChecked(not query and name==self.category)
        for category,text,card in self.cards:
            content=text+' '+' '.join(c.text() for c in card.findChildren(QCheckBox))
            visible=query in (category+' '+content).casefold() if query else category==self.category
            card.setVisible(visible);count+=visible
        self.empty.setVisible(count==0)
    def appearance(self,field,value):
        setattr(self.browser.appearance,field,value);self.browser.appearance.save(self.browser.appearance_path);self.browser._refresh_home_pages()
    def privacy(self,field,value):
        self.browser._apply_privacy_settings(replace(self.browser.settings,**{field:value}))
        self.refresh_privacy_status()
    def wipe(self):
        if QMessageBox.question(self,'Borrar datos','¿Borrar el historial, las cookies y la caché? Se cerrarán las sesiones de los sitios.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            self.browser._wipe_browsing_data()
