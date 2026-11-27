#!/usr/bin/env python3
"""Netlis — Navegador minimalista con transparencia, fondo personalizable, borrado total al salir y soporte Tor/Proxy."""
from __future__ import annotations

import argparse
import atexit
from datetime import datetime
import html as html_lib
import json
import os
from pathlib import Path
try:
    import resource
except ImportError:
    resource = None  # Windows no incluye el módulo Unix 'resource'
import shutil
import sys
import tempfile
import time
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlparse

from PyQt6.QtCore import QEventLoop, QPoint, QPointF, QRectF, QSize, Qt, QThread, QTimer, QUrl, QUrlQuery, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRegion, QShortcut
from PyQt6.QtNetwork import QNetworkProxy
from PyQt6.QtWebEngineCore import (
    QWebEngineFullScreenRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from dialogs import AppearanceDialog, BraveShieldsPopup, DownloadsDialog, HistoryDialog, PluginStoreDialog, PrivacyCenterDialog
from gecko_engine import is_gecko_available, launch_gecko_session
from netlis_search import render_search_loading_html, render_search_results_html, run_netlis_metasearch
from newtab import AppearanceSettings, SEARCH_ENGINES, _image_data_uri, render_new_tab_html
from plugins import PluginManager, compile_plugin_source, read_manifest_summary
from privacy import IP_REGIONS, PrivacySettings, TrackerInterceptor, build_chromium_flags, is_proxy_reachable
from security_shield import (
    analyze_url_threat,
    inspect_download_request,
    render_threat_warning_html,
    verify_downloaded_file_safety,
)
from stability import install_crash_shield, record_diagnostic
from storage import BrowserStorage
from tor_manager import EmbeddedTorManager
from updater import auto_refresh_threats_async

TOR_ENGINE: EmbeddedTorManager | None = None

NEWTAB_URL = "netlis://newtab"

NETLIS_NORMAL_QSS = """
QMainWindow { background: transparent; }
QWidget#windowFrame {
    background-color: #2e2e32;
    border: 1px solid #3c3c40;
    border-radius: 14px;
}
QWidget#tabStrip {
    background-color: #2e2e32;
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
    padding-top: 4px;
}
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent;
    color: #c8c8cc;
    padding: 7px 8px 7px 14px;
    margin: 3px 3px;
    border-radius: 16px;
    min-width: 165px;
    max-width: 250px;
    font-size: 13.5px;
}
QTabBar::tab:selected {
    background-color: #3e3e44;
    border: 1px solid rgba(255, 255, 255, 55);
    color: #ffffff;
}
QTabBar::tab:hover:!selected { background-color: #36363c; color: #ffffff; }
QPushButton#tabCloseBtn {
    min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px;
    padding: 0px; margin-right: 6px;
    border-radius: 9px;
    background-color: transparent;
    border: none;
    color: #c8c8cc;
    font-size: 11px;
    font-weight: 700;
}
QPushButton#tabCloseBtn:hover { background-color: rgba(255, 255, 255, 38); color: #ffffff; }
QMenu {
    background-color: #3a3a3e;
    color: #f4f4f6;
    border: 1px solid #525257;
    border-radius: 8px;
    padding: 6px;
    font-size: 13.5px;
}
QMenu::item {
    padding: 8px 18px;
    border-radius: 6px;
}
QMenu::item:selected {
    background-color: #545458;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #48484d;
    margin: 4px 8px;
}
QToolBar#navBar {
    background-color: #545458;
    border: none;
    spacing: 6px;
    padding: 6px 12px;
    min-height: 44px;
}
QToolButton {
    background-color: transparent;
    color: #e4e4e7;
    border: none;
    border-radius: 7px;
    padding: 6px 9px;
    font-size: 17px;
}
QToolButton:hover { background-color: #636368; color: #ffffff; }
QToolButton:pressed { background-color: #48484b; }
QPushButton {
    background-color: transparent;
    color: #e4e4e7;
    border: none;
    border-radius: 7px;
    padding: 6px 9px;
    font-size: 14px;
}
QPushButton:hover { background-color: #636368; color: #ffffff; }
QPushButton#pluginIconBtn {
    min-width: 34px; max-width: 34px; min-height: 32px; max-height: 32px;
    padding: 0px;
    border-radius: 7px;
    background-color: transparent;
    border: none;
    font-size: 16px;
}
QPushButton#pluginIconBtn:hover { background-color: #636368; }
QPushButton#shieldBtn {
    background-color: #b02a37;
    border: none;
    color: #ffffff;
    font-weight: 700;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    min-height: 26px;
}
QPushButton#shieldBtn:hover { background-color: #c83442; }
QPushButton#ipBtn {
    background-color: #48484b;
    border: none;
    color: #ececef;
    border-radius: 7px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
    min-height: 26px;
}
QPushButton#ipBtn:hover { background-color: #636368; }
QPushButton#winBtn, QPushButton#winCloseBtn {
    min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
    padding: 0px;
    border-radius: 13px;
    background-color: #434347;
    color: #e4e4e7;
    font-size: 12px;
}
QPushButton#winBtn:hover { background-color: #5a5a60; color: #ffffff; }
QPushButton#winCloseBtn:hover { background-color: #e0434f; color: #ffffff; }
QLineEdit#urlBarInput {
    background: transparent;
    border: none;
    color: #fbfbfe;
    padding: 5px 10px 5px 4px;
    font-size: 14px;
    selection-background-color: #0060df;
}
QFrame#urlPill {
    background-color: #48484b;
    border: 1px solid transparent;
    border-radius: 19px;
}
QFrame#urlPill:hover { background-color: #4f4f53; }
QPushButton#searchPickBtn {
    background-color: #5b5b60;
    border: none;
    border-radius: 14px;
    padding: 3px 9px 3px 7px;
    margin: 3px 2px 3px 4px;
    color: #f2f2f6;
    font-size: 11px;
    min-height: 26px;
}
QPushButton#searchPickBtn:hover { background-color: #6c6c72; }
QWidget#bookmarksStrip {
    background-color: #545458;
    border-bottom: 1px solid #3c3c40;
}
QPushButton#bmLinkBtn {
    background: transparent;
    border: none;
    color: #e0e0e4;
    font-size: 12.5px;
    padding: 3px 9px;
    border-radius: 5px;
}
QPushButton#bmLinkBtn:hover { background-color: #636368; color: #ffffff; }
QProgressBar { background-color: transparent; border: none; max-height: 2px; border-radius: 1px; }
QProgressBar::chunk { background-color: #b499fa; border-radius: 1px; }
QWidget#findBar {
    background-color: #545458;
    border-bottom: 1px solid #3c3c40;
}
QStackedWidget#contentArea { background-color: #131215; }
"""

NETLIS_ANTIGRAVITY_QSS = """
QMainWindow { background: transparent; }
QWidget#windowFrame {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(12, 14, 28, 245), stop:1 rgba(20, 16, 42, 245));
    border: 1px solid rgba(143, 122, 230, 130);
    border-radius: 14px;
}
QWidget#tabStrip {
    background: transparent;
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
    padding-top: 4px;
}
QTabBar { background: transparent; }
QTabBar::tab {
    background: rgba(255, 255, 255, 10);
    color: #c2c8e8;
    padding: 8px 8px 8px 14px;
    margin: 2px 3px 0px 3px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    min-width: 165px;
    max-width: 250px;
    font-size: 13.5px;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(124, 92, 255, 110), stop:1 rgba(56, 189, 248, 85));
    border: 1px solid rgba(165, 148, 255, 120);
    border-bottom: none;
    color: #ffffff;
}
QTabBar::tab:hover:!selected { background: rgba(143, 122, 230, 42); color: #ffffff; }
QPushButton#tabCloseBtn {
    min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px;
    padding: 0px; margin-right: 6px;
    border-radius: 9px;
    background-color: transparent;
    border: none;
    color: #cfd6f6;
    font-size: 11px;
    font-weight: 700;
}
QPushButton#tabCloseBtn:hover { background-color: rgba(244, 63, 94, 180); color: #ffffff; }
QMenu {
    background-color: rgba(16, 19, 38, 246);
    color: #f2f4ff;
    border: 1px solid rgba(143, 122, 230, 110);
    border-radius: 12px;
    padding: 6px;
    font-size: 13.5px;
}
QMenu::item { padding: 8px 18px; border-radius: 8px; }
QMenu::item:selected { background-color: rgba(124, 92, 255, 95); color: #ffffff; }
QMenu::separator { height: 1px; background: rgba(143, 122, 230, 50); margin: 4px 8px; }
QToolBar#navBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(22, 25, 50, 232), stop:1 rgba(26, 22, 54, 232));
    border: none;
    border-top: 1px solid rgba(143, 122, 230, 65);
    border-bottom: 1px solid rgba(56, 189, 248, 45);
    spacing: 6px;
    padding: 6px 12px;
    min-height: 44px;
}
QToolButton {
    background-color: rgba(255, 255, 255, 10);
    color: #e6ebff;
    border: 1px solid rgba(143, 122, 230, 38);
    border-radius: 9px;
    padding: 6px 9px;
    font-size: 17px;
}
QToolButton:hover { background-color: rgba(124, 92, 255, 80); border-color: rgba(56, 189, 248, 130); color: #ffffff; }
QPushButton {
    background-color: rgba(255, 255, 255, 10);
    color: #e6ebff;
    border: 1px solid rgba(143, 122, 230, 35);
    border-radius: 9px;
    padding: 6px 9px;
    font-size: 14px;
}
QPushButton:hover { background-color: rgba(124, 92, 255, 80); border-color: rgba(56, 189, 248, 130); color: #ffffff; }
QPushButton#pluginIconBtn {
    min-width: 34px; max-width: 34px; min-height: 32px; max-height: 32px;
    padding: 0px; border-radius: 9px;
    background-color: rgba(255, 255, 255, 14);
    border: 1px solid rgba(143, 122, 230, 55);
    font-size: 16px;
}
QPushButton#pluginIconBtn:hover { background-color: rgba(124, 92, 255, 90); border-color: #38bdf8; }
QPushButton#shieldBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c5cff, stop:1 #2563eb);
    border: 1px solid rgba(186, 174, 255, 130);
    color: #ffffff;
    font-weight: 700;
    border-radius: 9px;
    padding: 4px 10px;
    font-size: 12px;
    min-height: 26px;
}
QPushButton#shieldBtn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9176ff, stop:1 #38bdf8); }
QPushButton#ipBtn {
    background-color: rgba(255, 255, 255, 18);
    border: 1px solid rgba(56, 189, 248, 85);
    color: #bae6fd;
    border-radius: 9px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
    min-height: 26px;
}
QPushButton#ipBtn:hover { background-color: rgba(56, 189, 248, 55); color: #ffffff; }
QPushButton#winBtn, QPushButton#winCloseBtn {
    min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
    padding: 0px; border-radius: 13px;
    background-color: rgba(255, 255, 255, 24);
    color: #e6ebff; font-size: 12px;
}
QPushButton#winBtn:hover { background-color: rgba(124, 92, 255, 130); color: #ffffff; }
QPushButton#winCloseBtn:hover { background-color: #e11d48; color: #ffffff; }
QLineEdit#urlBarInput {
    background: transparent;
    border: none;
    color: #f8faff;
    padding: 5px 10px 5px 4px;
    font-size: 14px;
    selection-background-color: #7c5cff;
}
QFrame#urlPill {
    background-color: rgba(10, 12, 24, 185);
    border: 1px solid rgba(143, 122, 230, 85);
    border-radius: 19px;
}
QFrame#urlPill:hover { background-color: rgba(16, 18, 36, 210); border-color: rgba(165, 148, 255, 140); }
QPushButton#searchPickBtn {
    background-color: rgba(124, 92, 255, 75);
    border: 1px solid rgba(143, 122, 230, 90);
    border-radius: 14px;
    padding: 3px 9px 3px 7px;
    margin: 3px 2px 3px 4px;
    color: #f2f4ff;
    font-size: 11px;
    min-height: 26px;
}
QPushButton#searchPickBtn:hover { background-color: rgba(124, 92, 255, 130); border-color: #38bdf8; }
QWidget#bookmarksStrip {
    background-color: rgba(16, 19, 38, 215);
    border-bottom: 1px solid rgba(143, 122, 230, 45);
}
QPushButton#bmLinkBtn {
    background: transparent; border: none; color: #cbd5f5;
    font-size: 12.5px; padding: 3px 9px; border-radius: 6px;
}
QPushButton#bmLinkBtn:hover { background-color: rgba(124, 92, 255, 75); color: #ffffff; }
QProgressBar { background-color: transparent; border: none; max-height: 2px; border-radius: 1px; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c5cff, stop:1 #38bdf8); border-radius: 1px; }
QWidget#findBar { background-color: rgba(18, 21, 42, 235); border-bottom: 1px solid rgba(143, 122, 230, 75); }
QStackedWidget#contentArea { background-color: #090b16; border-bottom-left-radius: 14px; border-bottom-right-radius: 14px; }
"""

NETLIS_INCOGNITO_QSS = """
QMainWindow { background: transparent; }
QWidget#windowFrame {
    background-color: #1a1326;
    border: 1px solid #3a2b54;
    border-radius: 12px;
}
QWidget#tabStrip { background: transparent; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent;
    color: #b9a8d8;
    padding: 7px 14px;
    margin: 3px 2px;
    border-radius: 8px;
    min-width: 120px;
    max-width: 220px;
}
QTabBar::tab:selected { background-color: #3d2d5c; color: #ffffff; }
QTabBar::tab:hover:!selected { background-color: #2b2042; color: #ffffff; }
QPushButton#tabCloseBtn {
    min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px;
    padding: 0px; margin-left: 4px;
    border-radius: 10px;
    background-color: rgba(255, 255, 255, 22);
    border: none;
    color: #f4eeff;
    font-size: 11px;
    font-weight: 700;
}
QPushButton#tabCloseBtn:hover { background-color: #e0434f; color: #ffffff; }
QPushButton#pluginIconBtn {
    min-width: 36px; max-width: 36px; min-height: 34px; max-height: 34px;
    padding: 0px;
    border-radius: 10px;
    background-color: #33264d;
    border: 1px solid #4d3a73;
}
QPushButton#pluginIconBtn:hover { background-color: #42315f; }
QToolBar#navBar {
    background-color: #271d3b;
    border: none;
    border-radius: 12px;
    spacing: 6px;
    padding: 7px 10px;
    min-height: 44px;
}
QToolButton {
    background-color: transparent;
    color: #ece4fc;
    border: none;
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 14px;
}
QToolButton:hover { background-color: #3d2d5c; }
QPushButton {
    background-color: transparent;
    color: #ece4fc;
    border: none;
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 14px;
}
QPushButton:hover { background-color: #3d2d5c; }
QPushButton#shieldBtn {
    background-color: #33264d;
    color: #c9a8ff;
    font-weight: 600;
    border-radius: 10px;
    padding: 5px 12px;
    font-size: 12px;
}
QPushButton#shieldBtn:hover { background-color: #42315f; }
QPushButton#ipBtn {
    background-color: #33264d;
    color: #e2d6ff;
    border-radius: 10px;
    padding: 5px 12px;
    font-size: 12px;
}
QPushButton#ipBtn:hover { background-color: #42315f; }
QLabel#incognitoBadge {
    background-color: #5b34a8;
    color: #ffffff;
    border-radius: 11px;
    padding: 4px 11px;
    font-weight: 700;
    font-size: 11px;
}
QPushButton#winBtn, QPushButton#winCloseBtn {
    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
    padding: 0px;
    border-radius: 12px;
    background-color: #33264d;
    color: #ece4fc;
    font-size: 11px;
}
QPushButton#winBtn:hover { background-color: #4a3870; }
QPushButton#winCloseBtn:hover { background-color: #e0434f; color: #ffffff; }
QLineEdit {
    background-color: #150f20;
    color: #f8f5ff;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 13px;
    selection-background-color: #9d6bff;
}
QLineEdit:focus { border: 2px solid #b48cff; padding: 6px 13px; }
QProgressBar { background-color: transparent; border: none; max-height: 2px; }
QProgressBar::chunk { background-color: #b48cff; }
QWidget#findBar {
    background-color: #271d3b;
    border: 1px solid #4d3a73;
    border-radius: 10px;
}
QStackedWidget#contentArea { background-color: #271d3b; border-radius: 10px; }
"""


def _make_search_engine_icon(engine_key: str, netlis_icon: QIcon | None = None) -> QIcon:
    """Dibuja un ícono vectorial nítido (18x18) para cada buscador del menú rápido."""
    if engine_key == "netlis" and netlis_icon is not None and not netlis_icon.isNull():
        return netlis_icon
    pm = QPixmap(20, 20)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    colors = {
        "duckduckgo": ("#de5833", "D", "#ffffff"),
        "google": ("#ffffff", "G", "#4285f4"),
        "bing": ("#0ea5e9", "b", "#ffffff"),
        "brave": ("#fb542b", "B", "#ffffff"),
        "startpage": ("#6573ff", "S", "#ffffff"),
        "wikipedia": ("#e6e8ee", "W", "#1c1b22"),
    }
    bg_hex, letter, fg_hex = colors.get(engine_key, ("#7c5cff", "N", "#ffffff"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(bg_hex))
    p.drawEllipse(QRectF(1.5, 1.5, 17.0, 17.0))
    p.setPen(QColor(fg_hex))
    f = p.font()
    f.setBold(True)
    f.setPixelSize(11)
    p.setFont(f)
    p.drawText(QRectF(1.5, 1.5, 17.0, 17.0), Qt.AlignmentFlag.AlignCenter, letter)
    p.end()
    return QIcon(pm)


def _make_menu_action_icon(kind: str) -> QIcon:
    """Dibuja íconos vectoriales minimalistas para Marcadores, Pestañas, Historial, Seguridad y Ajustes."""
    pm = QPixmap(18, 18)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(232, 232, 242), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    if kind == "star":
        p.drawPolygon(QPolygonF([
            QPointF(9, 2), QPointF(11.1, 6.4), QPointF(16, 7.1), QPointF(12.4, 10.5),
            QPointF(13.3, 15.3), QPointF(9, 13), QPointF(4.7, 15.3), QPointF(5.6, 10.5),
            QPointF(2, 7.1), QPointF(6.9, 6.4),
        ]))
    elif kind == "tabs":
        p.drawRoundedRect(QRectF(2.5, 4.5, 13, 10), 2.0, 2.0)
        p.drawLine(QPointF(2.5, 7.5), QPointF(15.5, 7.5))
    elif kind == "history":
        p.drawEllipse(QRectF(2.5, 2.5, 13, 13))
        p.drawLine(QPointF(9, 5.5), QPointF(9, 9))
        p.drawLine(QPointF(9, 9), QPointF(11.8, 10.8))
    elif kind == "bolt":
        p.drawPolyline(QPolygonF([
            QPointF(10.5, 2), QPointF(5, 10), QPointF(9.5, 10),
            QPointF(7.5, 16), QPointF(13, 8), QPointF(8.5, 8),
        ]))
    else:  # gear
        p.drawEllipse(QRectF(6.2, 6.2, 5.6, 5.6))
        p.drawEllipse(QRectF(3.0, 3.0, 12.0, 12.0))
    p.end()
    return QIcon(pm)


def _make_plugin_puzzle_icon() -> QIcon:
    """Dibuja un ícono vectorial nítido de pieza de plugin (estilo extensiones Firefox/Chrome)."""
    pm = QPixmap(22, 22)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(242, 242, 252), 1.8)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(QColor(255, 255, 255, 32))

    path = QPainterPath()
    path.moveTo(5, 7)
    path.lineTo(9, 7)
    path.arcTo(QRectF(9, 3.5, 4, 4), 180, -180)
    path.lineTo(17, 7)
    path.lineTo(17, 11)
    path.arcTo(QRectF(15.2, 11, 4, 4), 90, -180)
    path.lineTo(17, 18)
    path.lineTo(5, 18)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def _make_account_avatar_icon(active: bool = False) -> QIcon:
    """Dibuja un ícono circular de cuenta/perfil estilo Firefox para la Bóveda Google."""
    pm = QPixmap(22, 22)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    ring_color = QColor(96, 165, 250) if active else QColor(235, 235, 245, 210)
    p.setPen(QPen(ring_color, 1.6))
    p.setBrush(QColor(96, 165, 250, 45) if active else QColor(255, 255, 255, 22))
    p.drawEllipse(QRectF(2.0, 2.0, 18.0, 18.0))
    # Cabeza y hombros
    fg = QColor(242, 242, 252)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fg)
    p.drawEllipse(QRectF(8.3, 6.2, 5.4, 5.4))
    shoulders = QPainterPath()
    shoulders.moveTo(5.6, 17.2)
    shoulders.quadTo(11.0, 12.2, 16.4, 17.2)
    p.drawPath(shoulders)
    p.end()
    return QIcon(pm)


