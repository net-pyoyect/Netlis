from interface_style import MANAGEMENT_QSS, navigation_icon
"""Embedded extension manager using the existing installation and toggle handlers."""
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QScrollArea, QFrame, QMenu, QStackedWidget)
from dialogs import PluginStoreDialog, IOS_GLASS_QSS

class ExtensionsPage(PluginStoreDialog):
    def __init__(self, plugin_mgr, on_changed, web_ext_api, close_page, appearance, settings, parent=None, current_theme="default", apply_theme=None):
        QDialog.__init__(self,parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.plugin_mgr=plugin_mgr; self.on_changed=on_changed; self.web_ext_api=web_ext_api
        self.close_page=close_page
        self.setObjectName('extensionsPage')
        self.setStyleSheet(IOS_GLASS_QSS+'''
            QWidget#extensionsPage { background: #19151f; }
            QWidget#side { background: #211c29; }
            QLabel#heading { font-size: 23px; }
            QLabel#cardTitle { font-size: 15px; }
            QLabel#cardDesc { font-size: 13px; color: #bdb6c9; }
            QFrame#hero, QFrame#settingRow { background: #2b2533; border: 1px solid #44394e; border-radius: 16px; }
            QFrame#settingRow:hover { background: #31293b; border-color: #6c527e; }
            QPushButton { border-radius: 16px; padding: 10px 16px; }
            QPushButton#primary { background: #bfa0ff; color: #21162e; }
            QPushButton#nav { background: transparent; text-align: left; border: none; padding: 12px 18px; }
            QPushButton#nav:checked { background: #bfa0ff; color: #21162e; font-weight: 600; }
            QPushButton#nav:hover:!checked { background: #352c40; }
            QLineEdit { border-radius: 16px; padding: 10px 14px; background: #27212f; }
        ''')
        self.setStyleSheet(self.styleSheet()+MANAGEMENT_QSS)
        root=QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        side=QWidget(); side.setObjectName('side'); side.setFixedWidth(280)
        nav=QVBoxLayout(side); nav.setContentsMargins(28,64,12,24); nav.setSpacing(4)
        title=QLabel('Complementos'); title.setObjectName('heading'); nav.addWidget(title); nav.addSpacing(18)
        self.nav_buttons=[]
        for text,mode in [('Explorar','all'),('Instalados','installed')]:
            b=QPushButton('  '+text); b.setIcon(navigation_icon(text)); b.setObjectName('nav'); b.setCheckable(True); b.setChecked(mode=='all')
            b.clicked.connect(lambda checked,m=mode:self.set_mode(m)); nav.addWidget(b); self.nav_buttons.append(b)
        self.themes_button=QPushButton('  Temas'); self.themes_button.setIcon(navigation_icon('Temas')); self.themes_button.setObjectName('nav'); self.themes_button.setCheckable(True)
        self.themes_button.clicked.connect(self.show_themes); nav.addWidget(self.themes_button)
        for text,callback in [('Fondo de inicio',appearance),('Ajustes',settings)]:
            b=QPushButton('  '+text); b.setIcon(navigation_icon(text)); b.setObjectName('nav'); b.clicked.connect(callback); nav.addWidget(b)
        nav.addStretch(); root.addWidget(side)
        main=QWidget(); layout=QVBoxLayout(main); layout.setContentsMargins(22,60,22,24); layout.setSpacing(18)
        self.sections=QStackedWidget(); self.sections.setMaximumWidth(740); self.sections.addWidget(main); root.addWidget(self.sections,1); root.addStretch()
        top=QHBoxLayout(); heading=QLabel('Administra tus extensiones'); heading.setObjectName('heading'); top.addWidget(heading); top.addStretch()
        self.active_pill=QLabel(); self.active_pill.setObjectName('subheading'); layout.addWidget(self.active_pill); layout.addLayout(top)
        row=QHBoxLayout(); self.search_input=QLineEdit(); self.search_input.setPlaceholderText('Buscar en tus complementos'); row.addWidget(self.search_input,1)
        install=QPushButton('Instalar desde…'); menu=QMenu(install)
        for label,cb in [('Archivo de extensión…',self._import_web_ext_package),('Carpeta de extensión…',self._import_web_ext_dir),('Archivo de script…',self._import_custom)]: menu.addAction(label,cb)
        install.setMenu(menu); row.addWidget(install); layout.addLayout(row)
        self.cmb_filter=QComboBox(); self.cmb_filter.addItem('Todos','all'); self.cmb_filter.addItem('Instalados','installed'); self.cmb_filter.hide()
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True)
        content=QWidget(); content_layout=QVBoxLayout(content); content_layout.setContentsMargins(0,0,8,0); content_layout.setSpacing(18)
        hero=QFrame(); hero.setObjectName('hero'); hero_row=QHBoxLayout(hero); hero_row.setContentsMargins(24,18,24,18)
        eagle=QLabel(); eagle.setAccessibleName('Águila con piezas de rompecabezas'); pix=QPixmap(str(Path(__file__).parent/'assets/extensions-eagle.png'))
        eagle.setPixmap(pix.scaled(155,155,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)); hero_row.addWidget(eagle)
        intro=QVBoxLayout(); h=QLabel('Haz Netlis a tu manera'); h.setObjectName('heading'); h.setWordWrap(True); intro.addWidget(h)
        desc=QLabel('Añade herramientas para leer, personalizar páginas\ny organizar tu navegación.'); desc.setObjectName('cardDesc'); desc.setWordWrap(True); intro.addWidget(desc)
        browse=QPushButton('Explorar complementos'); browse.setObjectName('primary'); browse.clicked.connect(lambda:self.set_mode('all')); intro.addWidget(browse,0,Qt.AlignmentFlag.AlignLeft); hero_row.addLayout(intro,1); content_layout.addWidget(hero)
        self.section_title=QLabel('Complementos disponibles'); self.section_title.setObjectName('cardTitle'); content_layout.addWidget(self.section_title)
        self.cards_host=QWidget(); self.cards_layout=QVBoxLayout(self.cards_host); self.cards_layout.setContentsMargins(0,0,0,0); self.cards_layout.setSpacing(14); content_layout.addWidget(self.cards_host)
        self.scroll.setWidget(content); layout.addWidget(self.scroll,1)
        url_row=QHBoxLayout(); self.url_install_input=QLineEdit(); self.url_install_input.setPlaceholderText('Dirección de un script (.user.js)'); self.url_install_input.returnPressed.connect(self._install_from_url); url_row.addWidget(self.url_install_input,1)
        url_btn=QPushButton('Instalar script'); url_btn.clicked.connect(self._install_from_url); url_row.addWidget(url_btn); layout.addLayout(url_row)
        self.install_status_lbl=QLabel(''); self.install_status_lbl.setObjectName('subheading'); self.install_status_lbl.setWordWrap(True); layout.addWidget(self.install_status_lbl)
        from theme_page import ThemesPanel
        self.themes=ThemesPanel(current_theme,apply_theme or (lambda key:None)); self.sections.addWidget(self.themes)
        self.search_input.textChanged.connect(self._rebuild_cards); self.cmb_filter.currentIndexChanged.connect(self._rebuild_cards); self._rebuild_cards()

    def show_themes(self):
        self.sections.setCurrentIndex(1); self.themes_button.setChecked(True)
        for button in self.nav_buttons: button.setChecked(False)

    def set_mode(self,mode):
        self.sections.setCurrentIndex(0); self.themes_button.setChecked(False)
        self.cmb_filter.setCurrentIndex(0 if mode=='all' else 1)
        for i,b in enumerate(self.nav_buttons): b.setChecked(i==(0 if mode=='all' else 1))
        self.section_title.setText('Complementos disponibles' if mode=='all' else 'Tus complementos instalados')

    def _rebuild_cards(self):
        super()._rebuild_cards()
        if self.cards_layout.count()==1:
            message=QLabel('No se encontraron complementos.'); message.setObjectName('subheading'); self.cards_layout.insertWidget(0,message)

    def close(self):
        self.close_page()
        return True

    def paintEvent(self,event):
        QWidget.paintEvent(self,event)

    def showEvent(self,event):
        QWidget.showEvent(self,event)

    def mousePressEvent(self,event):
        QWidget.mousePressEvent(self,event)

    def mouseMoveEvent(self,event):
        QWidget.mouseMoveEvent(self,event)

    def mouseReleaseEvent(self,event):
        QWidget.mouseReleaseEvent(self,event)
