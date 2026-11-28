"""Local browser themes and their previews."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QFrame,QScrollArea

THEMES = {
    'default': ('Ceniza', '#1c1b22', '#2b2a33', '#bfa0ff'),
    'lavender': ('Lavanda', '#281d38', '#3a2b4d', '#c5a4ff'),
    'sunset': ('Atardecer', '#3d2029', '#53303a', '#ffb184'),
    'ocean': ('Océano', '#102b3b', '#1b4053', '#7cd7ed'),
    'forest': ('Bosque', '#172d29', '#29413a', '#99d8b2'),
    'rose': ('Rosa', '#361d36', '#4e2b49', '#efa9d7'),
}

def theme_qss(key):
    _,top,bar,accent=THEMES.get(key,THEMES['default'])
    if key=='default': return ''
    return f'''
        QWidget#windowFrame, QWidget#tabStrip {{ background: {top}; }}
        QToolBar#navBar, QWidget#bookmarksStrip, QWidget#findBar {{ background: {bar}; }}
        QTabBar::tab:selected {{ background: {bar}; border: 1px solid {accent}; }}
        QFrame#urlPill {{ background: {top}; border: 1px solid {bar}; }}
        QLineEdit#urlBarInput {{ selection-background-color: {accent}; selection-color: #18151f; }}
        QProgressBar::chunk {{ background: {accent}; }}
    '''

class ThemePreview(QWidget):
    def __init__(self,key):
        super().__init__(); self.key=key; self.setMinimumHeight(90)
    def paintEvent(self,event):
        _,top,bar,accent=THEMES[self.key]; p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(top)); p.drawRoundedRect(QRectF(0,0,self.width(),90),12,12)
        p.setBrush(QColor(bar)); p.drawRoundedRect(QRectF(9,8,110,27),13,13)
        p.setPen(QPen(QColor(accent),3)); p.drawLine(23,21,99,21)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(bar)); p.drawRect(QRectF(0,42,self.width(),39))
        p.setBrush(QColor(top)); p.drawRoundedRect(QRectF(66,49,max(40,self.width()-106),25),12,12)
        p.setPen(QPen(QColor('#c9c3d2'),2));p.drawLine(17,61,29,61);p.drawLine(23,55,17,61);p.drawLine(23,67,17,61)
        p.drawLine(81,61,max(90,self.width()-62),61)

class ThemesPanel(QWidget):
    def __init__(self,current,apply_theme):
        super().__init__();self.current=current if current in THEMES else 'default';self.apply_theme=apply_theme; self.buttons={}
        layout=QVBoxLayout(self);layout.setContentsMargins(22,60,22,24);layout.setSpacing(20)
        title=QLabel('Administra tus temas');title.setObjectName('heading');layout.addWidget(title)
        self.active=QLabel();self.active.setObjectName('cardTitle');layout.addWidget(self.active)
        self.preview=ThemePreview(self.current);layout.addWidget(self.preview)
        desc=QLabel('Elige los colores de las pestañas y la barra de navegación.');desc.setObjectName('cardDesc');layout.addWidget(desc)
        scroll=QScrollArea();scroll.setWidgetResizable(True);host=QWidget();grid=QGridLayout(host);grid.setSpacing(18)
        for i,(key,(name,*colors)) in enumerate(THEMES.items()):
            card=QFrame();card.setObjectName('hero');box=QVBoxLayout(card);box.setContentsMargins(12,12,12,12);box.addWidget(ThemePreview(key))
            row=QHBoxLayout();row.addWidget(QLabel(name));row.addStretch();button=QPushButton();button.clicked.connect(lambda checked,k=key:self.choose(k));row.addWidget(button);self.buttons[key]=button;box.addLayout(row);grid.addWidget(card,i//2,i%2)
        grid.setRowStretch(3,1);scroll.setWidget(host);layout.addWidget(scroll,1);self.refresh()
    def choose(self,key):
        self.apply_theme(key);self.current=key;self.refresh()
    def refresh(self):
        self.active.setText('Tema activo · '+THEMES[self.current][0]);self.preview.key=self.current;self.preview.update()
        for key,button in self.buttons.items():
            button.setText('Activo' if key==self.current else 'Aplicar');button.setEnabled(key!=self.current)
