"""Persistencia ligera en JSON para marcadores e historial del navegador."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from stability import atomic_write_json, safe_load_json


class BrowserStorage:
    """Gestiona marcadores e historial de navegación en disco con escritura atómica y respaldo .bak."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or (Path(__file__).resolve().parent / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.bookmarks_path = self.data_dir / "marcadores.json"
        self.history_path = self.data_dir / "historial.json"
        self.bookmarks: list[dict[str, str]] = self._load_json(self.bookmarks_path, [])
        self.history: list[dict[str, str]] = self._load_json(self.history_path, [])

    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        return safe_load_json(path, list(default))

    def _save_json(self, path: Path, data: list[dict[str, str]]) -> None:
        atomic_write_json(path, data)

    def is_bookmarked(self, url: str) -> bool:
        return any(item.get("url") == url for item in self.bookmarks)

    def toggle_bookmark(self, title: str, url: str) -> bool:
        """Agrega o quita un marcador. Devuelve True si quedó guardado."""
        if not url or url.startswith("about:"):
            return False
        for i, item in enumerate(self.bookmarks):
            if item.get("url") == url:
                self.bookmarks.pop(i)
                self._save_json(self.bookmarks_path, self.bookmarks)
                return False
        self.bookmarks.append({"title": title or url, "url": url})
        self._save_json(self.bookmarks_path, self.bookmarks)
        return True

    def add_history(self, title: str, url: str) -> None:
        if not url or url.startswith("about:") or url == "data:text/html;charset=utf-8,":
            return
        entry = {
            "title": title or url,
            "url": url,
            "visited_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        if self.history and self.history[0].get("url") == url:
            self.history[0] = entry
        else:
            self.history.insert(0, entry)
        self.history = self.history[:500]
        self._save_json(self.history_path, self.history)

    def save_history(self) -> None:
        self._save_json(self.history_path, self.history)

    def clear_history(self) -> None:
        self.history.clear()
        self._save_json(self.history_path, self.history)
