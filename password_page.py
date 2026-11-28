"""Native password manager page. Secrets never enter a web renderer."""
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QStackedWidget, QFormLayout, QMessageBox, QApplication)
from password_vault import generate_strong_password

class VaultEmblem(QLabel):
    """User-supplied illustration loaded entirely from the application assets."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(240, 240)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName("Águila dormida abrazando un cofre")
        pixmap = QPixmap(str(Path(__file__).resolve().parent / "assets" / "password-vault-eagle.png"))
        if not pixmap.isNull():
            self.setPixmap(pixmap.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))


class PasswordPage(QWidget):
    def __init__(self, vault, close_page, parent=None):
        super().__init__(parent)
        self.vault = vault
        self.selected = None
        self.setObjectName('passwordPage')
        self.setStyleSheet('''
            QWidget#passwordPage, QWidget#detail { background: #19151f; color: #eeeef2; }
            QWidget#sidebar { background: #282231; border-right: 1px solid #463951; }
            QLabel { color: #eeeef2; background: transparent; font-size: 14px; }
            QLabel#title { font-size: 25px; font-weight: 600; }
            QLabel#muted { color: #aaa8b4; font-size: 13px; }
            QLineEdit { background: #252429; color: #eeeef2; border: 1px solid #77727f; border-radius: 12px; padding: 11px; font-size: 14px; }
            QLineEdit:focus { border-color: #b9a0ff; }
            QPushButton { background: transparent; color: #eeeef2; border: 1px solid #80728f; border-radius: 16px; padding: 10px 18px; font-size: 13px; }
            QPushButton:hover { background: #453650; }
            QPushButton#primary { background: #c2a3ff; color: #251637; border: none; }
            QPushButton#primary:hover { background: #d5bdff; }
            QPushButton:focus { border-color: #d3b5ff; }
            QListWidget::item:hover { background: #362b43; }
            QPushButton#danger { color: #ffb4b4; }
            QListWidget { background: transparent; color: #eeeef2; border: none; outline: none; font-size: 14px; }
            QListWidget::item { padding: 16px 12px; margin: 3px 0; border-radius: 12px; }
            QListWidget::item:selected { background: #503b6a; color: #fff4ff; }
        ''')
        root = QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        side = QWidget(); side.setObjectName('sidebar'); side.setFixedWidth(300)
        left = QVBoxLayout(side); left.setContentsMargins(16,18,16,18); left.setSpacing(16)
        search_row = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText('Buscar contraseñas')
        add = QPushButton('+'); add.setAccessibleName('Añadir contraseña'); add.setFixedWidth(42)
        search_row.addWidget(self.search); search_row.addWidget(add); left.addLayout(search_row)
        self.count = QLabel(); self.count.setObjectName('muted'); left.addWidget(self.count)
        self.items = QListWidget(); left.addWidget(self.items,1)
        self.no_results = QLabel('No hay contraseñas guardadas.\n\nPulsa + para añadir la primera.'); self.no_results.setWordWrap(True); self.no_results.setObjectName('muted'); left.insertWidget(2,self.no_results)
        root.addWidget(side)
        detail = QWidget(); detail.setObjectName('detail'); right = QVBoxLayout(detail); right.setContentsMargins(40,24,40,32); right.setSpacing(24)
        bar = QHBoxLayout(); label = QLabel('Contraseñas'); label.setObjectName('title'); bar.addWidget(label); bar.addStretch()
        lock = QPushButton('Bloquear'); lock.clicked.connect(lambda: (self.vault.lock(), close_page())); bar.addWidget(lock); right.addLayout(bar)
        self.pages = QStackedWidget(); right.addWidget(self.pages,1)
        empty = QWidget(); empty_l = QVBoxLayout(empty); empty_l.setSpacing(20); empty_l.addStretch(); empty_l.addWidget(VaultEmblem(),0,Qt.AlignmentFlag.AlignHCenter)
        for text, name in [('Tus contraseñas, en este equipo','title'),('Guarda tus datos de acceso y encuéntralos cuando los necesites.\nLa bóveda se cifra con tu contraseña maestra.','muted')]:
            label=QLabel(text); label.setObjectName(name); label.setAlignment(Qt.AlignmentFlag.AlignCenter); label.setWordWrap(True); empty_l.addWidget(label)
        create = QPushButton('Añadir contraseña'); create.setObjectName('primary'); create.clicked.connect(self.new_entry); empty_l.addWidget(create,0,Qt.AlignmentFlag.AlignHCenter); empty_l.addStretch(); self.pages.addWidget(empty)
        editor = QWidget(); form_outer=QVBoxLayout(editor); form_outer.setContentsMargins(0,24,0,0)
        self.heading=QLabel('Nueva contraseña'); self.heading.setObjectName('title'); form_outer.addWidget(self.heading)
        fields=QWidget(); fields.setMaximumWidth(650); form=QFormLayout(fields); form.setContentsMargins(0,24,0,24); form.setSpacing(18)
        self.domain=QLineEdit(); self.user=QLineEdit(); self.secret=QLineEdit(); self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('Sitio web',self.domain); form.addRow('Usuario o correo',self.user); form.addRow('Contraseña',self.secret); form_outer.addWidget(fields)
        options=QHBoxLayout()
        show=QPushButton('Mostrar'); show.setCheckable(True)
        show.toggled.connect(lambda checked: (self.secret.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password),show.setText('Ocultar' if checked else 'Mostrar')))
        self.show_button=show
        generate=QPushButton('Generar'); generate.clicked.connect(lambda:self.secret.setText(generate_strong_password()))
        copy=QPushButton('Copiar contraseña'); copy.clicked.connect(lambda:QApplication.clipboard().setText(self.secret.text()))
        for b in (show,generate,copy): options.addWidget(b)
        options.addStretch(); form_outer.addLayout(options); form_outer.addSpacing(24)
        actions=QHBoxLayout(); save=QPushButton('Guardar'); save.setObjectName('primary'); save.clicked.connect(self.save_entry)
        self.delete=QPushButton('Eliminar'); self.delete.setObjectName('danger'); self.delete.clicked.connect(self.delete_entry)
        actions.addWidget(save); actions.addWidget(self.delete); actions.addStretch(); form_outer.addLayout(actions); form_outer.addStretch(); self.pages.addWidget(editor); root.addWidget(detail,1)
        add.clicked.connect(self.new_entry); self.search.textChanged.connect(self.refresh); self.items.currentRowChanged.connect(self.select_entry); self.refresh()

    def refresh(self):
        q=self.search.text().casefold()
        self.matches=sorted([e for e in self.vault.entries() if q in (e.domain+' '+e.username).casefold()],key=lambda e:(e.domain.casefold(),e.username.casefold()))
        self.items.blockSignals(True); self.items.clear()
        for e in self.matches: self.items.addItem(e.domain+'\n'+e.username)
        self.items.blockSignals(False)
        self.count.setText(f'Nombre (A–Z) · {len(self.matches)} contraseñas')
        self.no_results.setVisible(not self.matches)
        self.no_results.setText('No hay coincidencias.' if q else 'No hay contraseñas guardadas.\n\nPulsa + para añadir la primera.')
        self.selected=None; self.domain.clear(); self.user.clear(); self.secret.clear(); self.pages.setCurrentIndex(0)

    def new_entry(self):
        self.selected=None; self.items.clearSelection(); self.heading.setText('Nueva contraseña')
        self.domain.clear(); self.user.clear(); self.secret.clear(); self.show_button.setChecked(False)
        self.domain.setReadOnly(False); self.user.setReadOnly(False); self.delete.hide(); self.pages.setCurrentIndex(1); self.domain.setFocus()

    def select_entry(self,index):
        if not 0 <= index < len(self.matches): return
        e=self.matches[index]; self.selected=e; self.heading.setText(e.domain)
        self.domain.setText(e.domain); self.user.setText(e.username); self.secret.setText(e.password); self.show_button.setChecked(False)
        self.domain.setReadOnly(True); self.user.setReadOnly(True); self.delete.show(); self.pages.setCurrentIndex(1)

    def save_entry(self):
        try: self.vault.add_or_update(self.domain.text(),self.user.text(),self.secret.text())
        except (ValueError,RuntimeError) as exc: QMessageBox.warning(self,'Contraseñas',str(exc)); return
        self.refresh()

    def delete_entry(self):
        if self.selected and QMessageBox.question(self,'Eliminar contraseña',f'¿Eliminar la contraseña de {self.selected.domain}?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            self.vault.delete(self.selected.domain,self.selected.username); self.refresh()
