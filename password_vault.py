"""Bóveda local cifrada de contraseñas para Netlis (cero nube, cero Google, scrypt + HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path

_MAGIC = b"NLV1"
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1


@dataclass
class VaultEntry:
    domain: str
    username: str
    password: str
    notes: str = ""


def normalize_domain(raw: str) -> str:
    h = (raw or "").strip().lower()
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0].split(":", 1)[0].strip(".")
    return h[4:] if h.startswith("www.") else h


def generate_strong_password(length: int = 20) -> str:
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*_-+"
    return "".join(secrets.choice(alphabet) for _ in range(max(12, length)))


def _derive_keys(master_password: str, salt: bytes) -> tuple[bytes, bytes]:
    dk = hashlib.scrypt(
        master_password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=64,
    )
    return dk[:32], dk[32:]


def _keystream_xor(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    out = bytearray(len(data))
    offset = 0
    counter = 0
    while offset < len(data):
        block = hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        chunk = min(len(block), len(data) - offset)
        for i in range(chunk):
            out[offset + i] = data[offset + i] ^ block[i]
        offset += chunk
        counter += 1
    return bytes(out)


class LocalPasswordVault:
    """Almacén local cifrado con contraseña maestra en data/passwords_vault.enc."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._master_password: str | None = None
        self._entries: list[VaultEntry] = []

    def exists(self) -> bool:
        return self.vault_path.is_file() and self.vault_path.stat().st_size > 40

    def is_unlocked(self) -> bool:
        return self._master_password is not None

    def lock(self) -> None:
        self._master_password = None
        self._entries.clear()

    def create(self, master_password: str) -> None:
        if len(master_password) < 6:
            raise ValueError("La contraseña maestra debe tener al menos 6 caracteres.")
        self._master_password = master_password
        self._entries = []
        self.save()

    def unlock(self, master_password: str) -> list[VaultEntry]:
        if not self.exists():
            raise FileNotFoundError("La bóveda aún no ha sido creada.")
        raw = self.vault_path.read_bytes()
        if len(raw) < 4 + 16 + 16 + 32 or raw[:4] != _MAGIC:
            raise ValueError("Archivo de bóveda inválido o corrupto.")
        salt = raw[4:20]
        nonce = raw[20:36]
        tag = raw[36:68]
        ciphertext = raw[68:]
        enc_key, mac_key = _derive_keys(master_password, salt)
        expected_tag = hmac.new(mac_key, _MAGIC + salt + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError("Contraseña maestra incorrecta o archivo alterado.")
        plaintext = _keystream_xor(enc_key, nonce, ciphertext)
        items = json.loads(plaintext.decode("utf-8"))
        self._entries = [VaultEntry(**item) for item in items]
        self._master_password = master_password
        return list(self._entries)

    def save(self) -> None:
        if self._master_password is None:
            raise RuntimeError("La bóveda está bloqueada.")
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(16)
        nonce = os.urandom(16)
        enc_key, mac_key = _derive_keys(self._master_password, salt)
        payload = json.dumps([asdict(e) for e in self._entries], ensure_ascii=False).encode("utf-8")
        ciphertext = _keystream_xor(enc_key, nonce, payload)
        tag = hmac.new(mac_key, _MAGIC + salt + nonce + ciphertext, hashlib.sha256).digest()
        tmp = self.vault_path.with_suffix(".tmp")
        tmp.write_bytes(_MAGIC + salt + nonce + tag + ciphertext)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.vault_path)

    def entries(self, domain_filter: str = "") -> list[VaultEntry]:
        dom = normalize_domain(domain_filter)
        if not dom:
            return list(self._entries)
        return [
            e
            for e in self._entries
            if normalize_domain(e.domain) == dom or dom.endswith("." + normalize_domain(e.domain))
        ]

    def add_or_update(self, domain: str, username: str, password: str, notes: str = "") -> None:
        dom = normalize_domain(domain)
        if not dom or not username or not password:
            raise ValueError("Dominio, usuario y contraseña son obligatorios.")
        for e in self._entries:
            if normalize_domain(e.domain) == dom and e.username == username:
                e.password = password
                e.notes = notes
                self.save()
                return
        self._entries.append(VaultEntry(domain=dom, username=username, password=password, notes=notes))
        self.save()

    def delete(self, domain: str, username: str) -> bool:
        dom = normalize_domain(domain)
        before = len(self._entries)
        self._entries = [
            e for e in self._entries if not (normalize_domain(e.domain) == dom and e.username == username)
        ]
        if len(self._entries) != before:
            self.save()
            return True
        return False
