"""Shared, restrained styling for browser management pages."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor

MANAGEMENT_QSS = '''
QWidget#settingsPage, QWidget#extensionsPage, QWidget#sidebar, QWidget#side { background: #111114; }
QLabel { color: #efedf4; font-size: 14px; }
QLabel#heading { font-size: 23px; font-weight: 600; }
QLabel#cardTitle { font-size: 16px; font-weight: 600; }
QLabel#muted, QLabel#cardDesc, QLabel#subheading { color: #b4b1ba; font-size: 14px; }
QFrame#card, QFrame#hero, QFrame#settingRow { background: #242428; border: 1px solid #323236; border-radius: 15px; }
QFrame#settingRow:hover { background: #29292e; border-color: #55515d; }
QPushButton { background: transparent; color: #efedf4; border: 1px solid #b99bf6; border-radius: 16px; padding: 6px 15px; font-size: 13px; font-weight: 500; }
QPushButton:hover { background: #343039; border-color: #cfb6ff; }
QPushButton:disabled { color: #9d97a6; border-color: #55505d; background: transparent; }
QPushButton#primary { background: #b99bf6; color: #20182b; border: none; border-radius: 14px; min-height: 20px; padding: 6px 16px; font-weight: 600; }
QPushButton#nav { background: transparent; text-align: left; border: none; border-radius: 21px; padding: 11px 14px; font-size: 14px; font-weight: 400; }
QPushButton#nav:checked { background: #b99bf6; color: #20182b; font-weight: 600; }
QPushButton#nav:hover:!checked { background: #26232b; }
QLineEdit,QComboBox { background: #242428; color: #efedf4; border: 1px solid #8a858e; border-radius: 16px; padding: 6px 12px; font-size: 14px; }
QLineEdit:focus,QComboBox:focus { border-color: #c5a8ff; }
QComboBox QAbstractItemView { background: #242428; color: #efedf4; selection-background-color: #55416d; }
QCheckBox { color: #efedf4; font-size: 14px; padding: 3px 0; spacing: 9px; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 4px; border-color: #8a858e; background: #242428; }
QCheckBox::indicator:checked { background: #b99bf6; }
QScrollBar::handle:vertical { background: #555159; }
'''

def navigation_icon(name):
    pix=QPixmap(20,20);pix.fill(Qt.GlobalColor.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor('#d5cfdf'),1.5));p.setBrush(Qt.BrushStyle.NoBrush)
    if name in ('Inicio','Fondo de inicio'):
        p.drawLine(3,9,10,3);p.drawLine(10,3,17,9);p.drawRect(5,9,10,8);p.drawRect(8,12,4,5)
    elif name=='Buscar':
        p.drawEllipse(3,3,10,10);p.drawLine(12,12,17,17)
    elif name in ('Contraseñas','Privacidad y seguridad'):
        p.drawRoundedRect(4,8,12,10,2,2);p.drawArc(6,1,8,12,0,180*16);p.drawLine(10,12,10,15)
    elif name=='Descargas':
        p.drawLine(10,2,10,13);p.drawLine(6,9,10,13);p.drawLine(14,9,10,13);p.drawLine(3,16,17,16)
    elif name in ('Cuenta','Acerca de Netlis'):
        p.drawEllipse(2,2,16,16);p.drawEllipse(7,5,6,6);p.drawArc(5,12,10,8,0,180*16)
    elif name in ('Apariencia','Temas'):
        p.drawRoundedRect(3,3,14,7,2,2);p.drawLine(10,10,10,17);p.drawLine(7,17,13,17)
    else:
        p.drawRoundedRect(3,3,14,14,3,3);p.drawLine(6,7,14,7);p.drawLine(6,11,14,11);p.drawLine(6,14,11,14)
    p.end();return QIcon(pix)