def normalize_input_to_url(raw: str, search_engine: str = "duckduckgo") -> QUrl:
    """Convierte texto de la barra de direcciones en URL o búsqueda con el buscador elegido."""
    text = raw.strip()
    if not text or text == NEWTAB_URL:
        return QUrl(NEWTAB_URL)
    if "://" in text:
        return QUrl(text)
    if " " not in text and ("." in text or text.startswith("localhost")):
        return QUrl(f"https://{text}")
    _, base_url = SEARCH_ENGINES.get(search_engine, SEARCH_ENGINES["duckduckgo"])
    return QUrl(f"{base_url}{quote_plus(text)}")


class _NetlisSearchWorker(QThread):
    """Ejecuta la metabúsqueda privada en segundo plano sin congelar la interfaz."""

    ready = pyqtSignal(dict)

    def __init__(self, query: str, use_tor: bool, parent=None) -> None:
        super().__init__(parent)
        self.query = query
        self.use_tor = use_tor

    def run(self) -> None:
        data = run_netlis_metasearch(self.query, use_tor=self.use_tor)
        self.ready.emit(data)


def _render_tor_warmup_html(target_url: str) -> str:
    safe_url = html_lib.escape(target_url)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Conectando Tor — Netlis</title>
<style>
body {{
    margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #1c1b22; color: #f4f4fc; font: 15px/1.55 system-ui, -apple-system, sans-serif;
}}
.card {{
    max-width: 460px; padding: 28px 32px; border-radius: 18px; text-align: center;
    background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.16);
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.45);
}}
.spinner {{
    width: 34px; height: 34px; margin: 0 auto 16px; border-radius: 50%;
    border: 3px solid rgba(0, 221, 255, 0.22); border-top-color: #00ddff;
    animation: spin 0.9s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
h2 {{ margin: 0 0 8px; font-size: 18px; font-weight: 700; }}
p {{ margin: 0; color: rgba(235, 235, 248, 0.78); font-size: 13px; word-break: break-all; }}
</style></head><body>
<div class="card">
  <div class="spinner"></div>
  <h2>Conectando circuito seguro Tor…</h2>
  <p>Protegiendo tu IP antes de abrir <strong>{safe_url}</strong>.<br>Se cargará automáticamente en un instante.</p>
</div>
</body></html>"""


def _is_google_vault_host(host: str) -> bool:
    """Devuelve True solo para dominios oficiales de Google/YouTube (cerco estricto de la Bóveda Google)."""
    h = (host or "").lower().strip(".")
    if not h:
        return False
    allowed = (
        "google.com",
        "youtube.com",
        "googleusercontent.com",
        "gstatic.com",
        "googleapis.com",
        "googlevideo.com",
        "ytimg.com",
        "ggpht.com",
    )
    return any(h == d or h.endswith("." + d) for d in allowed)


class SecureWebPage(QWebEnginePage):
    """Página endurecida: deniega permisos espía, abre pestañas del usuario y bloquea popups/phishing."""

    def __init__(self, profile: QWebEngineProfile, parent=None, browser_win: "BrowserWindow | None" = None) -> None:
        super().__init__(profile, parent)
        self.browser_win = browser_win
        self.featurePermissionRequested.connect(self._handle_feature_permission)

    def certificateError(self, error) -> bool:
        """Rechaza estrictamente certificados TLS inválidos, caducados o MITM."""
        try:
            error.rejectCertificate()
        except Exception:
            pass
        if self.browser_win is not None:
            host = error.url().host() if hasattr(error, "url") else ""
            self.browser_win.interceptor._mark_blocked(host, f"TLS inválido ({host})")
        return False

    def _handle_feature_permission(self, security_origin: QUrl, feature: QWebEnginePage.Feature) -> None:
        media_labels = {
            QWebEnginePage.Feature.MediaAudioCapture: "el micrófono",
            QWebEnginePage.Feature.MediaVideoCapture: "la cámara",
            QWebEnginePage.Feature.MediaAudioVideoCapture: "la cámara y el micrófono",
            QWebEnginePage.Feature.DesktopVideoCapture: "compartir pantalla",
            QWebEnginePage.Feature.DesktopAudioVideoCapture: "compartir pantalla y audio",
        }
        if feature in media_labels and self.browser_win is not None:
            host = security_origin.host() or security_origin.toString()
            key = (host, int(feature.value))
            cached = self.browser_win._session_media_permissions.get(key)
            if cached is None:
                ans = QMessageBox.question(
                    self.browser_win,
                    "Permiso de videollamada — Netlis",
                    f"¿Permitir que {host} use {media_labels[feature]} durante esta sesión?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                cached = ans == QMessageBox.StandardButton.Yes
                self.browser_win._session_media_permissions[key] = cached
            policy = (
                QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                if cached
                else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
            )
            self.setFeaturePermission(security_origin, feature, policy)
            return
        self.setFeaturePermission(
            security_origin,
            feature,
            QWebEnginePage.PermissionPolicy.PermissionDeniedByUser,
        )

    def createWindow(self, win_type: QWebEnginePage.WebWindowType) -> QWebEnginePage | None:
        """Permite clics medios / enlaces en pestaña nueva del usuario mientras bloquea ventanas emergentes."""
        if self.browser_win is None:
            return None
        cur_host = self.url().host().lower()
        allow_dialog = (
            cur_host == "zoom.us"
            or cur_host.endswith(".zoom.us")
            or cur_host == "accounts.google.com"
        )
        if win_type == QWebEnginePage.WebWindowType.WebDialog and not allow_dialog:
            return None
        switch_to = win_type != QWebEnginePage.WebWindowType.WebBrowserBackgroundTab
        in_google_vault = (
            self.browser_win._google_vault_profile is not None
            and self.profile() is self.browser_win._google_vault_profile
        )
        new_view = self.browser_win.add_new_tab(
            QUrl("about:blank"),
            "[G] Cargando…" if in_google_vault else "Cargando…",
            switch_to=switch_to,
            google_vault=in_google_vault,
        )
        return new_view.page()

    def acceptNavigationRequest(self, url: QUrl, nav_type: QWebEnginePage.NavigationType, is_main_frame: bool) -> bool:
        url_str = url.toString()
        if self.browser_win is not None and is_main_frame:
            is_internal = url_str.startswith(("netlis://", "about:", "data:"))
            allow_js = True if is_internal else (not self.browser_win.settings.safest_no_js)
            self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, allow_js)
            if url.scheme().lower() in ("http", "https") and isinstance(self.parent(), QWebEngineView):
                self.browser_win._last_requested_url[self.parent()] = QUrl(url)
        if url_str == NEWTAB_URL and self.browser_win is not None and isinstance(self.parent(), QWebEngineView):
            QTimer.singleShot(0, lambda v=self.parent(): self.browser_win._load_newtab_html(v))
            return False
        if url_str == "netlis://appearance" and self.browser_win is not None:
            QTimer.singleShot(0, self.browser_win._show_appearance)
            return False
        if url_str == "netlis://history" and self.browser_win is not None:
            QTimer.singleShot(0, self.browser_win._show_history)
            return False
        if url_str.startswith("netlis://search") and self.browser_win is not None and isinstance(self.parent(), QWebEngineView):
            q_val = QUrlQuery(url).queryItemValue("q")
            QTimer.singleShot(0, lambda v=self.parent(), q=q_val: self.browser_win._load_netlis_search(v, q))
            return False

        scheme = url.scheme().lower()
        if scheme in ("javascript", "vbscript", "file"):
            return False
        if (
            scheme == "data"
            and is_main_frame
            and nav_type in (
                QWebEnginePage.NavigationType.NavigationTypeLinkClicked,
                QWebEnginePage.NavigationType.NavigationTypeRedirect,
            )
        ):
            return False

        # Cerco estricto de Bóveda Google: cualquier enlace externo sale a una pestaña normal limpia (sin cookies de Google)
        if (
            is_main_frame
            and self.browser_win is not None
            and self.browser_win._google_vault_profile is not None
            and self.profile() is self.browser_win._google_vault_profile
            and scheme in ("http", "https")
            and not _is_google_vault_host(url.host())
        ):
            QTimer.singleShot(
                0,
                lambda u=QUrl(url): self.browser_win.add_new_tab(u, u.host() or "Externo", switch_to=True),
            )
            return False

        if (
            is_main_frame
            and self.browser_win is not None
            and self.browser_win.settings.phishing_and_malware_guard
        ):
            is_threat, reason = analyze_url_threat(url_str)
            if is_threat:
                self.browser_win.interceptor._mark_blocked()
                warn_html = render_threat_warning_html(url_str, reason)
                QTimer.singleShot(0, lambda: self.setHtml(warn_html, QUrl("about:blank")))
                return False

        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class BrowserWindow(QMainWindow):
    """Ventana principal minimalista de Netlis."""

    _open_windows: list["BrowserWindow"] = []

    def __init__(
        self,
        incognito: bool = False,
        settings: PrivacySettings | None = None,
        appearance: AppearanceSettings | None = None,
        data_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.incognito = incognito
        self.data_dir = data_dir or (Path(__file__).resolve().parent / "data")
        self.settings_path = self.data_dir / "privacidad.json"
        self.appearance_path = self.data_dir / "apariencia.json"
        self.settings = settings or PrivacySettings.load(self.settings_path)
        self.appearance = appearance or AppearanceSettings.load(self.appearance_path)
        self.storage = BrowserStorage(self.data_dir)
        self.plugin_mgr = PluginManager(self.data_dir)
        self._open_windows.append(self)

        self._apply_theme_stylesheet()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle("Netlis Privado" if self.incognito else "Netlis")
        logo_trans = Path(__file__).resolve().parent / "assets" / "netlis_logo_transparent.png"
        logo_path = logo_trans if logo_trans.exists() else (Path(__file__).resolve().parent / "assets" / "netlis_logo.jpg")
        self._netlis_icon = QIcon(str(logo_path)) if logo_path.exists() else QIcon()
        if not self._netlis_icon.isNull():
            self.setWindowIcon(self._netlis_icon)
        self.resize(1380, 860)
        self._drag_pos = None
        self.setWindowOpacity(max(0.55, min(1.0, self.appearance.opacity_percent / 100.0)))

        self._ephemeral_dirs: list[Path] = []
        self._profile_seq = 0
        # Perfil efímero en /tmp (tmpfs RAM) con nombre propio para soportar QWebEngineExtensionManager C++ sin persistir datos
        if self.incognito or self.settings.clear_on_exit:
            self.profile = self._create_ephemeral_named_profile("main")
        else:
            profile_dir = self.data_dir / "profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            self.profile = QWebEngineProfile("Netlis", self)
            self.profile.setPersistentStoragePath(str(profile_dir))
            self.profile.setCachePath(str(profile_dir / "cache"))

        self.interceptor = TrackerInterceptor(
            self.settings,
            on_blocked=self._schedule_shield_refresh,
            anti_spy_enabled=lambda: self.plugin_mgr.is_enabled("anti-espionaje-total"),
        )
        self._tab_profiles: dict[QWebEngineView, QWebEngineProfile] = {}
        self._google_vault_profile: QWebEngineProfile | None = None
        self._session_media_permissions: dict[tuple[str, int], bool] = {}
        self.blocked_downloads = 0
        self.downloads_records: list[dict] = []
        self._closed_tabs: list[tuple[str, str]] = []
        self._tor_pending_urls: dict[QWebEngineView, QUrl] = {}
        self._last_requested_url: dict[QWebEngineView, QUrl] = {}
        self.recovered_crashes = 0
        self.unresponsive_recoveries = 0
        self._was_maximized_before_fs = False
        self._configure_web_profile(self.profile)

        self._shield_timer = QTimer(self)
        self._shield_timer.setSingleShot(True)
        self._shield_timer.setInterval(200)
        self._shield_timer.timeout.connect(self._update_shield_label)

        # Ahorro automático de RAM: congela y descarta pestañas inactivas en segundo plano
        self._tab_last_active: dict[QWebEngineView, float] = {}
        self._ram_timer = QTimer(self)
        self._ram_timer.setInterval(30000)
        self._ram_timer.timeout.connect(self._suspend_inactive_tabs)
        self._ram_timer.start()

        # Guardián anti-congelamiento de pestañas activas (Health Watchdog)
        self._watchdog_pending = False
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(25000)
        self._watchdog_timer.timeout.connect(self._check_active_tab_health)
        self._watchdog_timer.start()

        self._tor_poll_timer = QTimer(self)
        self._tor_poll_timer.setInterval(1500)
        self._tor_poll_timer.timeout.connect(self._refresh_network_pill)
        self._tor_poll_timer.start()

        self._build_ui()
        self._bind_shortcuts()
        self.add_new_tab(None, "Privada" if self.incognito else "Inicio")

    def _create_ephemeral_named_profile(self, tag: str) -> QWebEngineProfile:
        self._profile_seq += 1
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"netlis-{tag}-"))
        self._ephemeral_dirs.append(tmp_dir)
        atexit.register(shutil.rmtree, tmp_dir, True)
        prof = QWebEngineProfile(f"Netlis_{tag}_{os.getpid()}_{id(self)}_{self._profile_seq}", self)
        prof.setPersistentStoragePath(str(tmp_dir))
        prof.setCachePath(str(tmp_dir / "cache"))
        prof.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        prof.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        return prof

    def _all_profiles(self) -> list[QWebEngineProfile]:
        seen = {id(self.profile): self.profile}
        for p in self._tab_profiles.values():
            seen[id(p)] = p
        if self._google_vault_profile is not None:
            seen[id(self._google_vault_profile)] = self._google_vault_profile
        return list(seen.values())

    def _get_google_vault_profile(self) -> QWebEngineProfile:
        if self._google_vault_profile is not None:
            return self._google_vault_profile
        vault_dir = self.data_dir / "google_vault"
        storage_dir = vault_dir / "storage"
        cache_dir = vault_dir / "cache"
        storage_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        prof = QWebEngineProfile("Netlis_Google_Vault", self)
        prof.setPersistentStoragePath(str(storage_dir))
        prof.setCachePath(str(cache_dir))
        prof.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        prof.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        self._google_vault_profile = prof
        self._configure_web_profile(prof)
        return prof

    def _open_google_vault(self, target_url: str = "https://accounts.google.com") -> None:
        vault_prof = self._get_google_vault_profile()
        for i in range(self.stack.count()):
            v = self.stack.widget(i)
            if isinstance(v, QWebEngineView) and v.page().profile() is vault_prof:
                self.tab_bar.setCurrentIndex(i)
                return
        self.add_new_tab(QUrl(target_url), "[G] Cuenta Google", switch_to=True, google_vault=True)

    def _wipe_google_vault(self) -> None:
        from PyQt6 import sip

        if self._google_vault_profile is not None:
            for i in range(self.stack.count() - 1, -1, -1):
                v = self.stack.widget(i)
                if isinstance(v, QWebEngineView) and v.page().profile() is self._google_vault_profile:
                    if self.stack.count() == 1:
                        self.add_new_tab(None, "Inicio", switch_to=False)
                    self.close_tab(i)
            try:
                self._google_vault_profile.cookieStore().deleteAllCookies()
                self._google_vault_profile.clearHttpCache()
            except Exception:
                pass
            if not sip.isdeleted(self._google_vault_profile):
                sip.delete(self._google_vault_profile)
            self._google_vault_profile = None
        shutil.rmtree(self.data_dir / "google_vault", ignore_errors=True)
        QMessageBox.information(
            self,
            "Bóveda Google borrada",
            "Se cerró tu sesión de Google y se eliminaron todas sus cookies y datos locales.",
        )

    def _load_google_account_info(self) -> dict[str, str]:
        info = safe_load_json(self.data_dir / "google_vault" / "account_info.json", {})
        return info if isinstance(info, dict) else {}

    def _sync_google_vault_account_badge(self, view: QWebEngineView) -> None:
        if self._google_vault_profile is None or view.page().profile() is not self._google_vault_profile:
            return
        if not _is_google_vault_host(view.url().host()):
            return
        js = """
        (() => {
            try {
                const emailRe = /([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})/;
                const elEmail = document.querySelector('[data-email]');
                if (elEmail) {
                    const em = (elEmail.getAttribute('data-email') || '').trim();
                    if (emailRe.test(em)) return { name: (elEmail.textContent || '').trim(), email: em };
                }
                const els = document.querySelectorAll('a[aria-label*="@"], button[aria-label*="@"]');
                for (const el of els) {
                    const lbl = el.getAttribute('aria-label') || '';
                    const m = lbl.match(emailRe);
                    if (m) {
                        const clean = lbl.replace(/^(Cuenta de Google|Google Account)\\s*:\\s*/i, '');
                        const name = clean.split('(')[0].replace(m[1], '').trim();
                        return { name, email: m[1] };
                    }
                }
            } catch (e) {}
            return null;
        })();
        """

        def _on_res(res) -> None:
            if not isinstance(res, dict):
                return
            email = str(res.get("email") or "").strip()
            name = str(res.get("name") or "").strip()
            if not email or "@" not in email:
                return
            vault_dir = self.data_dir / "google_vault"
            vault_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(vault_dir / "account_info.json", {"name": name, "email": email})
            self.google_btn.setIcon(_make_account_avatar_icon(active=True))
            self.google_btn.setToolTip(f"Cuenta Google aislada ({email}) — ninguna otra app puede ver tu correo")

        view.page().runJavaScript(js, _on_res)

    def _show_google_vault_menu(self) -> None:
        from PyQt6.QtWidgets import QFrame

        if getattr(self, "_google_popup", None) is not None:
            try:
                self._google_popup.close()
            except Exception:
                pass

        acct = self._load_google_account_info()
        acct_email = str(acct.get("email") or "").strip()
        acct_name = str(acct.get("name") or "").strip()
        vault_active = bool(acct_email) or (self.data_dir / "google_vault" / "storage").exists()
        popup = QFrame(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        popup.setFixedWidth(332)
        popup.setStyleSheet(
            """
            QFrame#googleVaultCard {
                background-color: #2b2a33;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 12px;
                color: #f0f0f5;
            }
            QFrame#googleBanner {
                background-color: rgba(66, 133, 244, 0.20);
                border: 1px solid rgba(100, 160, 255, 0.28);
                border-radius: 10px;
            }
            QPushButton#googlePrimaryBtn {
                background-color: #3b82f6;
                color: #ffffff;
                border: none;
                border-radius: 14px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton#googlePrimaryBtn:hover { background-color: #2563eb; }
            QPushButton#googleRowBtn {
                background: transparent;
                color: #eaeaf2;
                border: none;
                border-radius: 7px;
                padding: 7px 10px;
                text-align: left;
                font-size: 12.5px;
            }
            QPushButton#googleRowBtn:hover { background-color: rgba(255, 255, 255, 0.09); }
            QPushButton#googleDangerBtn {
                background: transparent;
                color: #fca5a5;
                border: none;
                border-radius: 7px;
                padding: 7px 10px;
                text-align: left;
                font-size: 12.5px;
            }
            QPushButton#googleDangerBtn:hover { background-color: rgba(239, 68, 68, 0.16); }
            """
        )
        popup.setObjectName("googleVaultCard")
        root = QVBoxLayout(popup)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # Tarjeta superior estilo Firefox
        banner = QFrame()
        banner.setObjectName("googleBanner")
        b_lay = QHBoxLayout(banner)
        b_lay.setContentsMargins(10, 10, 10, 10)
        b_lay.setSpacing(10)

        av_lbl = QLabel()
        av_lbl.setPixmap(_make_account_avatar_icon(active=True).pixmap(28, 28))
        b_lay.addWidget(av_lbl)

        txt_col = QVBoxLayout()
        txt_col.setSpacing(1)
        title_str = (acct_name or "Cuenta Google") if acct_email else ("Cuenta Google aislada" if vault_active else "Inicia sesión en Google")
        sub_str = f"{acct_email} • aislada" if acct_email else "Ninguna otra app ve tu correo"
        t_title = QLabel(title_str)
        t_title.setStyleSheet("font-weight: 600; font-size: 12.5px; color: #ffffff; background: transparent;")
        t_sub = QLabel(sub_str)
        t_sub.setStyleSheet("font-size: 11px; color: rgba(230, 236, 255, 195); background: transparent;")
        txt_col.addWidget(t_title)
        txt_col.addWidget(t_sub)
        b_lay.addLayout(txt_col, 1)

        target_acct_url = "https://myaccount.google.com" if acct_email else "https://accounts.google.com"
        login_btn = QPushButton("Gestionar" if acct_email else ("Abrir cuenta" if vault_active else "Iniciar sesión"))
        login_btn.setObjectName("googlePrimaryBtn")
        login_btn.clicked.connect(lambda: (popup.close(), self._open_google_vault(target_acct_url)))
        b_lay.addWidget(login_btn)
        root.addWidget(banner)

        sec1 = QLabel("Servicios Google (en bóveda)")
        sec1.setStyleSheet("color: rgba(210, 210, 225, 150); font-size: 11px; font-weight: 600; padding: 4px 6px 0 6px;")
        root.addWidget(sec1)

        for icon_txt, url in (
            ("✉   Gmail (aislado)", "https://mail.google.com"),
            ("▲   Google Drive (aislado)", "https://drive.google.com"),
            ("📅   Google Calendar (aislado)", "https://calendar.google.com"),
            ("▶   YouTube (en bóveda)", "https://www.youtube.com"),
        ):
            row = QPushButton(icon_txt)
            row.setObjectName("googleRowBtn")
            row.clicked.connect(lambda _c=False, u=url: (popup.close(), self._open_google_vault(u)))
            root.addWidget(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.10); max-height: 1px; margin: 2px 4px;")
        root.addWidget(sep)

        sec2 = QLabel("Herramientas de privacidad")
        sec2.setStyleSheet("color: rgba(210, 210, 225, 150); font-size: 11px; font-weight: 600; padding: 2px 6px 0 6px;")
        root.addWidget(sec2)

        shield_info = QLabel("🛡  Cerco activo: los enlaces externos se abren\n      en pestaña limpia sin tus cookies de Google.")
        shield_info.setStyleSheet("color: rgba(220, 224, 240, 195); font-size: 11.5px; padding: 4px 10px;")
        root.addWidget(shield_info)

        wipe_btn = QPushButton("🗑   Cerrar sesión y borrar Bóveda Google")
        wipe_btn.setObjectName("googleDangerBtn")
        wipe_btn.clicked.connect(lambda: (popup.close(), self._wipe_google_vault()))
        root.addWidget(wipe_btn)

        popup.adjustSize()
        pos = self.google_btn.mapToGlobal(self.google_btn.rect().bottomRight())
        popup.move(pos.x() - popup.width(), pos.y() + 6)
        self._google_popup = popup
        popup.show()

    def _configure_web_profile(self, prof: QWebEngineProfile) -> None:
        prof.setUrlRequestInterceptor(self.interceptor)
        try:
            prof.downloadRequested.disconnect(self._on_download_requested)
        except TypeError:
            pass
        prof.downloadRequested.connect(self._on_download_requested)

        ext_mgr = prof.extensionManager() if not prof.isOffTheRecord() else None
        if ext_mgr is not None:
            try:
                ext_mgr.loadFinished.disconnect(self._on_web_ext_loaded)
            except TypeError:
                pass
            ext_mgr.loadFinished.connect(self._on_web_ext_loaded)

            def _deferred_load_exts(m=ext_mgr) -> None:
                loaded_paths = {Path(i.path()).resolve() for i in m.extensions() if i.path() and i.isLoaded()}
                for ext_dir in self.plugin_mgr.list_saved_web_extension_dirs():
                    if ext_dir.resolve() in loaded_paths:
                        continue
                    if self.plugin_mgr.state.get(f"webext:{ext_dir.name}", {}).get("enabled", True):
                        m.loadExtension(str(ext_dir))

            QTimer.singleShot(0, _deferred_load_exts)

        self._apply_profile_privacy_to(prof)

    def _on_web_ext_loaded(self, info) -> None:
        if info is not None and info.error():
            record_diagnostic("webext_load_error", info.error())

    def _apply_profile_privacy(self) -> None:
        for prof in self._all_profiles():
            self._apply_profile_privacy_to(prof)

    def _apply_profile_privacy_to(self, prof: QWebEngineProfile) -> None:
        prof.setHttpCacheMaximumSize(64 * 1024 * 1024)
        web_settings = prof.settings()
        # LocalStorage activo en directorio efímero (se borra al salir) para compatibilidad total con web apps modernas
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.DnsPrefetchEnabled, not self.settings.proxy_enabled)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled, False)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)
        is_google_vault = prof is self._google_vault_profile
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, is_google_vault)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, False)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, False)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, True)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)

        # Bloqueo real de cookies de terceros en el motor (+ cerco estricto en Bóveda Google)
        block_3p = self.settings.block_third_party_cookies
        if prof is self._google_vault_profile:
            prof.cookieStore().setCookieFilter(
                lambda req: (
                    not req.thirdParty
                    and _is_google_vault_host(req.firstPartyUrl.host())
                    and _is_google_vault_host(req.origin.host())
                )
            )
        else:
            prof.cookieStore().setCookieFilter(lambda req: not (block_3p and req.thirdParty))

        # Limpiar y registrar protección JS temprana (DocumentCreation) contra fingerprinting
        scripts = prof.scripts()
        old = scripts.find("netlis_antifp")
        for s in old:
            scripts.remove(s)

        if is_google_vault:
            web_settings.setAttribute(QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly, True)
            prof.setHttpAcceptLanguage("es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7")
            # User-Agent Firefox en Bóveda Google: evita el bloqueo "This browser or app may not be secure" de Google Sign-In
            prof.setHttpUserAgent(
                "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0"
            )
            ff_script = QWebEngineScript()
            ff_script.setName("netlis_antifp")
            ff_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            ff_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            ff_script.setRunsOnSubFrames(True)
            ff_script.setSourceCode(
                """
                (() => {
                    try {
                        Object.defineProperty(navigator, 'webdriver', { get: () => false });
                        Object.defineProperty(navigator, 'userAgentData', { get: () => undefined });
                    } catch (e) {}
                })();
                """
            )
            scripts.insert(ff_script)
        elif self.settings.anti_fingerprinting:
            web_settings.setAttribute(QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly, True)
            prof.setHttpAcceptLanguage("en-US,en;q=0.9")
            try:
                from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion

                major_ver = qWebEngineChromiumVersion().split(".", 1)[0] or "140"
            except Exception:
                major_ver = "140"
            prof.setHttpUserAgent(
                f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{major_ver}.0.0.0 Safari/537.36"
            )
            shield_script = QWebEngineScript()
            shield_script.setName("netlis_antifp")
            shield_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            shield_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            shield_script.setRunsOnSubFrames(True)
            shield_script.setSourceCode(
                """
                (() => {
                    try {
                        Object.defineProperty(navigator, 'doNotTrack', { get: () => '1' });
                        Object.defineProperty(navigator, 'globalPrivacyControl', { get: () => true });
                        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
                        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                        Object.defineProperty(navigator, 'webdriver', { get: () => false });
                        Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
                        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                        try { delete Navigator.prototype.getBattery; navigator.getBattery = undefined; } catch (e) {}

                        if (typeof navigator.sendBeacon === 'function') {
                            const origBeacon = navigator.sendBeacon.bind(navigator);
                            navigator.sendBeacon = function(url, data) {
                                try {
                                    const u = new URL(String(url), location.href);
                                    if (u.origin === location.origin) return origBeacon(url, data);
                                } catch (e) {}
                                return true;
                            };
                        }

                        if (typeof AudioBuffer !== 'undefined') {
                            const origGetChannelData = AudioBuffer.prototype.getChannelData;
                            AudioBuffer.prototype.getChannelData = function(channel) {
                                const data = origGetChannelData.call(this, channel);
                                if (data && data.length > 0) {
                                    data[0] = data[0] + 1e-7;
                                }
                                return data;
                            };
                        }

                        const origGetParam = WebGLRenderingContext.prototype.getParameter;
                        WebGLRenderingContext.prototype.getParameter = function(p) {
                            if (p === 37445) return 'Generic Vendor';
                            if (p === 37446) return 'Generic Renderer';
                            return origGetParam.call(this, p);
                        };
                        if (typeof WebGL2RenderingContext !== 'undefined') {
                            const origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
                            WebGL2RenderingContext.prototype.getParameter = function(p) {
                                if (p === 37445) return 'Generic Vendor';
                                if (p === 37446) return 'Generic Renderer';
                                return origGetParam2.call(this, p);
                            };
                        }

                        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
                        HTMLCanvasElement.prototype.toDataURL = function(...args) {
                            try {
                                const ctx = this.getContext('2d');
                                if (ctx && this.width > 0 && this.height > 0 && this.width <= 1024 && this.height <= 1024) {
                                    const img = ctx.getImageData(0, 0, 1, 1);
                                    img.data[0] = img.data[0] ^ 1;
                                    ctx.putImageData(img, 0, 0);
                                }
                            } catch (e) {}
                            return origToDataURL.apply(this, args);
                        };
                    } catch (e) {}
                })();
                """
            )
            scripts.insert(shield_script)

        self._sync_plugin_scripts_to(prof)

    def _sync_plugin_scripts(self) -> None:
        """Inyecta en vivo los plugins activos de la Tienda en todos los perfiles y contenedores."""
        for prof in self._all_profiles():
            self._sync_plugin_scripts_to(prof)

    def _sync_plugin_scripts_to(self, prof: QWebEngineProfile) -> None:
        scripts = prof.scripts()
        for existing in list(scripts.toList()):
            if existing.name().startswith("netlis_plugin:"):
                scripts.remove(existing)

        for plug in self.plugin_mgr.active_plugins():
            sc = QWebEngineScript()
            sc.setName(f"netlis_plugin:{plug.plugin_id}")
            sc.setInjectionPoint(
                QWebEngineScript.InjectionPoint.DocumentCreation
                if plug.run_at_start
                else QWebEngineScript.InjectionPoint.DocumentReady
            )
            sc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            sc.setRunsOnSubFrames(plug.run_at_start)
            sc.setSourceCode(compile_plugin_source(plug))
            scripts.insert(sc)

    def _check_active_tab_health(self) -> None:
        """Verifica periódicamente que el hilo del motor JS de la pestaña activa responda sin bloqueo."""
        view = self._current_view()
        if view is None or view.page() is None or self.settings.safest_no_js:
            return
        url_s = view.url().toString()
        if not url_s or url_s.startswith(("netlis://", "about:")):
            return
        if self._watchdog_pending:
            record_diagnostic("watchdog_unresponsive", "Pestaña sin respuesta detectada por watchdog.")
            self._watchdog_pending = False
            return
        self._watchdog_pending = True

        def _pong(_res) -> None:
            self._watchdog_pending = False

        try:
            view.page().runJavaScript("1", _pong)
        except Exception:
            self._watchdog_pending = False

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("windowFrame")
        central.setMouseTracking(True)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Tira superior limpia estilo LibreWolf (controles circulares a la izquierda + pestañas)
        self.tab_strip = QWidget()
        self.tab_strip.setObjectName("tabStrip")
        strip_layout = QHBoxLayout(self.tab_strip)
        strip_layout.setContentsMargins(10, 4, 10, 0)
        strip_layout.setSpacing(6)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("winCloseBtn")
        close_btn.setToolTip("Cerrar Netlis")
        close_btn.clicked.connect(self.close)

        min_btn = QPushButton("–")
        min_btn.setObjectName("winBtn")
        min_btn.setToolTip("Minimizar")
        min_btn.clicked.connect(self.showMinimized)

        max_btn = QPushButton("⤢")
        max_btn.setObjectName("winBtn")
        max_btn.setToolTip("Maximizar / Restaurar")
        max_btn.clicked.connect(self._toggle_maximize)

        strip_layout.addWidget(close_btn)
        strip_layout.addWidget(min_btn)
        strip_layout.addWidget(max_btn)
        strip_layout.addSpacing(8)

        self.tab_bar = QTabBar()
        self.tab_bar.setIconSize(QSize(16, 16))
        self.tab_bar.setExpanding(False)
        self.tab_bar.setTabsClosable(False)
        self.tab_bar.setMovable(True)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabMoved.connect(self._on_tab_moved)

        add_tab_btn = QPushButton("+")
        add_tab_btn.setObjectName("pluginIconBtn")
        add_tab_btn.setToolTip("Nueva pestaña (Ctrl+T)")
        add_tab_btn.clicked.connect(lambda: self.add_new_tab(None, "Nueva pestaña"))

        strip_layout.addWidget(self.tab_bar)
        strip_layout.addWidget(add_tab_btn)
        strip_layout.addStretch()

        if self.incognito:
            badge = QLabel("Privada")
            badge.setObjectName("incognitoBadge")
            strip_layout.addWidget(badge)

        priv_win_btn = QPushButton("◫")
        priv_win_btn.setObjectName("pluginIconBtn")
        priv_win_btn.setToolTip("Nueva ventana privada (Ctrl+Shift+N)")
        priv_win_btn.clicked.connect(self.open_incognito_window)
        strip_layout.addWidget(priv_win_btn)

        root_layout.addWidget(self.tab_strip)

        # 2. Barra única minimalista (LibreWolf: ← → ↻ | barra píldora centrada | iconos limpios)
        nav_bar = QToolBar("Navegación")
        nav_bar.setObjectName("navBar")
        nav_bar.setMovable(False)
        nav_bar.setIconSize(QSize(16, 16))

        for label, tip, cb in (
            ("←", "Atrás", lambda: self._current_view() and self._current_view().back()),
            ("→", "Adelante", lambda: self._current_view() and self._current_view().forward()),
            ("↻", "Recargar", lambda: self._current_view() and self._current_view().reload()),
        ):
            act = QAction(label, self)
            act.setToolTip(tip)
            act.triggered.connect(cb)
            nav_bar.addAction(act)

        self.bookmark_act = QAction("☆", self)
        self.bookmark_act.setToolTip("Guardar marcador (Ctrl+D)")
        self.bookmark_act.triggered.connect(self._toggle_current_bookmark)
        nav_bar.addAction(self.bookmark_act)

        left_sp = QWidget()
        left_sp.setFixedWidth(18)
        nav_bar.addWidget(left_sp)

        url_pill = QFrame()
        url_pill.setObjectName("urlPill")
        url_pill_lay = QHBoxLayout(url_pill)
        url_pill_lay.setContentsMargins(2, 0, 6, 0)
        url_pill_lay.setSpacing(4)

        self.search_pick_btn = QPushButton("⌄")
        self.search_pick_btn.setObjectName("searchPickBtn")
        self.search_pick_btn.setIconSize(QSize(18, 18))
        self.search_pick_btn.setToolTip("Cambiar buscador o abrir Marcadores / Historial / Ajustes")
        self.search_pick_btn.clicked.connect(self._show_search_picker_menu)

        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("urlBarInput")
        self.url_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.url_bar.setMinimumWidth(360)
        self._refresh_url_bar_placeholder()
        self.url_bar.returnPressed.connect(self._on_url_entered)

        url_pill_lay.addWidget(self.search_pick_btn)
        url_pill_lay.addWidget(self.url_bar, stretch=1)
        nav_bar.addWidget(url_pill)

        right_sp = QWidget()
        right_sp.setFixedWidth(28)
        nav_bar.addWidget(right_sp)

        dl_btn = QPushButton("↓")
        dl_btn.setObjectName("pluginIconBtn")
        dl_btn.setToolTip("Descargas (Ctrl+J)")
        dl_btn.clicked.connect(self._show_downloads)
        nav_bar.addWidget(dl_btn)

        self.turbo_btn = QPushButton(self._mode_button_text())
        self.turbo_btn.setObjectName("ipBtn")
        self.turbo_btn.setToolTip("Cambiar en 1 clic entre Modo Tor (IP oculta) y Sin Tor (conexión directa rápida)")
        self.turbo_btn.clicked.connect(self._toggle_turbo_mode)
        nav_bar.addWidget(self.turbo_btn)

        self.google_btn = QPushButton()
        self.google_btn.setObjectName("pluginIconBtn")
        self.google_btn.setIcon(
            _make_account_avatar_icon(active=(self.data_dir / "google_vault" / "storage").exists())
        )
        self.google_btn.setIconSize(QSize(20, 20))
        self.google_btn.setToolTip(
            "Cuenta Google aislada: ninguna otra web o app puede ver tu correo ni tus cookies"
        )
        self.google_btn.clicked.connect(self._show_google_vault_menu)
        nav_bar.addWidget(self.google_btn)

        self.ip_btn = QPushButton(self._ip_button_text())
        self.ip_btn.setObjectName("ipBtn")
        self.ip_btn.setToolTip("Estado de IP / Proxy Tor — Clic para abrir Centro de Seguridad")
        self.ip_btn.clicked.connect(self._show_privacy_center)
        nav_bar.addWidget(self.ip_btn)

        self.plugins_btn = QPushButton()
        self.plugins_btn.setObjectName("pluginIconBtn")
        self.plugins_btn.setIcon(_make_plugin_puzzle_icon())
        self.plugins_btn.setIconSize(QSize(18, 18))
        self.plugins_btn.setToolTip(f"Extensiones y Plugins ({len(self.plugin_mgr.active_plugins())} activos)")
        self.plugins_btn.clicked.connect(self._show_plugin_store)
        nav_bar.addWidget(self.plugins_btn)

        self.shield_btn = QPushButton("🛡 0")
        self.shield_btn.setObjectName("shieldBtn")
        self.shield_btn.setToolTip("Ver anuncios y rastreadores bloqueados en este sitio (estilo Brave)")
        self.shield_btn.clicked.connect(self._show_site_shields)
        nav_bar.addWidget(self.shield_btn)

        self.menu_btn = QPushButton("☰")
        self.menu_btn.setObjectName("pluginIconBtn")
        self.menu_btn.setToolTip("Menú de Netlis")
        self.menu_btn.clicked.connect(self._show_main_menu)
        nav_bar.addWidget(self.menu_btn)
        if is_gecko_available():
            self.gecko_btn = self.menu_btn

        self.nav_bar = nav_bar
        root_layout.addWidget(self.nav_bar)

        # 2.2 Tira sutil de marcadores rápidos (como LibreWolf)
        self.bookmarks_strip = QWidget()
        self.bookmarks_strip.setObjectName("bookmarksStrip")
        self.bm_layout = QHBoxLayout(self.bookmarks_strip)
        self.bm_layout.setContentsMargins(10, 2, 10, 3)
        self.bm_layout.setSpacing(6)
        self._rebuild_bookmarks_bar()
        root_layout.addWidget(self.bookmarks_strip)

        # 2.5 Barra compacta de búsqueda en página (Ctrl+F)
        self.find_bar = QWidget()
        self.find_bar.setObjectName("findBar")
        find_layout = QHBoxLayout(self.find_bar)
        find_layout.setContentsMargins(10, 5, 10, 5)
        find_layout.setSpacing(6)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Buscar en la página...")
        self.find_input.setMaximumWidth(320)
        self.find_input.textChanged.connect(lambda txt: self._find_in_page(txt, backward=False))
        self.find_input.returnPressed.connect(lambda: self._find_in_page(self.find_input.text(), backward=False))
        btn_find_prev = QPushButton("↑")
        btn_find_prev.setToolTip("Anterior coincidencia")
        btn_find_prev.clicked.connect(lambda: self._find_in_page(self.find_input.text(), backward=True))
        btn_find_next = QPushButton("↓")
        btn_find_next.setToolTip("Siguiente coincidencia")
        btn_find_next.clicked.connect(lambda: self._find_in_page(self.find_input.text(), backward=False))
        self.find_status = QLabel("")
        self.find_status.setStyleSheet("color: #cfcfe0; font-size: 12px; padding: 0 6px;")
        btn_find_close = QPushButton("✕")
        btn_find_close.setObjectName("winBtn")
        btn_find_close.setToolTip("Cerrar búsqueda (Esc)")
        btn_find_close.clicked.connect(self._close_find_bar)
        find_layout.addWidget(self.find_input)
        find_layout.addWidget(btn_find_prev)
        find_layout.addWidget(btn_find_next)
        find_layout.addWidget(self.find_status)
        find_layout.addStretch()
        find_layout.addWidget(btn_find_close)
        self.find_bar.hide()
        root_layout.addWidget(self.find_bar)

        # 3. Progreso + Vistas web
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        root_layout.addWidget(self.progress)

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentArea")
        root_layout.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

    _RADIUS = 14
    _EDGE = 6

    def _update_round_mask(self) -> None:
        """Recorta la ventana con esquinas redondeadas (igual que Firefox) salvo maximizada."""
        if self.isMaximized() or self.isFullScreen():
            self.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._RADIUS, self._RADIUS)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _apply_letterbox(self) -> None:
        """Mantiene el área web limpia borde a borde sin marcos negros alrededor del contenido."""
        if hasattr(self, "stack"):
            self.stack.setContentsMargins(0, 0, 0, 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_round_mask()
        self._apply_letterbox()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_round_mask()
        self._apply_letterbox()

    def _edges_at(self, pos) -> Qt.Edge:
        edges = Qt.Edge(0)
        x, y, w, h, m = pos.x(), pos.y(), self.width(), self.height(), self._EDGE
        if x <= m:
            edges |= Qt.Edge.LeftEdge
        elif x >= w - m:
            edges |= Qt.Edge.RightEdge
        if y <= m:
            edges |= Qt.Edge.TopEdge
        elif y >= h - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _mode_button_text(self) -> str:
        return "Tor" if self.settings.proxy_enabled else "Sin Tor ⚡"

    def _ip_button_text(self) -> str:
        if self.settings.proxy_enabled:
            region = IP_REGIONS.get(self.settings.ip_region, "Auto").split(" ")[0]
            return f"● {region}" if is_proxy_reachable(self.settings.proxy_url) else "◐ Tor…"
        return "Directa"

    def _rebuild_bookmarks_bar(self) -> None:
        while self.bm_layout.count():
            item = self.bm_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if self.storage.bookmarks:
            for bm in self.storage.bookmarks[:8]:
                title = (bm.get("title") or bm.get("url") or "Sitio")[:20]
                u = bm.get("url", "")
                btn = QPushButton(title)
                btn.setObjectName("bmLinkBtn")
                btn.clicked.connect(lambda _c=False, url_s=u: self._navigate(url_s))
                self.bm_layout.addWidget(btn)
        else:
            hint = QLabel("Para un acceso rápido, guarda marcadores con ☆ (Ctrl+D).")
            hint.setStyleSheet("color: rgba(215, 215, 230, 155); font-size: 11.5px; padding-left: 4px;")
            self.bm_layout.addWidget(hint)
        mgr_btn = QPushButton("Administrar marcadores…")
        mgr_btn.setObjectName("bmLinkBtn")
        mgr_btn.setStyleSheet("color: #9e86ff; text-decoration: underline; font-size: 11.5px; background: transparent; border: none;")
        mgr_btn.clicked.connect(self._show_history)
        self.bm_layout.addWidget(mgr_btn)
        self.bm_layout.addStretch()

    def _refresh_network_pill(self) -> None:
        self.ip_btn.setText(self._ip_button_text())
        self.turbo_btn.setText(self._mode_button_text())
        if self._tor_pending_urls and (
            not self.settings.proxy_enabled or is_proxy_reachable(self.settings.proxy_url)
        ):
            pending = list(self._tor_pending_urls.items())
            self._tor_pending_urls.clear()
            for v, qurl in pending:
                if self.stack.indexOf(v) != -1:
                    v.setUrl(qurl)

    def _toggle_turbo_mode(self) -> None:
        global TOR_ENGINE
        self.settings.proxy_enabled = not self.settings.proxy_enabled
        self.settings.save(self.settings_path)
        if self.settings.proxy_enabled:
            if TOR_ENGINE is None:
                TOR_ENGINE = EmbeddedTorManager(self.data_dir)
            TOR_ENGINE.start_async(self.settings.ip_region, self.settings.tor_bridges_obfs4)
        elif TOR_ENGINE is not None:
            TOR_ENGINE.stop(wipe_files=False)
        apply_qt_network_proxy(self.settings)
        self._refresh_network_pill()

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+T"), self, lambda: self.add_new_tab(None, "Inicio"))
        QShortcut(QKeySequence("Ctrl+Shift+T"), self, self._reopen_closed_tab)
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, self.open_incognito_window)
        QShortcut(QKeySequence("Ctrl+W"), self, lambda: self.close_tab(self.tab_bar.currentIndex()))
        QShortcut(QKeySequence("Ctrl+L"), self, self._focus_url_bar)
        QShortcut(QKeySequence("Ctrl+F"), self, self._open_find_bar)
        QShortcut(QKeySequence("Ctrl+J"), self, self._show_downloads)
        QShortcut(QKeySequence("Ctrl+D"), self, self._toggle_current_bookmark)
        QShortcut(QKeySequence("Ctrl+H"), self, self._show_history)
        QShortcut(QKeySequence("Ctrl+R"), self, lambda: self._current_view() and self._current_view().reload())
        QShortcut(QKeySequence("Ctrl++"), self, lambda: self._adjust_zoom(0.1))
        QShortcut(QKeySequence("Ctrl+="), self, lambda: self._adjust_zoom(0.1))
        QShortcut(QKeySequence("Ctrl+-"), self, lambda: self._adjust_zoom(-0.1))
        QShortcut(QKeySequence("Ctrl+0"), self, lambda: self._adjust_zoom(None))
        QShortcut(QKeySequence("F11"), self, self._toggle_window_fullscreen)
        QShortcut(QKeySequence("Escape"), self, self._handle_escape)

    def _open_find_bar(self) -> None:
        self.find_bar.show()
        self.find_input.setFocus()
        self.find_input.selectAll()

    def _close_find_bar(self) -> None:
        self.find_bar.hide()
        self.find_status.setText("")
        view = self._current_view()
        if view is not None:
            view.findText("")

    def _find_in_page(self, text: str, backward: bool = False) -> None:
        view = self._current_view()
        if view is None:
            return
        if not text:
            view.findText("")
            self.find_status.setText("")
            return
        flags = QWebEnginePage.FindFlag.FindBackward if backward else QWebEnginePage.FindFlag(0)

        def _on_res(res) -> None:
            if hasattr(res, "numberOfMatches"):
                total = res.numberOfMatches()
                active = res.activeMatch()
                self.find_status.setText(f"{active}/{total}" if total > 0 else "Sin resultados")
            else:
                self.find_status.setText("" if res else "Sin resultados")

        view.findText(text, flags, _on_res)

    def _adjust_zoom(self, delta: float | None) -> None:
        view = self._current_view()
        if view is None:
            return
        if delta is None:
            view.setZoomFactor(1.0)
        else:
            new_z = max(0.5, min(2.5, round(view.zoomFactor() + delta, 2)))
            view.setZoomFactor(new_z)

    def _set_fullscreen_mode(self, enable: bool) -> None:
        if enable and not self.isFullScreen():
            self._was_maximized_before_fs = self.isMaximized()
            self.tab_strip.hide()
            self.nav_bar.hide()
            self.bookmarks_strip.hide()
            self.progress.hide()
            self.showFullScreen()
            self._update_round_mask()
        elif not enable and self.isFullScreen():
            self.tab_strip.show()
            self.nav_bar.show()
            self.bookmarks_strip.show()
            self.progress.show()
            if self._was_maximized_before_fs:
                self.showMaximized()
            else:
                self.showNormal()
            self._update_round_mask()

    def _toggle_window_fullscreen(self) -> None:
        self._set_fullscreen_mode(not self.isFullScreen())

    def _on_html5_fullscreen_requested(self, req: QWebEngineFullScreenRequest) -> None:
        req.accept()
        self._set_fullscreen_mode(req.toggleOn())

    def _handle_escape(self) -> None:
        if self.find_bar.isVisible():
            self._close_find_bar()
            return
        if self.isFullScreen():
            view = self._current_view()
            if view is not None and view.page() is not None:
                view.page().triggerAction(QWebEnginePage.WebAction.ExitFullScreen)
            self._set_fullscreen_mode(False)

    def _reopen_closed_tab(self) -> None:
        if not self._closed_tabs:
            return
        url_str, title = self._closed_tabs.pop()
        self.add_new_tab(QUrl(url_str), title)

    def open_incognito_window(self) -> "BrowserWindow":
        win = BrowserWindow(incognito=True, settings=self.settings, appearance=self.appearance)
        win.show()
        return win

    def _focus_url_bar(self) -> None:
        self.url_bar.setFocus()
        self.url_bar.selectAll()

    def _current_view(self) -> QWebEngineView | None:
        w = self.stack.currentWidget()
        return w if isinstance(w, QWebEngineView) else None

    def _load_newtab_html(self, view: QWebEngineView) -> None:
        html_doc = render_new_tab_html(
            blocked_count=self.interceptor.blocked_count,
            https_upgrades=self.interceptor.https_upgrades,
            incognito=self.incognito,
            bookmarks=self.storage.bookmarks,
            appearance=self.appearance,
        )
        view.setHtml(html_doc, QUrl(NEWTAB_URL))
        idx = self.stack.indexOf(view)
        if idx != -1 and not self._netlis_icon.isNull():
            self.tab_bar.setTabIcon(idx, self._netlis_icon)

    def _load_netlis_search(self, view: QWebEngineView, query: str) -> None:
        clean_q = query.strip()
        if not clean_q:
            self._load_newtab_html(view)
            return
        search_qurl = QUrl(f"netlis://search?q={quote_plus(clean_q)}")
        view.setHtml(render_search_loading_html(clean_q, self.settings.proxy_enabled), search_qurl)
        if view is self._current_view():
            self.url_bar.setText(clean_q)
        worker = _NetlisSearchWorker(clean_q, use_tor=self.settings.proxy_enabled, parent=self)
        if not hasattr(self, "_search_workers"):
            self._search_workers: list[_NetlisSearchWorker] = []
        self._search_workers.append(worker)

        def _on_done(data: dict, v=view, w=worker, u=search_qurl) -> None:
            if w in self._search_workers:
                self._search_workers.remove(w)
            if self.stack.indexOf(v) != -1:
                v.setHtml(render_search_results_html(data), u)
            w.deleteLater()

        worker.ready.connect(_on_done)
        worker.start()

    def _open_newtab_in_current(self) -> None:
        view = self._current_view()
        if view is not None:
            self._load_newtab_html(view)

    def _on_download_requested(self, download) -> None:
        fname = download.downloadFileName()
        src_url = download.url().toString() if hasattr(download, "url") else ""
        mime_type = download.mimeType() if hasattr(download, "mimeType") else ""
        rec = {
            "filename": fname,
            "state": "Descargando…",
            "received_bytes": int(download.receivedBytes() or 0),
            "total_bytes": int(download.totalBytes() or 0),
            "sha256": "",
            "started_at": datetime.now().strftime("%H:%M"),
        }
        if self.settings.phishing_and_malware_guard:
            is_bad, bad_reason = inspect_download_request(fname, src_url, mime_type)
            if is_bad:
                download.cancel()
                rec["state"] = f"Bloqueado ({bad_reason})"
                self.downloads_records.append(rec)
                self.blocked_downloads += 1
                self.interceptor._mark_blocked()
                return
        dl_dir = Path.home() / ("Descargas" if (Path.home() / "Descargas").exists() else "Downloads")
        dl_dir.mkdir(parents=True, exist_ok=True)
        download.setDownloadDirectory(str(dl_dir))
        self.downloads_records.append(rec)
        download.receivedBytesChanged.connect(
            lambda d=download, r=rec: r.__setitem__("received_bytes", int(d.receivedBytes() or 0))
        )
        download.totalBytesChanged.connect(
            lambda d=download, r=rec: r.__setitem__("total_bytes", int(d.totalBytes() or 0))
        )

        def _on_dl_done(d=download, r=rec) -> None:
            st_name = getattr(d.state(), "name", "")
            if "Completed" in st_name:
                final_path = Path(d.downloadDirectory()) / d.downloadFileName()
                if self.settings.phishing_and_malware_guard and final_path.is_file():
                    safe_ok, digest, reason = verify_downloaded_file_safety(final_path)
                    r["sha256"] = digest
                    if not safe_ok:
                        r["state"] = f"Cuarentena ({reason})"
                        self.blocked_downloads += 1
                        self.interceptor._mark_blocked()
                        return
                r["state"] = "Completado y verificado"
                r["received_bytes"] = int(d.receivedBytes() or r["total_bytes"])
            elif "Cancelled" in st_name:
                r["state"] = "Cancelado"
            else:
                r["state"] = "Interrumpido"

        download.isFinishedChanged.connect(_on_dl_done)
        download.accept()

    def _on_render_process_terminated(
        self,
        status: QWebEnginePage.RenderProcessTerminationStatus,
        _exit_code: int,
        view: QWebEngineView,
    ) -> None:
        """Auto-recuperación inmediata si un proceso de pestaña falla o se queda sin memoria."""
        if status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            return
        self.recovered_crashes += 1
        target_url = view.url().toString()

        def _recover() -> None:
            if self.stack.indexOf(view) == -1:
                return
            if not target_url or target_url == NEWTAB_URL:
                self._load_newtab_html(view)
            else:
                view.reload()

        QTimer.singleShot(250, _recover)

    def _show_web_context_menu(self, pos: QPoint, view: QWebEngineView) -> None:
        req = view.lastContextMenuRequest()
        menu = QMenu(self)
        link_url = req.linkUrl() if req is not None else QUrl()
        if link_url.isValid() and link_url.scheme().lower() in ("http", "https"):
            menu.addAction(
                "Abrir enlace en pestaña nueva",
                lambda u=QUrl(link_url): self.add_new_tab(u, "Cargando…", switch_to=True),
            )
            menu.addAction(
                "Abrir enlace en segundo plano",
                lambda u=QUrl(link_url): self.add_new_tab(u, "Cargando…", switch_to=False),
            )
            menu.addAction(
                "Copiar dirección del enlace",
                lambda s=link_url.toString(): QApplication.clipboard().setText(s),
            )
            menu.addSeparator()

        sel_text = view.selectedText().strip()
        if sel_text:
            menu.addAction("Copiar texto", lambda: view.triggerPageAction(QWebEnginePage.WebAction.Copy))
            short_q = (sel_text[:22] + "…") if len(sel_text) > 23 else sel_text
            menu.addAction(
                f"Buscar «{short_q}» en privado",
                lambda q=sel_text: self.add_new_tab(
                    normalize_input_to_url(q, self.appearance.search_engine), "Búsqueda"
                ),
            )
            menu.addSeparator()

        menu.addAction("Atrás", view.back).setEnabled(view.history().canGoBack())
        menu.addAction("Adelante", view.forward).setEnabled(view.history().canGoForward())
        menu.addAction("Recargar", view.reload)
        menu.addSeparator()
        menu.addAction("Buscar en la página (Ctrl+F)", self._open_find_bar)
        menu.addAction("Pantalla completa (F11)", self._toggle_window_fullscreen)
        menu.exec(view.mapToGlobal(pos))

    def add_new_tab(
        self,
        qurl: QUrl | None = None,
        label: str = "Inicio",
        switch_to: bool = True,
        isolated_container: bool | None = None,
        google_vault: bool = False,
    ) -> QWebEngineView:
        view = QWebEngineView()
        use_container = (
            self.settings.isolated_tab_containers
            if isolated_container is None
            else isolated_container
        )
        if google_vault:
            active_profile = self._get_google_vault_profile()
        elif use_container and self.stack.count() >= 1:
            tab_prof = QWebEngineProfile(self)
            tab_prof.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
            tab_prof.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self._tab_profiles[view] = tab_prof
            self._configure_web_profile(tab_prof)
            active_profile = tab_prof
        else:
            active_profile = self.profile

        page = SecureWebPage(active_profile, view, browser_win=self)
        page.setBackgroundColor(QColor("#1b1526" if self.incognito else "#131215"))
        page.fullScreenRequested.connect(self._on_html5_fullscreen_requested)
        view.setPage(page)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(lambda p, v=view: self._show_web_context_menu(p, v))
        self._tab_last_active[view] = time.monotonic()

        view.urlChanged.connect(lambda url, v=view: self._on_url_changed(url, v))
        view.titleChanged.connect(lambda title, v=view: self._on_title_changed(title, v))
        view.iconChanged.connect(lambda icon, v=view: self._on_icon_changed(icon, v))
        view.loadProgress.connect(lambda pct, v=view: self._on_load_progress(pct, v))
        view.loadFinished.connect(lambda ok, v=view: self._on_load_finished(ok, v))
        view.renderProcessTerminated.connect(
            lambda st, code, v=view: self._on_render_process_terminated(st, code, v)
        )

        self.stack.addWidget(view)
        idx = self.tab_bar.addTab(label)
        if not self._netlis_icon.isNull():
            self.tab_bar.setTabIcon(idx, self._netlis_icon)
        close_tab_btn = QPushButton("✕")
        close_tab_btn.setObjectName("tabCloseBtn")
        close_tab_btn.setToolTip("Cerrar pestaña (Ctrl+W)")
        close_tab_btn.clicked.connect(lambda _c=False, v=view: self._close_view(v))
        self.tab_bar.setTabButton(idx, QTabBar.ButtonPosition.RightSide, close_tab_btn)
        if switch_to or self.tab_bar.count() == 1:
            self.tab_bar.setCurrentIndex(idx)
            self.stack.setCurrentWidget(view)

        if qurl is not None and qurl.toString() == "about:blank":
            return view
        if qurl is None or qurl.toString() == NEWTAB_URL:
            self._load_newtab_html(view)
        elif qurl.toString().startswith("netlis://search"):
            self._load_netlis_search(view, QUrlQuery(qurl).queryItemValue("q"))
        else:
            if qurl.scheme().lower() in ("http", "https"):
                self._last_requested_url[view] = QUrl(qurl)
            view.setUrl(qurl)
        return view

    def _close_view(self, view: QWebEngineView) -> None:
        idx = self.stack.indexOf(view)
        if idx != -1:
            self.close_tab(idx)

    def close_tab(self, index: int) -> None:
        if self.tab_bar.count() <= 1:
            self._open_newtab_in_current()
            return
        widget = self.stack.widget(index)
        if isinstance(widget, QWebEngineView):
            u_str = widget.url().toString()
            if u_str and not u_str.startswith(("netlis://", "about:", "data:")):
                self._closed_tabs.append((u_str, widget.title() or "Pestaña"))
                if len(self._closed_tabs) > 25:
                    self._closed_tabs.pop(0)
            self._tor_pending_urls.pop(widget, None)
            self._last_requested_url.pop(widget, None)
        self.tab_bar.removeTab(index)
        if widget is not None:
            tab_prof = self._tab_profiles.pop(widget, None)
            self._tab_last_active.pop(widget, None)
            self.stack.removeWidget(widget)
            widget.deleteLater()
            if tab_prof is not None:
                tab_prof.clearHttpCache()
                tab_prof.cookieStore().deleteAllCookies()
                QTimer.singleShot(400, tab_prof.deleteLater)

    def _suspend_inactive_tabs(self, freeze_after_s: float = 90.0, discard_after_s: float = 240.0) -> int:
        """Congela o libera RAM de las pestañas en segundo plano que llevan tiempo sin usarse."""
        now = time.monotonic()
        current = self._current_view()
        suspended = 0
        for i in range(self.stack.count()):
            v = self.stack.widget(i)
            if not isinstance(v, QWebEngineView) or v is current:
                continue
            idle = now - self._tab_last_active.get(v, now)
            pg = v.page()
            if pg is None:
                continue
            if idle >= discard_after_s and pg.lifecycleState() != QWebEnginePage.LifecycleState.Discarded:
                pg.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
                suspended += 1
            elif idle >= freeze_after_s and pg.lifecycleState() == QWebEnginePage.LifecycleState.Active:
                pg.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
                suspended += 1
        return suspended

    def _on_tab_moved(self, from_idx: int, to_idx: int) -> None:
        w = self.stack.widget(from_idx)
        if w is not None:
            self.stack.removeWidget(w)
            self.stack.insertWidget(to_idx, w)
            self.stack.setCurrentIndex(self.tab_bar.currentIndex())

    def _navigate(self, raw_url: str) -> None:
        view = self._current_view()
        if view is None:
            return
        qurl = normalize_input_to_url(raw_url, self.appearance.search_engine)
        if qurl.toString() == NEWTAB_URL:
            self._load_newtab_html(view)
        elif qurl.toString().startswith("netlis://search"):
            self._load_netlis_search(view, QUrlQuery(qurl).queryItemValue("q"))
        else:
            if qurl.scheme().lower() in ("http", "https"):
                self._last_requested_url[view] = QUrl(qurl)
            view.setUrl(qurl)

    def _on_url_entered(self) -> None:
        self._navigate(self.url_bar.text())

    @staticmethod
    def _format_display_url(url_str: str) -> str:
        if not url_str or url_str == NEWTAB_URL or url_str.startswith("about:"):
            return ""
        parsed = urlparse(url_str)
        host = parsed.netloc.lower()
        if (
            url_str.startswith("netlis://search")
            or any(d in host for d in ("duckduckgo.com", "google.com", "search.brave.com", "startpage.com"))
        ):
            qs = parse_qs(parsed.query)
            for key in ("q", "query"):
                if key in qs and qs[key]:
                    return unquote_plus(qs[key][0]).strip()
        if url_str.startswith("https://"):
            return url_str[8:]
        return url_str

    def _on_tab_changed(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
        view = self._current_view()
        if view is not None:
            self._tab_last_active[view] = time.monotonic()
            if view.page() is not None and view.page().lifecycleState() != QWebEnginePage.LifecycleState.Active:
                view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            url_str = view.url().toString()
            self.url_bar.setText(self._format_display_url(url_str))
            self._update_bookmark_star(url_str)
            self._update_shield_label()
            suffix = "Netlis Privado" if self.incognito else "Netlis"
            self.setWindowTitle(f"{view.title() or 'Nueva pestaña'} — {suffix}")

    def _on_url_changed(self, url: QUrl, view: QWebEngineView) -> None:
        if view is self._current_view():
            url_str = url.toString()
            self.url_bar.setText(self._format_display_url(url_str))
            self.url_bar.setCursorPosition(0)
            self._update_bookmark_star(url_str)
            self._update_shield_label()

    def _on_icon_changed(self, icon: QIcon, view: QWebEngineView) -> None:
        idx = self.stack.indexOf(view)
        if idx == -1:
            return
        url_str = view.url().toString()
        if url_str.startswith("netlis://") or icon.isNull():
            if not self._netlis_icon.isNull():
                self.tab_bar.setTabIcon(idx, self._netlis_icon)
        else:
            self.tab_bar.setTabIcon(idx, icon)

    def _on_title_changed(self, title: str, view: QWebEngineView) -> None:
        idx = self.stack.indexOf(view)
        if idx != -1:
            short = (title[:22] + "…") if len(title) > 23 else title
            self.tab_bar.setTabText(idx, short or "Inicio")
        if view is self._current_view():
            suffix = "Netlis Privado" if self.incognito else "Netlis"
            self.setWindowTitle(f"{title or 'Inicio'} — {suffix}")

    def _on_load_progress(self, pct: int, view: QWebEngineView) -> None:
        if view is self._current_view():
            self.progress.setValue(pct if pct < 100 else 0)

    def _on_load_finished(self, ok: bool, view: QWebEngineView) -> None:
        url_str = view.url().toString()
        if not ok:
            candidate = view.url() if view.url().scheme().lower() in ("http", "https") else self._last_requested_url.get(view)
            if (
                candidate is not None
                and candidate.scheme().lower() in ("http", "https")
                and self.settings.proxy_enabled
                and not is_proxy_reachable(self.settings.proxy_url)
            ):
                self._tor_pending_urls[view] = QUrl(candidate)
                target_str = candidate.toString()
                view.setHtml(_render_tor_warmup_html(target_str), QUrl("about:blank"))
                if view is self._current_view():
                    self.url_bar.setText(target_str)
                    self.progress.setValue(0)
                return
        else:
            self._tor_pending_urls.pop(view, None)

        if ok and url_str != NEWTAB_URL and not url_str.startswith("about:"):
            if self.settings.anti_fingerprinting:
                self._inject_anti_tracking_js(view)
            if "duckduckgo.com" in url_str:
                self._inject_netlis_search_logo(view)
            if self.settings.block_youtube_ads and "youtube.com" in url_str:
                self._inject_youtube_adblock(view)
            self._sync_google_vault_account_badge(view)
        if ok and not self.incognito and url_str != NEWTAB_URL and not url_str.startswith("about:"):
            self.storage.add_history(view.title(), url_str)
        if view is self._current_view():
            self.progress.setValue(0)

    def _inject_anti_tracking_js(self, view: QWebEngineView) -> None:
        js = """
        (() => {
            try {
                if (typeof navigator.sendBeacon === 'function' && !navigator.__netlisBeaconGuarded) {
                    navigator.__netlisBeaconGuarded = true;
                    const origBeacon = navigator.sendBeacon.bind(navigator);
                    navigator.sendBeacon = function(url, data) {
                        try {
                            const u = new URL(String(url), location.href);
                            if (u.origin === location.origin) return origBeacon(url, data);
                        } catch (e) {}
                        return true;
                    };
                }
            } catch (e) {}
        })();
        """
        view.page().runJavaScript(js)

    def _inject_youtube_adblock(self, view: QWebEngineView) -> None:
        js = """
        (() => {
            if (window.__netlisYtAdblock) return;
            window.__netlisYtAdblock = true;
            const style = document.createElement('style');
            style.textContent = `
                ytd-ad-slot-renderer, #player-ads, ytd-banner-promo-renderer,
                .ytp-ad-overlay-container, .ytp-ad-message-container,
                ytd-promoted-sparkles-web-renderer, ytd-display-ad-renderer {
                    display: none !important;
                }
            `;
            document.documentElement.appendChild(style);
            let wasAd = false;
            setInterval(() => {
                const skip = document.querySelector('.ytp-ad-skip-button, .ytp-skip-ad-button, .ytp-ad-skip-button-modern');
                if (skip) skip.click();
                const player = document.querySelector('.html5-video-player');
                const video = document.querySelector('video');
                if (player && player.classList.contains('ad-showing') && video) {
                    wasAd = true;
                    video.muted = true;
                    if (isFinite(video.duration) && video.duration > 0) {
                        video.currentTime = video.duration;
                    }
                } else if (wasAd && video) {
                    wasAd = false;
                    video.muted = false;
                    video.playbackRate = 1.0;
                }
            }, 400);
        })();
        """
        view.page().runJavaScript(js)

    def _inject_netlis_search_logo(self, view: QWebEngineView) -> None:
        logo_file = Path(__file__).resolve().parent / "assets" / "netlis_logo.jpg"
        logo_uri = _image_data_uri(str(logo_file))
        if not logo_uri:
            return
        js = f"""
        (() => {{
            const uri = {json.dumps(logo_uri)};
            const applyLogo = () => {{
                const targets = document.querySelectorAll(
                    'a.header__logo, a[title*="DuckDuckGo"], a[aria-label*="DuckDuckGo"], header a[href="/"]'
                );
                for (const a of targets) {{
                    if (a.dataset.netlisBranded) continue;
                    a.dataset.netlisBranded = "1";
                    a.innerHTML = '';
                    const img = document.createElement('img');
                    img.src = uri;
                    img.alt = 'Netlis';
                    img.style.cssText = 'width:38px;height:38px;border-radius:50%;object-fit:cover;display:block;box-shadow:0 2px 8px rgba(0,0,0,0.25);';
                    a.appendChild(img);
                }}
            }};
            applyLogo();
            setTimeout(applyLogo, 400);
        }})();
        """
        view.page().runJavaScript(js)

    def _current_site_host(self) -> str:
        view = self._current_view()
        if view is None:
            return ""
        u = view.url()
        if u.scheme().lower() not in ("http", "https"):
            return ""
        return self.interceptor._norm_site(u.host())

    def _schedule_shield_refresh(self) -> None:
        if not self._shield_timer.isActive():
            self._shield_timer.start()

    def _update_shield_label(self) -> None:
        site_host = self._current_site_host()
        if site_host:
            site_total, _ = self.interceptor.site_report(site_host)
            self.shield_btn.setText(f"🛡 {site_total}")
        else:
            self.shield_btn.setText(f"🛡 {self.interceptor.blocked_count}")

    def _show_site_shields(self) -> None:
        site_host = self._current_site_host()
        site_total, site_items = self.interceptor.site_report(site_host)

        def _on_quick_save(updated: PrivacySettings) -> None:
            self.settings = updated
            self.settings.save(self.settings_path)
            self.interceptor.settings = updated
            self._apply_profile_privacy()
            v = self._current_view()
            if v is not None:
                v.reload()

        dlg = BraveShieldsPopup(
            site_host=site_host,
            site_total=site_total,
            site_items=site_items,
            global_total=self.interceptor.blocked_count,
            settings=self.settings,
            on_update_settings=_on_quick_save,
            on_open_full_center=self._show_privacy_center,
            parent=self,
        )
        pos = self.shield_btn.mapToGlobal(self.shield_btn.rect().bottomRight())
        dlg.move(max(12, pos.x() - dlg.width()), pos.y() + 6)
        dlg.exec()

    def _update_bookmark_star(self, url_str: str) -> None:
        self.bookmark_act.setText("★" if self.storage.is_bookmarked(url_str) else "☆")

    def _toggle_current_bookmark(self) -> None:
        view = self._current_view()
        if view is None:
            return
        url_str = view.url().toString()
        if url_str == NEWTAB_URL:
            return
        saved = self.storage.toggle_bookmark(view.title(), url_str)
        self.bookmark_act.setText("★" if saved else "☆")
        self._rebuild_bookmarks_bar()

    def _wipe_browsing_data(self) -> None:
        self._closed_tabs.clear()
        self.downloads_records.clear()
        self._tor_pending_urls.clear()
        self._last_requested_url.clear()
        self.storage.clear_history()
        self.profile.clearHttpCache()
        self.profile.cookieStore().deleteAllCookies()
        if self.storage.history_path.exists():
            self.storage.history_path.unlink(missing_ok=True)
        profile_dir = self.data_dir / "profile"
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)

    def _show_downloads(self) -> None:
        dlg = DownloadsDialog(self.downloads_records, self.downloads_records.clear, self)
        dlg.exec()

    def _list_web_extensions(self) -> list[dict]:
        mgr = self.profile.extensionManager()
        loaded_by_dir: dict[Path, object] = {}
        if mgr is not None:
            for info in mgr.extensions():
                if info.path() and info.isLoaded():
                    loaded_by_dir[Path(info.path()).resolve()] = info

        out: list[dict] = []
        for ext_dir in self.plugin_mgr.list_saved_web_extension_dirs():
            mf = read_manifest_summary(ext_dir)
            slug = ext_dir.name
            info = loaded_by_dir.get(ext_dir.resolve())
            enabled = bool(self.plugin_mgr.state.get(f"webext:{slug}", {}).get("enabled", True))
            popup_s = ""
            if info is not None:
                popup_qurl = info.actionPopupUrl()
                if popup_qurl.isValid():
                    popup_s = popup_qurl.toString()
            out.append(
                {
                    "id": slug,
                    "name": (info.name() if info is not None and info.name() else mf.get("name")) or slug,
                    "description": (info.description() if info is not None and info.description() else mf.get("description")) or "",
                    "version": mf.get("version", "1.0"),
                    "mv": mf.get("mv", "3"),
                    "permissions": mf.get("permissions", "sin permisos especiales"),
                    "enabled": enabled and (info is not None),
                    "path": str(ext_dir),
                    "popup_url": popup_s,
                }
            )
        return out

    def _install_web_extension_path(self, src_path: Path) -> tuple[bool, str]:
        ok, dest, msg = self.plugin_mgr.import_web_extension(src_path)
        if not ok or dest is None:
            return False, msg
        self.plugin_mgr.state[f"webext:{dest.name}"] = {"installed": True, "enabled": True}
        self.plugin_mgr.save()
        mgr_main = self.profile.extensionManager()
        loop = QEventLoop()

        def _quit_loop(_info) -> None:
            if loop.isRunning():
                loop.quit()

        if mgr_main is not None:
            mgr_main.loadFinished.connect(_quit_loop)
        try:
            any_loading = False
            for prof in self._all_profiles():
                if prof.isOffTheRecord():
                    continue
                mgr = prof.extensionManager()
                if mgr is not None:
                    already = any(
                        i.path() and i.isLoaded() and Path(i.path()).resolve() == dest.resolve()
                        for i in mgr.extensions()
                    )
                    if not already:
                        mgr.loadExtension(str(dest))
                        any_loading = True
            if any_loading:
                QTimer.singleShot(600, loop.quit)
                loop.exec()
            QApplication.processEvents()
        finally:
            if mgr_main is not None:
                try:
                    mgr_main.loadFinished.disconnect(_quit_loop)
                except TypeError:
                    pass
        return True, msg

    def _toggle_web_extension(self, ext_slug: str, enabled: bool) -> None:
        self.plugin_mgr.state[f"webext:{ext_slug}"] = {"installed": True, "enabled": enabled}
        self.plugin_mgr.save()
        if enabled:
            ext_dir = (self.plugin_mgr.web_ext_dir / ext_slug).resolve()
            for prof in self._all_profiles():
                if prof.isOffTheRecord():
                    continue
                mgr = prof.extensionManager()
                if mgr is not None and ext_dir.is_dir():
                    already = any(
                        i.path() and i.isLoaded() and Path(i.path()).resolve() == ext_dir
                        for i in mgr.extensions()
                    )
                    if not already:
                        mgr.loadExtension(str(ext_dir))

    def _uninstall_web_extension(self, ext_slug: str) -> None:
        self.plugin_mgr.state[f"webext:{ext_slug}"] = {
            "installed": False,
            "enabled": False,
            "removed": True,
        }
        self.plugin_mgr.save()

    def _show_main_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Nueva pestaña (Ctrl+T)", lambda: self.add_new_tab(None, "Inicio"))
        menu.addAction(
            "Nueva pestaña contenedor aislado",
            lambda: self.add_new_tab(None, "Contenedor", isolated_container=True),
        )
        reopen_act = menu.addAction("Reabrir pestaña cerrada (Ctrl+Shift+T)", self._reopen_closed_tab)
        reopen_act.setEnabled(bool(self._closed_tabs))
        menu.addAction("Nueva ventana privada (Ctrl+Shift+N)", self.open_incognito_window)
        menu.addSeparator()
        menu.addAction("Buscar en la página (Ctrl+F)", self._open_find_bar)
        menu.addAction("Descargas (Ctrl+J)", self._show_downloads)
        menu.addAction("Historial y limpieza (Ctrl+H)", self._show_history)
        menu.addSeparator()
        view = self._current_view()
        cur_zoom = int(round((view.zoomFactor() if view else 1.0) * 100))
        menu.addAction(f"Acercar zoom ({cur_zoom}%)  (Ctrl++)", lambda: self._adjust_zoom(0.1))
        menu.addAction("Alejar zoom (Ctrl+-)", lambda: self._adjust_zoom(-0.1))
        menu.addAction("Zoom original 100% (Ctrl+0)", lambda: self._adjust_zoom(None))
        menu.addAction("Pantalla completa (F11)", self._toggle_window_fullscreen)
        menu.addSeparator()
        menu.addAction("Apariencia y transparencia", self._show_appearance)
        menu.addAction("Extensiones y Plugins", self._show_plugin_store)
        menu.addAction("Centro de Seguridad e IP", self._show_privacy_center)
        if is_gecko_available():
            menu.addSeparator()
            menu.addAction("Abrir con Motor Firefox C++ (Huella TLS Firefox)", self._open_gecko_session)
        pos = self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomRight())
        menu.exec(QPoint(pos.x() - menu.sizeHint().width(), pos.y() + 4))

    def _open_gecko_session(self) -> None:
        launch_gecko_session(
            use_tor=self.settings.proxy_enabled,
            safest_no_js=self.settings.safest_no_js,
            blocked_count=self.interceptor.blocked_count,
            https_upgrades=self.interceptor.https_upgrades,
            appearance=self.appearance,
        )

    def _show_plugin_store(self) -> None:
        web_ext_api = {
            "list": self._list_web_extensions,
            "install_path": self._install_web_extension_path,
            "set_enabled": self._toggle_web_extension,
            "uninstall": self._uninstall_web_extension,
            "open_popup": lambda url_s: self.add_new_tab(QUrl(url_s), "Extensión", isolated_container=False),
        }

        def _on_plugins_changed() -> None:
            self._sync_plugin_scripts()
            n_tot = len(self.plugin_mgr.active_plugins()) + sum(
                1 for e in self._list_web_extensions() if e.get("enabled")
            )
            self.plugins_btn.setToolTip(f"Extensiones y Plugins ({n_tot} activos)")

        dlg = PluginStoreDialog(self.plugin_mgr, _on_plugins_changed, self, web_ext_api=web_ext_api)
        dlg.exec()

    def _apply_theme_stylesheet(self) -> None:
        if self.incognito:
            self.setStyleSheet(NETLIS_INCOGNITO_QSS)
        elif self.appearance.preset == "antigravity":
            self.setStyleSheet(NETLIS_ANTIGRAVITY_QSS)
        else:
            self.setStyleSheet(NETLIS_NORMAL_QSS)

    def _refresh_url_bar_placeholder(self) -> None:
        eng_label = SEARCH_ENGINES.get(self.appearance.search_engine, SEARCH_ENGINES["duckduckgo"])[0].split(" (")[0]
        self.url_bar.setPlaceholderText(f"Buscar con {eng_label} o introducir una dirección")
        if hasattr(self, "search_pick_btn"):
            self.search_pick_btn.setIcon(_make_search_engine_icon(self.appearance.search_engine, self._netlis_icon))

    def _set_quick_search_engine(self, engine_key: str) -> None:
        if engine_key not in SEARCH_ENGINES:
            return
        self.appearance.search_engine = engine_key
        self.appearance.save(self.appearance_path)
        self._refresh_url_bar_placeholder()
        for i in range(self.stack.count()):
            w = self.stack.widget(i)
            if isinstance(w, QWebEngineView) and w.url().toString().startswith(NEWTAB_URL):
                self._load_newtab_html(w)

    def _show_search_picker_menu(self) -> None:
        menu = QMenu(self)
        hdr = menu.addAction("Buscar con:")
        hdr.setEnabled(False)
        for key, (label, _) in SEARCH_ENGINES.items():
            short = label.split(" (")[0]
            menu.addAction(
                _make_search_engine_icon(key, self._netlis_icon),
                f"{short}" + ("  ✓" if key == self.appearance.search_engine else ""),
                lambda _c=False, k=key: self._set_quick_search_engine(k),
            )
        menu.addSeparator()
        menu.addAction(_make_menu_action_icon("star"), "Marcadores", self._show_history)
        menu.addAction(_make_menu_action_icon("tabs"), "Nueva pestaña   Ctrl+T", lambda: self.add_new_tab(None, "Nueva pestaña"))
        menu.addAction(_make_menu_action_icon("history"), "Historial", self._show_history)
        menu.addAction(_make_menu_action_icon("bolt"), "Escudos y Seguridad", self._show_site_shields)
        menu.addSeparator()
        menu.addAction(_make_menu_action_icon("gear"), "Ajustes y Apariencia", self._show_appearance)
        pos = self.search_pick_btn.mapToGlobal(self.search_pick_btn.rect().bottomLeft())
        menu.exec(QPoint(pos.x(), pos.y() + 6))

    def _show_appearance(self) -> None:
        def _on_apply(updated: AppearanceSettings) -> None:
            self.appearance = updated
            self.appearance.save(self.appearance_path)
            self._apply_theme_stylesheet()
            self._refresh_url_bar_placeholder()
            self.setWindowOpacity(max(0.55, min(1.0, updated.opacity_percent / 100.0)))
            for i in range(self.stack.count()):
                w = self.stack.widget(i)
                if isinstance(w, QWebEngineView) and w.url().toString().startswith(NEWTAB_URL):
                    self._load_newtab_html(w)

        dlg = AppearanceDialog(self.appearance, _on_apply, self)
        dlg.exec()

    def _show_history(self) -> None:
        dlg = HistoryDialog(
            self.storage,
            lambda u: self.add_new_tab(QUrl(u), "Historial"),
            self._wipe_browsing_data,
            self,
        )
        dlg.exec()

    def _show_privacy_center(self) -> None:
        def _on_save(updated: PrivacySettings) -> None:
            self.settings = updated
            self.settings.save(self.settings_path)
            self.interceptor.settings = updated
            self._apply_profile_privacy()
            apply_qt_network_proxy(updated)
            if TOR_ENGINE is not None and updated.proxy_enabled:
                TOR_ENGINE.set_bridges_enabled(updated.tor_bridges_obfs4)
                TOR_ENGINE.set_exit_region(updated.ip_region)
            self.ip_btn.setText(self._ip_button_text())

        dlg = PrivacyCenterDialog(
            self.settings,
            self.interceptor.blocked_count,
            self.interceptor.https_upgrades,
            _on_save,
            self._wipe_browsing_data,
            self,
        )
        dlg.exec()

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            edges = self._edges_at(event.position().toPoint())
            handle = self.windowHandle()
            if edges != Qt.Edge(0) and handle is not None and handle.startSystemResize(edges):
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= self.tab_strip.height() + 8:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= self.tab_strip.height():
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def closeEvent(self, event) -> None:
        from PyQt6 import sip

        for tmr in (self._shield_timer, self._ram_timer, self._watchdog_timer, self._tor_poll_timer):
            if tmr.isActive():
                tmr.stop()
        # Destruir determinísticamente todas las vistas/páginas C++ antes que los QWebEngineProfile
        while self.stack.count() > 0:
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            if w is not None and not sip.isdeleted(w):
                sip.delete(w)
        self._tab_profiles.clear()
        if self.settings.clear_on_exit:
            self._wipe_browsing_data()
        if self in self._open_windows:
            self._open_windows.remove(self)
        if not self._open_windows and TOR_ENGINE is not None:
            TOR_ENGINE.stop(wipe_files=False)
        super().closeEvent(event)


def apply_qt_network_proxy(settings: PrivacySettings) -> None:
    """Configura el proxy SOCKS5h a nivel de motor QtNetwork/QtWebEngine (incluyendo DNS remoto)."""
    from urllib.parse import urlparse

    if settings.proxy_enabled and settings.proxy_url.strip():
        raw = settings.proxy_url.strip()
        parsed = urlparse(raw if "://" in raw else f"socks5://{raw}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 19050
        proxy = QNetworkProxy(QNetworkProxy.ProxyType.Socks5Proxy, host, port)
        proxy.setCapabilities(proxy.capabilities() | QNetworkProxy.Capability.HostNameLookupCapability)
        QNetworkProxy.setApplicationProxy(proxy)
    else:
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))


def main() -> int:
    global TOR_ENGINE
    install_crash_shield()
    if resource is not None:
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, OSError):
            pass
    parser = argparse.ArgumentParser(description="Netlis Browser")
    parser.add_argument("--smoke", action="store_true", help="Verifica que Netlis inicie y sale")
    parser.add_argument("--incognito", action="store_true", help="Abre directamente en modo incógnito")
    parser.add_argument("--no-tor", "--sin-tor", dest="no_tor", action="store_true", help="Inicia sin Tor (conexión directa rápida)")
    parser.add_argument("urls", nargs="*", help="URLs opcionales a abrir al iniciar")
    args, qt_args = parser.parse_known_args()

    data_dir = Path(__file__).resolve().parent / "data"
    settings = PrivacySettings.load(data_dir / "privacidad.json")
    if args.no_tor:
        settings.proxy_enabled = False
    appearance = AppearanceSettings.load(data_dir / "apariencia.json")

    if not args.smoke:
        auto_refresh_threats_async(data_dir)
        if settings.proxy_enabled:
            TOR_ENGINE = EmbeddedTorManager(data_dir)
            TOR_ENGINE.start_async(ip_region=settings.ip_region, use_bridges=settings.tor_bridges_obfs4)

    chromium_flags = build_chromium_flags(settings)
    existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{existing_flags} {' '.join(chromium_flags)}".strip()
    apply_qt_network_proxy(settings)

    app = QApplication([sys.argv[0], *chromium_flags, *qt_args])
    app.setApplicationName("netlis")
    app.setApplicationDisplayName("Netlis")
    app.setDesktopFileName("netlis")
    window = BrowserWindow(incognito=args.incognito, settings=settings, appearance=appearance)
    if not window._netlis_icon.isNull():
        app.setWindowIcon(window._netlis_icon)
    for idx_u, raw_u in enumerate(args.urls):
        if not raw_u or raw_u.startswith("-"):
            continue
        target_q = normalize_input_to_url(raw_u, window.appearance.search_engine)
        if idx_u == 0:
            window._navigate(target_q.toString())
        else:
            window.add_new_tab(target_q, "Cargando…")
    if args.smoke:
        inc_win = BrowserWindow(incognito=True, settings=settings, appearance=appearance)
        window.resize(1000, 700)
        window.show()
        app.processEvents()
        mask_ok = not window.mask().isEmpty()
        print(
            f"SMOKE_OK title={window.windowTitle()} opacity={window.windowOpacity():.2f} "
            f"incognito={inc_win.windowTitle()} clear_on_exit={settings.clear_on_exit} "
            f"rounded_mask={mask_ok}"
        )
        inc_win.close()
        window.close()
        app.processEvents()
        os._exit(0)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
