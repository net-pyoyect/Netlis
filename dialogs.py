"""Interfaces de Netlis estilo vidrio translúcido tipo iOS (frosted blur real + switches iOS)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from newtab import AppearanceSettings, BACKGROUND_PRESETS, SEARCH_ENGINES, normalize_wallpaper_path
from plugins import PluginDefinition, PluginManager
from privacy import (
    DOH_PROVIDERS,
    IP_REGIONS,
    PrivacySettings,
    is_proxy_reachable,
    pick_random_region,
    rotate_tor_identity,
)
from storage import BrowserStorage
from tor_manager import check_exit_ip
import security_shield
from updater import (
    apply_app_update,
    check_app_update,
    get_local_version_info,
    get_security_health_report,
    install_systemd_timer,
    update_browser_engine,
    update_threat_feed,
)

IOS_GLASS_QSS = """
QDialog {
    background: transparent;
}
QLabel { background: transparent; color: #f5f5fa; }
QLabel#heading { font-size: 19px; font-weight: 700; color: #ffffff; }
QLabel#subheading { font-size: 12px; color: rgba(240, 240, 252, 185); }
QLabel#cardTitle { font-size: 13px; font-weight: 600; color: #ffffff; }
QLabel#cardDesc { font-size: 11px; color: rgba(235, 235, 248, 175); }
QLabel#statPill {
    background-color: rgba(255, 255, 255, 32);
    border: 1px solid rgba(255, 255, 255, 65);
    border-radius: 13px;
    padding: 5px 13px;
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
}
QFrame#sectionCard {
    background-color: rgba(255, 255, 255, 22);
    border: 1px solid rgba(255, 255, 255, 48);
    border-radius: 16px;
    padding: 10px;
}
QFrame#settingRow {
    background-color: rgba(255, 255, 255, 20);
    border: 1px solid rgba(255, 255, 255, 42);
    border-radius: 15px;
    padding: 8px 12px;
}
QFrame#settingRow:hover {
    background-color: rgba(255, 255, 255, 34);
    border: 1px solid rgba(255, 255, 255, 78);
}
QScrollArea, QScrollArea > QWidget > QWidget { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 0; }
QScrollBar::handle:vertical { background: rgba(255, 255, 255, 70); min-height: 28px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 120); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: rgba(255, 255, 255, 18);
    border: 1px solid rgba(255, 255, 255, 38);
    color: rgba(245, 245, 255, 200);
    padding: 8px 18px;
    border-radius: 12px;
    margin-right: 6px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: rgba(255, 255, 255, 58);
    border: 1px solid rgba(255, 255, 255, 115);
    color: #ffffff;
}
QTabBar::tab:hover:!selected { background: rgba(255, 255, 255, 32); color: #ffffff; }
QLineEdit {
    background-color: rgba(10, 10, 18, 105);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 52);
    border-radius: 12px;
    padding: 8px 13px;
    font-size: 13px;
}
QLineEdit:focus { border: 1px solid rgba(100, 210, 255, 230); background-color: rgba(10, 10, 18, 135); }
QListWidget {
    background-color: rgba(12, 12, 20, 95);
    border: 1px solid rgba(255, 255, 255, 45);
    border-radius: 15px;
    padding: 6px;
    color: #f4f4fc;
    font-size: 13px;
}
QListWidget::item { padding: 9px 12px; border-radius: 10px; margin-bottom: 3px; }
QListWidget::item:hover { background-color: rgba(255, 255, 255, 24); }
QListWidget::item:selected {
    background-color: rgba(255, 255, 255, 50);
    border: 1px solid rgba(255, 255, 255, 85);
    color: #ffffff;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 52), stop:1 rgba(255, 255, 255, 24));
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 68);
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 78), stop:1 rgba(255, 255, 255, 40));
    border: 1px solid rgba(255, 255, 255, 115);
}
QPushButton:pressed { background: rgba(255, 255, 255, 32); }
QPushButton#danger {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 69, 58, 175), stop:1 rgba(215, 38, 48, 175));
    border: 1px solid rgba(255, 165, 160, 145);
    color: #ffffff;
}
QPushButton#danger:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 90, 80, 205), stop:1 rgba(235, 50, 60, 205));
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(10, 132, 255, 210), stop:1 rgba(0, 102, 220, 210));
    border: 1px solid rgba(165, 220, 255, 165);
    color: #ffffff;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(45, 155, 255, 235), stop:1 rgba(15, 120, 240, 235));
}
QPushButton#presetBtn {
    border-radius: 13px; padding: 11px; text-align: left; font-weight: 600;
    border: 1px solid rgba(255, 255, 255, 58); color: #ffffff;
}
QPushButton#presetBtn:checked { border: 2px solid #64d2ff; }
QComboBox {
    background: rgba(15, 15, 24, 120);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 58);
    border-radius: 11px;
    padding: 7px 12px;
    font-size: 13px;
}
"""


def _fast_frosted_blur(pixmap: QPixmap, factor: int = 12) -> QPixmap:
    """Desenfoque gaussiano rápido multi-escala estilo iOS Control Center."""
    if pixmap.isNull() or pixmap.width() < factor or pixmap.height() < factor:
        return pixmap
    w, h = pixmap.width(), pixmap.height()
    small = pixmap.scaled(
        max(1, w // factor),
        max(1, h // factor),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    mid = small.scaled(
        max(1, w // 3),
        max(1, h // 3),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return mid.scaled(
        w,
        h,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class IOSToggle(QPushButton):
    """Interruptor deslizante estilo iPhone (cápsula translúcida con círculo blanco)."""

    def __init__(self, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(QSize(50, 28))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = rect.height() / 2.0

        if self.isChecked():
            grad = QLinearGradient(0, 0, 0, rect.height())
            grad.setColorAt(0.0, QColor(52, 215, 98, 235))
            grad.setColorAt(1.0, QColor(36, 180, 78, 235))
            p.setBrush(grad)
            p.setPen(QPen(QColor(180, 255, 200, 150), 1.0))
        else:
            p.setBrush(QColor(255, 255, 255, 42))
            p.setPen(QPen(QColor(255, 255, 255, 75), 1.0))

        p.drawRoundedRect(rect, radius, radius)

        knob_d = rect.height() - 5.0
        knob_x = (rect.right() - knob_d - 2.5) if self.isChecked() else (rect.left() + 2.5)
        knob_y = rect.top() + 2.5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 55))
        p.drawEllipse(QRectF(knob_x, knob_y + 1.0, knob_d, knob_d))
        p.setBrush(QColor(255, 255, 255, 250))
        p.drawEllipse(QRectF(knob_x, knob_y, knob_d, knob_d))
        p.end()


class ToggleRow(QFrame):
    """Tarjeta translúcida con interruptor estilo iPhone."""

    def __init__(self, title: str, desc: str, checked: bool) -> None:
        super().__init__()
        self.setObjectName("settingRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(13, 9, 13, 9)
        row.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        lbl_title = QLabel(title)
        lbl_title.setObjectName("cardTitle")
        lbl_desc = QLabel(desc)
        lbl_desc.setObjectName("cardDesc")
        lbl_desc.setWordWrap(True)
        text_col.addWidget(lbl_title)
        text_col.addWidget(lbl_desc)

        self.btn = IOSToggle(checked)
        row.addLayout(text_col, stretch=1)
        row.addWidget(self.btn)

    def isChecked(self) -> bool:
        return self.btn.isChecked()


class RoundedDialog(QDialog):
    """Ventana modal con vidrio esmerilado translúcido estilo iPhone sobre la ventana padre."""

    _RADIUS = 22.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_pos = None
        self._blurred_parent: QPixmap | None = None
        if parent is not None and isinstance(parent, QWidget):
            try:
                snap = parent.grab()
                self._blurred_parent = _fast_frosted_blur(snap, factor=13)
            except Exception:
                self._blurred_parent = None

    def showEvent(self, event) -> None:
        p = self.parentWidget()
        if p is not None:
            center = p.mapToGlobal(p.rect().center())
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        super().showEvent(event)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)

        clip = QPainterPath()
        clip.addRoundedRect(rect, self._RADIUS, self._RADIUS)
        painter.save()
        painter.setClipPath(clip)

        # 1. Pintar el fondo desenfocado real de la ventana inferior (efecto vidrio iPhone)
        p_widget = self.parentWidget()
        if self._blurred_parent is not None and p_widget is not None:
            top_left_in_parent = p_widget.mapFromGlobal(self.mapToGlobal(QPoint(0, 0)))
            src_rect = QRect(top_left_in_parent, self.size())
            painter.drawPixmap(self.rect(), self._blurred_parent, src_rect)

        # 2. Tinte translúcido tipo iOS Dark Glass + reflejo superior
        glass_grad = QLinearGradient(0, 0, 0, self.height())
        glass_grad.setColorAt(0.0, QColor(36, 38, 52, 162))
        glass_grad.setColorAt(1.0, QColor(20, 21, 30, 182))
        painter.fillRect(rect, glass_grad)

        shine = QLinearGradient(0, 0, 0, 70)
        shine.setColorAt(0.0, QColor(255, 255, 255, 36))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 70), shine)
        painter.restore()

        # 3. Borde especular luminoso de cristal
        border_grad = QLinearGradient(0, 0, 0, self.height())
        border_grad.setColorAt(0.0, QColor(255, 255, 255, 115))
        border_grad.setColorAt(0.5, QColor(255, 255, 255, 48))
        border_grad.setColorAt(1.0, QColor(255, 255, 255, 28))
        painter.setPen(QPen(border_grad, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, self._RADIUS, self._RADIUS)
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 54:
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


class AppearanceDialog(RoundedDialog):
    """Selector de fondo y transparencia con vidrio tipo iPhone."""

    def __init__(
        self,
        appearance: AppearanceSettings,
        on_apply: Callable[[AppearanceSettings], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.appearance = AppearanceSettings(
            preset=appearance.preset,
            image_path=appearance.image_path,
            opacity_percent=appearance.opacity_percent,
            search_engine=appearance.search_engine,
        )
        self.on_apply = on_apply
        self.setWindowTitle("Apariencia — Netlis")
        self.resize(540, 470)
        self.setStyleSheet(IOS_GLASS_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("Apariencia y cristal")
        title.setObjectName("heading")
        sub = QLabel("Personaliza el fondo de inicio y la transparencia de Netlis.")
        sub.setObjectName("subheading")
        layout.addWidget(title)
        layout.addWidget(sub)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.preset_buttons: dict[str, QPushButton] = {}
        swatch_colors = {
            "netlis": "rgba(43, 42, 51, 185)",
            "antigravity": "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(124,92,255,215),stop:1 rgba(56,189,248,205))",
            "oceano": "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(15,32,39,195),stop:1 rgba(44,83,100,195))",
            "aurora": "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(18,27,40,195),stop:1 rgba(42,27,61,195))",
            "atardecer": "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(31,20,40,195),stop:1 rgba(61,29,52,195))",
            "minimal": "rgba(18, 19, 24, 195)",
        }
        for i, (key, (label, _)) in enumerate(BACKGROUND_PRESETS.items()):
            btn = QPushButton(label)
            btn.setObjectName("presetBtn")
            btn.setCheckable(True)
            btn.setChecked(key == self.appearance.preset)
            bg = swatch_colors.get(key, "rgba(43, 42, 51, 185)")
            btn.setStyleSheet(f"QPushButton#presetBtn {{ background: {bg}; }}")
            btn.clicked.connect(lambda _c=False, k=key: self._select_preset(k))
            self.preset_buttons[key] = btn
            grid.addWidget(btn, i // 2, i % 2)
        layout.addLayout(grid)

        card = QFrame()
        card.setObjectName("sectionCard")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        row_img = QHBoxLayout()
        self.lbl_img = QLabel(self.appearance.image_path or "Sin imagen personalizada")
        self.lbl_img.setObjectName("subheading")
        btn_pick = QPushButton("Elegir imagen...")
        btn_pick.clicked.connect(self._pick_image)
        btn_clear_img = QPushButton("Quitar")
        btn_clear_img.clicked.connect(self._clear_image)
        row_img.addWidget(self.lbl_img, stretch=1)
        row_img.addWidget(btn_pick)
        row_img.addWidget(btn_clear_img)
        card_layout.addLayout(row_img)

        self.lbl_opacity = QLabel(f"Transparencia de ventana: {self.appearance.opacity_percent}%")
        self.lbl_opacity.setObjectName("cardTitle")
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(55, 100)
        self.slider_opacity.setValue(self.appearance.opacity_percent)
        self.slider_opacity.valueChanged.connect(self._on_slider)
        card_layout.addWidget(self.lbl_opacity)
        card_layout.addWidget(self.slider_opacity)

        row_search = QHBoxLayout()
        row_search.addWidget(QLabel("Buscador por defecto:"))
        self.cmb_search = QComboBox()
        for k, (label, _) in SEARCH_ENGINES.items():
            self.cmb_search.addItem(label, k)
        s_idx = self.cmb_search.findData(self.appearance.search_engine)
        if s_idx >= 0:
            self.cmb_search.setCurrentIndex(s_idx)
        row_search.addWidget(self.cmb_search, stretch=1)
        card_layout.addLayout(row_search)

        layout.addWidget(card)

        actions = QHBoxLayout()
        apply_btn = QPushButton("Aplicar")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self._apply)
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.close)
        actions.addStretch()
        actions.addWidget(apply_btn)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

    def _select_preset(self, key: str) -> None:
        self.appearance.preset = key
        for k, b in self.preset_buttons.items():
            b.setChecked(k == key)

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar fondo", "", "Imágenes (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            norm = normalize_wallpaper_path(path)
            self.appearance.image_path = norm
            self.lbl_img.setText(norm)

    def _clear_image(self) -> None:
        self.appearance.image_path = ""
        self.lbl_img.setText("Sin imagen personalizada")

    def _on_slider(self, val: int) -> None:
        self.appearance.opacity_percent = val
        self.lbl_opacity.setText(f"Transparencia de ventana: {val}%")

    def _apply(self) -> None:
        self.appearance.search_engine = str(self.cmb_search.currentData() or "duckduckgo")
        self.on_apply(self.appearance)
        self.close()


class HistoryDialog(RoundedDialog):
    """Historial translúcido estilo vidrio iOS."""

    def __init__(
        self,
        storage: BrowserStorage,
        on_open_url: Callable[[str], None],
        on_clear_browsing_data: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.storage = storage
        self.on_open_url = on_open_url
        self.on_clear_browsing_data = on_clear_browsing_data
        self.setWindowTitle("Historial — Netlis")
        self.resize(740, 520)
        self.setStyleSheet(IOS_GLASS_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        left = QVBoxLayout()
        header = QLabel("Historial de navegación")
        header.setObjectName("heading")
        subtitle = QLabel("Se borra automáticamente al cerrar Netlis.")
        subtitle.setObjectName("subheading")
        left.addWidget(header)
        left.addWidget(subtitle)
        top.addLayout(left)
        top.addStretch()

        pill = QLabel("Limpieza automática activa")
        pill.setObjectName("statPill")
        top.addWidget(pill)
        layout.addLayout(top)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar en el historial...")
        self.search_input.textChanged.connect(self._populate_list)
        layout.addWidget(self.search_input)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.list_widget, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("subheading")
        layout.addWidget(self.status_label)

        clean_card = QFrame()
        clean_card.setObjectName("sectionCard")
        clean_layout = QHBoxLayout(clean_card)

        btn_1h = QPushButton("Última hora")
        btn_1h.clicked.connect(lambda: self._clear_since(hours=1))
        btn_24h = QPushButton("Últimas 24h")
        btn_24h.clicked.connect(lambda: self._clear_since(hours=24))
        btn_sel = QPushButton("Quitar")
        btn_sel.clicked.connect(self._remove_selected)
        btn_all = QPushButton("Borrar todo ahora")
        btn_all.setObjectName("danger")
        btn_all.clicked.connect(self._clear_all)

        clean_layout.addWidget(btn_1h)
        clean_layout.addWidget(btn_24h)
        clean_layout.addWidget(btn_sel)
        clean_layout.addStretch()
        clean_layout.addWidget(btn_all)
        layout.addWidget(clean_card)

        bottom = QHBoxLayout()
        open_btn = QPushButton("Abrir pestaña")
        open_btn.setObjectName("primary")
        open_btn.clicked.connect(self._open_current)
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(open_btn)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self._populate_list()

    def _populate_list(self) -> None:
        query = self.search_input.text().strip().lower()
        self.list_widget.clear()
        shown = 0
        for idx, entry in enumerate(self.storage.history):
            title = entry.get("title", "")
            url = entry.get("url", "")
            visited = entry.get("visited_at", "")
            if query and query not in title.lower() and query not in url.lower():
                continue
            item = QListWidgetItem(f"{visited}   —   {title}\n{url}")
            item.setData(Qt.ItemDataRole.UserRole, (idx, url))
            self.list_widget.addItem(item)
            shown += 1
        self.status_label.setText(f"{shown} de {len(self.storage.history)} elementos")

    def _open_selected(self, item: QListWidgetItem) -> None:
        _, url = item.data(Qt.ItemDataRole.UserRole)
        if url:
            self.on_open_url(url)
            self.close()

    def _open_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is not None:
            self._open_selected(item)

    def _remove_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        idx, _ = item.data(Qt.ItemDataRole.UserRole)
        if 0 <= idx < len(self.storage.history):
            self.storage.history.pop(idx)
            self.storage.save_history()
            self._populate_list()

    def _clear_since(self, hours: int) -> None:
        cutoff = datetime.now() - timedelta(hours=hours)
        kept = []
        for entry in self.storage.history:
            try:
                ts = datetime.strptime(entry.get("visited_at", ""), "%Y-%m-%d %H:%M")
                if ts < cutoff:
                    kept.append(entry)
            except ValueError:
                kept.append(entry)
        removed = len(self.storage.history) - len(kept)
        self.storage.history = kept
        self.storage.save_history()
        self._populate_list()
        self.status_label.setText(f"Se eliminaron {removed} elementos de las últimas {hours}h.")

    def _clear_all(self) -> None:
        self.storage.clear_history()
        self.on_clear_browsing_data()
        self._populate_list()
        self.status_label.setText("Historial, cookies y caché eliminados.")


class PrivacyCenterDialog(RoundedDialog):
    """Panel de Privacidad, Seguridad e IP con vidrio esmerilado tipo iPhone."""

    def __init__(
        self,
        settings: PrivacySettings,
        blocked_count: int,
        https_upgrades: int,
        on_save: Callable[[PrivacySettings], None],
        on_wipe_now: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.on_save = on_save
        self.on_wipe_now = on_wipe_now
        self.setWindowTitle("Privacidad y seguridad — Netlis")
        self.resize(650, 585)
        self.setStyleSheet(IOS_GLASS_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        left = QVBoxLayout()
        title = QLabel("Privacidad y seguridad")
        title.setObjectName("heading")
        n_mal = len(security_shield.DYNAMIC_THREAT_DOMAINS)
        upd_st = get_update_status()
        last_upd = upd_st.get("last_threat_date") or "automático activo"
        self.sub_lbl = QLabel(
            f"{blocked_count} bloqueados  •  {https_upgrades} HTTPS  •  {n_mal:,} firmas locales ({last_upd})"
        )
        self.sub_lbl.setObjectName("subheading")
        left.addWidget(title)
        left.addWidget(self.sub_lbl)
        top.addLayout(left)
        top.addStretch()

        pill = QLabel(self._security_level_label())
        pill.setObjectName("statPill")
        top.addWidget(pill)
        layout.addLayout(top)

        tabs = QTabWidget()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        tab_shield = QWidget()
        shield_layout = QVBoxLayout(tab_shield)
        shield_layout.setSpacing(8)

        self.row_trackers = ToggleRow(
            "Bloqueador de rastreadores y anuncios",
            "Impide que redes publicitarias y scripts de análisis sigan tu navegación.",
            settings.block_trackers,
        )
        self.row_yt_ads = ToggleRow(
            "Bloqueador de anuncios en YouTube",
            "Bloquea peticiones de publicidad y salta anuncios en el reproductor.",
            settings.block_youtube_ads,
        )
        self.row_strip = ToggleRow(
            "Limpiar parámetros de rastreo en enlaces",
            "Elimina etiquetas utm_*, fbclid y gclid antes de cargar la página.",
            settings.strip_tracking_params,
        )
        self.row_https = ToggleRow(
            "Modo solo HTTPS",
            "Actualiza automáticamente conexiones HTTP sin cifrar a HTTPS.",
            settings.https_only,
        )
        self.row_cookies = ToggleRow(
            "Bloquear cookies de terceros",
            "Evita el seguimiento entre sitios distintos mediante cookies.",
            settings.block_third_party_cookies,
        )
        self.row_fp = ToggleRow(
            "Protección contra huellas digitales y WebRTC",
            "Bloquea sendBeacon, oculta la IP local WebRTC y envía DNT + Sec-GPC.",
            settings.anti_fingerprinting,
        )
        self.row_jitless = ToggleRow(
            "Blindaje Anti-Exploit V8 (Modo Jitless)",
            "Desactiva la compilación JIT y WebAssembly para neutralizar >70% de exploits día cero.",
            settings.exploit_shield_jitless,
        )
        self.row_site_iso = ToggleRow(
            "Aislamiento estricto de sitios (Proceso OS por dominio)",
            "Ejecuta cada sitio en un proceso aislado con partición total de caché y almacenamiento.",
            settings.strict_site_isolation,
        )
        self.row_tab_containers = ToggleRow(
            "Contenedores efímeros aislados por pestaña",
            "Cada pestaña nueva usa su propio almacén aislado de cookies y sesión en RAM.",
            settings.isolated_tab_containers,
        )
        self.row_no_js = ToggleRow(
            "Nivel Más Seguro (Bloquear todo JavaScript)",
            "Apaga 100% JavaScript en sitios externos (igual al nivel Safest de Tor Browser).",
            settings.safest_no_js,
        )
        self.row_phishing = ToggleRow(
            "Escudo local Anti-Phishing y Guardia Magic-Bytes",
            "Bloquea sitios falsos y verifica firmas binarias ELF/MZ + SHA-256 en cada descarga.",
            settings.phishing_and_malware_guard,
        )
        self.row_clear_exit = ToggleRow(
            "Borrar todo al salir",
            "Elimina historial, cookies, caché y perfil físico al cerrar Netlis.",
            settings.clear_on_exit,
        )

        for r in (
            self.row_site_iso,
            self.row_tab_containers,
            self.row_no_js,
            self.row_jitless,
            self.row_phishing,
            self.row_trackers,
            self.row_yt_ads,
            self.row_strip,
            self.row_https,
            self.row_cookies,
            self.row_fp,
            self.row_clear_exit,
        ):
            shield_layout.addWidget(r)
        shield_layout.addStretch()
        scroll.setWidget(tab_shield)
        tabs.addTab(scroll, "Protección")

        tab_net = QWidget()
        net_layout = QVBoxLayout(tab_net)
        net_layout.setSpacing(10)

        self.row_doh = ToggleRow(
            "DNS sobre HTTPS (DoH)",
            "Cifra tus consultas DNS para que el proveedor de internet no las vea.",
            settings.doh_enabled,
        )
        net_layout.addWidget(self.row_doh)

        doh_card = QFrame()
        doh_card.setObjectName("sectionCard")
        doh_row = QHBoxLayout(doh_card)
        doh_row.addWidget(QLabel("Proveedor DNS:"))
        self.cmb_doh = QComboBox()
        for key, (label, _) in DOH_PROVIDERS.items():
            self.cmb_doh.addItem(label, key)
        idx = self.cmb_doh.findData(settings.doh_provider)
        if idx >= 0:
            self.cmb_doh.setCurrentIndex(idx)
        doh_row.addWidget(self.cmb_doh, stretch=1)
        net_layout.addWidget(doh_card)

        proxy_online = is_proxy_reachable(settings.proxy_url)
        proxy_desc = (
            "Túnel Tor integrado activo: tu IP real y tu DNS están 100% ocultos."
            if proxy_online
            else "Túnel Tor integrado en Netlis (se inicia automáticamente al abrir)."
        )
        self.row_proxy = ToggleRow(
            "Ocultar mi IP real con red Tor integrada",
            proxy_desc,
            settings.proxy_enabled,
        )
        net_layout.addWidget(self.row_proxy)

        self.row_bridges = ToggleRow(
            "Puentes Anticensura (obfs4 / lyrebird)",
            "Disfraza tu conexión Tor para que ni tu proveedor ni redes bloqueadas sepan que usas Tor.",
            settings.tor_bridges_obfs4,
        )
        net_layout.addWidget(self.row_bridges)

        ip_card = QFrame()
        ip_card.setObjectName("sectionCard")
        ip_v = QVBoxLayout(ip_card)
        ip_v.setSpacing(8)

        reg_row = QHBoxLayout()
        reg_row.addWidget(QLabel("Región de salida:"))
        self.cmb_region = QComboBox()
        for code, name in IP_REGIONS.items():
            self.cmb_region.addItem(name, code)
        r_idx = self.cmb_region.findData(settings.ip_region)
        if r_idx >= 0:
            self.cmb_region.setCurrentIndex(r_idx)
        reg_row.addWidget(self.cmb_region, stretch=1)

        btn_rotate = QPushButton("Rotar IP aleatoria")
        btn_rotate.clicked.connect(self._rotate_ip)
        reg_row.addWidget(btn_rotate)
        ip_v.addLayout(reg_row)

        self.txt_proxy = QLineEdit(settings.proxy_url)
        self.txt_proxy.setPlaceholderText("socks5://127.0.0.1:19050")
        ip_v.addWidget(self.txt_proxy)

        check_row = QHBoxLayout()
        btn_check_ip = QPushButton("Comprobar mi IP")
        btn_check_ip.clicked.connect(self._check_current_ip)
        self.lbl_ip_status = QLabel("Pulsa para consultar tu IP pública actual.")
        self.lbl_ip_status.setObjectName("subheading")
        check_row.addWidget(btn_check_ip)
        check_row.addWidget(self.lbl_ip_status, stretch=1)
        ip_v.addLayout(check_row)

        net_layout.addWidget(ip_card)
        net_layout.addStretch()
        tabs.addTab(tab_net, "Red e IP")

        tab_maint = QWidget()
        maint_layout = QVBoxLayout(tab_maint)
        maint_layout.setSpacing(10)
        maint_card = QFrame()
        maint_card.setObjectName("sectionCard")
        maint_v = QVBoxLayout(maint_card)
        maint_v.setSpacing(8)
        lbl_m_head = QLabel("Auditoría Criptográfica y Parches de Seguridad")
        lbl_m_head.setObjectName("cardTitle")
        self.lbl_health_details = QLabel("")
        self.lbl_health_details.setObjectName("cardDesc")
        self.lbl_health_details.setWordWrap(True)
        btn_sys_timer = QPushButton("Activar / Verificar auto-actualización en segundo plano (systemd)")
        btn_sys_timer.clicked.connect(self._activate_systemd_timer)
        btn_app_upd = QPushButton("Buscar y aplicar actualización de Netlis (GitHub)")
        btn_app_upd.setObjectName("primary")
        btn_app_upd.clicked.connect(self._check_and_apply_app_update)
        maint_v.addWidget(lbl_m_head)
        maint_v.addWidget(self.lbl_health_details)
        maint_v.addWidget(btn_app_upd)
        maint_v.addWidget(btn_sys_timer)
        maint_layout.addWidget(maint_card)
        maint_layout.addStretch()
        self._refresh_health_card()
        tabs.addTab(tab_maint, "Mantenimiento")

        layout.addWidget(tabs, stretch=1)

        actions = QHBoxLayout()
        wipe_btn = QPushButton("Borrar rastros ahora")
        wipe_btn.setObjectName("danger")
        wipe_btn.clicked.connect(self._wipe_now)

        upd_btn = QPushButton("Actualizar firmas y motor")
        upd_btn.clicked.connect(self._run_updates)

        save_btn = QPushButton("Guardar")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.close)

        actions.addWidget(wipe_btn)
        actions.addWidget(upd_btn)
        actions.addStretch()
        actions.addWidget(save_btn)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

    def _security_level_label(self) -> str:
        score = sum([
            self.settings.block_trackers,
            self.settings.block_youtube_ads,
            self.settings.https_only,
            self.settings.doh_enabled,
            self.settings.anti_fingerprinting,
            self.settings.clear_on_exit,
        ])
        if score >= 6:
            return "Protección estricta"
        if score >= 4:
            return "Protección estándar"
        return "Protección básica"

    def _rotate_ip(self) -> None:
        code, name = pick_random_region()
        idx = self.cmb_region.findData(code)
        if idx >= 0:
            self.cmb_region.setCurrentIndex(idx)
        _, msg = rotate_tor_identity(region_code=code)
        self.lbl_ip_status.setText(f"{name} — {msg}")

    def _check_current_ip(self) -> None:
        self.lbl_ip_status.setText("Consultando IP de salida a través del túnel...")
        self.lbl_ip_status.repaint()
        try:
            info = check_exit_ip(use_tor=self.row_proxy.isChecked())
            tag = "Tor oculto" if info.get("is_tor") else "Directa"
            self.lbl_ip_status.setText(f"IP vista por las webs ({tag}): {info['ip']} ({info['location']})")
        except Exception:
            self.lbl_ip_status.setText("Conectando circuito Tor... intenta en unos segundos.")

    def _refresh_health_card(self) -> None:
        rep = get_security_health_report()
        v_info = get_local_version_info()
        t_sha = (rep.get("threat_sha256") or "pendiente")[:16]
        tor_sha = (rep.get("tor_sha256") or "pendiente")[:16]
        tmr = "Activo (06:00 y 18:00)" if rep.get("systemd_timer_installed") else "No instalado"
        self.lbl_health_details.setText(
            f"• Netlis Browser: v{v_info.get('version', '1.0.0')}  (Repo: {v_info.get('repo') or 'local'})\n"
            f"• Motor Chromium: {rep['chromium_version']}  (Parche CVE: {rep['chromium_security_patch']})\n"
            f"• QtWebEngine: {rep['qtwebengine_version']}   •   Tor integrado: {rep['tor_version']} (SHA-256: {tor_sha}…)\n"
            f"• Base Anti-Phishing/Malware: {rep['threat_count']:,} dominios (SHA-256: {t_sha}…)\n"
            f"• Mantenimiento automático con navegador cerrado (systemd --user): {tmr}"
        )

    def _check_and_apply_app_update(self) -> None:
        self.sub_lbl.setText("Consultando nuevas versiones de Netlis...")
        self.sub_lbl.repaint()
        chk = check_app_update()
        if not chk.get("ok"):
            self.sub_lbl.setText(str(chk.get("notes") or "No se pudo consultar actualización."))
            return
        if not chk.get("has_update"):
            self.sub_lbl.setText(f"Netlis ya está al día (v{chk.get('local_version')}).")
            return
        ok, msg = apply_app_update()
        self.sub_lbl.setText(msg if ok else f"Error: {msg}")
        self._refresh_health_card()

    def _activate_systemd_timer(self) -> None:
        _, msg = install_systemd_timer()
        self.sub_lbl.setText(msg)
        self._refresh_health_card()

    def _run_updates(self) -> None:
        self.sub_lbl.setText("Verificando SHA-256, firmas URLhaus/Phishing Army y parches Chromium...")
        self.sub_lbl.repaint()
        ok_f, count, _ = update_threat_feed()
        ok_e, msg_e = update_browser_engine()
        status_f = f"{count:,} firmas verificadas" if ok_f else f"{count:,} firmas íntegras en caché"
        self.sub_lbl.setText(f"{status_f}  •  {msg_e}")
        self._refresh_health_card()

    def _wipe_now(self) -> None:
        self.on_wipe_now()
        self.close()

    def _save(self) -> None:
        updated = PrivacySettings(
            block_trackers=self.row_trackers.isChecked(),
            block_youtube_ads=self.row_yt_ads.isChecked(),
            strip_tracking_params=self.row_strip.isChecked(),
            https_only=self.row_https.isChecked(),
            doh_enabled=self.row_doh.isChecked(),
            doh_provider=str(self.cmb_doh.currentData() or "adguard"),
            block_third_party_cookies=self.row_cookies.isChecked(),
            anti_fingerprinting=self.row_fp.isChecked(),
            exploit_shield_jitless=self.row_jitless.isChecked(),
            strict_site_isolation=self.row_site_iso.isChecked(),
            isolated_tab_containers=self.row_tab_containers.isChecked(),
            safest_no_js=self.row_no_js.isChecked(),
            phishing_and_malware_guard=self.row_phishing.isChecked(),
            clear_on_exit=self.row_clear_exit.isChecked(),
            proxy_enabled=self.row_proxy.isChecked(),
            tor_bridges_obfs4=self.row_bridges.isChecked(),
            proxy_url=self.txt_proxy.text().strip() or "socks5://127.0.0.1:19050",
            ip_region=str(self.cmb_region.currentData() or "auto"),
        )
        self.on_save(updated)
        self.close()


class PluginIconBadge(QWidget):
    """Ícono vectorial en azulejo de vidrio estilo iOS App Store para cada plugin."""

    def __init__(self, icon_kind: str, accent_hex: str, parent=None) -> None:
        super().__init__(parent)
        self.icon_kind = icon_kind
        self.accent = QColor(accent_hex)
        self.setFixedSize(QSize(46, 46))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1.5, 1.5, self.width() - 3.0, self.height() - 3.0)

        bg = QLinearGradient(0, 0, 0, self.height())
        c_top = QColor(self.accent)
        c_top.setAlpha(82)
        c_bot = QColor(self.accent)
        c_bot.setAlpha(32)
        bg.setColorAt(0.0, c_top)
        bg.setColorAt(1.0, c_bot)
        p.setBrush(bg)

        rim = QColor(self.accent)
        rim.setAlpha(155)
        p.setPen(QPen(rim, 1.2))
        p.drawRoundedRect(r, 12.0, 12.0)

        pen = QPen(QColor(255, 255, 255, 240), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        k = self.icon_kind
        if k == "radar_shield":
            sh = QPainterPath()
            sh.moveTo(23, 10)
            sh.lineTo(34, 14)
            sh.quadTo(34, 27, 23, 36)
            sh.quadTo(12, 27, 12, 14)
            sh.closeSubpath()
            p.drawPath(sh)
            p.drawEllipse(QPointF(23, 22), 4.0, 4.0)
            p.setBrush(self.accent)
            p.drawEllipse(QPointF(23, 22), 1.5, 1.5)
        elif k == "moon":
            moon = QPainterPath()
            moon.addEllipse(QRectF(13, 12, 20, 20))
            cut = QPainterPath()
            cut.addEllipse(QRectF(19, 10, 18, 18))
            p.drawPath(moon.subtracted(cut))
        elif k == "cookie_block":
            p.drawEllipse(QRectF(13, 13, 20, 20))
            p.drawLine(16, 30, 30, 16)
        elif k == "unlock":
            p.drawRoundedRect(QRectF(15, 22, 16, 12), 3.0, 3.0)
            arc = QPainterPath()
            arc.moveTo(18, 22)
            arc.lineTo(18, 16)
            arc.quadTo(23, 11, 28, 16)
            p.drawPath(arc)
        elif k == "pip":
            p.drawRoundedRect(QRectF(11, 13, 24, 18), 3.0, 3.0)
            p.setBrush(QColor(255, 255, 255, 210))
            p.drawRoundedRect(QRectF(23, 21, 9, 7), 1.5, 1.5)
        elif k == "speed":
            t1 = QPolygonF([QPointF(13, 15), QPointF(23, 23), QPointF(13, 31)])
            t2 = QPolygonF([QPointF(23, 15), QPointF(33, 23), QPointF(23, 31)])
            p.drawPolygon(t1)
            p.drawPolygon(t2)
        elif k == "translate":
            p.drawEllipse(QRectF(12, 12, 22, 22))
            p.drawLine(12, 23, 34, 23)
            p.drawEllipse(QRectF(18, 12, 10, 22))
        elif k == "reader":
            p.drawRoundedRect(QRectF(14, 12, 18, 22), 3.0, 3.0)
            p.drawLine(18, 18, 28, 18)
            p.drawLine(18, 23, 28, 23)
            p.drawLine(18, 28, 24, 28)
        elif k == "key":
            p.drawEllipse(QRectF(12, 17, 10, 10))
            p.drawLine(22, 22, 34, 22)
            p.drawLine(30, 22, 30, 26)
            p.drawLine(34, 22, 34, 26)
        else:
            p.drawLine(18, 16, 12, 23)
            p.drawLine(12, 23, 18, 30)
            p.drawLine(28, 16, 34, 23)
            p.drawLine(34, 23, 28, 30)
        p.end()


class PluginStoreDialog(RoundedDialog):
    """Tienda de Extensiones WebExtension C++ (manifest.json / .crx / .xpi / .zip) y Plugins Netlis."""

    def __init__(
        self,
        plugin_mgr: PluginManager,
        on_changed: Callable[[], None],
        parent=None,
        web_ext_api: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.plugin_mgr = plugin_mgr
        self.on_changed = on_changed
        self.web_ext_api = web_ext_api or {}
        self.setWindowTitle("Extensiones y Plugins — Netlis")
        self.resize(730, 620)
        self.setStyleSheet(IOS_GLASS_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        left = QVBoxLayout()
        title = QLabel("Gestor de Extensiones y Plugins")
        title.setObjectName("heading")
        sub = QLabel("Motor nativo C++ WebExtensions (manifest.json / .crx / .xpi / .zip) + Userscripts GM_*.")
        sub.setObjectName("subheading")
        left.addWidget(title)
        left.addWidget(sub)
        top.addLayout(left)
        top.addStretch()

        self.active_pill = QLabel("")
        self.active_pill.setObjectName("statPill")
        top.addWidget(self.active_pill)
        layout.addLayout(top)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar plugins por nombre, función o categoría...")
        self.search_input.textChanged.connect(self._rebuild_cards)
        filter_row.addWidget(self.search_input, stretch=1)

        self.cmb_filter = QComboBox()
        self.cmb_filter.addItem("Todos los plugins", "all")
        self.cmb_filter.addItem("Instalados", "installed")
        self.cmb_filter.currentIndexChanged.connect(self._rebuild_cards)
        filter_row.addWidget(self.cmb_filter)
        layout.addLayout(filter_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setSpacing(9)
        self.scroll.setWidget(self.cards_host)
        layout.addWidget(self.scroll, stretch=1)

        url_card = QFrame()
        url_card.setObjectName("sectionCard")
        url_row = QHBoxLayout(url_card)
        url_row.setContentsMargins(10, 8, 10, 8)
        url_row.setSpacing(8)
        self.url_install_input = QLineEdit()
        self.url_install_input.setPlaceholderText("Instalar Userscript por URL (https://...archivo.user.js)...")
        self.url_install_input.returnPressed.connect(self._install_from_url)
        btn_url_install = QPushButton("Instalar URL")
        btn_url_install.setObjectName("primary")
        btn_url_install.clicked.connect(self._install_from_url)
        url_row.addWidget(self.url_install_input, stretch=1)
        url_row.addWidget(btn_url_install)
        layout.addWidget(url_card)

        bottom = QHBoxLayout()
        ext_pkg_btn = QPushButton("Extensión .zip/.xpi/.crx...")
        ext_pkg_btn.clicked.connect(self._import_web_ext_package)
        ext_dir_btn = QPushButton("Carpeta manifest.json...")
        ext_dir_btn.clicked.connect(self._import_web_ext_dir)
        import_btn = QPushButton("Userscript .js...")
        import_btn.clicked.connect(self._import_custom)
        self.install_status_lbl = QLabel("Soporta WebExtensions Manifest V3 y Userscripts GM_*.")
        self.install_status_lbl.setObjectName("subheading")
        close_btn = QPushButton("Listo")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(ext_pkg_btn)
        bottom.addWidget(ext_dir_btn)
        bottom.addWidget(import_btn)
        bottom.addWidget(self.install_status_lbl, stretch=1)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self._rebuild_cards()

    def _build_web_ext_card(self, ext_item: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("settingRow")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(14)

        icon_widget = PluginIconBadge("code", "#30d158")
        row.addWidget(icon_widget)

        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        head_row = QHBoxLayout()
        lbl_name = QLabel(ext_item["name"])
        lbl_name.setObjectName("cardTitle")
        lbl_cat = QLabel(f"WebExtension MV{ext_item.get('mv', '3')} · v{ext_item.get('version', '1.0')}")
        lbl_cat.setStyleSheet(
            "background: rgba(48,209,88,45); border: 1px solid rgba(48,209,88,120); "
            "border-radius: 8px; padding: 2px 8px; font-size: 10px; color: #d8ffe2;"
        )
        head_row.addWidget(lbl_name)
        head_row.addWidget(lbl_cat)
        head_row.addStretch()

        desc_txt = ext_item.get("description") or "Extensión nativa cargada en motor C++ Chromium."
        perms_txt = ext_item.get("permissions") or "sin permisos especiales"
        lbl_desc = QLabel(f"{desc_txt}  •  Permisos: {perms_txt}")
        lbl_desc.setObjectName("cardDesc")
        lbl_desc.setWordWrap(True)
        info_col.addLayout(head_row)
        info_col.addWidget(lbl_desc)
        row.addLayout(info_col, stretch=1)

        ext_id = ext_item["id"]
        popup_url = ext_item.get("popup_url", "")
        if popup_url and "open_popup" in self.web_ext_api:
            pop_btn = QPushButton("Panel")
            pop_btn.clicked.connect(lambda _c=False, u=popup_url: self._open_ext_popup(u))
            row.addWidget(pop_btn)

        toggle = IOSToggle(bool(ext_item.get("enabled", True)))
        toggle.toggled.connect(lambda st, eid=ext_id: self._on_toggle_web_ext(eid, st))
        rm_btn = QPushButton("Quitar")
        rm_btn.clicked.connect(lambda _c=False, eid=ext_id: self._on_remove_web_ext(eid))
        row.addWidget(toggle)
        row.addWidget(rm_btn)
        return card

    def _build_plugin_card(self, plug: PluginDefinition) -> QFrame:
        card = QFrame()
        card.setObjectName("settingRow")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(14)

        icon_widget = PluginIconBadge(plug.icon_kind, plug.accent_hex)
        row.addWidget(icon_widget)

        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        head_row = QHBoxLayout()
        lbl_name = QLabel(plug.name)
        lbl_name.setObjectName("cardTitle")
        lbl_cat = QLabel(plug.category)
        lbl_cat.setStyleSheet(
            "background: rgba(255,255,255,28); border: 1px solid rgba(255,255,255,50); "
            "border-radius: 8px; padding: 2px 8px; font-size: 10px; color: #e8e8f5;"
        )
        head_row.addWidget(lbl_name)
        head_row.addWidget(lbl_cat)
        head_row.addStretch()

        lbl_desc = QLabel(plug.description)
        lbl_desc.setObjectName("cardDesc")
        lbl_desc.setWordWrap(True)
        info_col.addLayout(head_row)
        info_col.addWidget(lbl_desc)
        row.addLayout(info_col, stretch=1)

        if self.plugin_mgr.is_installed(plug.plugin_id):
            toggle = IOSToggle(self.plugin_mgr.is_enabled(plug.plugin_id))
            toggle.toggled.connect(lambda st, pid=plug.plugin_id: self._on_toggle(pid, st))
            rm_btn = QPushButton("Quitar")
            rm_btn.clicked.connect(lambda _c=False, pid=plug.plugin_id: self._on_uninstall(pid))
            row.addWidget(toggle)
            row.addWidget(rm_btn)
        else:
            inst_btn = QPushButton("Instalar")
            inst_btn.setObjectName("primary")
            inst_btn.clicked.connect(lambda _c=False, pid=plug.plugin_id: self._on_install(pid))
            row.addWidget(inst_btn)

        return card

    def _rebuild_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        query = self.search_input.text().strip().lower()
        mode = str(self.cmb_filter.currentData() or "all")

        web_exts = self.web_ext_api.get("list", lambda: [])()
        n_web_active = 0
        for ext_item in web_exts:
            if ext_item.get("enabled"):
                n_web_active += 1
            if query and (
                query not in ext_item["name"].lower()
                and query not in ext_item.get("description", "").lower()
            ):
                continue
            self.cards_layout.addWidget(self._build_web_ext_card(ext_item))

        for plug in self.plugin_mgr.all_catalog():
            if mode == "installed" and not self.plugin_mgr.is_installed(plug.plugin_id):
                continue
            if query and (
                query not in plug.name.lower()
                and query not in plug.description.lower()
                and query not in plug.category.lower()
            ):
                continue
            self.cards_layout.addWidget(self._build_plugin_card(plug))

        self.cards_layout.addStretch()
        n_act = len(self.plugin_mgr.active_plugins()) + n_web_active
        self.active_pill.setText(f"{n_act} extensiones activas")

    def _on_install(self, plugin_id: str) -> None:
        self.plugin_mgr.install(plugin_id)
        self.on_changed()
        self._rebuild_cards()

    def _on_uninstall(self, plugin_id: str) -> None:
        self.plugin_mgr.uninstall(plugin_id)
        self.on_changed()
        self._rebuild_cards()

    def _on_toggle(self, plugin_id: str, enabled: bool) -> None:
        self.plugin_mgr.set_enabled(plugin_id, enabled)
        self.on_changed()
        n_act = len(self.plugin_mgr.active_plugins())
        self.active_pill.setText(f"{n_act} plugins activos")

    def _open_ext_popup(self, popup_url: str) -> None:
        fn = self.web_ext_api.get("open_popup")
        if fn:
            fn(popup_url)
            self.close()

    def _on_toggle_web_ext(self, ext_id: str, enabled: bool) -> None:
        fn = self.web_ext_api.get("set_enabled")
        if fn:
            fn(ext_id, enabled)
        self.on_changed()
        self._rebuild_cards()

    def _on_remove_web_ext(self, ext_id: str) -> None:
        fn = self.web_ext_api.get("uninstall")
        if fn:
            fn(ext_id)
        self.on_changed()
        self._rebuild_cards()

    def _import_web_ext_package(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar paquete WebExtension (.zip / .xpi / .crx)",
            "",
            "WebExtensions (*.zip *.xpi *.crx)",
        )
        if path and "install_path" in self.web_ext_api:
            ok, msg = self.web_ext_api["install_path"](Path(path))
            self.install_status_lbl.setText(msg)
            if ok:
                self.on_changed()
                self._rebuild_cards()

    def _import_web_ext_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta con manifest.json")
        if folder and "install_path" in self.web_ext_api:
            ok, msg = self.web_ext_api["install_path"](Path(folder))
            self.install_status_lbl.setText(msg)
            if ok:
                self.on_changed()
                self._rebuild_cards()

    def _import_custom(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Userscript (.js / .user.js)", "", "JavaScript (*.js *.user.js)"
        )
        if path:
            self.plugin_mgr.import_custom_script(Path(path))
            self.install_status_lbl.setText(f"Instalado desde archivo: {Path(path).name}")
            self.on_changed()
            self._rebuild_cards()

    def _install_from_url(self) -> None:
        url = self.url_install_input.text().strip()
        if not url:
            return
        self.install_status_lbl.setText("Descargando y verificando Userscript...")
        self.install_status_lbl.repaint()
        ok, msg = self.plugin_mgr.install_from_url(url)
        self.install_status_lbl.setText(msg)
        if ok:
            self.url_install_input.clear()
            self.on_changed()
            self._rebuild_cards()


class DownloadsDialog(RoundedDialog):
    """Gestor de descargas con vidrio translúcido tipo iOS y protección contra ejecutables maliciosos."""

    def __init__(
        self,
        downloads_records: list[dict],
        on_clear: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.downloads_records = downloads_records
        self.on_clear = on_clear
        self.setWindowTitle("Descargas — Netlis")
        self.resize(620, 470)
        self.setStyleSheet(IOS_GLASS_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        left = QVBoxLayout()
        title = QLabel("Gestor de Descargas")
        title.setObjectName("heading")
        sub = QLabel("Archivos guardados en ~/Descargas con filtro anti-ejecutables maliciosos.")
        sub.setObjectName("subheading")
        left.addWidget(title)
        left.addWidget(sub)
        top.addLayout(left)
        top.addStretch()

        self.count_pill = QLabel("")
        self.count_pill.setObjectName("statPill")
        top.addWidget(self.count_pill)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, stretch=1)

        bottom = QHBoxLayout()
        btn_open_dir = QPushButton("Abrir carpeta Descargas")
        btn_open_dir.clicked.connect(self._open_downloads_folder)
        btn_clear = QPushButton("Limpiar lista")
        btn_clear.clicked.connect(self._clear_list)
        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.close)

        bottom.addWidget(btn_open_dir)
        bottom.addWidget(btn_clear)
        bottom.addStretch()
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

        self._populate()

    def _fmt_bytes(self, n: int) -> str:
        if n <= 0:
            return "—"
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.1f} MB"

    def _populate(self) -> None:
        self.list_widget.clear()
        self.count_pill.setText(f"{len(self.downloads_records)} archivos")
        if not self.downloads_records:
            empty = QListWidgetItem("No hay descargas recientes en esta sesión.")
            self.list_widget.addItem(empty)
            return
        for rec in reversed(self.downloads_records):
            fname = rec.get("filename", "archivo")
            state = rec.get("state", "En curso")
            rec_b = int(rec.get("received_bytes", 0) or 0)
            tot_b = int(rec.get("total_bytes", 0) or 0)
            when = rec.get("started_at", "")
            size_txt = (
                f"{self._fmt_bytes(rec_b)} / {self._fmt_bytes(tot_b)}"
                if tot_b > 0
                else self._fmt_bytes(rec_b)
            )
            sha_short = str(rec.get("sha256") or "")[:12]
            sha_txt = f"   •   SHA-256: {sha_short}…" if sha_short else ""
            line = f"{fname}   •   {state} ({size_txt}){sha_txt}   •   {when}"
            self.list_widget.addItem(QListWidgetItem(line))

    def _open_downloads_folder(self) -> None:
        import os
        import subprocess
        import sys

        dl_dir = Path.home() / ("Descargas" if (Path.home() / "Descargas").exists() else "Downloads")
        dl_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(dl_dir))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(dl_dir)], close_fds=True)
        else:
            subprocess.Popen(["xdg-open", str(dl_dir)], close_fds=True)

    def _clear_list(self) -> None:
        self.on_clear()
        self._populate()


class BraveShieldsPopup(RoundedDialog):
    """Panel estilo Brave Shields: muestra exactamente los anuncios y rastreadores bloqueados en el sitio actual."""

    def __init__(
        self,
        site_host: str,
        site_total: int,
        site_items: list[tuple[str, int]],
        global_total: int,
        settings: PrivacySettings,
        on_update_settings: Callable[[PrivacySettings], None],
        on_open_full_center: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.on_update_settings = on_update_settings
        self.on_open_full_center = on_open_full_center
        self.setWindowTitle("Escudos Netlis")
        self.resize(420, 500)
        self.setStyleSheet(IOS_GLASS_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        left = QVBoxLayout()
        domain_lbl = QLabel(site_host or "Nueva pestaña")
        domain_lbl.setObjectName("heading")
        sub = QLabel(f"Escudos Netlis activos  •  {global_total} bloqueos totales en sesión")
        sub.setObjectName("subheading")
        left.addWidget(domain_lbl)
        left.addWidget(sub)
        top.addLayout(left)
        top.addStretch()

        badge = QLabel(f"{site_total}")
        badge.setStyleSheet(
            "background: #b02a37; color: #ffffff; font-size: 18px; font-weight: 800; "
            "padding: 6px 14px; border-radius: 12px;"
        )
        top.addWidget(badge)
        layout.addLayout(top)

        summary_card = QFrame()
        summary_card.setObjectName("sectionCard")
        s_lay = QVBoxLayout(summary_card)
        s_lay.setSpacing(4)
        s_title = QLabel(
            f"{site_total} anuncios y rastreadores bloqueados en este sitio"
            if site_host
            else "Navega a un sitio web para ver los bloqueos en tiempo real"
        )
        s_title.setObjectName("cardTitle")
        s_lay.addWidget(s_title)
        layout.addWidget(summary_card)

        self.blocked_list = QListWidget()
        if site_items:
            for tracker_name, count in site_items:
                self.blocked_list.addItem(QListWidgetItem(f"✕  {tracker_name}   ({count} bloqueos)"))
        else:
            self.blocked_list.addItem(
                QListWidgetItem("Sin anuncios ni rastreadores detectados todavía en esta página.")
            )
        layout.addWidget(self.blocked_list, stretch=1)

        self.row_trackers = ToggleRow(
            "Bloquear rastreadores y anuncios",
            "Detiene redes publicitarias y scripts de seguimiento.",
            settings.block_trackers,
        )
        self.row_yt = ToggleRow(
            "Bloquear anuncios de YouTube",
            "Elimina anuncios en el reproductor.",
            settings.block_youtube_ads,
        )
        self.row_cookies = ToggleRow(
            "Bloquear cookies de terceros",
            "Aísla cookies entre sitios distintos.",
            settings.block_third_party_cookies,
        )
        for r in (self.row_trackers, self.row_yt, self.row_cookies):
            layout.addWidget(r)

        actions = QHBoxLayout()
        btn_full = QPushButton("Centro completo…")
        btn_full.clicked.connect(self._open_full)
        btn_apply = QPushButton("Aplicar")
        btn_apply.setObjectName("primary")
        btn_apply.clicked.connect(self._apply)
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.close)
        actions.addWidget(btn_full)
        actions.addStretch()
        actions.addWidget(btn_apply)
        actions.addWidget(btn_close)
        layout.addLayout(actions)

    def _open_full(self) -> None:
        self.close()
        self.on_open_full_center()

    def _apply(self) -> None:
        self.settings.block_trackers = self.row_trackers.isChecked()
        self.settings.block_youtube_ads = self.row_yt.isChecked()
        self.settings.block_third_party_cookies = self.row_cookies.isChecked()
        self.on_update_settings(self.settings)
        self.close()
